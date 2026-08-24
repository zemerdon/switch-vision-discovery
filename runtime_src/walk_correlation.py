#!/usr/bin/env python3
"""Target-aware, time-aware port correlation for Support My Switch diagnostics."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

STATUS_SUFFIX = "_status"
MAX_PORT_ROWS = 512
MAX_WALK_FILES = 128
MAX_WALK_AGE_SECONDS = 15 * 60

def _now_dt() -> datetime:
    return datetime.now(timezone.utc)

def _parse_run_timestamp(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)

def _discovery_run_window(root: Path) -> tuple[datetime, datetime] | None:
    """Return the trustworthy timestamp window from the latest Discovery run."""
    path = root / "last-discovery-run.txt"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    started = None
    generated = None
    for line in lines:
        if line.startswith("Discovery app loaded: "):
            started = _parse_run_timestamp(line.split(": ", 1)[1])
        elif line.startswith("Generated: "):
            generated = _parse_run_timestamp(line.split(": ", 1)[1])
    if started is None or generated is None or generated < started:
        return None
    if (generated - started).total_seconds() > 24 * 60 * 60:
        return None
    return started, generated

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

def _state_map(states: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in states:
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("entity_id") or "").strip()
        if entity_id:
            result[entity_id] = item
    return result

def _suffix_alternatives(entity_id: str, state_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    pattern = re.compile(rf"^{re.escape(entity_id)}_(\d+)$")
    out: list[dict[str, Any]] = []
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
    out: list[dict[str, Any]] = []
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
            if not object_id or not object_id.endswith(STATUS_SUFFIX):
                continue
            component = "binary_sensor" if sensor.get("binary_sensor") is True else "sensor"
            out.append({
                "target": target_name,
                "object_id": object_id,
                "entity_id": f"{component}.{object_id}",
                "oid": str(sensor.get("oid") or sensor.get("object_id_oid") or "").strip().lstrip("."),
            })
    return out

def _status_prefix(card: dict[str, Any]) -> str:
    value = str(card.get("status_entity_prefix") or "").strip().lower()
    value = re.sub(r"^(?:sensor|binary_sensor)\.", "", value)
    if "_port_" in value:
        value = value.split("_port_", 1)[0]
    return _slug(value)

def _card_prefix_to_walk_key(card_bindings: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    cards = card_bindings.get("cards") if isinstance(card_bindings, dict) else []
    for card in cards if isinstance(cards, list) else []:
        if not isinstance(card, dict):
            continue
        walk_key = _slug(card.get("discovery_selected_switch"))
        if not walk_key:
            continue
        candidates = {
            _slug(card.get("selected_switch")),
            _slug(card.get("member")),
            _slug(card.get("sensor_prefix")),
            _status_prefix(card),
        }
        for prefix in candidates:
            if prefix:
                mapping[prefix] = walk_key
    return mapping

def _walk_source_key(root: Path, path: Path) -> str:
    snmpwalks = root / "snmpwalks"
    try:
        relative = path.relative_to(snmpwalks)
        if relative.parts:
            return _slug(relative.parts[0])
    except ValueError:
        pass
    return _slug(path.parent.name)

def _parse_walk_sources(root: Path, *, now: datetime | None = None) -> dict[str, dict[str, Any]]:
    now = now or _now_dt()
    discovery_window = _discovery_run_window(root)
    pattern = re.compile(
        r"^\s*\.?(1\.3\.6\.1\.2\.1\.2\.2\.1\.8\.\d+)\s*=\s*(?:INTEGER:\s*)?([A-Za-z]+(?:\(\d+\))?|\d+)",
        re.I,
    )
    candidates = [
        path for path in root.rglob("*.txt")
        if path.is_file() and "walk" in path.name.lower()
    ]
    candidates.sort(key=lambda p: (p.stat().st_mtime if p.exists() else 0, str(p)))
    sources: dict[str, dict[str, Any]] = {}
    for path in candidates[-MAX_WALK_FILES:]:
        statuses: dict[str, str] = {}
        try:
            for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
                match = pattern.match(raw)
                if match:
                    statuses[match.group(1)] = match.group(2).strip()
            stat = path.stat()
        except OSError:
            continue
        if not statuses:
            continue
        key = _walk_source_key(root, path)
        if not key:
            continue
        previous = sources.get(key)
        if previous and float(previous["mtime"]) >= stat.st_mtime:
            continue
        age_seconds = max(0.0, now.timestamp() - stat.st_mtime)
        current_discovery_run = False
        if discovery_window is not None:
            run_start, run_end = discovery_window
            # Filesystem timestamps can differ by a few seconds from the shell
            # timestamps written into last-discovery-run.txt.
            current_discovery_run = (
                run_start.timestamp() - 5.0
                <= stat.st_mtime
                <= run_end.timestamp() + 5.0
            )
        fresh_by_age = age_seconds <= MAX_WALK_AGE_SECONDS
        fresh = current_discovery_run or fresh_by_age
        freshness_reason = (
            "current_discovery_run"
            if current_discovery_run
            else ("age" if fresh_by_age else "stale")
        )
        try:
            relative = str(path.relative_to(root))
        except ValueError:
            relative = path.name
        sources[key] = {
            "path": relative,
            "mtime": stat.st_mtime,
            "captured_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "age_seconds": round(age_seconds, 3),
            "fresh": fresh,
            "current_discovery_run": current_discovery_run,
            "freshness_reason": freshness_reason,
            "statuses": statuses,
        }
    return sources

def _object_prefix(object_id: str, known_prefixes: dict[str, str]) -> str | None:
    matches = [
        prefix for prefix in known_prefixes
        if object_id == prefix or object_id.startswith(prefix + "_")
    ]
    return max(matches, key=len) if matches else None

def build_port_pipeline(
    root: Path,
    generated: Any,
    states: list[dict[str, Any]],
    card_bindings: dict[str, Any],
    *,
    ha_available: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or _now_dt()
    state_map = _state_map(states) if ha_available else {}
    prefix_map = _card_prefix_to_walk_key(card_bindings)
    walk_sources = _parse_walk_sources(root, now=now)
    rows: list[dict[str, Any]] = []
    fresh_walk_rows = 0
    stale_walk_rows = 0
    unmapped_walk_rows = 0

    for sensor in _sensor_rows(generated):
        exact = state_map.get(sensor["entity_id"]) if ha_available else None
        prefix = _object_prefix(sensor["object_id"], prefix_map)
        walk_key = prefix_map.get(prefix) if prefix else None
        source = walk_sources.get(walk_key) if walk_key else None
        status = source["statuses"].get(sensor["oid"]) if source and sensor["oid"] else None
        source_state = "unmapped"
        if source:
            source_state = "fresh" if source["fresh"] else "stale"
            if source["fresh"]:
                fresh_walk_rows += 1
            else:
                stale_walk_rows += 1
        else:
            unmapped_walk_rows += 1
        rows.append({
            "target": sensor["target"],
            "object_id": sensor["object_id"],
            "expected_entity_id": sensor["entity_id"],
            "status_oid": sensor["oid"] or None,
            "walk_if_oper_status": status,
            "walk_source_status": source_state,
            "walk_source": source["path"] if source else None,
            "walk_captured_at": source["captured_at"] if source else None,
            "walk_age_seconds": source["age_seconds"] if source else None,
            "walk_current_discovery_run": source["current_discovery_run"] if source else None,
            "walk_freshness_reason": source["freshness_reason"] if source else None,
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
    fresh_walk_up_rows = [
        row for row in rows
        if row["walk_source_status"] == "fresh"
        and row["walk_if_oper_status"]
        and str(row["walk_if_oper_status"]).casefold().startswith("up")
    ]
    stale_walk_up_rows = [
        row for row in rows
        if row["walk_source_status"] == "stale"
        and row["walk_if_oper_status"]
        and str(row["walk_if_oper_status"]).casefold().startswith("up")
    ]
    anomalies = [
        row for row in fresh_walk_up_rows
        if ha_available and (
            not row["exact_present"]
            or row["ha_state"] not in {"up", "on", "true", "1"}
        )
    ]
    if fresh_walk_rows:
        walk_state_status = "fresh"
    elif stale_walk_rows:
        walk_state_status = "stale"
    elif walk_sources:
        walk_state_status = "unmapped"
    else:
        walk_state_status = "unavailable"

    source_summary = [
        {
            "key": key,
            "path": source["path"],
            "captured_at": source["captured_at"],
            "age_seconds": source["age_seconds"],
            "fresh": source["fresh"],
            "current_discovery_run": source["current_discovery_run"],
            "freshness_reason": source["freshness_reason"],
        }
        for key, source in sorted(walk_sources.items())
    ]

    return {
        "schema_version": 2,
        "generated_at": now.isoformat(),
        "scope": (
            "generated Switch Vision port status entities correlated only with the "
            "correct per-switch captured walk source; stale walk evidence is preserved "
            "but never treated as a current HA mismatch; no HA attributes"
        ),
        "summary": {
            "status_rows": len(rows),
            "ha_state_status": "available" if ha_available else "unavailable",
            "walk_state_status": walk_state_status,
            "walk_freshness_limit_seconds": MAX_WALK_AGE_SECONDS,
            "fresh_walk_status_rows": sum(1 for row in rows if row["walk_source_status"] == "fresh"),
            "current_run_walk_status_rows": sum(1 for row in rows if row.get("walk_current_discovery_run") is True),
            "stale_walk_status_rows": sum(1 for row in rows if row["walk_source_status"] == "stale"),
            "unmapped_walk_status_rows": sum(1 for row in rows if row["walk_source_status"] == "unmapped"),
            "fresh_walk_up_count": len(fresh_walk_up_rows),
            "stale_walk_up_count": len(stale_walk_up_rows),
            "walk_up_count": len(fresh_walk_up_rows) + len(stale_walk_up_rows),
            "walk_up_but_exact_not_up": (
                len(anomalies) if ha_available and fresh_walk_rows else None
            ),
            "suffix_alternative_count": (
                sum(len(row["suffix_alternatives"]) for row in rows)
                if ha_available
                else None
            ),
        },
        "walk_sources": source_summary,
        "ports": rows,
        "anomalies": anomalies[:128],
    }
