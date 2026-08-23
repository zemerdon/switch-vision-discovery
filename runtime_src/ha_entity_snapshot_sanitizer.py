#!/usr/bin/env python3
"""Capture privacy-scoped HA entity resolution before Support My Switch sanitization.

This runtime wrapper records only Switch Vision-generated port status/traffic/speed
entities and then delegates to the existing sanitizer. It intentionally excludes
Home Assistant attributes and unrelated states.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

from support_diagnostics import capture_support_diagnostics

BASE_SANITIZER = Path(os.environ.get("SWITCH_VISION_BASE_SANITIZER", "/sanitize_support_bundle_base.py"))
HA_STATES_URL = os.environ.get("SWITCH_VISION_HA_STATES_URL", "http://supervisor/core/api/states")
SNAPSHOT_RELATIVE_PATH = Path("diagnostics/home-assistant-entity-resolution.json")
SAFE_OBJECT_SUFFIXES = (
    "_status",
    "_rx_bytes",
    "_tx_bytes",
    "_speed_mbps",
    "_speed_bps",
)
SAFE_TEXT_STATES = {
    "up",
    "down",
    "on",
    "off",
    "true",
    "false",
    "online",
    "offline",
    "available",
    "unavailable",
    "unknown",
}


def _slugify_sensor_name(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace("~", "_")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    return text.strip("_")


def expected_entity_ids(generated_yaml: Path) -> list[str]:
    try:
        document = yaml.safe_load(generated_yaml.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return []

    targets = document.get("targets", []) if isinstance(document, dict) else []
    if not isinstance(targets, list):
        return []

    expected: set[str] = set()
    for target in targets:
        if not isinstance(target, dict):
            continue
        sensors = target.get("sensors", [])
        if not isinstance(sensors, list):
            continue
        for sensor in sensors:
            if not isinstance(sensor, dict):
                continue
            object_id = _slugify_sensor_name(sensor.get("object_id") or sensor.get("name"))
            if not object_id or not object_id.endswith(SAFE_OBJECT_SUFFIXES):
                continue
            domain = "binary_sensor" if sensor.get("binary_sensor") is True else "sensor"
            expected.add(f"{domain}.{object_id}")
    return sorted(expected)


def _safe_state(entity_id: str, raw: Any) -> str | None:
    text = str(raw if raw is not None else "").strip()
    if not text:
        return None
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return text
    lowered = text.casefold()
    if entity_id.endswith("_status") and lowered in SAFE_TEXT_STATES:
        return lowered
    return "<NON_NUMERIC>"


def build_snapshot(expected: list[str], states: list[dict[str, Any]]) -> dict[str, Any]:
    state_map: dict[str, dict[str, Any]] = {}
    for item in states:
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("entity_id") or "").strip()
        if entity_id:
            state_map[entity_id] = item

    entries: list[dict[str, Any]] = []
    exact_present = 0
    suffix_alternative_count = 0
    for entity_id in expected:
        exact = state_map.get(entity_id)
        if exact is not None:
            exact_present += 1

        alternative_pattern = re.compile(rf"^{re.escape(entity_id)}_\d+$")
        alternatives = []
        for candidate_id, candidate in state_map.items():
            if not alternative_pattern.fullmatch(candidate_id):
                continue
            alternatives.append(
                {
                    "entity_id": candidate_id,
                    "state": _safe_state(candidate_id, candidate.get("state")),
                    "last_updated": str(candidate.get("last_updated") or ""),
                }
            )
        alternatives.sort(key=lambda item: item["entity_id"])
        suffix_alternative_count += len(alternatives)

        entries.append(
            {
                "expected_entity_id": entity_id,
                "exact_present": exact is not None,
                "state": _safe_state(entity_id, exact.get("state")) if exact else None,
                "last_updated": str(exact.get("last_updated") or "") if exact else "",
                "suffix_alternatives": alternatives,
            }
        )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "generated Switch Vision status/RX/TX/speed entities only; Home Assistant attributes excluded",
        "status": "ok",
        "summary": {
            "expected_count": len(expected),
            "exact_present_count": exact_present,
            "missing_exact_count": len(expected) - exact_present,
            "suffix_alternative_count": suffix_alternative_count,
        },
        "entities": entries,
    }


def capture_snapshot(root: Path) -> None:
    generated_yaml = root / "generated-snmp2mqtt.yaml"
    if not generated_yaml.is_file():
        return

    expected = expected_entity_ids(generated_yaml)
    output = root / SNAPSHOT_RELATIVE_PATH
    output.parent.mkdir(parents=True, exist_ok=True)

    token = os.environ.get("SUPERVISOR_TOKEN", "").strip()
    if not token:
        payload = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scope": "generated Switch Vision status/RX/TX/speed entities only; Home Assistant attributes excluded",
            "status": "unavailable",
            "reason": "Home Assistant API token unavailable",
            "summary": {"expected_count": len(expected)},
            "entities": [],
        }
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return

    request = Request(
        HA_STATES_URL,
        method="GET",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            states = json.loads(response.read().decode("utf-8"))
        if not isinstance(states, list):
            raise ValueError("Home Assistant states response was not a list")
        payload = build_snapshot(expected, states)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, HTTPError, URLError) as exc:
        payload = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scope": "generated Switch Vision status/RX/TX/speed entities only; Home Assistant attributes excluded",
            "status": "unavailable",
            "reason": f"Home Assistant state query failed: {type(exc).__name__}",
            "summary": {"expected_count": len(expected)},
            "entities": [],
        }

    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    if len(sys.argv) >= 2:
        root = Path(sys.argv[1])
        try:
            capture_snapshot(root)
        except Exception as exc:  # Diagnostic capture must never block sanitization.
            output = root / SNAPSHOT_RELATIVE_PATH
            try:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "generated_at": datetime.now(timezone.utc).isoformat(),
                            "status": "unavailable",
                            "reason": f"entity snapshot failed safely: {type(exc).__name__}",
                            "entities": [],
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except OSError:
                pass

        try:
            capture_support_diagnostics(root)
        except Exception as exc:  # Extended diagnostics must never block sanitization.
            status = root / "diagnostics/support-diagnostics-status.json"
            try:
                status.parent.mkdir(parents=True, exist_ok=True)
                status.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "generated_at": datetime.now(timezone.utc).isoformat(),
                            "status": "unavailable",
                            "reason": f"extended diagnostics failed safely: {type(exc).__name__}",
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except OSError:
                pass

    if not BASE_SANITIZER.is_file():
        raise SystemExit(f"Base sanitizer not found: {BASE_SANITIZER}")
    os.execv(sys.executable, [sys.executable, str(BASE_SANITIZER), *sys.argv[1:]])


if __name__ == "__main__":
    main()
