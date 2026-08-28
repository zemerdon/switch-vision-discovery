#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"

EXACT = {
    "sv-2026-000011-5548p": "evidence-dell-powerconnect-5548p-a",
    "sv-2026-000011-gs1900": "evidence-zyxel-gs1900-24e-a",
    "sv-2026-000008": "evidence-cisco-c3750x-48p-a",
    "sv-2026-000048": "evidence-cisco-sg350-20-a",
    "sv-2026-000033": "evidence-hp-j8693a-a",
    "sv-2026-000006-hd24": "evidence-unifi-pro-hd24-snmp-a",
    "sv-2026-000006-snmp": "evidence-unifi-pro-xg8-snmp-a",
    "sv-2026-000028-aggregation": "evidence-unifi-aggregation-api-a",
    "sv-2026-000028-enterprise24": "evidence-unifi-enterprise24-api-a",
    "sv-2026-000028-flex2p5g5": "evidence-unifi-flex-2p5g-5-api-a",
    "sv-2026-000028-wan": "evidence-unifi-wan-api-a",
    "sv-2026-000028-enterprise8": "evidence-unifi-enterprise8-refresh-a",
    "sv-2026-000028-flexmini": "evidence-unifi-flex-mini-refresh-a",
    "support_my_switch_sv_2026_000028_unifi2mqtt_2.0.50": "anonymous_real_hardware_unifi2mqtt_2.0.50_refresh",
    "support_my_switch_sv_2026_000006_real_hardware_snmp": "anonymous_real_hardware_snmp_validation",
}

SUBMISSION = re.compile(r"(?i)SV[-_]20\d{2}[-_]\d+(?:[-_][A-Za-z0-9]+)*")


def sanitize_string(value: str) -> str:
    lower = value.casefold()
    for old, new in EXACT.items():
        if old in lower:
            # Preserve surrounding prose while replacing the identifier token.
            value = re.sub(re.escape(old), new, value, flags=re.IGNORECASE)
            lower = value.casefold()
    value = SUBMISSION.sub("anonymous-retained-evidence", value)
    return value


def walk(value):
    if isinstance(value, dict):
        return {k: walk(v) for k, v in value.items()}
    if isinstance(value, list):
        return [walk(v) for v in value]
    if isinstance(value, str):
        return sanitize_string(value)
    return value


def main() -> None:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    data = walk(data)
    REGISTRY.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
