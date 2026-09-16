#!/usr/bin/env python3
"""Regression for unified SNMP/UniFi device state, order and dashboard projection."""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import dashboard_device_order
import discovery_backups
import support_web as web


def row(name: str, host: str, prefix: str) -> dict:
    return {
        "switch_name": name,
        "switch_host": host,
        "sensor_prefix": prefix,
        "snmp_community": f"private-{prefix}",
        "enabled": "enabled",
        "walk_mode": "targeted",
        "switch_model": "auto",
    }


assert "device_order_update" in discovery_backups._ALLOWED_REASONS

state = {
    "enable_switch_list": True,
    "switches": [
        row("SW-A", "192.0.2.10", "swa"),
        {"switch_name": "", "switch_host": "", "sensor_prefix": "", "snmp_community": "readonly"},
        row("SW-B", "192.0.2.20", "swb"),
        row("SW-C", "192.0.2.30", "swc"),
    ],
}
backup_reasons: list[str] = []
original_options = web._self_addon_options
original_supervisor = web._supervisor_json
original_backup = web.create_pre_mutation_backup
original_snapshot = web.DEFAULT_UNIFI_SNAPSHOT
original_control = web.DEFAULT_DEVICE_CONTROL


def read_options() -> dict:
    return copy.deepcopy(state)


def write_options(path: str, *, method: str = "GET", timeout: float = 0, payload=None):
    assert path == "/addons/self/options", path
    assert method == "POST", method
    assert isinstance(payload, dict) and isinstance(payload.get("options"), dict), payload
    state.clear()
    state.update(copy.deepcopy(payload["options"]))
    return {}


web._self_addon_options = read_options
web._supervisor_json = write_options
web.create_pre_mutation_backup = lambda options, *, reason: backup_reasons.append(reason)

try:
    with tempfile.TemporaryDirectory(prefix="sv-unified-device-order-") as tmp:
        root = Path(tmp)
        web.DEFAULT_DEVICE_CONTROL = root / "device-control.json"
        web.DEFAULT_UNIFI_SNAPSHOT = root / "unifi-devices.json"
        web.DEFAULT_UNIFI_SNAPSHOT.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "devices": [
                        {
                            "id": "u-flex",
                            "name": "USW Flex Mini",
                            "model": "USW Flex Mini",
                            "state": "ONLINE",
                            "ports": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        before = web._configured_devices_snapshot(Path("/unused/options.json"))
        assert [item["switch_name"] for item in before["devices"]] == ["SW-A", "SW-B", "SW-C"], before
        assert before["device_order"] == [
            "snmp:SW-A",
            "snmp:SW-B",
            "snmp:SW-C",
            "unifi:u-flex",
        ], before

        # A mixed move changes only the unified order. It must never force a
        # UniFi row into the authoritative SNMP switch list.
        mixed = web._move_configured_device(
            Path("/unused/options.json"),
            {"device_key": "unifi:u-flex", "destination_device_key": "snmp:SW-C"},
        )
        assert mixed["device_order"] == [
            "snmp:SW-A",
            "snmp:SW-B",
            "unifi:u-flex",
            "snmp:SW-C",
        ], mixed
        assert [str(item.get("switch_name") or "") for item in state["switches"]] == [
            "SW-A", "", "SW-B", "SW-C"
        ], state
        assert backup_reasons == [], backup_reasons

        # SNMP-to-SNMP reordering also preserves Discovery's own target order.
        moved = web._move_configured_device(
            Path("/unused/options.json"),
            {"device_key": "snmp:SW-C", "destination_device_key": "snmp:SW-B"},
        )
        assert [str(item.get("switch_name") or "") for item in state["switches"]] == [
            "SW-A", "", "SW-C", "SW-B"
        ], state
        assert backup_reasons == ["device_order_update"], backup_reasons
        assert moved["device_order"] == [
            "snmp:SW-A", "snmp:SW-C", "unifi:u-flex", "snmp:SW-B"
        ], moved

        # SNMP state remains authoritative in Supervisor and is mirrored into
        # the shared control state for one consistent Hub/dashboard contract.
        after_snmp_state = web._set_configured_device_state(
            Path("/unused/options.json"),
            {"device_key": "snmp:SW-C", "enabled": "disabled"},
        )
        assert next(
            item for item in after_snmp_state["devices"] if item["switch_name"] == "SW-C"
        )["enabled"] == "disabled"
        assert after_snmp_state["device_states"]["snmp:SW-C"] == "disabled"
        assert backup_reasons == ["device_order_update", "device_state_update"]

        # UniFi state is local operational state. It must not mutate the SNMP
        # switch list and is consumed by UniFi2MQTT to gate per-device polling.
        before_rows = copy.deepcopy(state["switches"])
        after_unifi_state = web._set_configured_device_state(
            Path("/unused/options.json"),
            {"device_key": "unifi:u-flex", "enabled": "disabled"},
        )
        assert state["switches"] == before_rows
        assert after_unifi_state["device_states"]["unifi:u-flex"] == "disabled"

        # Stored-state apply must regenerate both real live outputs without a
        # new SNMP walk so disabling an SNMP device changes polling immediately.
        apply_snapshot = web._write_device_state_application_options_snapshot(
            root / "apply.json"
        )
        apply_options = json.loads(apply_snapshot.read_text(encoding="utf-8"))
        assert apply_options["run_snmp_walks"] is False
        assert apply_options["run_live_snmpwalk"] is False
        assert apply_options["parse_all_walks"] is True
        assert apply_options["generate_snmp2mqtt"] is True
        assert apply_options["generated_yaml_path"] == str(web.DEFAULT_GENERATED_SNMP2MQTT)
        assert apply_options["generated_card_path"] == str(web.DEFAULT_GENERATED_CARD)

        # The dashboard projection uses the same mixed order and removes a
        # disabled standalone UniFi card while preserving the header/card text.
        dashboard = root / "dashboard.yaml"
        dashboard.write_text(
            """views:
  - title: Switch Vision
    cards:
      - type: markdown
        content: header
      - type: custom:switch-vision-3650
        title: A
        discovery_selected_switch: SW-A
      - type: custom:switch-vision-3650
        title: Flex
        unifi_device_id: u-flex
      - type: custom:switch-vision-3650
        title: B
        discovery_selected_switch: SW-B
      - type: custom:switch-vision-3650
        title: C
        discovery_selected_switch: SW-C
""",
            encoding="utf-8",
        )
        result = dashboard_device_order.apply_dashboard_order(
            dashboard, web.DEFAULT_DEVICE_CONTROL
        )
        assert result["disabled_cards_removed"] == 1, result
        text = dashboard.read_text(encoding="utf-8")
        assert "unifi_device_id: u-flex" not in text
        assert text.index("discovery_selected_switch: SW-A") < text.index(
            "discovery_selected_switch: SW-C"
        ) < text.index("discovery_selected_switch: SW-B"), text

        serialized = json.dumps(web._configured_devices_snapshot(Path("/unused/options.json")))
        assert "private-swa" not in serialized
        assert "private-swb" not in serialized
        assert "private-swc" not in serialized
finally:
    web._self_addon_options = original_options
    web._supervisor_json = original_supervisor
    web.create_pre_mutation_backup = original_backup
    web.DEFAULT_UNIFI_SNAPSHOT = original_snapshot
    web.DEFAULT_DEVICE_CONTROL = original_control

source = Path(web.__file__).read_text(encoding="utf-8")
for literal in (
    "/api/configured-devices/order",
    "device_order_update",
    "unifi:${item.unifi_device_id}",
    "device-state-toggle",
    "device-order-button",
    "_start_device_state_application",
    "apply_device_state",
    "dashboard_refresh_started",
    "polling_refresh_started",
):
    assert literal in source, literal

# All interactive device controls stop row-expansion propagation.
assert "event.preventDefault();event.stopPropagation()" in source
assert "item?.data_source==='UniFi API'&&item?.unifi_device_id" in source
assert "controllable:true" in source
assert "Toggle whether this device is actively polled" in source

job = Path(web.__file__).with_name("discovery_job.sh").read_text(encoding="utf-8")
assert "dashboard_device_order.py" in job
assert "device-control.json" in job
walk_fn = job.split("multi_switch_walk_rows() {", 1)[1].split("\n}\n", 1)[0]
assert '(.switches // .multi_switch_walks // [])[]?' in walk_fn, walk_fn[:1000]
assert "sort_by" not in walk_fn and "sort " not in walk_fn, walk_fn[:1000]

print("Switch Vision Discovery unified device control/order regression: PASS")
