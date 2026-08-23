#!/usr/bin/env python3
"""Privacy-scoped Support My Switch diagnostics.

This module captures cross-layer evidence needed to diagnose Switch Vision
binding/entity failures without collecting credentials, Home Assistant
attributes, unrelated entities, or raw MQTT discovery payloads.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

from supervisor_runtime import read_supervisor_token
from walk_correlation import build_port_pipeline as build_correlated_port_pipeline

DIAG_DIR = Path("diagnostics")
ENTITY_SNAPSHOT = DIAG_DIR / "home-assistant-entity-resolution.json"
SAFE_MODEL_KEYS = (
    "vendor", "vendor_name", "family", "model", "model_text",
    "detected_model_text", "effective_model_text", "model_override",
    "compatibility_mode", "sys_object_id", "support_status",
)
CARD_KEYS = (
    "type", "title", "faceplate_label", "member", "selected_switch",
    "discovery_selected_switch", "stack_member_number", "sensor_prefix",
    "status_entity_prefix", "status_entity_suffix", "cpu_entity",
    "temperature_entity", "poe_used_entity", "calibration_profile",
)
STATUS_SUFFIX = "_status"
MAX_PORT_ROWS = 512
MAX_CARD_ROWS = 128
MAX_CAPABILITY_FILES = 128
MAX_PROVENANCE_FILES = 512
HA_STATES_URL = os.environ.get(
    "SWITCH_VISION_HA_STATES_URL", "http://supervisor/core/api/states"
)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _write(root: Path, relative: Path, payload: Any) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

def _yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None

def _slug(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace("~", "_")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    return text.strip("_")

def _safe_state(entity_id: str, raw: Any) -> str | None:
    text = str(raw if raw is not None else "").strip()
    if not text:
        return None
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return text
    lowered = text.casefold()
    if entity_id.endswith("_status") and lowered in {
        "up", "down", "on", "off", "true", "false",
        "online", "offline", "available", "unavailable", "unknown",
    }:
        return lowered
    return "<NON_NUMERIC>"

def _ha_states() -> tuple[list[dict[str, Any]], str | None]:
    token = read_supervisor_token()
    if not token:
        return [], "Home Assistant API token unavailable"
    request = Request(
        HA_STATES_URL,
        method="GET",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, list):
            return [], "Home Assistant states response was not a list"
        return [x for x in data if isinstance(x, dict)], None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, HTTPError, URLError) as exc:
        return [], f"Home Assistant state query failed: {type(exc).__name__}"

def _state_map(states: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for item in states:
        entity_id = str(item.get("entity_id") or "").strip()
        if entity_id:
            result[entity_id] = item
    return result

def _suffix_alternatives(entity_id: str, state_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    pattern = re.compile(rf"^{re.escape(entity_id)}_(\d+)$")
    out = []
    for candidate_id, item in state_map.items():
        if not pattern.fullmatch(candidate_id):
            continue
        out.append({
            "entity_id": candidate_id,
            "state": _safe_state(candidate_id, item.get("state")),
            "last_updated": str(item.get("last_updated") or ""),
        })
    return sorted(out, key=lambda row: row["entity_id"])

def _targets(generated: Any) -> list[dict[str, Any]]:
    rows = generated.get("targets") if isinstance(generated, dict) else None
    return [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []

def _sensor_rows(generated: Any) -> list[dict[str, Any]]:
    out = []
    for target_index, target in enumerate(_targets(generated), start=1):
        target_name = str(
            target.get("name") or target.get("target") or target.get("id") or f"target-{target_index}"
        )
        sensors = target.get("sensors")
        if not isinstance(sensors, list):
            continue
        for sensor in sensors:
            if not isinstance(sensor, dict):
                continue
            object_id = _slug(sensor.get("object_id") or sensor.get("name"))
            if not object_id:
                continue
            component = "binary_sensor" if sensor.get("binary_sensor") is True else "sensor"
            out.append({
                "target": target_name,
                "component": component,
                "object_id": object_id,
                "entity_id": f"{component}.{object_id}",
                "oid": str(sensor.get("oid") or sensor.get("object_id_oid") or "").strip(),
                "name": str(sensor.get("name") or "").strip(),
            })
    return out

def _parse_walk_statuses(root: Path) -> dict[str, str]:
    """Return latest observed ifOperStatus by exact numeric OID."""
    statuses: dict[str, str] = {}
    candidates = []
    for path in root.rglob("*.txt"):
        name = path.name.lower()
        if "walk" in name and path.is_file():
            candidates.append(path)
    candidates.sort(key=lambda p: (p.stat().st_mtime if p.exists() else 0, str(p)))
    pattern = re.compile(
        r"^\s*\.?(1\.3\.6\.1\.2\.1\.2\.2\.1\.8\.\d+)\s*=\s*(?:INTEGER:\s*)?([A-Za-z]+(?:\(\d+\))?|\d+)",
        re.I,
    )
    for path in candidates[-64:]:
        try:
            for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
                match = pattern.match(raw)
                if match:
                    statuses[match.group(1)] = match.group(2).strip()
        except OSError:
            continue
    return statuses

def build_port_pipeline(
    generated: Any,
    states: list[dict[str, Any]],
    walk_status: dict[str, str],
    *,
    ha_available: bool = True,
) -> dict[str, Any]:
    state_map = _state_map(states) if ha_available else {}
    rows = []
    for sensor in _sensor_rows(generated):
        if not sensor["object_id"].endswith(STATUS_SUFFIX):
            continue
        exact = state_map.get(sensor["entity_id"]) if ha_available else None
        oid = sensor["oid"].lstrip(".")
        rows.append({
            "target": sensor["target"],
            "object_id": sensor["object_id"],
            "expected_entity_id": sensor["entity_id"],
            "status_oid": oid or None,
            "walk_if_oper_status": walk_status.get(oid) if oid else None,
            "exact_present": (exact is not None) if ha_available else None,
            "ha_state": _safe_state(sensor["entity_id"], exact.get("state")) if exact else None,
            "last_updated": str(exact.get("last_updated") or "") if exact else "",
            "suffix_alternatives": (
                _suffix_alternatives(sensor["entity_id"], state_map)
                if ha_available
                else []
            ),
        })
    rows = rows[:MAX_PORT_ROWS]
    walk_up_rows = [
        row for row in rows
        if row["walk_if_oper_status"]
        and str(row["walk_if_oper_status"]).casefold().startswith("up")
    ]
    anomalies = [
        row for row in walk_up_rows
        if ha_available
        and (
            not row["exact_present"]
            or row["ha_state"] not in {"up", "on", "true", "1"}
        )
    ]
    return {
        "schema_version": 1,
        "generated_at": _now(),
        "scope": "generated Switch Vision port status entities correlated with captured walk ifOperStatus and HA state; no attributes",
        "summary": {
            "status_rows": len(rows),
            "ha_state_status": "available" if ha_available else "unavailable",
            "walk_up_count": len(walk_up_rows),
            "walk_up_but_exact_not_up": len(anomalies) if ha_available else None,
            "suffix_alternative_count": (
                sum(len(x["suffix_alternatives"]) for x in rows)
                if ha_available
                else None
            ),
        },
        "ports": rows,
        "anomalies": anomalies[:128],
    }

def _capability_model(path: Path) -> dict[str, Any] | None:
    data = _json(path)
    if not isinstance(data, dict):
        return None
    device = data.get("device") if isinstance(data.get("device"), dict) else {}
    registry = data.get("registry") if isinstance(data.get("registry"), dict) else {}
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    row = {"source": path.name}
    for key in SAFE_MODEL_KEYS:
        if key in device and device.get(key) not in (None, ""):
            row[key] = device.get(key)
    row["registry_match"] = bool(registry.get("match")) if registry else False
    if registry:
        row["registry_status"] = registry.get("status")
    for key in ("interface_count", "physical_count", "rj45_count", "sfp_count", "sfp_plus_count", "sfp28_count", "uplink_count", "stack_count"):
        if key in summary:
            row[key] = summary.get(key)
    evidence = {}
    for container_name in ("identity", "model_detection", "detection", "classification"):
        container = data.get(container_name)
        if isinstance(container, dict):
            for key in (
                "source", "method", "product_match", "model_source", "sys_object_id",
                "detected_model_text", "effective_model_text", "model_override",
            ):
                if key in container and container.get(key) not in (None, ""):
                    evidence[f"{container_name}.{key}"] = container.get(key)
    if evidence:
        row["evidence"] = evidence
    return row

def build_model_provenance(root: Path) -> dict[str, Any]:
    files = sorted(root.rglob("*-capabilities.json"))[:MAX_CAPABILITY_FILES]
    rows = []
    for path in files:
        row = _capability_model(path)
        if row:
            rows.append(row)
    return {
        "schema_version": 1,
        "generated_at": _now(),
        "scope": "safe model/classification fields from sanitized capability outputs; names, addresses and credentials excluded",
        "device_count": len(rows),
        "devices": rows,
    }

def _walk_mappings(node: Any, path: str = "$") -> list[dict[str, Any]]:
    out = []
    if isinstance(node, dict):
        selected = {key: node.get(key) for key in CARD_KEYS if key in node and node.get(key) not in (None, "")}
        if selected and ("type" in selected or "selected_switch" in selected or "discovery_selected_switch" in selected):
            selected["_path"] = path
            out.append(selected)
        for key, value in node.items():
            out.extend(_walk_mappings(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out.extend(_walk_mappings(value, f"{path}[{index}]"))
    return out

def build_card_bindings(root: Path, generated: Any) -> dict[str, Any]:
    card = _yaml(root / "generated-dashboard-card.yaml")
    cards = _walk_mappings(card)[:MAX_CARD_ROWS] if card is not None else []
    targets = []
    for index, target in enumerate(_targets(generated), start=1):
        sensors = target.get("sensors") if isinstance(target.get("sensors"), list) else []
        status_ids = []
        for sensor in sensors:
            if not isinstance(sensor, dict):
                continue
            object_id = _slug(sensor.get("object_id") or sensor.get("name"))
            if object_id.endswith(STATUS_SUFFIX):
                status_ids.append(object_id)
        targets.append({
            "index": index,
            "target": str(target.get("name") or target.get("target") or target.get("id") or f"target-{index}"),
            "status_entity_count": len(status_ids),
            "status_entity_first": status_ids[:8],
        })
    return {
        "schema_version": 1,
        "generated_at": _now(),
        "scope": "generated card identity/binding keys and generated target/entity contract; credentials and management addresses excluded",
        "cards": cards,
        "targets": targets,
    }

def build_file_provenance(root: Path) -> dict[str, Any]:
    selected = []
    fixed = [
        root / "generated-snmp2mqtt.yaml",
        root / "generated-dashboard-card.yaml",
        root / "discovery-report.txt",
        root / "last-discovery-run.txt",
    ]
    candidates = fixed + sorted(root.rglob("*-capabilities.json")) + [
        p for p in sorted(root.rglob("*.txt")) if "walk" in p.name.lower()
    ]
    seen = set()
    for path in candidates:
        if len(selected) >= MAX_PROVENANCE_FILES or not path.is_file():
            continue
        try:
            relative = str(path.relative_to(root))
        except ValueError:
            continue
        if relative in seen:
            continue
        seen.add(relative)
        try:
            raw = path.read_bytes()
            stat = path.stat()
        except OSError:
            continue
        selected.append({
            "path": relative,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "mtime_ns": stat.st_mtime_ns,
        })
    return {
        "schema_version": 1,
        "generated_at": _now(),
        "scope": "file names, sizes, hashes and mtimes only; no file contents",
        "files": selected,
    }

def capture_mqtt_maintenance(root: Path) -> dict[str, Any]:
    try:
        from mqtt_maintenance_runtime import scan_mqtt_entities
        result = scan_mqtt_entities()
        if not isinstance(result, dict):
            raise RuntimeError("maintenance scan returned invalid data")
        result = {
            key: value for key, value in result.items()
            if key != "plan_token" and not str(key).startswith("_")
        }
        payload = {
            "schema_version": 1,
            "generated_at": _now(),
            "status": "ok",
            "scope": "safe Switch Vision-owned retained MQTT discovery counts/entity IDs only; raw payloads excluded",
            **result,
        }
    except Exception as exc:
        payload = {
            "schema_version": 1,
            "generated_at": _now(),
            "status": "unavailable",
            "reason": f"MQTT maintenance scan failed safely: {type(exc).__name__}",
        }
    _write(root, DIAG_DIR / "mqtt-maintenance-scan.json", payload)
    return payload

def build_runtime_versions() -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "generated_at": _now(),
        "discovery_version": os.environ.get("SWITCH_VISION_DISCOVERY_VERSION", "unknown"),
        "home_assistant": {},
        "switch_vision_addons": [],
    }
    token = read_supervisor_token()
    if not token:
        payload["status"] = "partial"
        payload["reason"] = "Supervisor token unavailable"
        return payload
    def get(path: str) -> Any:
        req = Request(
            f"http://supervisor{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        with urlopen(req, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    try:
        core = get("/core/info")
        data = core.get("data") if isinstance(core, dict) and isinstance(core.get("data"), dict) else core
        if isinstance(data, dict):
            for key in ("version", "version_latest", "arch", "machine"):
                if key in data:
                    payload["home_assistant"][key] = data.get(key)
        addons_doc = get("/addons")
        data = addons_doc.get("data") if isinstance(addons_doc, dict) and isinstance(addons_doc.get("data"), dict) else addons_doc
        addons = data.get("addons") if isinstance(data, dict) else []
        for addon in addons if isinstance(addons, list) else []:
            if not isinstance(addon, dict):
                continue
            haystack = f"{addon.get('slug','')} {addon.get('name','')}".casefold()
            if "switch vision" not in haystack and "switch_vision" not in haystack and "snmp2mqtt" not in haystack and "unifi2mqtt" not in haystack:
                continue
            payload["switch_vision_addons"].append({
                key: addon.get(key) for key in ("slug", "name", "version", "version_latest", "state")
                if addon.get(key) not in (None, "")
            })
        payload["status"] = "ok"
    except Exception as exc:
        payload["status"] = "partial"
        payload["reason"] = f"Supervisor version query failed: {type(exc).__name__}"
    return payload

def build_summary(
    entity_snapshot: Any,
    port_pipeline: dict[str, Any],
    model_provenance: dict[str, Any],
    card_bindings: dict[str, Any],
    mqtt_scan: dict[str, Any],
) -> dict[str, Any]:
    entity_summary = entity_snapshot.get("summary", {}) if isinstance(entity_snapshot, dict) else {}
    return {
        "schema_version": 1,
        "generated_at": _now(),
        "purpose": "Cross-layer Support My Switch diagnostic summary",
        "signals": {
            "expected_entity_count": entity_summary.get("expected_count"),
            "missing_exact_entity_count": entity_summary.get("missing_exact_count"),
            "suffix_alternative_count": entity_summary.get("suffix_alternative_count"),
            "port_status_rows": port_pipeline.get("summary", {}).get("status_rows"),
            "ha_state_status": port_pipeline.get("summary", {}).get("ha_state_status"),
            "walk_state_status": port_pipeline.get("summary", {}).get("walk_state_status"),
            "walk_up_count": port_pipeline.get("summary", {}).get("walk_up_count"),
            "fresh_walk_up_count": port_pipeline.get("summary", {}).get("fresh_walk_up_count"),
            "stale_walk_up_count": port_pipeline.get("summary", {}).get("stale_walk_up_count"),
            "walk_up_but_exact_not_up": port_pipeline.get("summary", {}).get("walk_up_but_exact_not_up"),
            "mqtt_current_missing_retained_count": (
                mqtt_scan.get("current_missing_retained_count")
                if mqtt_scan.get("status") == "ok"
                else None
            ),
            "mqtt_stale_count": mqtt_scan.get("stale_count") if mqtt_scan.get("status") == "ok" else None,
            "model_device_count": model_provenance.get("device_count"),
            "generated_card_binding_count": len(card_bindings.get("cards", [])),
            "generated_target_count": len(card_bindings.get("targets", [])),
        },
        "privacy": {
            "home_assistant_attributes_included": False,
            "unrelated_home_assistant_entities_included": False,
            "raw_mqtt_discovery_payloads_included": False,
            "credentials_included": False,
        },
    }

def capture_support_diagnostics(root: Path) -> None:
    generated = _yaml(root / "generated-snmp2mqtt.yaml") or {}
    states, ha_error = _ha_states()
    entity_snapshot = _json(root / ENTITY_SNAPSHOT) or {}
    card_bindings = build_card_bindings(root, generated)
    port_pipeline = build_correlated_port_pipeline(
        root,
        generated,
        states,
        card_bindings,
        ha_available=ha_error is None,
    )
    model_provenance = build_model_provenance(root)
    file_provenance = build_file_provenance(root)
    mqtt_scan = capture_mqtt_maintenance(root)
    runtime_versions = build_runtime_versions()
    if ha_error:
        runtime_versions.setdefault("warnings", []).append(ha_error)

    _write(root, DIAG_DIR / "port-pipeline.json", port_pipeline)
    _write(root, DIAG_DIR / "model-provenance.json", model_provenance)
    _write(root, DIAG_DIR / "card-entity-bindings.json", card_bindings)
    _write(root, DIAG_DIR / "generated-file-provenance.json", file_provenance)
    _write(root, DIAG_DIR / "runtime-versions.json", runtime_versions)
    _write(
        root,
        DIAG_DIR / "diagnostic-summary.json",
        build_summary(entity_snapshot, port_pipeline, model_provenance, card_bindings, mqtt_scan),
    )
