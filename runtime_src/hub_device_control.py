#!/usr/bin/env python3
"""Hub device inventory, state, and ordering orchestration.

The durable device-control state format remains owned by device_control.py.
This module owns the Hub-facing coordination around Supervisor options and the
shared state file, with all platform/runtime dependencies injected explicitly.
It never imports support_web.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Callable

import device_control as device_control_state


@dataclass(frozen=True)
class HubDeviceControlRuntime:
    self_addon_options: Callable[[], dict[str, Any]]
    load_options: Callable[[Path], dict[str, Any]]
    read_json: Callable[[Path], Any]
    safe_bool: Callable[[Any, bool], bool]
    switch_enabled_state: Callable[[Any, str], str]
    effective_discovery_switch_row: Callable[[Any, int], dict[str, Any]]
    plain_text: Callable[..., str]
    discovery_options_with_required_defaults: Callable[[dict[str, Any]], dict[str, Any]]
    validate_inventory_identities: Callable[[dict[str, Any]], None]
    create_pre_mutation_backup: Callable[..., Any]
    supervisor_json: Callable[..., dict[str, Any]]
    options_update_lock: Any
    unifi_snapshot: Path
    device_control_path: Path


def current_unified_device_keys(
    options: dict[str, Any],
    *,
    runtime: HubDeviceControlRuntime,
) -> list[str]:
    keys: list[str] = []
    rows = options.get("switches") if isinstance(options.get("switches"), list) else []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("switch_name") or "").strip()
        host = str(raw.get("switch_host") or "").strip()
        prefix = str(raw.get("sensor_prefix") or "").strip()
        if name and (name or host or prefix):
            keys.append(device_control_state.device_key("snmp", name))

    snapshot = runtime.read_json(runtime.unifi_snapshot)
    if isinstance(snapshot, dict) and isinstance(snapshot.get("devices"), list):
        for raw in snapshot["devices"]:
            if not isinstance(raw, dict):
                continue
            identity = str(raw.get("id") or "").strip()
            if identity:
                keys.append(device_control_state.device_key("unifi", identity))
    return keys


def reconcile_device_added_at(
    options: dict[str, Any],
    *,
    runtime: HubDeviceControlRuntime,
) -> dict[str, Any]:
    """Persist immutable first-added timestamps for every currently known device."""
    current_keys = current_unified_device_keys(options, runtime=runtime)
    control = device_control_state.load(runtime.device_control_path)
    control, changed = device_control_state.reconcile_added_at(control, current_keys)
    if changed:
        control = device_control_state.save(control, runtime.device_control_path)
    return control


def configured_devices_snapshot(
    options_file: Path,
    *,
    runtime: HubDeviceControlRuntime,
) -> dict[str, Any]:
    """Return browser-safe persistent switch inventory plus unified device control."""
    writable = True
    source = "supervisor"
    warning = ""
    try:
        options = runtime.self_addon_options()
    except RuntimeError as exc:
        options = runtime.load_options(options_file)
        writable = False
        source = "local_fallback"
        warning = str(exc)

    rows = options.get("switches")
    if not isinstance(rows, list):
        rows = []

    devices: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            continue
        switch_name = str(raw.get("switch_name") or "").strip()
        switch_host = str(raw.get("switch_host") or "").strip()
        sensor_prefix = str(raw.get("sensor_prefix") or "").strip()
        if not (switch_name or switch_host or sensor_prefix):
            continue
        if not switch_name:
            continue

        configured_management_target = ""
        configured_management_source = "unset"
        for management_key in ("switch_host", "host", "manual_switch_host"):
            management_value = str(raw.get(management_key) or "").strip()
            if management_value:
                configured_management_target = management_value[:255]
                configured_management_source = management_key
                break

        try:
            effective_row = runtime.effective_discovery_switch_row(raw, index + 1)
        except ValueError:
            effective_management_target = ""
            effective_management_status = "invalid_saved_row"
        else:
            effective_management_target = str(
                effective_row.get("switch_host") or ""
            ).strip()[:255]
            effective_management_status = (
                "ready" if effective_management_target else "not_configured"
            )

        try:
            state = runtime.switch_enabled_state(
                raw.get("enabled", "enabled"),
                f"Switch entry {index + 1} enabled",
            )
        except ValueError:
            state = "enabled"

        devices.append(
            {
                "device_key": device_control_state.device_key("snmp", switch_name),
                "index": index,
                "switch_name": switch_name,
                "display_name": str(raw.get("display_name") or "").strip()[:120],
                "switch_host": switch_host[:255],
                "configured_management_target": configured_management_target,
                "configured_management_source": configured_management_source,
                "effective_management_target": effective_management_target,
                "effective_management_status": effective_management_status,
                "sensor_prefix": sensor_prefix[:64],
                "switch_model": str(raw.get("switch_model") or "auto").strip()[:120]
                or "auto",
                "enabled": state,
            }
        )

    current_keys = current_unified_device_keys(options, runtime=runtime)
    control = reconcile_device_added_at(options, runtime=runtime)
    return {
        "devices": devices,
        "count": len(devices),
        "writable": writable,
        "source": source,
        "warning": warning,
        "switch_list_enabled": runtime.safe_bool(
            options.get("enable_switch_list"), True
        ),
        "device_order": device_control_state.ordered_keys(current_keys, control),
        "device_states": dict(control.get("states") or {}),
        "device_control_writable": os.access(
            runtime.device_control_path.parent, os.W_OK
        ),
    }


def set_configured_device_state(
    options_file: Path,
    request_data: Any,
    *,
    runtime: HubDeviceControlRuntime,
) -> dict[str, Any]:
    """Persist one SNMP or UniFi device state through its authoritative path."""
    if not isinstance(request_data, dict):
        raise ValueError("Device state request must contain a JSON object.")
    desired = runtime.switch_enabled_state(request_data.get("enabled"), "enabled")
    key = runtime.plain_text(
        request_data.get("device_key", ""),
        "device_key",
        max_length=320,
        allow_empty=False,
    ).strip()

    if key.startswith("unifi:"):
        options = runtime.self_addon_options()
        control = device_control_state.load(runtime.device_control_path)
        current_keys = current_unified_device_keys(options, runtime=runtime)
        if key not in current_keys:
            raise ValueError(
                "The UniFi device list changed. Refresh Devices and try again."
            )
        updated = device_control_state.set_state(
            control, key, desired == "enabled"
        )
        device_control_state.save(updated, runtime.device_control_path)
        return configured_devices_snapshot(options_file, runtime=runtime)

    if not key.startswith("snmp:"):
        raise ValueError("Device identity is invalid.")
    expected_name = key.split(":", 1)[1]

    with runtime.options_update_lock:
        options = runtime.self_addon_options()
        rows = options.get("switches")
        if not isinstance(rows, list):
            raise ValueError(
                "The saved device list changed. Refresh Devices and try again."
            )
        matches = [
            index
            for index, item in enumerate(rows)
            if isinstance(item, dict)
            and str(item.get("switch_name") or "").strip() == expected_name
        ]
        if len(matches) != 1:
            raise ValueError(
                "The saved device list changed. Refresh Devices and try again."
            )
        raw_index = matches[0]
        current = rows[raw_index]
        if not isinstance(current, dict):
            raise ValueError(
                "The saved device entry is invalid. Open Discovery Settings to review it."
            )

        updated_rows = list(rows)
        updated_row = dict(current)
        updated_row["enabled"] = desired
        updated_rows[raw_index] = updated_row
        updated_options = runtime.discovery_options_with_required_defaults(options)
        updated_options["switches"] = updated_rows
        runtime.validate_inventory_identities(updated_options)
        runtime.create_pre_mutation_backup(options, reason="device_state_update")
        runtime.supervisor_json(
            "/addons/self/options",
            method="POST",
            timeout=12.0,
            payload={"options": updated_options},
        )

        confirmed = runtime.self_addon_options()
        confirmed_rows = confirmed.get("switches")
        if not isinstance(confirmed_rows, list) or raw_index >= len(confirmed_rows):
            raise RuntimeError(
                "Home Assistant saved the request but the updated device state could not be confirmed."
            )
        confirmed_row = confirmed_rows[raw_index]
        if not isinstance(confirmed_row, dict):
            raise RuntimeError(
                "Home Assistant returned an invalid device entry after saving."
            )
        confirmed_state = runtime.switch_enabled_state(
            confirmed_row.get("enabled", "enabled"), "enabled"
        )
        if (
            str(confirmed_row.get("switch_name") or "").strip() != expected_name
            or confirmed_state != desired
        ):
            raise RuntimeError(
                "Home Assistant did not confirm the requested device state."
            )

        control = device_control_state.load(runtime.device_control_path)
        device_control_state.save(
            device_control_state.set_state(
                control, key, desired == "enabled"
            ),
            runtime.device_control_path,
        )

    return configured_devices_snapshot(options_file, runtime=runtime)


def move_configured_device(
    options_file: Path,
    request_data: Any,
    *,
    runtime: HubDeviceControlRuntime,
) -> dict[str, Any]:
    """Persist one mixed SNMP/UniFi display/dashboard order move."""
    if not isinstance(request_data, dict):
        raise ValueError("Device order request must contain a JSON object.")
    source_key = runtime.plain_text(
        request_data.get("device_key", ""),
        "device_key",
        max_length=320,
        allow_empty=False,
    ).strip()
    destination_key = runtime.plain_text(
        request_data.get("destination_device_key", ""),
        "destination_device_key",
        max_length=320,
        allow_empty=False,
    ).strip()
    if source_key == destination_key:
        raise ValueError("Device order did not change.")

    with runtime.options_update_lock:
        options = runtime.self_addon_options()
        current_keys = current_unified_device_keys(options, runtime=runtime)
        control = device_control_state.load(runtime.device_control_path)
        updated_control = device_control_state.move(
            control, current_keys, source_key, destination_key
        )
        rows = options.get("switches")
        if not isinstance(rows, list):
            raise ValueError(
                "The saved device list changed. Refresh Devices and try again."
            )

        if source_key.startswith("snmp:") and destination_key.startswith("snmp:"):
            source_name = source_key.split(":", 1)[1]
            destination_name = destination_key.split(":", 1)[1]
            indexes = {
                str(item.get("switch_name") or "").strip(): index
                for index, item in enumerate(rows)
                if isinstance(item, dict)
                and str(item.get("switch_name") or "").strip()
            }
            if source_name not in indexes or destination_name not in indexes:
                raise ValueError(
                    "The saved device list changed. Refresh Devices and try again."
                )
            updated_rows = list(rows)
            source_index = indexes[source_name]
            destination_index = indexes[destination_name]
            updated_rows[source_index], updated_rows[destination_index] = (
                updated_rows[destination_index],
                updated_rows[source_index],
            )
            updated_options = runtime.discovery_options_with_required_defaults(options)
            updated_options["switches"] = updated_rows
            runtime.validate_inventory_identities(updated_options)
            runtime.create_pre_mutation_backup(
                options, reason="device_order_update"
            )
            runtime.supervisor_json(
                "/addons/self/options",
                method="POST",
                timeout=12.0,
                payload={"options": updated_options},
            )
            confirmed = runtime.self_addon_options()
            confirmed_rows = confirmed.get("switches")
            if not isinstance(confirmed_rows, list):
                raise RuntimeError(
                    "Home Assistant did not confirm the requested device order."
                )
            confirmed_names = [
                str(item.get("switch_name") or "").strip()
                for item in confirmed_rows
                if isinstance(item, dict)
            ]
            expected_names = [
                str(item.get("switch_name") or "").strip()
                for item in updated_rows
                if isinstance(item, dict)
            ]
            if confirmed_names != expected_names:
                raise RuntimeError(
                    "Home Assistant did not confirm the requested device order."
                )

        device_control_state.save(updated_control, runtime.device_control_path)

    return configured_devices_snapshot(options_file, runtime=runtime)


def reset_configured_device_order(
    options_file: Path,
    *,
    runtime: HubDeviceControlRuntime,
) -> dict[str, Any]:
    """Restore mixed SNMP/UniFi display order to immutable first-added order."""
    with runtime.options_update_lock:
        options = runtime.self_addon_options()
        current_keys = current_unified_device_keys(options, runtime=runtime)
        control = device_control_state.load(runtime.device_control_path)
        updated_control = device_control_state.reset_order(control, current_keys)
        reset_keys = list(updated_control.get("order") or [])

        rows = options.get("switches")
        if not isinstance(rows, list):
            rows = []
        by_name = {
            str(row.get("switch_name") or "").strip(): row
            for row in rows
            if isinstance(row, dict)
            and str(row.get("switch_name") or "").strip()
        }
        snmp_names = [
            key.split(":", 1)[1]
            for key in reset_keys
            if key.startswith("snmp:")
        ]
        snmp_name_set = set(snmp_names)
        updated_rows = [
            by_name[name] for name in snmp_names if name in by_name
        ]
        updated_rows.extend(
            row
            for row in rows
            if not isinstance(row, dict)
            or not str(row.get("switch_name") or "").strip()
            or str(row.get("switch_name") or "").strip() not in snmp_name_set
        )

        if updated_rows != rows:
            updated_options = runtime.discovery_options_with_required_defaults(options)
            updated_options["switches"] = updated_rows
            runtime.validate_inventory_identities(updated_options)
            runtime.create_pre_mutation_backup(
                options, reason="device_order_reset"
            )
            runtime.supervisor_json(
                "/addons/self/options",
                method="POST",
                timeout=12.0,
                payload={"options": updated_options},
            )
            confirmed = runtime.self_addon_options()
            confirmed_rows = confirmed.get("switches")
            confirmed_names = (
                [
                    str(item.get("switch_name") or "").strip()
                    for item in confirmed_rows
                    if isinstance(item, dict)
                ]
                if isinstance(confirmed_rows, list)
                else []
            )
            expected_names = [
                str(item.get("switch_name") or "").strip()
                for item in updated_rows
                if isinstance(item, dict)
            ]
            if confirmed_names != expected_names:
                raise RuntimeError(
                    "Home Assistant did not confirm the reset device order."
                )

        device_control_state.save(updated_control, runtime.device_control_path)

    return configured_devices_snapshot(options_file, runtime=runtime)
