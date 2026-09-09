#!/usr/bin/env python3
"""Bounded, credential-sanitized Discovery operation history."""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_HISTORY_PATH = Path("/share/switch_vision/discovery-history.json")
HISTORY_LIMIT = 20
DEBUG_LINE_LIMIT = 80
HISTORY_SCHEMA = "switch-vision-discovery-history-v1"

_SECRET_ASSIGNMENT_RE = re.compile(
    r"((?:community|community_string|password|passwd|token|api[_-]?key|secret|authorization|credential|credentials)\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
    re.IGNORECASE,
)
_SECRET_ARG_RE = re.compile(
    r"(\s(?:-c|--community|-A|--auth-password|-X|--priv-password|--token)\s+)"
    r"(?:\"[^\"]*\"|'[^']*'|\S+)",
    re.IGNORECASE,
)
_AUTH_HEADER_RE = re.compile(
    r"(Authorization:\s*(?:Bearer|Basic)\s+)[^\s]+",
    re.IGNORECASE,
)
_URL_CREDS_RE = re.compile(
    r"(https?://)([^/\s:@]+):([^@\s/]+)@",
    re.IGNORECASE,
)


def sanitize_debug_text(value: Any) -> str:
    """Remove credential-shaped values before text enters persistent history."""
    text = str(value or "")
    text = _SECRET_ASSIGNMENT_RE.sub(r"\1[REDACTED]", text)
    text = _SECRET_ARG_RE.sub(r"\1[REDACTED]", text)
    text = _AUTH_HEADER_RE.sub(r"\1[REDACTED]", text)
    text = _URL_CREDS_RE.sub(r"\1[REDACTED]:[REDACTED]@", text)
    return text


def _safe_text(value: Any, *, limit: int = 2048) -> str:
    return sanitize_debug_text(value).replace("\x00", "")[:limit]


def _safe_snmp2mqtt(value: Any) -> dict[str, str]:
    source = value if isinstance(value, dict) else {}
    result: dict[str, str] = {}
    for key in ("status", "action", "slug", "state", "message"):
        if key in source and source.get(key) is not None:
            result[key] = _safe_text(source.get(key), limit=512)
    return result


def _history_status(snapshot: dict[str, Any]) -> str:
    phase = str(snapshot.get("phase") or "").strip().lower()
    if phase in {"stopped", "cancelled", "canceled"}:
        return "stopped"
    success = snapshot.get("success")
    if success is True:
        return "complete"
    if success is False:
        return "failed"
    return "unknown"


def _duration_seconds(snapshot: dict[str, Any]) -> int | None:
    value = snapshot.get("elapsed_seconds")
    if not isinstance(value, bool) and isinstance(value, (int, float)) and value >= 0:
        return int(value)
    started = str(snapshot.get("started_at") or "").strip()
    finished = str(snapshot.get("finished_at") or "").strip()
    if not started or not finished:
        return None
    try:
        delta = datetime.fromisoformat(finished) - datetime.fromisoformat(started)
    except ValueError:
        return None
    seconds = int(delta.total_seconds())
    return seconds if seconds >= 0 else None


def history_record(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return the bounded public-safe record stored for one completed operation."""
    debug = snapshot.get("log_tail")
    debug_lines = debug if isinstance(debug, list) else []
    return {
        "mode": _safe_text(snapshot.get("mode") or "discovery", limit=64),
        "status": _history_status(snapshot),
        "started_at": _safe_text(snapshot.get("started_at"), limit=64),
        "finished_at": _safe_text(snapshot.get("finished_at"), limit=64),
        "duration_seconds": _duration_seconds(snapshot),
        "message": _safe_text(snapshot.get("message"), limit=1024),
        "stage": _safe_text(snapshot.get("stage"), limit=512),
        "switch": _safe_text(snapshot.get("switch"), limit=255),
        "target": _safe_text(snapshot.get("target"), limit=255),
        "activity": _safe_text(snapshot.get("activity"), limit=512),
        "command": _safe_text(snapshot.get("command"), limit=2048),
        "snmp2mqtt": _safe_snmp2mqtt(snapshot.get("snmp2mqtt")),
        "debug_tail": [
            _safe_text(line, limit=2048)
            for line in debug_lines[-DEBUG_LINE_LIMIT:]
        ],
    }


def _read_items(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict) or data.get("schema") != HISTORY_SCHEMA:
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)][-HISTORY_LIMIT:]


def discovery_history_snapshot(path: Path = DEFAULT_HISTORY_PATH) -> dict[str, Any]:
    """Return bounded recent history; corrupt/missing state is fail-soft empty."""
    return {
        "schema": HISTORY_SCHEMA,
        "limit": HISTORY_LIMIT,
        "debug_line_limit": DEBUG_LINE_LIMIT,
        "items": _read_items(path),
    }


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
    finally:
        if fd >= 0:
            os.close(fd)
        temp_path.unlink(missing_ok=True)


def append_discovery_history(
    snapshot: dict[str, Any],
    path: Path = DEFAULT_HISTORY_PATH,
) -> dict[str, Any]:
    """Append one completed operation and retain only the newest bounded records."""
    items = _read_items(path)
    items.append(history_record(snapshot))
    items = items[-HISTORY_LIMIT:]
    payload = {
        "schema": HISTORY_SCHEMA,
        "limit": HISTORY_LIMIT,
        "debug_line_limit": DEBUG_LINE_LIMIT,
        "items": items,
    }
    _atomic_write(path, payload)
    return payload
