#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "runtime_src" / "unifi_dashboard_cards.py"
REGISTRY_PATH = ROOT / "runtime_src" / "opt" / "switch-vision" / "devices" / "supported_devices.json"

spec = importlib.util.spec_from_file_location("sv_unifi_cards", HELPER_PATH)
assert spec and spec.loader
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def ports(rj45: int, sfp: int) -> list[dict[str, object]]:
    rows = [
        {"idx": idx, "connector": "RJ45", "state": "UP", "poe": {"available": False}}
        for idx in range(1, rj45 + 1)
    ]
    rows.extend(
        {
            "idx": rj45 + offset,
            "connector": "SFP",
            "state": "UP",
            "poe": {"available": False},
        }
        for offset in range(1, sfp + 1)
    )
    return rows


snapshot = {
    "schema_version": 1,
    "devices": [
        {
            "id": "controller-device-a",
            "name": "Lab A",
            "model": "US-8-150W",
            "ip_address": "192.0.2.10",
            "mac_address": "02:11:22:33:44:55",
            "ports": ports(8, 2),
            "api_capabilities": {"port_detail": True, "per_port_traffic": False},
        },
        {
            "id": "controller-device-b",
            "name": "Lab B",
            "model": "US 8 60W",
            "ip_address": "192.0.2.11",
            "mac_address": "02:aa:bb:cc:dd:ee",
            "ports": ports(8, 0),
            "api_capabilities": {"port_detail": True, "per_port_traffic": False},
        },
    ],
}

binding = helper.binding_card_fields(snapshot, registry, "192.0.2.10")
assert binding is not None
assert binding["unifi_device_id"] == "controller-device-a"
assert binding["unifi_hybrid"] is True
assert binding["unifi_match_basis"] == "management_ip"
assert binding["unifi_rj45_ports"] == 8
assert binding["unifi_sfp_port_offset"] == 8
assert binding["unifi_per_port_traffic"] is False

# Hardware MAC is stronger than management IP. This still selects A even when
# the supplied IP points at B, which covers DHCP/address changes safely.
mac_binding = helper.binding_card_fields(
    snapshot, registry, "192.0.2.11", "02-11-22-33-44-55"
)
assert mac_binding is not None
assert mac_binding["unifi_device_id"] == "controller-device-a"
assert mac_binding["unifi_match_basis"] == "hardware_mac"

# Suppression is by the exact matched API device identity, not the possibly
# changed IP, so a MAC-based reconciliation cannot hide a different switch.
text, emitted, *_ = helper.render(
    snapshot, registry, 6, set(), {"controller-device-a"}
)
assert emitted == 1
assert "controller-device-a" not in text
assert "controller-device-b" in text

ambiguous = json.loads(json.dumps(snapshot))
ambiguous["devices"][1]["ip_address"] = "192.0.2.10"
assert helper.unique_device_for_ip(ambiguous, "192.0.2.10") is None
assert helper.binding_card_fields(ambiguous, registry, "192.0.2.10") is None

ambiguous_mac = json.loads(json.dumps(snapshot))
ambiguous_mac["devices"][1]["mac_address"] = "02:11:22:33:44:55"
device, basis = helper.unique_device_for_identity(
    ambiguous_mac, device_mac="02:11:22:33:44:55", host="192.0.2.10"
)
assert device is None and basis == ""

print("UniFi/SNMP source reconciliation contract: PASS")
