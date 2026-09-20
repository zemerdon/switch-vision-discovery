#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "runtime_src" / "opt" / "switch-vision" / "devices" / "supported_devices.json"

EXPECTED = {
    "USW Flex": ((5, 0), "faceplates/unifi-5rj45.png", "default_unifi_5_rj45"),
    "USW Flex Mini": ((5, 0), "faceplates/usw-flex-mini.png", "usw_flex_mini"),
    "USW-Lite-8-PoE": ((8, 0), "faceplates/unifi-8rj45.png", "default_unifi_8_rj45"),
    "USW-Enterprise-8-PoE": ((8, 2), "faceplates/unifi-8-rj45-2sfp.png", "unifi_8_rj45_2sfp"),
    "USW Pro XG 8 PoE": ((8, 2), "faceplates/unifi-8-rj45-2sfp.png", "unifi_8_rj45_2sfp"),
    "USW Pro HD 24 PoE": ((24, 4), "faceplates/unifi-24-rj45-4sfp-inline.png", "unifi_24_rj45_4sfp_inline"),
    "USW Pro Aggregation": ((0, 32), "faceplates/unifi-32sfp.png", "unifi_32sfp"),
    "USW-16-PoE": ((16, 2), "faceplates/unifi-16rj45-2sfp.png", "unifi_16_rj45_2sfp"),
    "US 16 PoE 150W": ((16, 2), "faceplates/unifi-16rj45-2sfp.png", "unifi_16_rj45_2sfp"),
    "UDM Pro": ((9, 2), "faceplates/unifi-9rj45-2sfp.png", "unifi_9_rj45_2sfp"),
    "UniFi Dream Machine PRO SE": ((9, 2), "faceplates/unifi-9rj45-2sfp.png", "unifi_9_rj45_2sfp"),
    "UDM Pro Max": ((9, 2), "faceplates/unifi-9rj45-2sfp.png", "unifi_9_rj45_2sfp"),
    "USW WAN": ((1, 3), "faceplates/unifi-3sfp.png", "unifi_3sfp"),
}


def main() -> None:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    rows = payload.get("devices") or []
    by_model = {row.get("model"): row for row in rows if isinstance(row, dict)}

    for model, (physical, faceplate, profile) in EXPECTED.items():
        row = by_model[model]
        ports = row.get("ports") or {}
        assert (int(ports.get("rj45") or 0), int(ports.get("uplinks") or 0)) == physical, model
        assert row.get("dashboard_support") is True, model
        assert row.get("default_faceplate") == faceplate, model
        assert row.get("calibration_profile") == profile, model
        visuals = row.get("visuals") or {}
        assert visuals.get("recommended_faceplate") == faceplate, model
        assert visuals.get("calibration_profile") == profile, model

    # USW WAN keeps one real rear management RJ45 in device truth even though
    # the selected front-panel faceplate contains only three optical cages.
    usw = by_model["USW WAN"]
    assert usw["ports"]["rj45"] == 1
    assert usw["ports"]["uplinks"] == 3
    assert usw["unifi_api_port_map"] == {"rj45": [4], "sfp": [1, 2, 3]}

    print("Discovery 2.4.19 exact-model faceplate matrix: PASS")


if __name__ == "__main__":
    main()
