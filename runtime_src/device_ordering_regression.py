#!/usr/bin/env python3
"""Regression for persistent deterministic configured-device ordering."""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

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
    before = web._configured_devices_snapshot(Path("/unused/options.json"))
    assert [item["switch_name"] for item in before["devices"]] == ["SW-A", "SW-B", "SW-C"], before

    moved = web._move_configured_device(Path("/unused/options.json"), {
        "index": 3,
        "switch_name": "SW-C",
        "destination_index": 2,
        "destination_switch_name": "SW-B",
    })
    assert [item["switch_name"] for item in moved["devices"]] == ["SW-A", "SW-C", "SW-B"], moved
    assert [str(item.get("switch_name") or "") for item in state["switches"]] == ["SW-A", "", "SW-C", "SW-B"], state
    assert backup_reasons == ["device_order_update"], backup_reasons

    # A normal enable/disable save must retain the persisted row order.
    after_state = web._set_configured_device_state(Path("/unused/options.json"), {
        "index": 2,
        "switch_name": "SW-C",
        "enabled": "disabled",
    })
    assert [item["switch_name"] for item in after_state["devices"]] == ["SW-A", "SW-C", "SW-B"], after_state

    effective = web._effective_discovery_options(read_options())
    assert [str(item.get("switch_name") or "") for item in effective["switches"]] == ["SW-A", "", "SW-C", "SW-B"], effective

    with tempfile.TemporaryDirectory(prefix="sv-ordering-") as tmp:
        root = Path(tmp)
        authoritative_path = web._write_authoritative_discovery_options_snapshot(
            root / "discovery.json",
            options=read_options(),
        )
        yaml_path = web._write_snmp2mqtt_regeneration_options_snapshot(root / "yaml.json")
        card_path = web._write_dashboard_card_regeneration_options_snapshot(root / "card.json")
        for path in (authoritative_path, yaml_path, card_path):
            saved = json.loads(path.read_text(encoding="utf-8"))
            assert [str(item.get("switch_name") or "") for item in saved["switches"]] == ["SW-A", "", "SW-C", "SW-B"], (path, saved)

    try:
        web._move_configured_device(Path("/unused/options.json"), {
            "index": 2,
            "switch_name": "STALE",
            "destination_index": 3,
            "destination_switch_name": "SW-B",
        })
    except ValueError as exc:
        assert "changed" in str(exc).lower(), exc
    else:
        raise AssertionError("stale source identity must fail closed")


    serialized = json.dumps(web._configured_devices_snapshot(Path("/unused/options.json")))
    assert "private-swa" not in serialized
    assert "private-swb" not in serialized
    assert "private-swc" not in serialized
finally:
    web._self_addon_options = original_options
    web._supervisor_json = original_supervisor
    web.create_pre_mutation_backup = original_backup

source = Path(web.__file__).read_text(encoding="utf-8")
for literal in (
    "/api/configured-devices/order",
    "Move up",
    "Move down",
    "_move_configured_device",
    "device_order_update",
):
    assert literal in source, literal

for forbidden in (
    "device-drag-handle",
    "draggedConfiguredDeviceName",
    "reorderConfiguredByDrag",
    "saveConfiguredDeviceOrder",
    "dragstart",
    "dragover",
):
    assert forbidden not in source, forbidden
assert "device-order-controls" in source
assert "summary.append(orderControls,main,actions)" in source

job = Path(web.__file__).with_name("discovery_job.sh").read_text(encoding="utf-8")
walk_fn = job.split("multi_switch_walk_rows() {", 1)[1].split("\n}\n", 1)[0]
assert '(.switches // .multi_switch_walks // [])[]?' in walk_fn, walk_fn[:1000]
assert "sort_by" not in walk_fn and "sort " not in walk_fn, walk_fn[:1000]

print("Switch Vision Discovery persistent device ordering regression: PASS")
