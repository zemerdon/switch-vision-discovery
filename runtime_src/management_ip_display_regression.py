#!/usr/bin/env python3
"""Regression for configured/effective Discovery management target display."""
from __future__ import annotations

import json
from pathlib import Path

import support_web as web


def snapshot(options: dict) -> dict:
    original = web._self_addon_options
    web._self_addon_options = lambda: options
    try:
        return web._configured_devices_snapshot(Path("/definitely-not-used/options.json"))
    finally:
        web._self_addon_options = original


canonical_secret = "canonical-private-community"
canonical = snapshot({
    "enable_switch_list": True,
    "switches": [{
        "switch_name": "SW1",
        "switch_host": "192.0.2.10",
        "sensor_prefix": "sw1",
        "snmp_community": canonical_secret,
        "enabled": "enabled",
        "walk_mode": "targeted",
        "switch_model": "auto",
    }],
})
assert canonical["count"] == 1, canonical
item = canonical["devices"][0]
assert item["switch_host"] == "192.0.2.10", item
assert item["configured_management_target"] == "192.0.2.10", item
assert item["configured_management_source"] == "switch_host", item
assert item["effective_management_target"] == "192.0.2.10", item
assert item["effective_management_status"] == "ready", item
assert canonical_secret not in json.dumps(canonical), canonical

legacy_secret = "legacy-private-community"
legacy = snapshot({
    "enable_switch_list": True,
    "switches": [{
        "switch_name": "SW2",
        "host": "198.51.100.20",
        "sensor_prefix": "sw2",
        "community": legacy_secret,
        "enabled": "enabled",
    }],
})
assert legacy["count"] == 1, legacy
item = legacy["devices"][0]
assert item["switch_host"] == "", item
assert item["configured_management_target"] == "198.51.100.20", item
assert item["configured_management_source"] == "host", item
assert item["effective_management_target"] == "198.51.100.20", item
assert item["effective_management_status"] == "ready", item
assert legacy_secret not in json.dumps(legacy), legacy

conflict_secret = "conflict-private-community"
conflict = snapshot({
    "enable_switch_list": True,
    "switches": [{
        "switch_name": "SW3",
        "switch_host": "203.0.113.30",
        "host": "203.0.113.31",
        "sensor_prefix": "sw3",
        "snmp_community": conflict_secret,
        "enabled": "enabled",
    }],
})
assert conflict["count"] == 1, conflict
item = conflict["devices"][0]
assert item["configured_management_target"] == "203.0.113.30", item
assert item["configured_management_source"] == "switch_host", item
assert item["effective_management_target"] == "", item
assert item["effective_management_status"] == "invalid_saved_row", item
assert conflict_secret not in json.dumps(conflict), conflict

source = Path(web.__file__).read_text(encoding="utf-8")
for literal in (
    "configured_management_target",
    "configured_management_source",
    "effective_management_target",
    "effective_management_status",
    "Configured management IP/host:",
    "Effective management IP/host:",
):
    assert literal in source, literal

print("Switch Vision Discovery configured/effective management target regression: PASS")
