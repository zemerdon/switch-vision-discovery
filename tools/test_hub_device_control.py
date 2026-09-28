#!/usr/bin/env python3
"""Permanent contracts for extracted Hub device-control orchestration."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import hub_device_control


def plain_text(value, field, *, max_length, allow_empty=True):
    text = str(value if value is not None else "")
    if len(text) > max_length:
        raise ValueError(f"{field} is too long.")
    if not allow_empty and not text:
        raise ValueError(f"{field} cannot be empty.")
    return text


def switch_enabled(value, field):
    text = str(value or "").strip().lower()
    if text not in {"enabled", "disabled"}:
        raise ValueError(f"{field} is invalid.")
    return text


def effective_row(raw, _index):
    row = dict(raw)
    if row.get("conflict"):
        raise ValueError("conflict")
    return row


def defaults(options):
    return dict(options)


def validate_inventory(_options):
    return None


def main() -> int:
    source = (RUNTIME / "hub_device_control.py").read_text(encoding="utf-8")
    assert re.search(r"(?m)^\s*import\s+support_web\b", source) is None
    assert re.search(r"(?m)^\s*from\s+support_web\b", source) is None

    with tempfile.TemporaryDirectory(prefix="sv-hub-device-control-") as tmp:
        root = Path(tmp)
        control = root / "device-control.json"
        unifi = root / "unifi.json"
        unifi.write_text(
            json.dumps({"devices": [{"id": "u1", "name": "UniFi"}]}),
            encoding="utf-8",
        )
        state = {
            "enable_switch_list": True,
            "switches": [
                {
                    "switch_name": "SW1",
                    "display_name": "Lab",
                    "switch_host": "192.0.2.10",
                    "sensor_prefix": "sw1",
                    "snmp_community": "private-community",
                    "enabled": "enabled",
                },
                {
                    "switch_name": "SW2",
                    "display_name": "Lab 2",
                    "switch_host": "192.0.2.20",
                    "sensor_prefix": "sw2",
                    "snmp_community": "private-community-2",
                    "enabled": "enabled",
                },
            ],
        }
        backups = []
        posts = []

        def self_options():
            return copy.deepcopy(state)

        def supervisor(path, *, method="GET", timeout=12.0, payload=None):
            assert path == "/addons/self/options"
            assert method == "POST"
            posts.append(copy.deepcopy(payload))
            state.clear()
            state.update(copy.deepcopy(payload["options"]))
            return {}

        runtime = hub_device_control.HubDeviceControlRuntime(
            self_addon_options=self_options,
            load_options=lambda _path: copy.deepcopy(state),
            read_json=lambda path: json.loads(Path(path).read_text(encoding="utf-8")),
            safe_bool=lambda value, default: bool(value) if value is not None else default,
            switch_enabled_state=switch_enabled,
            effective_discovery_switch_row=effective_row,
            plain_text=plain_text,
            discovery_options_with_required_defaults=defaults,
            validate_inventory_identities=validate_inventory,
            create_pre_mutation_backup=lambda _options, *, reason: backups.append(reason),
            supervisor_json=supervisor,
            options_update_lock=threading.RLock(),
            unifi_snapshot=unifi,
            device_control_path=control,
        )

        keys = hub_device_control.current_unified_device_keys(state, runtime=runtime)
        assert keys == ["snmp:SW1", "snmp:SW2", "unifi:u1"], keys

        snapshot = hub_device_control.configured_devices_snapshot(
            root / "fallback.json", runtime=runtime
        )
        encoded = json.dumps(snapshot, sort_keys=True)
        assert snapshot["count"] == 2
        assert snapshot["device_order"] == keys
        assert "private-community" not in encoded

        after = hub_device_control.set_configured_device_state(
            root / "fallback.json",
            {"device_key": "snmp:SW1", "enabled": "disabled"},
            runtime=runtime,
        )
        assert state["switches"][0]["enabled"] == "disabled"
        assert after["device_states"]["snmp:SW1"] == "disabled"
        assert backups == ["device_state_update"]
        assert posts

        before_rows = copy.deepcopy(state["switches"])
        after_unifi = hub_device_control.set_configured_device_state(
            root / "fallback.json",
            {"device_key": "unifi:u1", "enabled": "disabled"},
            runtime=runtime,
        )
        assert state["switches"] == before_rows
        assert after_unifi["device_states"]["unifi:u1"] == "disabled"

        moved = hub_device_control.move_configured_device(
            root / "fallback.json",
            {
                "device_key": "unifi:u1",
                "destination_device_key": "snmp:SW1",
            },
            runtime=runtime,
        )
        assert moved["device_order"] == ["unifi:u1", "snmp:SW1", "snmp:SW2"]
        assert state["switches"] == before_rows

    print("Switch Vision Hub device-control module contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
