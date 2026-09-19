#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"
PROFILES_PATH = ROOT / "runtime_src/profiles/switch-vision-profiles.yaml"
JOB_PATH = ROOT / "runtime_src/discovery_job.sh"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


physical = load_module("sv_physical_contract_promotions", ROOT / "runtime_src/physical_contract.py")
unifi = load_module("sv_unifi_dashboard_promotions", ROOT / "runtime_src/unifi_dashboard_cards.py")
registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
profiles_doc = yaml.safe_load(PROFILES_PATH.read_text(encoding="utf-8")) or {}
profiles = profiles_doc.get("profiles", profiles_doc)
models = {
    row["model"]: row
    for row in registry["devices"]
    if isinstance(row, dict) and row.get("model")
}

xr = models["WS-C2960XR-48LPS-I"]
assert xr["status"] == "experimental"
assert xr["dashboard_support"] is True
assert xr["mapping_profile"] == "cisco-2960xr-48lps-48p-4sfp"
assert xr["ports"]["rj45"] == 48
assert xr["ports"]["uplinks"] == 4
assert xr["ports"]["gigabit_sfp"] == 4
assert xr["ports"]["ten_gigabit_sfp_plus"] == 0
assert xr["calibration_profile"] == "default_cisco_48_port"
assert xr["default_faceplate"] == "faceplates/48rj45-4sfp.png"
pxr = profiles[xr["mapping_profile"]]
assert pxr["status"] == "experimental"
assert pxr["layout"] == {
    "members": "auto",
    "rj45_ports": 48,
    "sfp_1g_ports": 4,
    "sfp_10g_ports": 0,
}

interfaces = []
for port in range(1, 49):
    interfaces.append({
        "if_index": 10000 + port,
        "name": f"Gi1/0/{port}",
        "physical": True,
        "media": "rj45",
    })
for port in range(49, 53):
    interfaces.append({
        "if_index": 10000 + port,
        "name": f"Gi1/0/{port}",
        "physical": True,
        "media": "sfp",
    })
contract = physical.resolve(
    {
        "device": {
            "model_text": "WS-C2960XR-48LPS-I",
            "vendor_name": "Cisco",
        },
        "interfaces": interfaces,
    },
    registry,
)
assert contract["status"] == "resolved", contract
assert contract["device"]["registry_match"] is True
assert contract["device"]["mapping_profile"] == "cisco-2960xr-48lps-48p-4sfp"
assert contract["observed"]["physical"] == 52
assert contract["observed"]["rj45"] == 48
assert contract["observed"]["uplinks"] == 4
assert contract["observed"]["sfp"] == 4
assert not contract["errors"]

job = JOB_PATH.read_text(encoding="utf-8")
assert 'if (m ~ /^WS-C2960XR-48LPS-I$/) return "cisco-2960xr-48lps-48p-4sfp"' in job
assert 'model ~ /^WS-C2960XR-48LPS-I$/' in job
assert '*WS-C2960XR-48LPS-I*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_1g_{port}_status" ;;' in job

fiber = models["UCG Fiber"]
assert fiber["status"] == "experimental"
assert fiber["dashboard_support"] is True
assert fiber["mapping_profile"] == "ubiquiti-ucg-fiber-api"
assert fiber["ports"]["rj45"] == 5
assert fiber["ports"]["uplinks"] == 2
assert fiber["ports"]["poe"] is True
assert fiber["unifi_api_port_map"] == {
    "rj45": [1, 2, 3, 4, 5],
    "sfp": [6, 7],
}
assert fiber["calibration_profile"] == "unifi_8_rj45_2sfp"
assert fiber["default_faceplate"] == "faceplates/unifi-8-rj45-2sfp.png"
pfiber = profiles[fiber["mapping_profile"]]
assert pfiber["status"] == "experimental"
assert pfiber["layout"] == {
    "members": 1,
    "rj45_ports": 5,
    "sfp_1g_ports": 0,
    "sfp_10g_ports": 2,
}

fiber_ports = [
    {"idx": 1, "connector": "RJ45", "max_speed_mbps": 2500},
    {"idx": 2, "connector": "RJ45", "max_speed_mbps": 2500},
    {"idx": 3, "connector": "RJ45", "max_speed_mbps": 2500},
    {
        "idx": 4,
        "connector": "RJ45",
        "max_speed_mbps": 2500,
        "poe": {"available": True, "standard": "802.3at"},
    },
    {"idx": 5, "connector": "RJ45", "max_speed_mbps": 10000},
    {"idx": 6, "connector": "SFPPLUS", "max_speed_mbps": 10000},
    {"idx": 7, "connector": "SFPPLUS", "max_speed_mbps": 10000},
]
fiber_render = unifi.render(
    {
        "devices": [{
            "id": "fiber-fixture",
            "name": "Fiber fixture",
            "model": "UCG Fiber",
            "ports": fiber_ports,
        }]
    },
    registry,
)
fiber_text = fiber_render[0]
assert fiber_render[1] == 1, fiber_render[1:]
assert "switch_model: UCG Fiber" in fiber_text
assert "port_count: 5" in fiber_text
assert "sfp_port_count: 2" in fiber_text
assert "faceplate_file: unifi-8-rj45-2sfp.png" in fiber_text
assert "calibration_profile: unifi_8_rj45_2sfp" in fiber_text
assert "generic_faceplate: false" in fiber_text

agg = models["USW Pro Aggregation"]
assert agg["status"] == "experimental"
assert agg["dashboard_support"] is True
assert agg["ports"]["rj45"] == 0
assert agg["ports"]["ten_gigabit_sfp_plus"] == 28
assert agg["ports"]["twenty_five_gigabit_sfp28"] == 4
assert profiles["ubiquiti-usw-pro-aggregation-api"]["status"] == "experimental"
agg_ports = [
    *[
        {"idx": idx, "connector": "SFPPLUS", "max_speed_mbps": 10000}
        for idx in range(1, 29)
    ],
    *[
        {"idx": idx, "connector": "SFP28", "max_speed_mbps": 25000}
        for idx in range(29, 33)
    ],
]
agg_render = unifi.render(
    {
        "devices": [{
            "id": "agg-fixture",
            "name": "Aggregation fixture",
            "model": "USW Pro Aggregation",
            "ports": agg_ports,
        }]
    },
    registry,
)
assert agg_render[1] == 1, agg_render[1:]
assert "sfp_port_count: 32" in agg_render[0]
assert "faceplate_file: unifi-32sfp.png" in agg_render[0]
assert "generic_faceplate: false" in agg_render[0]

print("Switch Vision Discovery dashboard-first promotion contracts: PASS")
