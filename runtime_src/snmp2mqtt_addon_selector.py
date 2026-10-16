"""Pure Supervisor add-on selection, shared by Hub and MQTT maintenance."""
from __future__ import annotations

from typing import Any


def select_snmp2mqtt_addon(payload: Any) -> dict[str, Any] | None:
    """Preserve the reviewed Switch Vision add-on rank and Supervisor order.

    Selection consumes only a parsed Supervisor /addons response. The caller
    owns request authentication, timeouts and error handling.
    """
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
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
