#!/usr/bin/env python3
"""Runtime-safe historical MQTT discovery repair for Switch Vision Hub."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
import unicodedata
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import yaml
from websockets.sync.client import connect as websocket_connect

from mqtt_maintenance import (
    build_repair_plan,
    classify_owned_retained_config,
    discovery_subscription_filter,
    public_repair_plan,
)

GENERATED_YAML = Path("/share/switch_vision/generated-snmp2mqtt.yaml")
RETIREMENT_STATE = Path("/data/snmp2mqtt-retirement-topics.json")
MAX_RETAINED_MESSAGES = 5000


def _read_supervisor_token() -> str:
    for name in ("SUPERVISOR_TOKEN", "HASSIO_TOKEN"):
        token = os.environ.get(name, "").strip()
        if token:
            return token
    for path in (
        Path("/run/s6/container_environment/SUPERVISOR_TOKEN"),
        Path("/var/run/s6/container_environment/SUPERVISOR_TOKEN"),
        Path("/run/s6/container_environment/HASSIO_TOKEN"),
        Path("/var/run/s6/container_environment/HASSIO_TOKEN"),
    ):
        try:
            token = path.read_text(encoding="utf-8").strip().strip("\x00")
        except OSError:
            continue
        if token:
            return token
    return ""


def _supervisor_json(
    path: str,
    *,
    method: str = "GET",
    timeout: float = 12.0,
    payload: Any | None = None,
) -> dict[str, Any]:
    token = _read_supervisor_token()
    if not token:
        raise RuntimeError("Supervisor API token is unavailable.")
    request = Request(
        f"http://supervisor{path}",
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Supervisor API returned HTTP {exc.code}: {detail[:240]}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Supervisor API request failed: {exc}") from exc
    if not raw:
        return {}
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Supervisor API returned invalid JSON.") from exc
    if not isinstance(document, dict):
        raise RuntimeError("Supervisor API returned an invalid response.")
    if document.get("result") == "error":
        raise RuntimeError(str(document.get("message") or "Supervisor API request failed."))
    return document


def _home_assistant_service(domain: str, service: str, payload: dict[str, Any]) -> None:
    token = _read_supervisor_token()
    if not token:
        raise RuntimeError("Home Assistant API token is unavailable.")
    request = Request(
        f"http://supervisor/core/api/services/{quote(domain, safe='')}/{quote(service, safe='')}",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload).encode("utf-8"),
    )
    try:
        with urlopen(request, timeout=12.0) as response:
            response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Home Assistant API returned HTTP {exc.code}: {detail[:240]}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Home Assistant API request failed: {exc}") from exc


def _find_snmp2mqtt_addon() -> dict[str, Any] | None:
    payload = _supervisor_json("/addons")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    addons = data.get("addons", []) if isinstance(data, dict) else []
    candidates: list[tuple[int, dict[str, Any]]] = []
    for addon in addons if isinstance(addons, list) else []:
        if not isinstance(addon, dict):
            continue
        slug = str(addon.get("slug") or "")
        name = str(addon.get("name") or "")
        haystack = f"{slug} {name}".lower().replace("-", "_")
        if "snmp2mqtt" not in haystack or "discovery" in haystack:
            continue
        score = 0
        if "switch_vision" in haystack or "switch vision" in haystack:
            score += 10
        if slug.endswith("switch_vision_snmp2mqtt") or slug.endswith(
            "switch_vision_snmp2mqtt_addon"
        ):
            score += 10
        if name.strip().lower() == "switch vision snmp2mqtt":
            score += 20
        candidates.append((score, addon))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _snmp2mqtt_runtime_info() -> dict[str, Any]:
    addon = _find_snmp2mqtt_addon()
    if addon is None:
        return {
            "installed": False,
            "slug": None,
            "state": "not_installed",
            "options_readable": False,
            "homeassistant_prefix": None,
            "base_topic": None,
        }
    slug = str(addon.get("slug") or "").strip()
    state = str(addon.get("state") or addon.get("status") or "unknown").lower()
    result: dict[str, Any] = {
        "installed": bool(slug),
        "slug": slug or None,
        "state": state,
        "options_readable": False,
        "homeassistant_prefix": None,
        "base_topic": None,
    }
    if not slug:
        return result

    info = _supervisor_json(f"/addons/{quote(slug, safe='')}/info")
    data = info.get("data") if isinstance(info.get("data"), dict) else info
    if not isinstance(data, dict):
        return result
    result["state"] = str(data.get("state") or state).lower()
    options = data.get("options")
    if not isinstance(options, dict):
        return result
    mqtt = options.get("mqtt") if isinstance(options.get("mqtt"), dict) else {}
    homeassistant = (
        options.get("homeassistant")
        if isinstance(options.get("homeassistant"), dict)
        else {}
    )
    prefix = str(homeassistant.get("prefix") or "homeassistant").strip().strip("/")
    base_topic = str(mqtt.get("base_topic") or "snmp2mqtt").strip().strip("/")
    if (
        not prefix
        or not base_topic
        or "+" in prefix
        or "#" in prefix
        or "+" in base_topic
        or "#" in base_topic
    ):
        return result
    result.update(
        {
            "options_readable": True,
            "homeassistant_prefix": prefix,
            "base_topic": base_topic,
        }
    )
    return result


def _snmp2mqtt_slug(value: Any) -> str:
    text = str(value or "").lower().replace("-", "_").replace("~", "_")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    return text.strip("_")


def _generated_discovery_topics(path: Path, prefix: str) -> list[str]:
    if not path.is_file():
        raise RuntimeError(
            "Repair MQTT Entities requires a current valid generated-snmp2mqtt.yaml. "
            "Run Discovery or Regenerate SNMP2MQTT YAML first."
        )
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise RuntimeError(
            "Repair MQTT Entities requires a current valid generated-snmp2mqtt.yaml. "
            "Run Discovery or Regenerate SNMP2MQTT YAML first."
        ) from exc
    targets = document.get("targets") if isinstance(document, dict) else None
    if not isinstance(targets, list) or not targets:
        raise RuntimeError(
            "Repair MQTT Entities requires a current valid generated-snmp2mqtt.yaml "
            "with at least one target."
        )
    topics: set[str] = set()
    for target in targets:
        if not isinstance(target, dict):
            continue
        sensors = target.get("sensors")
        if not isinstance(sensors, list):
            continue
        for sensor in sensors:
            if not isinstance(sensor, dict):
                continue
            component = "binary_sensor" if bool(sensor.get("binary_sensor")) else "sensor"
            object_id = str(sensor.get("object_id") or "").strip() or _snmp2mqtt_slug(
                sensor.get("name")
            )
            if (
                not object_id
                or not re.fullmatch(r"[A-Za-z0-9_-]+", object_id)
            ):
                raise RuntimeError(
                    "Generated SNMP2MQTT YAML contains an unsafe Home Assistant object ID."
                )
            topics.add(f"{prefix}/{component}/snmp2mqtt/{object_id}/config")
    if not topics:
        raise RuntimeError(
            "Generated SNMP2MQTT YAML does not contain any Home Assistant discovery sensors."
        )
    return sorted(topics)


def _retained_messages(
    topic_filter: str,
    *,
    idle_timeout: float = 1.0,
    hard_timeout: float = 8.0,
) -> list[dict[str, Any]]:
    token = _read_supervisor_token()
    if not token:
        raise RuntimeError("Home Assistant API token is unavailable.")

    messages: list[dict[str, Any]] = []
    try:
        with websocket_connect(
            "ws://supervisor/core/websocket",
            open_timeout=12,
            close_timeout=5,
            max_size=4 * 1024 * 1024,
        ) as connection:
            required = json.loads(connection.recv(timeout=12))
            if required.get("type") != "auth_required":
                raise RuntimeError("Home Assistant WebSocket did not request authentication.")
            connection.send(json.dumps({"type": "auth", "access_token": token}))
            authenticated = json.loads(connection.recv(timeout=12))
            if authenticated.get("type") != "auth_ok":
                raise RuntimeError(
                    str(
                        authenticated.get("message")
                        or "Home Assistant WebSocket authentication failed."
                    )
                )

            connection.send(
                json.dumps(
                    {
                        "id": 1,
                        "type": "mqtt/subscribe",
                        "topic": topic_filter,
                        "qos": 0,
                    }
                )
            )
            result_seen = False
            deadline = time.monotonic() + hard_timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if result_seen:
                        break
                    raise RuntimeError("Home Assistant MQTT subscription timed out.")
                timeout = min(12.0 if not result_seen else idle_timeout, remaining)
                try:
                    response = json.loads(connection.recv(timeout=timeout))
                except TimeoutError:
                    if result_seen:
                        break
                    raise RuntimeError("Home Assistant MQTT subscription timed out.") from None

                if response.get("id") != 1:
                    continue
                if response.get("type") == "result":
                    if response.get("success") is not True:
                        error = response.get("error")
                        detail = (
                            error.get("message") or error.get("code")
                            if isinstance(error, dict)
                            else error
                        )
                        raise RuntimeError(
                            str(detail or "Home Assistant MQTT subscription failed.")
                        )
                    result_seen = True
                    continue
                if response.get("type") != "event":
                    continue
                event = response.get("event")
                if not isinstance(event, dict) or event.get("retain") is not True:
                    continue
                topic = event.get("topic")
                payload = event.get("payload")
                if isinstance(topic, str) and isinstance(payload, str):
                    messages.append(
                        {"topic": topic, "payload": payload, "retain": True}
                    )
                    if len(messages) > MAX_RETAINED_MESSAGES:
                        raise RuntimeError(
                            "MQTT maintenance scan exceeded its safety limit; no repair was performed."
                        )
            if not result_seen:
                raise RuntimeError("Home Assistant MQTT subscription did not confirm successfully.")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Home Assistant MQTT maintenance scan failed: {exc}") from exc
    return messages


def _save_retirement_topics(topics: list[str]) -> None:
    clean = sorted(
        {
            str(topic).strip().strip("/")
            for topic in topics
            if str(topic).strip()
            and "+" not in str(topic)
            and "#" not in str(topic)
            and str(topic).strip().endswith("/config")
        }
    )
    RETIREMENT_STATE.parent.mkdir(parents=True, exist_ok=True)
    if not clean:
        RETIREMENT_STATE.unlink(missing_ok=True)
        return
    payload = {
        "version": 1,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "topics": clean,
    }
    temporary = RETIREMENT_STATE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, RETIREMENT_STATE)


def _scan_internal() -> tuple[dict[str, Any], dict[str, Any]]:
    runtime = _snmp2mqtt_runtime_info()
    if not runtime.get("installed"):
        raise RuntimeError("Switch Vision SNMP2MQTT is not installed.")
    if not runtime.get("options_readable"):
        raise RuntimeError(
            "Switch Vision could not safely read the SNMP2MQTT MQTT settings, "
            "so no repair plan was created."
        )
    prefix = str(runtime.get("homeassistant_prefix") or "").strip().strip("/")
    base_topic = str(runtime.get("base_topic") or "").strip().strip("/")
    current_topics = _generated_discovery_topics(GENERATED_YAML, prefix)
    retained = _retained_messages(discovery_subscription_filter(prefix))

    owned_entries: list[dict[str, str]] = []
    for message in retained:
        owned = classify_owned_retained_config(
            message.get("topic"),
            message.get("payload"),
            message.get("retain"),
            prefix,
            base_topic,
        )
        if owned is not None:
            owned_entries.append(owned)

    plan = build_repair_plan(current_topics, owned_entries)
    plan["snmp2mqtt_state"] = str(runtime.get("state") or "unknown")
    plan["generated_yaml_found"] = True
    return plan, runtime


def scan_mqtt_entities() -> dict[str, Any]:
    plan, _runtime = _scan_internal()
    return public_repair_plan(plan)


def repair_mqtt_entities(request_data: Any) -> dict[str, Any]:
    if not isinstance(request_data, dict):
        raise ValueError("MQTT repair request must contain a JSON object.")
    if request_data.get("confirmation") != "REPAIR STALE MQTT ENTITIES":
        raise ValueError("MQTT repair confirmation is invalid.")
    supplied_token = str(request_data.get("plan_token") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", supplied_token):
        raise ValueError("MQTT repair plan token is invalid.")

    plan, runtime = _scan_internal()
    if supplied_token != plan.get("plan_token"):
        raise ValueError(
            "The MQTT entity state changed after the scan. Scan again before repairing."
        )

    stale_topics = list(plan.get("_stale_topics") or [])
    current_topics = list(plan.get("_current_topics") or [])
    if not stale_topics:
        result = public_repair_plan(plan)
        result.update(
            {
                "repaired": True,
                "topics_cleared": 0,
                "remaining_stale_count": 0,
                "snmp2mqtt_restarted": False,
                "warnings": [],
                "message": "No stale Switch Vision MQTT discovery entities were found.",
            }
        )
        return result

    cleared_topics: list[str] = []
    warnings: list[str] = []
    for topic in stale_topics:
        try:
            _home_assistant_service(
                "mqtt",
                "publish",
                {"topic": topic, "payload": "", "qos": 0, "retain": True},
            )
            cleared_topics.append(topic)
        except RuntimeError as exc:
            warnings.append(
                f"Could not retire one stale Switch Vision MQTT entity: {exc}"
            )
            if len(warnings) >= 8:
                break

    restarted = False
    if str(runtime.get("state") or "").lower() in {"started", "running"}:
        slug = str(runtime.get("slug") or "").strip()
        if slug:
            try:
                _supervisor_json(
                    f"/addons/{quote(slug, safe='')}/restart",
                    method="POST",
                    timeout=30.0,
                )
                restarted = True
            except RuntimeError as exc:
                warnings.append(f"Could not restart Switch Vision SNMP2MQTT: {exc}")

    cleared_set = set(cleared_topics)
    failed_topics = [topic for topic in stale_topics if topic not in cleared_set]
    _save_retirement_topics(sorted(set(current_topics + failed_topics)))

    verification, _ = _scan_internal()
    remaining = int(verification.get("stale_count") or 0)
    if remaining:
        warnings.append(
            f"{remaining} stale Switch Vision MQTT discovery "
            f"{'entry remains' if remaining == 1 else 'entries remain'} after repair."
        )

    result = public_repair_plan(verification)
    result.update(
        {
            "repaired": True,
            "topics_cleared": len(cleared_topics),
            "requested_stale_count": len(stale_topics),
            "remaining_stale_count": remaining,
            "snmp2mqtt_restarted": restarted,
            "warnings": warnings,
            "message": (
                "MQTT entity repair complete."
                if not warnings and remaining == 0
                else "MQTT entity repair completed with warnings."
            ),
        }
    )
    return result
