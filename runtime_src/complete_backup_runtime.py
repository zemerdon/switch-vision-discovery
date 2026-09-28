#!/usr/bin/env python3
"""Runtime read/export orchestration for complete Switch Vision backups.

All platform-specific behavior is supplied explicitly by the Hub backend.  This
module does not import support_web, Supervisor helpers, or Home Assistant
services directly; that keeps the backup export boundary testable and avoids a
shared-global/monkey-patch architecture.
"""
from __future__ import annotations

import copy
import json
import time
from typing import Any, Callable


def core_calibration_backup(
    *,
    home_assistant_ws: Callable[..., Any],
    calibration_profile_name: Callable[[Any], str],
) -> dict[str, Any]:
    listing = home_assistant_ws({"type": "switch_vision/list_calibrations"})
    if not isinstance(listing, dict):
        raise RuntimeError("Switch Vision Core did not return calibration metadata.")
    items = listing.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Switch Vision Core calibration metadata is invalid.")
    profiles: list[dict[str, Any]] = []
    active_profiles: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict) or str(item.get("scope") or "") == "factory":
            continue
        profile = calibration_profile_name(item.get("profile"))
        detail = home_assistant_ws(
            {
                "type": "switch_vision/get_calibration",
                "profile": profile,
                "exact": True,
            }
        )
        if (
            not isinstance(detail, dict)
            or detail.get("exists") is not True
            or not isinstance(detail.get("calibration"), dict)
        ):
            raise RuntimeError(
                f"Switch Vision Core could not export calibration profile {profile!r}."
            )
        calibration = copy.deepcopy(detail["calibration"])
        encoded = json.dumps(calibration, ensure_ascii=False).encode("utf-8")
        if len(encoded) > 2 * 1024 * 1024:
            raise RuntimeError(
                f"Calibration profile {profile!r} exceeds the backup size limit."
            )
        profiles.append({"profile": profile, "calibration": calibration})
        base = str(item.get("base_profile") or "").strip()
        if item.get("active") is True and base and base != profile:
            active_profiles[base] = profile
    return {"profiles": profiles, "active_profiles": active_profiles}


def core_asset_backup(
    *,
    home_assistant_ws: Callable[..., Any],
) -> list[dict[str, Any]]:
    listing = home_assistant_ws({"type": "switch_vision/list_assets"})
    if not isinstance(listing, dict):
        raise RuntimeError("Switch Vision Core did not return asset metadata.")
    if int(listing.get("backup_api") or 0) < 2:
        raise RuntimeError(
            "Switch Vision Core is too old for complete configuration backup. "
            "Update Core before exporting."
        )
    result: list[dict[str, Any]] = []
    for kind in ("logos", "faceplates"):
        names = listing.get(f"custom_{kind}")
        if not isinstance(names, list):
            raise RuntimeError(
                f"Switch Vision Core custom asset list for {kind} is invalid."
            )
        for raw_name in names:
            name = str(raw_name or "").strip()
            if not name:
                continue
            asset = home_assistant_ws(
                {
                    "type": "switch_vision/get_backup_asset",
                    "kind": kind,
                    "filename": name,
                },
                max_size=32 * 1024 * 1024,
            )
            if not isinstance(asset, dict):
                raise RuntimeError(
                    f"Switch Vision Core could not export asset {kind}/{name}."
                )
            result.append(
                {
                    "kind": kind,
                    "filename": name,
                    "size": int(asset.get("size") or 0),
                    "sha256": str(asset.get("sha256") or ""),
                    "content_base64": str(asset.get("content_base64") or ""),
                }
            )
    return result


def export_complete_backup(
    version: str,
    *,
    backup_format: str,
    schema_version: int,
    core_settings_status: Callable[[], dict[str, Any]],
    discovery_settings_status: Callable[[], dict[str, Any]],
    snmp2mqtt_settings_status: Callable[[], dict[str, Any]],
    unifi2mqtt_settings_status: Callable[[], dict[str, Any]],
    installer_settings_status: Callable[[], dict[str, Any]],
    configured_devices_snapshot: Callable[[Any], Any],
    options_file: Any,
    load_device_control: Callable[[Any], dict[str, Any]],
    device_control_file: Any,
    core_calibration_backup: Callable[[], dict[str, Any]],
    core_asset_backup: Callable[[], list[dict[str, Any]]],
    credential_requirements: Callable[
        [dict[str, Any], dict[str, Any], dict[str, Any]],
        list[dict[str, str]],
    ],
    validate_complete_backup: Callable[[Any], dict[str, Any]],
    exported_at: str | None = None,
) -> dict[str, Any]:
    core = core_settings_status()
    discovery = discovery_settings_status()
    snmp2mqtt = snmp2mqtt_settings_status()
    unifi2mqtt = unifi2mqtt_settings_status()
    installer = installer_settings_status()

    # Snapshotting configured devices establishes any missing immutable added_at
    # migration metadata before the control state is captured.
    configured_devices_snapshot(options_file)
    control = load_device_control(device_control_file)

    payload = {
        "format": backup_format,
        "schema_version": schema_version,
        "switch_vision_discovery_version": version,
        "exported_at": exported_at or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "secrets_included": False,
        "secret_policy": {
            "snmp_communities": "excluded",
            "mqtt_passwords": "excluded",
            "unifi_api_keys": "excluded",
            "tokens_and_passwords": "excluded",
            "support_contributor_value": "excluded_private_value",
        },
        "components": {
            "core": {"settings": copy.deepcopy(core.get("settings"))},
            "discovery": {"settings": copy.deepcopy(discovery.get("settings"))},
            "snmp2mqtt": {
                "installed": bool(snmp2mqtt.get("installed")),
                "settings": copy.deepcopy(snmp2mqtt.get("settings")),
            },
            "unifi2mqtt": {
                "installed": bool(unifi2mqtt.get("installed")),
                "options": copy.deepcopy(unifi2mqtt.get("options")),
            },
            "installer": {
                "installed": bool(installer.get("installed")),
                "settings": copy.deepcopy(installer.get("settings")),
            },
        },
        "device_control": copy.deepcopy(control),
        "calibrations": core_calibration_backup(),
        "assets": core_asset_backup(),
        "credential_requirements": credential_requirements(
            discovery, snmp2mqtt, unifi2mqtt
        ),
    }
    validate_complete_backup(payload)
    return payload
