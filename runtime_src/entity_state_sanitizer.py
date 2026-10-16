"""Strict redaction of Home Assistant entity state for local support diagnostics."""
from __future__ import annotations

import re
from typing import Any

SAFE_TEXT_STATES = frozenset({
    "up", "down", "on", "off", "true", "false",
    "online", "offline", "available", "unavailable", "unknown",
})


def safe_entity_state(entity_id: str, raw: Any) -> str | None:
    text = str(raw if raw is not None else "").strip()
    if not text:
        return None
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return text
    lowered = text.casefold()
    if entity_id.endswith("_status") and lowered in SAFE_TEXT_STATES:
        return lowered
    return "<NON_NUMERIC>"
