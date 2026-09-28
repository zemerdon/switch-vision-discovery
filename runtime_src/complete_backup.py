#!/usr/bin/env python3
"""Pure schema and validation helpers for complete Switch Vision backups.

This module deliberately owns no Home Assistant, Supervisor, filesystem-write,
or restore side effects. Runtime-specific validators are injected by the Hub
backend so the portable backup contract can be tested independently.
"""
from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Collection

COMPLETE_BACKUP_FORMAT = "switch-vision-complete-backup-v1"
COMPLETE_BACKUP_SCHEMA_VERSION = 1
MAX_COMPLETE_BACKUP_ASSET_BYTES = 16 * 1024 * 1024


def backup_credential_requirements(
    discovery: dict[str, Any],
    snmp2mqtt: dict[str, Any],
    unifi2mqtt: dict[str, Any],
) -> list[dict[str, str]]:
    requirements: list[dict[str, str]] = []
    settings = discovery.get("settings") if isinstance(discovery, dict) else None
    switches = settings.get("switches") if isinstance(settings, dict) else None
    if isinstance(switches, list):
        for row in switches:
            if not isinstance(row, dict) or not row.get("snmp_community_configured"):
                continue
            identifier = str(
                row.get("switch_name") or row.get("display_name") or "switch"
            ).strip()
            requirements.append(
                {
                    "component": "discovery",
                    "kind": "snmp_community",
                    "identifier": identifier,
                }
            )
    if isinstance(settings, dict) and settings.get("support_contributor_value_configured"):
        requirements.append(
            {
                "component": "discovery",
                "kind": "private_contributor_value",
                "identifier": "Support My Switch recognition",
            }
        )
    if isinstance(snmp2mqtt, dict) and snmp2mqtt.get("password_configured"):
        requirements.append(
            {"component": "snmp2mqtt", "kind": "mqtt_password", "identifier": "MQTT"}
        )
    if isinstance(unifi2mqtt, dict):
        for key, kind, label in (
            ("local_api_key_configured", "api_key", "Local controller"),
            ("remote_api_key_configured", "api_key", "Remote / Site Manager"),
            ("mqtt_password_configured", "mqtt_password", "MQTT"),
        ):
            if unifi2mqtt.get(key):
                requirements.append(
                    {"component": "unifi2mqtt", "kind": kind, "identifier": label}
                )
        options = unifi2mqtt.get("options")
        controllers = options.get("controllers") if isinstance(options, dict) else None
        if isinstance(controllers, list):
            for row in controllers:
                if isinstance(row, dict) and row.get("api_key_configured"):
                    requirements.append(
                        {
                            "component": "unifi2mqtt",
                            "kind": "controller_api_key",
                            "identifier": str(row.get("id") or "controller"),
                        }
                    )
    return requirements


def validate_complete_backup(
    data: Any,
    *,
    validate_stack_row: Callable[[Any, int], dict[str, Any]],
    validate_inventory_identities: Callable[[dict[str, Any]], None],
    calibration_profile_name: Callable[[Any], str],
    unifi_secret_fields: Collection[str],
    validate_device_control: Callable[[dict[str, Any]], Any],
) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("format") != COMPLETE_BACKUP_FORMAT:
        raise ValueError("This is not a supported complete Switch Vision backup.")
    if data.get("schema_version") != COMPLETE_BACKUP_SCHEMA_VERSION:
        raise ValueError("Unsupported complete Switch Vision backup schema version.")
    if data.get("secrets_included") is not False:
        raise ValueError("Complete Switch Vision backups must not contain secrets.")
    components = data.get("components")
    if not isinstance(components, dict):
        raise ValueError("Complete backup components are missing.")
    for required in ("core", "discovery", "snmp2mqtt", "unifi2mqtt", "installer"):
        if not isinstance(components.get(required), dict):
            raise ValueError(f"Complete backup component {required!r} is missing.")

    discovery_settings = components["discovery"].get("settings")
    if not isinstance(discovery_settings, dict):
        raise ValueError("Complete backup Discovery settings are invalid.")
    if str(discovery_settings.get("support_contributor_value") or ""):
        raise ValueError("Complete backup contains a private Support My Switch value.")
    switches = discovery_settings.get("switches")
    if not isinstance(switches, list) or len(switches) > 256:
        raise ValueError("Complete backup Discovery switch list is invalid.")
    for row in switches:
        if not isinstance(row, dict) or str(row.get("snmp_community") or ""):
            raise ValueError("Complete backup must not contain SNMP community strings.")
    stack_members = discovery_settings.get("stack_member_prefixes")
    if not isinstance(stack_members, list) or len(stack_members) > 512:
        raise ValueError("Complete backup Discovery stack member list is invalid.")
    for index, row in enumerate(stack_members, start=1):
        validate_stack_row(row, index)
    validate_inventory_identities(discovery_settings)

    snmp_settings = components["snmp2mqtt"].get("settings")
    if snmp_settings is not None:
        if not isinstance(snmp_settings, dict):
            raise ValueError("Complete backup SNMP2MQTT settings are invalid.")
        mqtt = snmp_settings.get("mqtt")
        if isinstance(mqtt, dict) and str(mqtt.get("password") or ""):
            raise ValueError("Complete backup must not contain MQTT passwords.")

    unifi_options = components["unifi2mqtt"].get("options")
    if unifi_options is not None:
        if not isinstance(unifi_options, dict):
            raise ValueError("Complete backup UniFi2MQTT options are invalid.")
        for key in unifi_secret_fields:
            if str(unifi_options.get(key) or ""):
                raise ValueError("Complete backup must not contain UniFi/MQTT secrets.")
        controllers = unifi_options.get("controllers")
        if controllers is not None:
            if not isinstance(controllers, list) or len(controllers) > 32:
                raise ValueError("Complete backup UniFi controller list is invalid.")
            for row in controllers:
                if not isinstance(row, dict) or str(row.get("api_key") or ""):
                    raise ValueError("Complete backup must not contain controller API keys.")

    calibrations = data.get("calibrations")
    if not isinstance(calibrations, dict):
        raise ValueError("Complete backup calibration data is invalid.")
    profiles = calibrations.get("profiles")
    if not isinstance(profiles, list) or len(profiles) > 2048:
        raise ValueError("Complete backup calibration profile list is invalid.")
    for row in profiles:
        if not isinstance(row, dict) or not isinstance(row.get("calibration"), dict):
            raise ValueError("Complete backup contains an invalid calibration profile.")
        calibration_profile_name(row.get("profile"))
        if len(json.dumps(row["calibration"], ensure_ascii=False).encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("Complete backup contains an oversized calibration profile.")
    active_profiles = calibrations.get("active_profiles")
    if not isinstance(active_profiles, dict):
        raise ValueError("Complete backup active calibration map is invalid.")

    assets = data.get("assets")
    if not isinstance(assets, list) or len(assets) > 2048:
        raise ValueError("Complete backup asset list is invalid.")
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError("Complete backup contains an invalid asset.")
        if str(asset.get("kind") or "") not in {"logos", "faceplates"}:
            raise ValueError("Complete backup contains an unsupported asset kind.")
        name = str(asset.get("filename") or "")
        if not name or name != Path(name).name or name.startswith("."):
            raise ValueError("Complete backup contains an invalid asset filename.")
        digest = str(asset.get("sha256") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Complete backup contains an invalid asset digest.")
        content = asset.get("content_base64")
        if not isinstance(content, str) or len(content) > 24 * 1024 * 1024:
            raise ValueError("Complete backup contains an invalid or oversized asset payload.")
        try:
            raw_asset = base64.b64decode(content.encode("ascii"), validate=True)
        except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
            raise ValueError("Complete backup contains invalid base64 asset content.") from exc
        if len(raw_asset) > MAX_COMPLETE_BACKUP_ASSET_BYTES:
            raise ValueError("Complete backup contains an asset above the 16 MiB restore limit.")
        if int(asset.get("size") or -1) != len(raw_asset):
            raise ValueError("Complete backup asset size does not match its manifest.")
        if hashlib.sha256(raw_asset).hexdigest() != digest:
            raise ValueError("Complete backup asset SHA-256 does not match its content.")

    control = data.get("device_control")
    if not isinstance(control, dict):
        raise ValueError("Complete backup device-control state is invalid.")
    validate_device_control(control)
    return copy.deepcopy(data)
