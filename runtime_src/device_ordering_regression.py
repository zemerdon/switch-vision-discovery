#!/usr/bin/env python3
"""Regression for unified SNMP/UniFi device state, order and dashboard projection."""
from __future__ import annotations

import copy
import json
import tempfile
import threading
import time
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
original_card = web.DEFAULT_GENERATED_CARD
original_card_full = web.DEFAULT_GENERATED_CARD_FULL


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
        web.DEFAULT_GENERATED_CARD = dashboard
        web.DEFAULT_GENERATED_CARD_FULL = root / "dashboard-full.yaml"
        result = web._apply_saved_device_order_to_dashboard()
        assert result["updated"] is True, result
        assert result["full_source_seeded"] is True, result
        assert result["disabled_cards_removed"] == 2, result
        text = dashboard.read_text(encoding="utf-8")
        full_text = web.DEFAULT_GENERATED_CARD_FULL.read_text(encoding="utf-8")
        assert "unifi_device_id: u-flex" not in text
        assert "discovery_selected_switch: SW-C" not in text
        assert "unifi_device_id: u-flex" in full_text
        assert "discovery_selected_switch: SW-C" in full_text
        assert text.index("discovery_selected_switch: SW-A") < text.index(
            "discovery_selected_switch: SW-B"
        ), text

        # Re-enable both sources without regenerating cards. Projection must
        # restore the exact retained cards from the private full source.
        web._set_configured_device_state(
            Path("/unused/options.json"),
            {"device_key": "snmp:SW-C", "enabled": "enabled"},
        )
        web._set_configured_device_state(
            Path("/unused/options.json"),
            {"device_key": "unifi:u-flex", "enabled": "enabled"},
        )
        restored = web._apply_saved_device_order_to_dashboard()
        assert restored["disabled_cards_removed"] == 0, restored
        restored_text = dashboard.read_text(encoding="utf-8")
        assert "unifi_device_id: u-flex" in restored_text
        assert "discovery_selected_switch: SW-C" in restored_text
        assert restored_text.index("discovery_selected_switch: SW-A") < restored_text.index(
            "discovery_selected_switch: SW-C"
        ) < restored_text.index("unifi_device_id: u-flex") < restored_text.index(
            "discovery_selected_switch: SW-B"
        ), restored_text
        assert web.DEFAULT_GENERATED_CARD_FULL.read_text(encoding="utf-8") == full_text

        # Fresh generation may omit a disabled SNMP row. Retain its old exact
        # card, but do not retain stale enabled SNMP or stale UniFi cards that
        # disappeared from the fresh authoritative source.
        merge_full = root / "merge-full.yaml"
        merge_full.write_text(
            """views:
  - title: Switch Vision
    cards:
      - type: markdown
        content: header
      - type: custom:switch-vision-3650
        title: Keep disabled
        discovery_selected_switch: SW-DISABLED
      - type: custom:switch-vision-3650
        title: Drop enabled stale
        discovery_selected_switch: SW-STALE
      - type: custom:switch-vision-3650
        title: Drop stale UniFi
        unifi_device_id: stale-u
""",
            encoding="utf-8",
        )
        fresh = root / "fresh.yaml"
        fresh.write_text(
            """views:
  - title: Switch Vision
    cards:
      - type: markdown
        content: header
      - type: custom:switch-vision-3650
        title: Fresh
        discovery_selected_switch: SW-FRESH
""",
            encoding="utf-8",
        )
        merge = dashboard_device_order.refresh_full_dashboard_source(
            fresh,
            merge_full,
            snmp_states={
                "snmp:SW-DISABLED": False,
                "snmp:SW-STALE": True,
                "snmp:SW-FRESH": True,
            },
        )
        merged_text = merge_full.read_text(encoding="utf-8")
        assert merge["retained_disabled_snmp_keys"] == 1, merge
        assert "SW-DISABLED" in merged_text
        assert "SW-FRESH" in merged_text
        assert "SW-STALE" not in merged_text
        assert "stale-u" not in merged_text

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
    web.DEFAULT_GENERATED_CARD = original_card
    web.DEFAULT_GENERATED_CARD_FULL = original_card_full

source = Path(web.__file__).read_text(encoding="utf-8")
for literal in (
    "/api/configured-devices/order",
    "device_order_update",
    "unifi:${item.unifi_device_id}",
    "device-state-toggle",
    "device-order-button",
    "_start_device_state_application",
    "_device_state_application_worker",
    "_device_configuration_update",
    "polling_refresh_coalesced",
    "apply_device_state",
    "dashboard_refresh_started",
    "_apply_saved_device_order_to_dashboard",
    "polling_refresh_started",
    "deviceControlsBlocked",
    "lastDiscoveryState?.mode!=='apply_device_state'",
):
    assert literal in source, literal

# All interactive device controls stop row-expansion propagation.
assert "event.preventDefault();event.stopPropagation()" in source
assert "item?.data_source==='UniFi API'&&item?.unifi_device_id" in source
assert "controllable:true" in source
assert "Toggle whether this device is actively polled" in source


# Reorder must apply directly to the existing dashboard source and must not start
# a Discovery/card-regeneration operation that disables subsequent row actions.
state_handler = source.split('if path == "/api/configured-devices/state":', 1)[1].split('if path == "/api/configured-devices/order":', 1)[0]
assert "_apply_saved_device_order_to_dashboard()" in state_handler
assert "_start_dashboard_card_regeneration" not in state_handler
assert "_start_device_state_application(self.app.discovery_script)" in state_handler
assert web.DEFAULT_DISCOVERY_SCRIPT == Path("/discovery_contract_entrypoint.py")
assert 'with _device_configuration_update("Device configuration update"):' in state_handler

order_handler = source.split('if path == "/api/configured-devices/order":', 1)[1].split('if path == "/api/configuration/import":', 1)[0]
assert "_apply_saved_device_order_to_dashboard()" in order_handler
assert "_start_dashboard_card_regeneration" not in order_handler
assert 'with _device_configuration_update("Device order update"):' in order_handler

# Device mutations remain available while the background SNMP state reconciler
# owns the long-running operation, but remain blocked by a real Discovery run.
with web._OPERATION_LOCK:
    web._OPERATION_ACTIVE["name"] = "Device state application"
    web._OPERATION_ACTIVE["started_at"] = "test"
with web._device_configuration_update("Device configuration update"):
    pass
with web._OPERATION_LOCK:
    web._OPERATION_ACTIVE["name"] = "Discovery"
    web._OPERATION_ACTIVE["started_at"] = "test"
try:
    with web._device_configuration_update("Device configuration update"):
        raise AssertionError("Discovery must block device mutation")
except web.OperationConflict:
    pass
finally:
    with web._OPERATION_LOCK:
        web._OPERATION_ACTIVE["name"] = None
        web._OPERATION_ACTIVE["started_at"] = None

# Changes made during an in-flight state pass are coalesced into one latest-state
# rerun rather than rejected or run concurrently. The real worker's per-pass
# _run_discovery releases the operation; the fake mirrors that lifecycle.
original_run = web._run_discovery
original_projection = web._apply_saved_device_order_to_dashboard
original_history = web.append_discovery_history
original_debounce = web._DEVICE_STATE_RECONCILE_DEBOUNCE_SECONDS
original_retry = web._DEVICE_STATE_RECONCILE_RETRY_SECONDS
started = threading.Event()
release_first = threading.Event()
passes: list[str] = []
projections: list[int] = []
history_rows: list[dict] = []
try:
    web._DEVICE_STATE_RECONCILE_DEBOUNCE_SECONDS = 0.01
    web._DEVICE_STATE_RECONCILE_RETRY_SECONDS = 0.005
    web._DEVICE_STATE_RECONCILE_REQUESTED = 0
    web._DEVICE_STATE_RECONCILE_RUNNING = False
    web._release_operation("Device state application")

    def fake_run(_script: Path, mode: str = "discovery") -> None:
        passes.append(mode)
        if len(passes) == 1:
            started.set()
            assert release_first.wait(2.0), "timed out waiting to queue a second state change"
        web._release_operation("Device state application")

    def fake_projection() -> dict[str, bool]:
        projections.append(len(passes))
        return {"updated": True}

    web._run_discovery = fake_run
    web._apply_saved_device_order_to_dashboard = fake_projection
    web.append_discovery_history = lambda snapshot: history_rows.append(copy.deepcopy(snapshot)) or {}
    first = web._start_device_state_application(Path("/tmp/fake-discovery-job.sh"))
    assert first["started"] is True and first["coalesced"] is False, first
    assert started.wait(2.0), "first coalesced state pass did not start"
    second = web._start_device_state_application(Path("/tmp/fake-discovery-job.sh"))
    assert second["started"] is False and second["coalesced"] is True, second
    assert second["generation"] == first["generation"] + 1, (first, second)
    release_first.set()
    deadline = time.monotonic() + 3.0
    while web._DEVICE_STATE_RECONCILE_RUNNING and time.monotonic() < deadline:
        time.sleep(0.01)
    assert web._DEVICE_STATE_RECONCILE_RUNNING is False, "state reconciler did not quiesce"
    assert passes == ["apply_device_state", "apply_device_state"], passes
    assert len(projections) == 2, projections
    assert len(history_rows) == 1, history_rows
finally:
    release_first.set()
    web._run_discovery = original_run
    web._apply_saved_device_order_to_dashboard = original_projection
    web.append_discovery_history = original_history
    web._DEVICE_STATE_RECONCILE_DEBOUNCE_SECONDS = original_debounce
    web._DEVICE_STATE_RECONCILE_RETRY_SECONDS = original_retry
    web._release_operation("Device state application")
    web._DEVICE_STATE_RECONCILE_RUNNING = False

# A required final dashboard projection failure must not be swallowed as a
# successful device-state application. The worker must quiesce with an explicit
# failed state so the Hub cannot claim the visible dashboard is current.
original_run = web._run_discovery
original_projection = web._apply_saved_device_order_to_dashboard
original_history = web.append_discovery_history
original_debounce = web._DEVICE_STATE_RECONCILE_DEBOUNCE_SECONDS
failure_history_rows: list[dict] = []
try:
    web._DEVICE_STATE_RECONCILE_DEBOUNCE_SECONDS = 0.01
    web._DEVICE_STATE_RECONCILE_REQUESTED = 0
    web._DEVICE_STATE_RECONCILE_RUNNING = False
    web._release_operation("Device state application")

    def successful_state_apply(_script: Path, mode: str = "discovery") -> None:
        assert mode == "apply_device_state", mode
        web._set_discovery_state(
            success=True,
            message="Device state applied",
            stage="Complete",
            activity="Device state applied",
            phase="complete",
        )
        web._release_operation("Device state application")

    def failed_projection() -> dict[str, bool]:
        raise RuntimeError("injected dashboard projection failure")

    web._run_discovery = successful_state_apply
    web._apply_saved_device_order_to_dashboard = failed_projection
    web.append_discovery_history = lambda snapshot: failure_history_rows.append(copy.deepcopy(snapshot)) or {}
    started = web._start_device_state_application(Path("/tmp/fake-discovery-job.sh"))
    assert started["started"] is True and started["coalesced"] is False, started
    deadline = time.monotonic() + 3.0
    while web._DEVICE_STATE_RECONCILE_RUNNING and time.monotonic() < deadline:
        time.sleep(0.01)
    assert web._DEVICE_STATE_RECONCILE_RUNNING is False, "failed projection worker did not quiesce"
    failed_state = web._discovery_state_snapshot()
    assert failed_state["success"] is False, failed_state
    assert failed_state["phase"] == "failed", failed_state
    assert failed_state["stage"] == "Dashboard refresh failed", failed_state
    assert "dashboard refresh failed" in str(failed_state["message"]).casefold(), failed_state
    assert "injected dashboard projection failure" in str(failed_state["message"]), failed_state
    assert len(failure_history_rows) == 1, failure_history_rows
    assert failure_history_rows[0]["success"] is False, failure_history_rows
    assert failure_history_rows[0]["phase"] == "failed", failure_history_rows
finally:
    web._run_discovery = original_run
    web._apply_saved_device_order_to_dashboard = original_projection
    web.append_discovery_history = original_history
    web._DEVICE_STATE_RECONCILE_DEBOUNCE_SECONDS = original_debounce
    web._release_operation("Device state application")
    web._DEVICE_STATE_RECONCILE_RUNNING = False

job = Path(web.__file__).with_name("discovery_job.sh").read_text(encoding="utf-8")
assert "dashboard_device_order.py" in job
assert "device-control.json" in job
assert '--fresh "/tmp/switch_vision_generated_dashboard_raw_$$.yaml"' in job
assert '--source "$GENERATED_CARD_FULL_PATH"' in job
assert '--options "$CONFIG_FILE"' in job
run_source = Path(web.__file__).with_name("run.sh").read_text(encoding="utf-8")
assert 'SWITCH_VISION_GENERATED_CARD_FULL_PATH' in run_source
assert '/data/generated-dashboard-card-full.yaml' in run_source
entrypoint = Path(web.__file__).with_name("discovery_contract_entrypoint.py").read_text(encoding="utf-8")
assert "refresh_full_dashboard_source" in entrypoint
assert "_project_generated_dashboard(generated_card, options, fresh_path=fresh_card)" in entrypoint
assert "_append_display_fallbacks(full_card, accepted_evidence, options)" in entrypoint
walk_fn = job.split("multi_switch_walk_rows() {", 1)[1].split("\n}\n", 1)[0]
assert '(.switches // .multi_switch_walks // [])[]?' in walk_fn, walk_fn[:1000]
assert "sort_by" not in walk_fn and "sort " not in walk_fn, walk_fn[:1000]

print("Switch Vision Discovery unified device control/order regression: PASS")
