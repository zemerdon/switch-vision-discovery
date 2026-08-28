#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "runtime_src/profiles/switch-vision-profiles.yaml"
REGISTRY = ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_profiles() -> None:
    text = PROFILES.read_text(encoding="utf-8")
    old_2960x = '''  cisco-2960x-48fpd-48p-2x10g:\n    status: experimental\n    vendor: Cisco\n    family: Catalyst 2960X\n    model_patterns:\n    - WS-C2960X-48FPD-L\n    layout:\n      members: auto\n      rj45_ports: 48\n      sfp_1g_ports: 2\n      sfp_10g_ports: 2\n    interface_patterns:\n      rj45:\n      - Gi{member}/0/{port}\n      - GigabitEthernet{member}/0/{port}\n      sfp_1g:\n      - Gi{member}/0/{port}\n      - GigabitEthernet{member}/0/{port}\n      sfp_10g:\n      - Te{member}/0/{port}\n      - TenGigabitEthernet{member}/0/{port}\n'''
    new_2960x = '''  cisco-2960x-48fpd-48p-2x10g:\n    status: experimental\n    vendor: Cisco\n    family: Catalyst 2960X\n    model_patterns:\n    - WS-C2960X-48FPD-L\n    layout:\n      members: auto\n      rj45_ports: 48\n      sfp_1g_ports: 0\n      sfp_10g_ports: 2\n    interface_patterns:\n      rj45:\n      - Gi{member}/0/{port}\n      - GigabitEthernet{member}/0/{port}\n      sfp_1g: []\n      sfp_10g:\n      - Te{member}/0/{port}\n      - TenGigabitEthernet{member}/0/{port}\n    notes:\n    - Exact WS-C2960X-48FPD-L physical contract is 48 copper ports plus two 10G SFP+ uplinks.\n    - Do not treat Gi{member}/0/* access-port aliases as separate 1G SFP cages.\n'''
    old_2960s = '''  cisco-2960s-48fpd-48p-2x10g:\n    status: experimental\n    vendor: Cisco\n    family: Catalyst 2960S\n    model_patterns:\n    - WS-C2960S-48FPD-L\n    layout:\n      members: auto\n      rj45_ports: 48\n      sfp_1g_ports: 2\n      sfp_10g_ports: 2\n    interface_patterns:\n      rj45:\n      - Gi{member}/0/{port}\n      - GigabitEthernet{member}/0/{port}\n      sfp_1g:\n      - Gi{member}/0/{port}\n      - GigabitEthernet{member}/0/{port}\n      sfp_10g:\n      - Te{member}/0/{port}\n      - TenGigabitEthernet{member}/0/{port}\n'''
    new_2960s = '''  cisco-2960s-48fpd-48p-2x10g:\n    status: experimental\n    vendor: Cisco\n    family: Catalyst 2960S\n    model_patterns:\n    - WS-C2960S-48FPD-L\n    layout:\n      members: auto\n      rj45_ports: 48\n      sfp_1g_ports: 0\n      sfp_10g_ports: 2\n    interface_patterns:\n      rj45:\n      - Gi{member}/0/{port}\n      - GigabitEthernet{member}/0/{port}\n      sfp_1g: []\n      sfp_10g:\n      - Te{member}/0/{port}\n      - TenGigabitEthernet{member}/0/{port}\n    notes:\n    - Exact WS-C2960S-48FPD-L physical contract is 48 copper ports plus two 10G SFP+ uplinks.\n    - Do not treat Gi{member}/0/* access-port aliases as separate 1G SFP cages.\n'''
    text = replace_once(text, old_2960x, new_2960x, "2960X profile")
    text = replace_once(text, old_2960s, new_2960s, "2960S profile")
    PROFILES.write_text(text, encoding="utf-8")


def patch_registry() -> None:
    text = REGISTRY.read_text(encoding="utf-8")
    old = '''      "ports": {\n        "rj45": 48,\n        "poe": true,\n        "uplinks": 4,\n        "uplink_type": "SFP/SFP+",\n        "gigabit_sfp": 4,\n        "ten_gigabit_sfp_plus": 4\n      },\n      "stack_support": false,\n      "discovery_support": true,\n      "dashboard_support": true,\n      "mapping_profile": "juniper-ex3300-48p",\n'''
    new = '''      "ports": {\n        "rj45": 48,\n        "poe": true,\n        "uplinks": 4,\n        "uplink_type": "4 dual-speed 1G/10G SFP+ cages",\n        "gigabit_sfp": 0,\n        "ten_gigabit_sfp_plus": 4\n      },\n      "stack_support": false,\n      "discovery_support": true,\n      "dashboard_support": true,\n      "mapping_profile": "juniper-ex3300-48p",\n'''
    text = replace_once(text, old, new, "EX3300 registry ports")
    old_note = '''        "Physical SFP/SFP+ uplink link state, activity, and 64-bit traffic counters validated on real hardware.",\n'''
    new_note = '''        "Physical SFP/SFP+ uplink link state, activity, and 64-bit traffic counters validated on real hardware.",\n        "The four physical uplink cages are dual-speed: ge-0/1/N and xe-0/1/N are alternate identities for the same four cages and are not additive physical ports.",\n'''
    # Scope note replacement to a unique exact occurrence in the EX3300 entry.
    before, marker, after = text.partition('"model": "EX3300-48P"')
    if not marker:
        raise SystemExit("EX3300 registry model entry not found")
    after = replace_once(after, old_note, new_note, "EX3300 alias note")
    REGISTRY.write_text(before + marker + after, encoding="utf-8")


if __name__ == "__main__":
    patch_profiles()
    patch_registry()
