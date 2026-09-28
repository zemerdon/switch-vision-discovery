#!/usr/bin/env python3
"""Explicit Core and SNMP2MQTT Hub settings orchestration.

All Home Assistant/Supervisor behavior is injected by the Hub backend. This
module deliberately does not import support_web or depend on its mutable global
state, which keeps component-settings behavior independently testable.
"""
from __future__ import annotations

import copy
from pathlib import PurePosixPath
from typing import Any, Callable
from urllib.parse import quote


def core_settings_status(
    *,
    home_assistant_ws: Callable[[dict[str, Any]], Any],
) -> dict[str, Any]:
    result = home_assistant_ws({"type": "switch_vision/get_settings"})
    if not isinstance(result, dict) or not isinstance(result.get("settings"), dict):
        raise RuntimeError("Switch Vision Core did not return a valid settings payload.")
    return result


def save_core_settings(
    data: Any,
    *,
    home_assistant_ws: Callable[[dict[str, Any]], Any],
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Core settings request must contain a JSON object.")
    unknown = sorted(set(data) - {"settings", "reset_to_defaults"})
    if unknown:
        raise ValueError(f"Unsupported Core settings request field: {unknown[0]}")
    reset = data.get("reset_to_defaults", False)
    if not isinstance(reset, bool):
        raise ValueError("reset_to_defaults must be true or false.")
    command: dict[str, Any] = {
        "type": "switch_vision/set_settings",
        "reset_to_defaults": reset,
    }
    if not reset:
        settings = data.get("settings")
        if not isinstance(settings, dict):
            raise ValueError("Core settings must contain a settings object.")
        command["settings"] = settings
    result = home_assistant_ws(command)
    if not isinstance(result, dict) or not isinstance(result.get("settings"), dict):
        raise RuntimeError("Switch Vision Core did not confirm the saved settings.")
    return result


def hub_app_path(
    value: Any,
    field: str,
    *,
    plain_text: Callable[..., str],
) -> str:
    text = plain_text(
        value,
        field,
        max_length=512,
        allow_empty=False,
    ).strip()
    path = PurePosixPath(text)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field} must be an absolute path without parent traversal.")
    if not (
        text == "/config"
        or text.startswith("/config/")
        or text == "/share"
        or text.startswith("/share/")
    ):
        raise ValueError(f"{field} must stay under /config or /share.")
    return str(path)


def snmp2mqtt_addon_options(
    *,
    find_snmp2mqtt_addon: Callable[[], dict[str, Any] | None],
    supervisor_json: Callable[..., dict[str, Any]],
) -> tuple[str, str, dict[str, Any]]:
    addon = find_snmp2mqtt_addon()
    if addon is None:
        raise RuntimeError("Switch Vision SNMP2MQTT is not installed.")
    slug = str(addon.get("slug") or "").strip()
    if not slug:
        raise RuntimeError("Switch Vision SNMP2MQTT slug could not be resolved.")
    payload = supervisor_json(f"/addons/{quote(slug, safe='')}/info")
    info = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    options = info.get("options") if isinstance(info, dict) else None
    if not isinstance(options, dict):
        raise RuntimeError("Home Assistant did not expose the SNMP2MQTT app options.")
    state = str(info.get("state") or addon.get("state") or "unknown").strip().lower()
    return slug, state, dict(options)


def snmp2mqtt_settings_status(
    *,
    snmp2mqtt_addon_options: Callable[[], tuple[str, str, dict[str, Any]]],
) -> dict[str, Any]:
    try:
        slug, state, options = snmp2mqtt_addon_options()
    except RuntimeError as exc:
        if "not installed" in str(exc).lower():
            return {
                "schema_version": 1,
                "installed": False,
                "settings": None,
                "password_configured": False,
            }
        raise
    mqtt = options.get("mqtt") if isinstance(options.get("mqtt"), dict) else {}
    return {
        "schema_version": 1,
        "installed": True,
        "slug": slug,
        "state": state,
        "password_configured": bool(str(mqtt.get("password") or "")),
        "settings": {
            "mqtt": {
                "host": str(mqtt.get("host") or ""),
                "port": int(mqtt.get("port") or 1883),
                "username": str(mqtt.get("username") or ""),
                "password": "",
            },
            "targets_path": str(
                options.get("targets_path")
                or "/config/app_configs/switch_vision_snmp2mqtt/targets.yaml"
            ),
            "use_switch_vision_generated_yaml": bool(
                options.get("use_switch_vision_generated_yaml", True)
            ),
            "switch_vision_generated_yaml_path": str(
                options.get("switch_vision_generated_yaml_path")
                or "/share/switch_vision/generated-snmp2mqtt.yaml"
            ),
            "imported_targets_path": str(
                options.get("imported_targets_path")
                or "/config/app_configs/switch_vision_snmp2mqtt/imported/generated-snmp2mqtt.yaml"
            ),
            "backup_existing_config": bool(options.get("backup_existing_config", False)),
            "homeassistant": {"discovery": True, "prefix": "homeassistant"},
            "clear_password": False,
        },
        "enforced": {
            "homeassistant_discovery": True,
            "homeassistant_prefix": "homeassistant",
        },
    }


def save_snmp2mqtt_settings(
    data: Any,
    *,
    snmp2mqtt_addon_options: Callable[[], tuple[str, str, dict[str, Any]]],
    supervisor_json: Callable[..., dict[str, Any]],
    plain_text: Callable[..., str],
    settings_status: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("settings"), dict):
        raise ValueError("SNMP2MQTT settings request must contain a settings object.")
    if sorted(set(data) - {"settings"}):
        raise ValueError("SNMP2MQTT settings request contains unsupported fields.")
    requested = data["settings"]
    allowed = {
        "mqtt",
        "targets_path",
        "use_switch_vision_generated_yaml",
        "switch_vision_generated_yaml_path",
        "imported_targets_path",
        "backup_existing_config",
        "homeassistant",
        "clear_password",
    }
    unknown = sorted(set(requested) - allowed)
    if unknown:
        raise ValueError(f"Unsupported SNMP2MQTT setting: {unknown[0]}")
    ha_requested = requested.get("homeassistant")
    if not isinstance(ha_requested, dict) or sorted(
        set(ha_requested) - {"discovery", "prefix"}
    ):
        raise ValueError("SNMP2MQTT Home Assistant discovery settings are invalid.")
    if (
        ha_requested.get("discovery") is not True
        or str(ha_requested.get("prefix") or "") != "homeassistant"
    ):
        raise ValueError(
            "Switch Vision requires SNMP2MQTT MQTT Discovery with the homeassistant prefix."
        )

    slug, app_state, current = snmp2mqtt_addon_options()
    updated = copy.deepcopy(current)
    current_mqtt = current.get("mqtt") if isinstance(current.get("mqtt"), dict) else {}
    mqtt_requested = requested.get("mqtt")
    if not isinstance(mqtt_requested, dict) or sorted(
        set(mqtt_requested) - {"host", "port", "username", "password"}
    ):
        raise ValueError("SNMP2MQTT MQTT settings are invalid.")

    host = plain_text(
        mqtt_requested.get("host", ""),
        "MQTT host",
        max_length=255,
    ).strip()
    username = plain_text(
        mqtt_requested.get("username", ""),
        "MQTT username",
        max_length=256,
    ).strip()
    port = mqtt_requested.get("port", 1883)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("MQTT port must be between 1 and 65535.")
    password = plain_text(
        mqtt_requested.get("password", ""),
        "MQTT password",
        max_length=512,
    )
    clear_password = requested.get("clear_password", False)
    if not isinstance(clear_password, bool):
        raise ValueError("Clear saved MQTT password must be true or false.")

    merged_mqtt = copy.deepcopy(current_mqtt)
    merged_mqtt.update({"host": host, "port": port, "username": username})
    merged_mqtt["password"] = (
        ""
        if clear_password
        else (password if password else current_mqtt.get("password", ""))
    )
    updated["mqtt"] = merged_mqtt

    for key in (
        "targets_path",
        "switch_vision_generated_yaml_path",
        "imported_targets_path",
    ):
        if key not in requested:
            raise ValueError(
                f"SNMP2MQTT setting '{key}' is required by the Hub contract."
            )
        updated[key] = hub_app_path(requested[key], key, plain_text=plain_text)

    for key in ("use_switch_vision_generated_yaml", "backup_existing_config"):
        value = requested.get(key)
        if type(value) is not bool:
            raise ValueError(f"{key} must be true or false.")
        updated[key] = value

    homeassistant = (
        copy.deepcopy(current.get("homeassistant"))
        if isinstance(current.get("homeassistant"), dict)
        else {}
    )
    homeassistant.update({"discovery": True, "prefix": "homeassistant"})
    updated["homeassistant"] = homeassistant

    changed = updated != current
    if changed:
        supervisor_json(
            f"/addons/{quote(slug, safe='')}/options",
            method="POST",
            timeout=20.0,
            payload={"options": updated},
        )
        confirmed_slug, _, confirmed = snmp2mqtt_addon_options()
        if confirmed_slug != slug:
            raise RuntimeError("SNMP2MQTT app identity changed while saving settings.")
        if confirmed != updated:
            raise RuntimeError(
                "Home Assistant did not confirm the complete SNMP2MQTT settings update."
            )
        if app_state in {"started", "running"}:
            supervisor_json(
                f"/addons/{quote(slug, safe='')}/restart",
                method="POST",
                timeout=30.0,
            )

    result = settings_status()
    result.update(
        {
            "saved": True,
            "changed": changed,
            "restart_requested": bool(
                changed and app_state in {"started", "running"}
            ),
        }
    )
    return result
