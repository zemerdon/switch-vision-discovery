#!/usr/bin/env python3
"""Explicit complete Switch Vision backup restore orchestration.

The bounded mutation adapters and their transaction coordinator live here.
Every platform operation is injected explicitly; this module never imports
support_web or reaches Home Assistant/Supervisor through shared globals.
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Collection
from urllib.parse import quote


def restore_core_calibrations(
    calibrations: dict[str, Any],
    *,
    calibration_profile_name: Callable[[Any], str],
    home_assistant_service: Callable[..., Any],
) -> int:
    profiles = calibrations.get("profiles") if isinstance(calibrations, dict) else None
    if not isinstance(profiles, list):
        raise ValueError("Calibration restore payload is invalid.")
    by_name: dict[str, dict[str, Any]] = {}
    restored = 0
    for row in profiles:
        profile = calibration_profile_name(row.get("profile"))
        calibration = row.get("calibration")
        if not isinstance(calibration, dict):
            raise ValueError(f"Calibration profile {profile!r} is invalid.")
        by_name[profile] = copy.deepcopy(calibration)
        home_assistant_service(
            "switch_vision",
            "save_calibration",
            {
                "profile": profile,
                "calibration": calibration,
                "mirror_to_base": False,
            },
        )
        restored += 1

    active = calibrations.get("active_profiles")
    if isinstance(active, dict):
        for base, profile_value in active.items():
            base_name = calibration_profile_name(base)
            profile = calibration_profile_name(profile_value)
            calibration = by_name.get(profile)
            if calibration is None:
                raise ValueError(
                    f"Active calibration {profile!r} is missing from the backup."
                )
            if not profile.startswith(f"{base_name}__faceplate__"):
                raise ValueError(
                    "Active calibration map does not match its base profile."
                )
            home_assistant_service(
                "switch_vision",
                "save_calibration",
                {
                    "profile": profile,
                    "calibration": calibration,
                    "mirror_to_base": True,
                },
            )
    return restored


def restore_core_assets(
    assets: list[dict[str, Any]],
    *,
    home_assistant_ws: Callable[..., Any],
) -> int:
    restored = 0
    for asset in assets:
        result = home_assistant_ws(
            {
                "type": "switch_vision/put_backup_asset",
                "kind": asset["kind"],
                "filename": asset["filename"],
                "sha256": asset["sha256"],
                "content_base64": asset["content_base64"],
            },
            max_size=32 * 1024 * 1024,
        )
        if (
            not isinstance(result, dict)
            or str(result.get("sha256") or "") != asset["sha256"]
        ):
            raise RuntimeError(
                "Switch Vision Core did not confirm restored asset "
                f"{asset['filename']!r}."
            )
        restored += 1
    return restored


def restore_unifi2mqtt_nonsecret(
    options: dict[str, Any],
    *,
    unifi2mqtt_settings_status: Callable[[], dict[str, Any]],
    supervisor_json: Callable[..., dict[str, Any]],
    validate_unifi2mqtt_options: Callable[
        [dict[str, Any], dict[str, Any]], dict[str, Any]
    ],
    unifi_secret_fields: Collection[str],
) -> None:
    status = unifi2mqtt_settings_status()
    if not status.get("installed") or not status.get("slug"):
        raise RuntimeError("Switch Vision UniFi2MQTT is not installed.")
    slug = str(status["slug"])

    info_payload = supervisor_json(f"/addons/{quote(slug, safe='')}/info")
    info = (
        info_payload.get("data")
        if isinstance(info_payload.get("data"), dict)
        else info_payload
    )
    stored = info.get("options") if isinstance(info, dict) else None
    if not isinstance(stored, dict):
        raise RuntimeError(
            "Home Assistant did not expose current UniFi2MQTT options."
        )

    safe = {
        key: copy.deepcopy(value)
        for key, value in options.items()
        if key not in unifi_secret_fields and key != "controllers"
    }
    updated = validate_unifi2mqtt_options(safe, dict(stored))
    if updated != stored:
        supervisor_json(
            f"/addons/{quote(slug, safe='')}/options",
            method="POST",
            timeout=20.0,
            payload={"options": updated},
        )


def restore_complete_backup(
    data: Any,
    *,
    backup_format: str,
    validate_complete_backup: Callable[[Any], dict[str, Any]],
    home_assistant_ws: Callable[..., Any],
    save_core_settings: Callable[[dict[str, Any]], Any],
    restore_core_assets: Callable[[list[dict[str, Any]]], int],
    restore_core_calibrations: Callable[[dict[str, Any]], int],
    save_installer_settings: Callable[[dict[str, Any]], Any],
    save_snmp2mqtt_settings: Callable[[dict[str, Any]], Any],
    load_configuration_restore_pending: Callable[[], dict[str, Any]],
    restore_unifi2mqtt_nonsecret: Callable[[dict[str, Any]], None],
    save_discovery_settings: Callable[[dict[str, Any]], Any],
    save_configuration_restore_pending: Callable[[dict[str, Any]], Any],
    load_device_control_from_object: Callable[[dict[str, Any]], dict[str, Any]],
    save_device_control: Callable[[dict[str, Any], Any], Any],
    device_control_file: Any,
) -> dict[str, Any]:
    backup = validate_complete_backup(data)

    # Preflight the coordinated Core contract before changing any component.
    core_assets = home_assistant_ws({"type": "switch_vision/list_assets"})
    if not isinstance(core_assets, dict) or int(core_assets.get("backup_api") or 0) < 2:
        raise RuntimeError(
            "Switch Vision Core is too old for complete configuration restore. "
            "Update Core before importing."
        )

    components = backup["components"]
    restored_components: list[str] = []
    warnings: list[str] = []

    core_settings = components["core"].get("settings")
    if isinstance(core_settings, dict):
        save_core_settings({"settings": core_settings})
        restored_components.append("core")

    asset_count = restore_core_assets(backup["assets"])
    profile_count = restore_core_calibrations(backup["calibrations"])

    installer_settings = components["installer"].get("settings")
    if components["installer"].get("installed") and isinstance(installer_settings, dict):
        try:
            save_installer_settings(installer_settings)
            restored_components.append("installer")
        except RuntimeError as exc:
            warnings.append(str(exc))

    snmp_settings = components["snmp2mqtt"].get("settings")
    if components["snmp2mqtt"].get("installed") and isinstance(snmp_settings, dict):
        try:
            safe_snmp = copy.deepcopy(snmp_settings)
            if isinstance(safe_snmp.get("mqtt"), dict):
                safe_snmp["mqtt"]["password"] = ""
            safe_snmp["clear_password"] = False
            save_snmp2mqtt_settings({"settings": safe_snmp})
            restored_components.append("snmp2mqtt")
        except RuntimeError as exc:
            warnings.append(str(exc))

    pending = load_configuration_restore_pending()

    unifi_options = components["unifi2mqtt"].get("options")
    if components["unifi2mqtt"].get("installed") and isinstance(unifi_options, dict):
        controllers = unifi_options.get("controllers")
        pending["unifi_controllers"] = (
            [
                {
                    key: copy.deepcopy(value)
                    for key, value in row.items()
                    if key not in {"api_key", "api_key_configured"}
                }
                | {"api_key_configured": False, "restore_pending": True}
                for row in controllers
                if isinstance(row, dict)
            ]
            if isinstance(controllers, list)
            else []
        )
        try:
            restore_unifi2mqtt_nonsecret(unifi_options)
            restored_components.append("unifi2mqtt")
        except RuntimeError as exc:
            warnings.append(str(exc))

    discovery_settings = copy.deepcopy(components["discovery"].get("settings"))
    if not isinstance(discovery_settings, dict):
        raise ValueError("Complete backup Discovery settings are invalid.")

    switches = discovery_settings.pop("switches", [])
    stack_members = discovery_settings.pop("stack_member_prefixes", [])
    discovery_settings.pop("support_contributor_value_configured", None)

    contributor_was_configured = bool(
        components["discovery"]
        .get("settings", {})
        .get("support_contributor_value_configured")
    )
    discovery_settings["support_contributor_value"] = ""
    if (
        contributor_was_configured
        and str(discovery_settings.get("support_contributor_type") or "anonymous")
        != "anonymous"
    ):
        # The backup intentionally excludes this private value. Preserve current
        # live recognition until the operator explicitly re-enters it.
        discovery_settings.pop("support_contributor_type", None)
        discovery_settings.pop("support_contributor_value", None)

    save_discovery_settings({"settings": discovery_settings})
    restored_components.append("discovery")

    pending["discovery_switches"] = [
        {
            key: copy.deepcopy(value)
            for key, value in row.items()
            if key
            not in {
                "snmp_community",
                "snmp_community_configured",
                "original_switch_name",
            }
        }
        | {
            "snmp_community": "",
            "snmp_community_configured": False,
            "restore_pending": True,
        }
        for row in switches
        if isinstance(row, dict)
        and (
            str(row.get("switch_name") or "").strip()
            or str(row.get("switch_host") or "").strip()
        )
    ]
    pending["discovery_stack_member_prefixes"] = [
        copy.deepcopy(row) for row in stack_members if isinstance(row, dict)
    ]
    save_configuration_restore_pending(pending)

    control = load_device_control_from_object(backup["device_control"])
    save_device_control(control, device_control_file)

    return {
        "imported": True,
        "format": backup_format,
        "restored_components": restored_components,
        "asset_count": asset_count,
        "calibration_profile_count": profile_count,
        "credential_requirements": copy.deepcopy(
            backup.get("credential_requirements") or []
        ),
        "pending_discovery_switches": len(pending["discovery_switches"]),
        "pending_discovery_stack_members": len(
            pending["discovery_stack_member_prefixes"]
        ),
        "pending_unifi_controllers": len(pending["unifi_controllers"]),
        "warnings": warnings,
        "restart_required": False,
    }
