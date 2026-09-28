#!/usr/bin/env python3
"""Explicit side-effect adapters for complete Switch Vision backup restore.

The overall restore transaction remains in the Hub coordinator.  This module
only owns the three bounded mutation adapters and receives every platform
operation as an explicit callback; it never imports support_web.
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
