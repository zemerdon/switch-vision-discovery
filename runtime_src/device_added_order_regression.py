#!/usr/bin/env python3
"""Regression for immutable first-added metadata and Reset Order."""
from __future__ import annotations

import copy
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import device_control
import discovery_backups
import support_web as web

assert "device_order_reset" in discovery_backups._ALLOWED_REASONS

start = datetime(2026, 9, 17, 3, 0, 0, tzinfo=timezone.utc)
legacy = {
    "schema_version": 1,
    "order": ["snmp:SW-C", "snmp:SW-A", "snmp:SW-B", "unifi:u-flex"],
    "states": {},
}
seeded, changed = device_control.reconcile_added_at(
    legacy,
    ["snmp:SW-A", "snmp:SW-B", "snmp:SW-C", "unifi:u-flex"],
    now=start,
)
assert changed is True
assert device_control.added_order(
    ["snmp:SW-A", "snmp:SW-B", "snmp:SW-C", "unifi:u-flex"], seeded
) == ["snmp:SW-C", "snmp:SW-A", "snmp:SW-B", "unifi:u-flex"]
original_dates = copy.deepcopy(seeded["added_at"])

# Manual order changes never alter first-added metadata.
moved = device_control.move(
    seeded,
    ["snmp:SW-A", "snmp:SW-B", "snmp:SW-C", "unifi:u-flex"],
    "snmp:SW-B",
    "snmp:SW-C",
)
assert moved["added_at"] == original_dates
reset = device_control.reset_order(
    moved,
    ["snmp:SW-A", "snmp:SW-B", "snmp:SW-C", "unifi:u-flex"],
)
assert reset["order"] == ["snmp:SW-C", "snmp:SW-A", "snmp:SW-B", "unifi:u-flex"]
assert reset["added_at"] == original_dates

# A newly observed device is appended chronologically; existing dates remain immutable.
later, later_changed = device_control.reconcile_added_at(
    reset,
    ["snmp:SW-A", "snmp:SW-B", "snmp:SW-C", "unifi:u-flex", "snmp:SW-D"],
    now=start + timedelta(hours=1),
)
assert later_changed is True
assert {k: later["added_at"][k] for k in original_dates} == original_dates
assert device_control.added_order(
    ["snmp:SW-D", "unifi:u-flex", "snmp:SW-C", "snmp:SW-A", "snmp:SW-B"], later
)[-1] == "snmp:SW-D"


def row(name: str, host: str) -> dict:
    return {
        "switch_name": name,
        "switch_host": host,
        "sensor_prefix": name.lower().replace("-", ""),
        "snmp_community": "fixture-community",
        "enabled": "enabled",
        "walk_mode": "targeted",
        "switch_model": "auto",
    }

state = {"enable_switch_list": True, "switches": [row("SW-C", "192.0.2.30"), row("SW-A", "192.0.2.10"), row("SW-B", "192.0.2.20")]}
backup_reasons: list[str] = []
original_options = web._self_addon_options
original_supervisor = web._supervisor_json
original_backup = web.create_pre_mutation_backup
original_control = web.DEFAULT_DEVICE_CONTROL
original_unifi = web.DEFAULT_UNIFI_SNAPSHOT

try:
    with tempfile.TemporaryDirectory(prefix="sv-added-order-") as tmp:
        root = Path(tmp)
        web.DEFAULT_DEVICE_CONTROL = root / "device-control.json"
        web.DEFAULT_UNIFI_SNAPSHOT = root / "unifi.json"
        web.DEFAULT_UNIFI_SNAPSHOT.write_text(json.dumps({"schema_version": 1, "devices": []}), encoding="utf-8")

        baseline = {
            "schema_version": 2,
            "order": ["snmp:SW-C", "snmp:SW-A", "snmp:SW-B"],
            "states": {},
            "added_at": {
                "snmp:SW-A": "2026-09-17T00:00:00.000000Z",
                "snmp:SW-B": "2026-09-17T00:00:01.000000Z",
                "snmp:SW-C": "2026-09-17T00:00:02.000000Z",
            },
        }
        device_control.save(baseline, web.DEFAULT_DEVICE_CONTROL)

        web._self_addon_options = lambda: copy.deepcopy(state)
        def supervisor(path: str, *, method: str = "GET", timeout: float = 0, payload=None):
            assert path == "/addons/self/options"
            assert method == "POST"
            state.clear(); state.update(copy.deepcopy(payload["options"]))
            return {}
        web._supervisor_json = supervisor
        web.create_pre_mutation_backup = lambda _options, *, reason: backup_reasons.append(reason)

        result = web._reset_configured_device_order(Path("/unused"))
        assert [r["switch_name"] for r in state["switches"]] == ["SW-A", "SW-B", "SW-C"], state
        assert result["device_order"] == ["snmp:SW-A", "snmp:SW-B", "snmp:SW-C"], result
        assert backup_reasons == ["device_order_reset"], backup_reasons
        stored = device_control.load(web.DEFAULT_DEVICE_CONTROL)
        assert stored["added_at"] == baseline["added_at"]
finally:
    web._self_addon_options = original_options
    web._supervisor_json = original_supervisor
    web.create_pre_mutation_backup = original_backup
    web.DEFAULT_DEVICE_CONTROL = original_control
    web.DEFAULT_UNIFI_SNAPSHOT = original_unifi

source = Path(web.__file__).read_text(encoding="utf-8")
for marker in (
    'id="resetDeviceOrderButton"',
    '/api/configured-devices/reset-order',
    '_reset_configured_device_order',
    'Restore the device list and Native dashboard to immutable first-added order.',
    'reconcile_added_at',
    'reset_order',
):
    assert marker in source, marker

print("Switch Vision immutable device added-order regression: PASS")
