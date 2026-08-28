#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"
PROFILES = ROOT / "runtime_src/profiles/switch-vision-profiles.yaml"

PROFILE_TEXT = r'''
  dell-powerconnect-5548p-48p-2x10g:
    status: experimental
    vendor: Dell
    family: PowerConnect 5500
    model_patterns:
    - PowerConnect 5548P
    layout:
      members: 1
      rj45_ports: 48
      sfp_1g_ports: 0
      sfp_10g_ports: 2
    interface_patterns:
      rj45:
      - gi1/0/{port}
      sfp_1g: []
      sfp_10g:
      - te1/0/{port}
    notes:
    - Exact lowercase Gi/Te mapping derived from anonymous real-hardware evidence.
  cisco-3750x-48p-c3kx:
    status: experimental
    vendor: Cisco
    family: Catalyst 3750X
    model_patterns:
    - WS-C3750X-48P
    layout:
      members: auto
      rj45_ports: 48
      sfp_1g_ports: 2
      sfp_10g_ports: 2
    interface_patterns:
      rj45:
      - Gi{member}/0/{port}
      - GigabitEthernet{member}/0/{port}
      sfp_1g:
      - Gi{member}/1/3
      - Gi{member}/1/4
      - GigabitEthernet{member}/1/3
      - GigabitEthernet{member}/1/4
      sfp_10g:
      - Te{member}/1/1
      - Te{member}/1/2
      - TenGigabitEthernet{member}/1/1
      - TenGigabitEthernet{member}/1/2
    notes:
    - Gi network-module aliases for cages also exposed as Te are excluded by the exact-model classifier to prevent duplicate physical ports.
  ubiquiti-usw-pro-hd-24-poe-snmp:
    status: experimental
    vendor: Ubiquiti
    family: UniFi Switch Pro HD
    model_patterns:
    - USW Pro HD 24 PoE
    - USWProHD24PoE
    layout:
      members: 1
      rj45_ports: 24
      sfp_1g_ports: 0
      sfp_10g_ports: 4
    interface_patterns:
      rj45:
      - 0/{port}
      sfp_1g: []
      sfp_10g:
      - 0/25
      - 0/26
      - 0/27
      - 0/28
  ubiquiti-usw-aggregation-api:
    status: experimental
    vendor: Ubiquiti
    family: UniFi Switch Aggregation
    model_patterns:
    - USW Aggregation
    layout:
      members: 1
      rj45_ports: 0
      sfp_1g_ports: 0
      sfp_10g_ports: 8
    interface_patterns:
      rj45: []
      sfp_1g: []
      sfp_10g:
      - api-port-1
      - api-port-2
      - api-port-3
      - api-port-4
      - api-port-5
      - api-port-6
      - api-port-7
      - api-port-8
  ubiquiti-usw-enterprise-24-poe-api:
    status: experimental
    vendor: Ubiquiti
    family: UniFi Switch Enterprise
    model_patterns:
    - USW Enterprise 24 PoE
    layout:
      members: 1
      rj45_ports: 24
      sfp_1g_ports: 0
      sfp_10g_ports: 2
    interface_patterns:
      rj45:
      - api-port-{port}
      sfp_1g: []
      sfp_10g:
      - api-port-25
      - api-port-26
    notes:
    - API ports 1-12 are 1G-capable RJ45 and ports 13-24 are 2.5G-capable RJ45.
  ubiquiti-usw-flex-2p5g-5-api:
    status: experimental
    vendor: Ubiquiti
    family: UniFi Switch Flex
    model_patterns:
    - USW Flex 2.5G 5
    layout:
      members: 1
      rj45_ports: 5
      sfp_1g_ports: 0
      sfp_10g_ports: 0
    interface_patterns:
      rj45:
      - api-port-{port}
      sfp_1g: []
      sfp_10g: []
    notes:
    - All five API ports are 2.5G-capable RJ45 positions.
  ubiquiti-usw-wan-api:
    status: experimental
    vendor: Ubiquiti
    family: UniFi WAN Switch
    model_patterns:
    - USW WAN
    layout:
      members: 1
      rj45_ports: 1
      sfp_1g_ports: 0
      sfp_10g_ports: 3
    interface_patterns:
      rj45:
      - api-port-4
      sfp_1g: []
      sfp_10g:
      - api-port-1
      - api-port-2
      - api-port-3
'''


def main() -> None:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    by_model = {
        str(item.get("model") or ""): item
        for item in data.get("devices", [])
        if isinstance(item, dict)
    }

    # These exact models are intentionally handled by the vendor/interface layer,
    # because the current profile schema cannot faithfully express their neutral
    # or dual-personality front-panel semantics.
    for model in ("GS1900-24E", "SG350-20", "HP J8693A Switch 3500yl-48G"):
        by_model[model]["mapping_profile"] = ""

    # Existing Core-shared entries must retain their support-status contract.
    enterprise8 = by_model["USW-Enterprise-8-PoE"]
    enterprise8["evidence"] = "support_my_switch_contribution_community validation_multiple_devices; unifi2mqtt_live_snapshot_2026-08-11"

    xg8 = by_model["USW Pro XG 8 PoE"]
    xg8["evidence"] = "unifi_integration_api_samples_2026-08-10; unifi2mqtt_live_snapshot_2026-08-11"
    xg8["validation"] = {
        "exact_model_detection": "api_confirmed",
        "rj45_mapping": "api_confirmed_port_indices",
        "poe": "api_confirmed_metadata",
        "system_sensors": "api_confirmed_cpu_memory",
        "uplinks": "api_confirmed_connector_and_speed",
        "stack": "not_applicable",
    }

    flexmini = by_model["USW Flex Mini"]
    flexmini["evidence"] = "support_my_switch_community validation_unifi_api"

    REGISTRY.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    text = PROFILES.read_text(encoding="utf-8")
    first_key = "  dell-powerconnect-5548p-48p-2x10g:"
    if first_key not in text:
        if not text.endswith("\n"):
            text += "\n"
        text += PROFILE_TEXT.lstrip("\n")
        PROFILES.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
