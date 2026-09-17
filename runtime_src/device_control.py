#!/usr/bin/env python3
"""Shared local device order/state/first-added contract for Switch Vision.

The file is derived operational state under /share/switch_vision. It never
contains credentials. SNMP enable/disable remains authoritative in Discovery
Supervisor options; UniFi enable/disable is persisted here so UniFi2MQTT can
stop per-device polling while Discovery/Hub can keep a unified device list.

``added_at`` is intentionally independent from the mutable display order. Once
assigned to a stable device key it is retained so Reset Order can always return
to the device's original first-added sequence.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1
DEFAULT_PATH = Path("/share/switch_vision/device-control.json")
_KEY_RE = re.compile(r"^(snmp|unifi):[^\x00-\x1f\x7f]{1,300}$")


def device_key(source: str, identity: Any) -> str:
    prefix = str(source or "").strip().casefold()
    value = str(identity or "").strip()
    key = f"{prefix}:{value}"
    if not _KEY_RE.fullmatch(key):
        raise ValueError("Device identity is invalid.")
    return key


def _empty() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "order": [], "states": {}, "added_at": {}}


def _normalise_key(value: Any) -> str | None:
    key = str(value or "").strip()
    return key if _KEY_RE.fullmatch(key) else None


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def load_from_object(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return _empty()
    order: list[str] = []
    seen: set[str] = set()
    raw_order = payload.get("order")
    if isinstance(raw_order, list):
        for value in raw_order:
            key = _normalise_key(value)
            if key and key not in seen:
                seen.add(key)
                order.append(key)
    states: dict[str, str] = {}
    raw_states = payload.get("states")
    if isinstance(raw_states, dict):
        for raw_key, raw_state in raw_states.items():
            key = _normalise_key(raw_key)
            state = str(raw_state or "").strip().casefold()
            if key and state in {"enabled", "disabled"}:
                states[key] = state
    added_at: dict[str, str] = {}
    raw_added = payload.get("added_at")
    if isinstance(raw_added, dict):
        for raw_key, raw_timestamp in raw_added.items():
            key = _normalise_key(raw_key)
            parsed = _parse_timestamp(raw_timestamp)
            if key and parsed is not None:
                added_at[key] = _format_timestamp(parsed)
    return {
        "schema_version": SCHEMA_VERSION,
        "order": order,
        "states": states,
        "added_at": added_at,
    }


def load(path: Path = DEFAULT_PATH) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return _empty()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _empty()
    if not isinstance(payload, dict) or payload.get("schema_version") not in {
        LEGACY_SCHEMA_VERSION,
        SCHEMA_VERSION,
    }:
        return _empty()
    return load_from_object(payload)


def save(payload: dict[str, Any], path: Path = DEFAULT_PATH) -> dict[str, Any]:
    path = Path(path)
    normalised = load_from_object(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(normalised, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        # This file is a cross-app control contract and contains no credentials.
        # Keep it readable by sibling Switch Vision app containers mounted on /share.
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
        os.chmod(path, 0o644)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return normalised


def ordered_keys(current_keys: Iterable[str], payload: dict[str, Any]) -> list[str]:
    available: list[str] = []
    seen: set[str] = set()
    for raw in current_keys:
        key = _normalise_key(raw)
        if key and key not in seen:
            seen.add(key)
            available.append(key)
    order = load_from_object(payload).get("order", [])
    ranked = [key for key in order if key in seen]
    ranked_set = set(ranked)
    ranked.extend(key for key in available if key not in ranked_set)
    return ranked


def reconcile_added_at(
    payload: dict[str, Any],
    current_keys: Iterable[str],
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any], bool]:
    """Assign immutable first-added timestamps to current devices if missing.

    A v1 installation has no historical timestamps. Its first v2 reconciliation
    seeds timestamps in its current saved display order, preserving that order as
    the deterministic migration baseline. Existing timestamps are never changed
    or removed, even when a device is temporarily absent.
    """
    result = load_from_object(payload)
    ordered = ordered_keys(current_keys, result)
    existing = [
        parsed
        for parsed in (_parse_timestamp(value) for value in result["added_at"].values())
        if parsed is not None
    ]
    clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cursor = max([clock, *existing]) if existing else clock
    changed = False
    for key in ordered:
        if key in result["added_at"]:
            continue
        if changed or existing:
            cursor += timedelta(microseconds=1)
        result["added_at"][key] = _format_timestamp(cursor)
        changed = True
    return result, changed


def added_order(current_keys: Iterable[str], payload: dict[str, Any]) -> list[str]:
    result, _ = reconcile_added_at(payload, current_keys)
    current = ordered_keys(current_keys, result)
    fallback = {key: index for index, key in enumerate(current)}
    return sorted(
        current,
        key=lambda key: (
            _parse_timestamp(result["added_at"].get(key)) or datetime.max.replace(tzinfo=timezone.utc),
            fallback[key],
        ),
    )


def reset_order(payload: dict[str, Any], current_keys: Iterable[str]) -> dict[str, Any]:
    result, _ = reconcile_added_at(payload, current_keys)
    result["order"] = added_order(current_keys, result)
    return result


def set_state(payload: dict[str, Any], key: str, enabled: bool) -> dict[str, Any]:
    valid = _normalise_key(key)
    if not valid:
        raise ValueError("Device identity is invalid.")
    result = load_from_object(payload)
    result["states"][valid] = "enabled" if enabled else "disabled"
    if valid not in result["order"]:
        result["order"].append(valid)
    result, _ = reconcile_added_at(result, result["order"])
    return result


def state_for(payload: dict[str, Any], key: str, default: bool = True) -> bool:
    valid = _normalise_key(key)
    if not valid:
        return default
    state = load_from_object(payload).get("states", {}).get(valid)
    if state == "disabled":
        return False
    if state == "enabled":
        return True
    return default


def move(payload: dict[str, Any], current_keys: Iterable[str], source: str, destination: str) -> dict[str, Any]:
    source_key = _normalise_key(source)
    destination_key = _normalise_key(destination)
    if not source_key or not destination_key or source_key == destination_key:
        raise ValueError("Device order request is invalid.")
    result, _ = reconcile_added_at(payload, current_keys)
    order = ordered_keys(current_keys, result)
    if source_key not in order or destination_key not in order:
        raise ValueError("The device list changed. Refresh Devices and try again.")
    source_index = order.index(source_key)
    destination_index = order.index(destination_key)
    order[source_index], order[destination_index] = order[destination_index], order[source_index]
    result["order"] = order
    return result
