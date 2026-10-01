#!/usr/bin/env python3
"""Local Home Assistant Ingress UI for Support My Switch.

The UI creates privacy-processed contribution bundles by invoking the existing
support_my_switch.sh backend. It never sends email or stores mail credentials.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import copy
from contextlib import contextmanager
import html
import ipaddress
import json
import mimetypes
import os
import subprocess
import threading
import signal
import time
import traceback
import zipfile
import hashlib
import re
import shutil
import ssl
import unicodedata

import yaml
from websockets.sync.client import connect as websocket_connect
from email.message import EmailMessage
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from registry_lookup import lookup as registry_lookup
from mqtt_maintenance_runtime import (
    generated_yaml_generation_id,
    repair_mqtt_entities,
    scan_mqtt_entities,
    verify_generated_yaml_loaded,
)
from discovery_backups import (
    create_pre_mutation_backup,
    discovery_backup_status,
    enforce_retention,
    remove_discovery_backup,
)
from discovery_history import (
    DEFAULT_HISTORY_PATH as DEFAULT_DISCOVERY_HISTORY,
    append_discovery_history,
    discovery_history_snapshot,
    sanitize_debug_text,
)
import device_control as device_control_state
import dashboard_device_order
import autodiscover
import complete_backup
import complete_backup_runtime
import complete_backup_restore
import hub_component_settings
import hub_device_control
import hub_diagnostics
import hub_autodiscover

SUPPORT_ADDRESS = "switch-vision@zemerdon.com"
SUPERVISOR_INGRESS_IP = "172.30.32.2"
GITHUB_SPONSORS_URL = "https://github.com/sponsors/zemerdon"
HUB_MOTD_ENV_VAR = "SWITCH_VISION_HUB_MOTD"
HUB_MOTD_DEFAULT = (
    "Thank you for your continued support. Please use Support My Switch and submit your "
    "contribution package to switch-vision@zemerdon.com. Even if nothing is wrong, a "
    "contribution package validates correctness. Also feel free to express any feedback, "
    "ideas, or bugs. If any faceplate geometry is not correct, can you please click Reset "
    "Faceplate in the Calibration tool, and if that doesn't work, let me know please."
)
HUB_MOTD_MAX_CHARS = 500
DEFAULT_CONTRIBUTIONS_DIR = Path("/share/switch_vision/contributions")
DEFAULT_OPTIONS_FILE = Path("/data/options.json")
DEFAULT_SUPPORT_SCRIPT = Path("/support_my_switch.sh")
DEFAULT_DISCOVERY_SCRIPT = Path("/discovery_contract_entrypoint.py")
DEFAULT_SHARE_DIR = Path("/share/switch_vision")
DEFAULT_INSTALLER_MAINTENANCE_RESPONSE = DEFAULT_SHARE_DIR / "installer-maintenance-response.json"
DEFAULT_REGISTRY_FILE = Path("/opt/switch-vision/devices/supported_devices.json")
DEFAULT_GENERATED_SNMP2MQTT = Path("/share/switch_vision/generated-snmp2mqtt.yaml")
DEFAULT_GENERATED_CARD = Path("/share/switch_vision/generated-dashboard-card.yaml")
DEFAULT_GENERATED_CARD_FULL = Path(
    os.environ.get(
        "SWITCH_VISION_GENERATED_CARD_FULL_PATH",
        str(dashboard_device_order.full_dashboard_path(DEFAULT_GENERATED_CARD)),
    )
)
DEFAULT_UNIFI_SNAPSHOT = Path("/share/switch_vision/unifi/devices.json")
DEFAULT_UNIFI_DIAGNOSTICS = Path("/share/switch_vision/unifi/diagnostics.json")
DEFAULT_DEVICE_CONTROL = Path(
    os.environ.get("SV_DEVICE_CONTROL_PATH", str(DEFAULT_SHARE_DIR / "device-control.json"))
)
DEFAULT_CONFIGURATION_RESTORE_PENDING = DEFAULT_SHARE_DIR / "configuration-restore-pending.json"
COMPLETE_BACKUP_FORMAT = complete_backup.COMPLETE_BACKUP_FORMAT
COMPLETE_BACKUP_SCHEMA_VERSION = complete_backup.COMPLETE_BACKUP_SCHEMA_VERSION
MAX_COMPLETE_BACKUP_BYTES = 128 * 1024 * 1024
MAX_COMPLETE_BACKUP_ASSET_BYTES = complete_backup.MAX_COMPLETE_BACKUP_ASSET_BYTES
DEFAULT_DISCOVERY_LOG = DEFAULT_SHARE_DIR / "discovery-web.log"
_current_debug_override = os.environ.get("SV_CURRENT_DISCOVERY_DEBUG_PATH", "").strip()
if _current_debug_override:
    DEFAULT_CURRENT_DISCOVERY_DEBUG = Path(_current_debug_override)
elif Path("/data").is_dir() and os.access("/data", os.W_OK):
    DEFAULT_CURRENT_DISCOVERY_DEBUG = Path("/data/current-discovery-debug.log")
else:
    DEFAULT_CURRENT_DISCOVERY_DEBUG = Path("/tmp/switch-vision-current-discovery-debug.log")
DEFAULT_SNMPWALKS_DIR = DEFAULT_SHARE_DIR / "snmpwalks"
DEFAULT_CAPABILITIES_DIR = DEFAULT_SHARE_DIR / "capabilities"
DEFAULT_SNMP_RETIREMENT_STATE = Path("/data/snmp2mqtt-retirement-topics.json")
SNMP_RESET_FILES = (
    DEFAULT_SHARE_DIR / "snmpwalk.txt",
    DEFAULT_SHARE_DIR / "generated-snmp2mqtt.yaml",
    DEFAULT_SHARE_DIR / "generated-dashboard-card.yaml",
    DEFAULT_GENERATED_CARD_FULL,
    DEFAULT_SHARE_DIR / "discovery-report.txt",
    DEFAULT_SHARE_DIR / "last-discovery-run.txt",
    DEFAULT_SHARE_DIR / "snmpwalk.log",
    DEFAULT_SHARE_DIR / "live-snmpwalk.log",
)

UNIFI2MQTT_DEFAULT_OPTIONS = {
    # Legacy single-transport fields remain readable for migration compatibility.
    "transport": "local",
    "controller_url": "https://192.168.1.1",
    "host_id": "auto",
    "site_id": "auto",
    "api_key": "",
    "verify_ssl": "false",
    "allow_insecure_http": "false",
    # Preferred single-controller connection model.
    "priority_transport": "local",
    "fallback_transport": "remote",
    "local_controller_url": "https://192.168.1.1:11443",
    "local_site_id": "auto",
    "local_api_key": "",
    "local_verify_ssl": "false",
    "local_allow_insecure_http": "false",
    "remote_host_id": "auto",
    "remote_site_id": "auto",
    "remote_api_key": "",
    # Optional first-class multi-controller configuration.
    "controllers": [],
    "poll_interval": "10",
    "mqtt_host": "",
    "mqtt_port": "1883",
    "mqtt_username": "",
    "mqtt_password": "",
    "mqtt_tls": "false",
    "mqtt_verify_ssl": "true",
    "mqtt_ca": "",
    "mqtt_topic_prefix": "switch_vision/unifi",
    "mqtt_discovery_prefix": "homeassistant",
}
UNIFI2MQTT_SECRET_FIELDS = {
    "api_key",
    "local_api_key",
    "remote_api_key",
    "mqtt_password",
}

DISCOVERY_REQUIRED_OPTION_DEFAULTS = {
    "autodiscover_networks": [],
}


def _discovery_options_with_required_defaults(options: dict[str, Any]) -> dict[str, Any]:
    """Return a Supervisor-save-safe Discovery options object.

    Home Assistant retains pre-upgrade option objects verbatim. New required
    root keys therefore have to be added before any whole-options POST, even
    when the operator is changing an unrelated setting.
    """
    updated = dict(options)
    for key, value in DISCOVERY_REQUIRED_OPTION_DEFAULTS.items():
        if key not in updated:
            updated[key] = copy.deepcopy(value)
    return updated


DISCOVERY_RESET_OPTIONS = {
    "input_path": "/share/switch_vision/snmpwalk.txt",
    "snmpwalks_dir": "/share/switch_vision/snmpwalks",
    "report_path": "/share/switch_vision/discovery-report.txt",
    "run_snmp_walks": "true",
    "enable_switch_list": "true",
    "switches": [{
        "switch_name": "",
        "switch_host": "",
        "sensor_prefix": "",
        "snmp_community": "readonly",
        "enabled": "enabled",
        "walk_mode": "targeted",
        "switch_model": "auto",
        "card_header_title": "",
    }],
    "stack_member_prefixes": [],
    "autodiscover_networks": [],
    "parse_all_walks": "false",
    "generate_snmp2mqtt": "true",
    "clean_output_before_walk": "false",
    "targets_csv": "/share/switch_vision/discovery-targets.csv",
    "last_run_summary_path": "/share/switch_vision/last-discovery-run.txt",
    "generated_yaml_path": "/share/switch_vision/generated-snmp2mqtt.yaml",
    "generated_card_path": "/share/switch_vision/generated-dashboard-card.yaml",
    "snmp_timeout": "3",
    "snmp_retries": "1",
    "snmp_log_path": "/share/switch_vision/snmpwalk.log",
    "minimum_valid_walk_lines": "100",
    "backup_retention_enabled": "true",
    "backup_retention_count": 5,
    "generate_support_my_switch_bundle": "true",
    "support_mask_management_ips": "true",
    "support_mask_mac_addresses": "true",
    "support_mask_hostnames": "true",
    "support_mask_vlan_names": "true",
    "support_mask_interface_descriptions": "true",
    "support_contributor_type": "anonymous",
    "support_contributor_value": "",
}

SNMP2MQTT_RESET_OPTIONS = {
    "mqtt": {"host": "", "port": 1883, "username": "", "password": ""},
    "targets_path": "/config/app_configs/switch_vision_snmp2mqtt/targets.yaml",
    "use_switch_vision_generated_yaml": True,
    "switch_vision_generated_yaml_path": "/share/switch_vision/generated-snmp2mqtt.yaml",
    "imported_targets_path": "/config/app_configs/switch_vision_snmp2mqtt/imported/generated-snmp2mqtt.yaml",
    "backup_existing_config": False,
    "homeassistant": {"discovery": True, "prefix": "homeassistant"},
}

INSTALLER_RESET_SETTINGS = {
    "release_api_url": "https://api.github.com/repos/zemerdon/switch-vision-releases/releases/latest",
    "allow_custom_release_source": False,
    "release_asset_pattern": "switch-vision-*.zip",
    "preserve_custom_assets": True,
    "create_backup": True,
    "allow_prerelease": False,
    "backup_retention": 5,
}

RESET_EVERYTHING_CONFIRMATION = "RESET EVERYTHING"

UI_PREFERENCES_PATH = Path("/share/switch_vision/ui-preferences.json")
UI_TEXT_SIZE_MIN_PX = 10
UI_TEXT_SIZE_MAX_PX = 20
UI_TEXT_SIZE_DEFAULT_PX = 16
UI_TEXT_SIZE_LEGACY = {"normal": 16, "small": 14}
_UI_DEFAULTS = {
    "density": "comfortable",
    "text_size": UI_TEXT_SIZE_DEFAULT_PX,
    "content_width": "standard",
    "show_unifi_integration": True,
}
_UI_ALLOWED = {
    "density": {"spacious", "comfortable", "compact", "dense", "ultra_dense"},
    "content_width": {
        "standard", "standard_plus", "wide", "wide_plus", "extra_wide",
        "extra_wide_plus", "ultra_wide", "ultra_wide_plus", "max_wide", "full",
    },
}


def _normalise_ui_text_size(value: Any) -> int:
    """Resolve legacy labels and explicit values to a safe 10-20 px size."""
    if isinstance(value, bool):
        return UI_TEXT_SIZE_DEFAULT_PX
    if isinstance(value, str):
        text = value.strip().lower()
        if text in UI_TEXT_SIZE_LEGACY:
            return UI_TEXT_SIZE_LEGACY[text]
        if text.endswith("px"):
            text = text[:-2].strip()
        if not text.isdigit():
            return UI_TEXT_SIZE_DEFAULT_PX
        pixels = int(text)
    elif isinstance(value, int):
        pixels = value
    else:
        return UI_TEXT_SIZE_DEFAULT_PX
    if UI_TEXT_SIZE_MIN_PX <= pixels <= UI_TEXT_SIZE_MAX_PX:
        return pixels
    return UI_TEXT_SIZE_DEFAULT_PX


def _discovery_ui_preferences() -> dict[str, Any]:
    """Read and validate shared Switch Vision Discovery UI preferences."""
    values = dict(_UI_DEFAULTS)
    try:
        document = json.loads(UI_PREFERENCES_PATH.read_text(encoding="utf-8"))
        discovery = document.get("discovery", {}) if isinstance(document, dict) else {}
        if isinstance(discovery, dict):
            for key, allowed in _UI_ALLOWED.items():
                candidate = str(discovery.get(key, values[key])).strip().lower()
                if candidate in allowed:
                    values[key] = candidate
            values["text_size"] = _normalise_ui_text_size(
                discovery.get("text_size", values["text_size"])
            )
            values["show_unifi_integration"] = bool(
                discovery.get("show_unifi_integration", values["show_unifi_integration"])
            )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    return values


def _hub_motd_text() -> str:
    """Return the bounded operator notice rendered in the Hub home view."""
    raw = os.environ.get(HUB_MOTD_ENV_VAR, "")
    value = " ".join(str(raw).split())
    if not value:
        return HUB_MOTD_DEFAULT
    return value[:HUB_MOTD_MAX_CHARS]


def _page_with_ui_preferences(version: str | None = None) -> str:
    """Apply current UI preferences and inject bounded runtime metadata."""
    preferences = _discovery_ui_preferences()
    classes = " ".join(
        (
            f"density-{preferences['density']}",
            f"width-{preferences['content_width']}",
        )
    )
    document_version = str(
        version
        or os.environ.get("SWITCH_VISION_DISCOVERY_VERSION", "unknown")
        or "unknown"
    ).strip()
    page = _PAGE.replace(
        "<body><main>",
        (
            f'<body class="{classes}" '
            f'data-sv-discovery-version="{html.escape(document_version, quote=True)}" '
            f'style="--sv-font-body:{preferences["text_size"]}px"><main>'
        ),
        1,
    )
    return page.replace("__SV_HUB_MOTD__", html.escape(_hub_motd_text()), 1)

DISCOVERY_EXPORT_FORMAT = "switch-vision-discovery-config-v2"
DISCOVERY_IMPORT_FORMATS = {
    "switch-vision-discovery-config-v1",
    DISCOVERY_EXPORT_FORMAT,
}
DISCOVERY_CONFIG_KEYS = {
    "input_path", "snmpwalks_dir", "report_path", "run_snmp_walks",
    "enable_switch_list", "switches", "stack_member_prefixes", "autodiscover_networks",
    "parse_all_walks", "generate_snmp2mqtt", "clean_output_before_walk",
    "targets_csv", "last_run_summary_path", "generated_yaml_path",
    "generated_card_path", "snmp_timeout", "snmp_retries",
    "snmp_log_path", "minimum_valid_walk_lines",
    "backup_retention_enabled", "backup_retention_count",
}


def _discovery_export(options_file: Path, version: str) -> dict[str, Any]:
    # Supervisor is the authoritative persistent configuration source. The
    # options_file argument is retained for call-site compatibility only.
    del options_file
    options = _self_addon_options()
    exported = {key: options[key] for key in DISCOVERY_CONFIG_KEYS if key in options}
    # v2 exports make the persistent switch state explicit even when the live
    # options came from a pre-v2.1.8 installation where the field was absent.
    switches = exported.get("switches")
    if isinstance(switches, list):
        normalized_switches: list[Any] = []
        for index, item in enumerate(switches, start=1):
            if isinstance(item, dict):
                row = dict(item)
                row["enabled"] = _switch_enabled_state(
                    row.get("enabled", "enabled"),
                    f"Switch entry {index} enabled",
                )
                normalized_switches.append(row)
            else:
                normalized_switches.append(item)
        exported["switches"] = normalized_switches
    return {
        "format": DISCOVERY_EXPORT_FORMAT,
        "switch_vision_version": version,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "configuration": exported,
    }


SWITCHES_EXPORT_FORMAT = "switch-vision-switch-configuration-v1"
_SWITCH_EXPORT_FIELDS = {
    "switch_name", "display_name", "switch_host", "sensor_prefix", "enabled",
    "walk_mode", "switch_model", "card_header_title", "output_dir",
}
_STACK_EXPORT_FIELDS = {
    "switch_name", "member", "display_name", "sensor_prefix", "card_header_title",
}


def _switches_export(version: str) -> dict[str, Any]:
    """Return only portable, non-secret switch and stack configuration."""
    settings = _discovery_settings_status().get("settings", {})
    exported_switches: list[dict[str, Any]] = []
    for raw in settings.get("switches", []) if isinstance(settings, dict) else []:
        if not isinstance(raw, dict):
            continue
        if not (
            str(raw.get("switch_name") or "").strip()
            or str(raw.get("switch_host") or "").strip()
        ):
            continue
        exported_switches.append({
            key: copy.deepcopy(value)
            for key, value in raw.items()
            if key in _SWITCH_EXPORT_FIELDS
        })
    exported_stack = [
        {
            key: copy.deepcopy(value)
            for key, value in raw.items()
            if key in _STACK_EXPORT_FIELDS
        }
        for raw in settings.get("stack_member_prefixes", [])
        if isinstance(raw, dict)
    ] if isinstance(settings, dict) and isinstance(settings.get("stack_member_prefixes"), list) else []
    return {
        "format": SWITCHES_EXPORT_FORMAT,
        "switch_vision_version": version,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "secrets_included": False,
        "switches": exported_switches,
        "stack_member_prefixes": exported_stack,
    }


def _validate_switches_import(data: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(data, dict) or data.get("format") != SWITCHES_EXPORT_FORMAT:
        raise ValueError("This is not a supported Switch Vision switch configuration export.")
    if data.get("secrets_included") is not False:
        raise ValueError("Switch configuration exports must not contain secrets.")

    raw_switches = data.get("switches")
    raw_stack = data.get("stack_member_prefixes")
    if not isinstance(raw_switches, list) or len(raw_switches) > 256:
        raise ValueError("Switch configuration switch list is invalid.")
    if not isinstance(raw_stack, list) or len(raw_stack) > 512:
        raise ValueError("Switch configuration stack member list is invalid.")

    switches: list[dict[str, Any]] = []
    validation_switches: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_switches, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Switch entry {index} must be an object.")
        unknown = sorted(set(raw) - _SWITCH_EXPORT_FIELDS)
        if unknown:
            raise ValueError(f"Switch entry {index} contains unsupported field '{unknown[0]}'.")
        candidate = dict(raw)
        candidate["snmp_community"] = "__switch_vision_import_pending__"
        validated = _validate_switch_row(candidate, index)
        portable = {
            key: copy.deepcopy(value)
            for key, value in validated.items()
            if key in _SWITCH_EXPORT_FIELDS
        }
        switches.append(portable)
        validation_switches.append(dict(validated))

    stack: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_stack, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Stack member entry {index} must be an object.")
        unknown = sorted(set(raw) - _STACK_EXPORT_FIELDS)
        if unknown:
            raise ValueError(f"Stack member entry {index} contains unsupported field '{unknown[0]}'.")
        stack.append(_validate_stack_row(dict(raw), index))

    _validate_inventory_identities({
        "switches": validation_switches,
        "stack_member_prefixes": stack,
    })
    return {"switches": switches, "stack_member_prefixes": stack}


def _import_switches_only(data: Any) -> dict[str, Any]:
    imported = _validate_switches_import(data)
    pending = _load_configuration_restore_pending()
    pending["discovery_switches"] = [
        dict(row)
        | {
            "snmp_community": "",
            "snmp_community_configured": False,
            "restore_pending": True,
        }
        for row in imported["switches"]
    ]
    pending["discovery_stack_member_prefixes"] = [
        dict(row) for row in imported["stack_member_prefixes"]
    ]
    _save_configuration_restore_pending(pending)
    return {
        "imported": True,
        "format": SWITCHES_EXPORT_FORMAT,
        "switch_count": len(imported["switches"]),
        "stack_member_count": len(imported["stack_member_prefixes"]),
        "credentials_included": False,
        "restart_required": False,
    }


def _plain_text(value: Any, field: str, *, max_length: int, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text.")
    if len(value) > max_length:
        raise ValueError(f"{field} is too long.")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{field} contains control characters.")
    if not allow_empty and not value.strip():
        raise ValueError(f"{field} cannot be empty.")
    return value


def _share_path(value: Any, field: str) -> str:
    text = _plain_text(value, field, max_length=512, allow_empty=False).strip()
    path = PurePosixPath(text)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field} must be an absolute path under /share/switch_vision.")
    try:
        path.relative_to(PurePosixPath("/share/switch_vision"))
    except ValueError as exc:
        raise ValueError(f"{field} must stay under /share/switch_vision.") from exc
    return str(path)


def _bool_string(value: Any, field: str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower()
    raise ValueError(f"{field} must be true or false.")


def _switch_enabled_state(value: Any, field: str) -> str:
    """Normalize a persistent switch generation state."""
    if isinstance(value, bool):
        return "enabled" if value else "disabled"
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"enabled", "enable", "true", "on", "yes", "1", ""}:
            return "enabled"
        if text in {"disabled", "disable", "false", "off", "no", "0"}:
            return "disabled"
    raise ValueError(f"{field} must be enabled or disabled.")


def _bounded_int_string(value: Any, field: str, minimum: int, maximum: int) -> str:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number.")
    text = str(value).strip()
    if not re.fullmatch(r"\d+", text):
        raise ValueError(f"{field} must be a whole number.")
    number = int(text)
    if number < minimum or number > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}.")
    return text


def _manual_snmp_override_models() -> set[str]:
    """Return exact SNMP model overrides from the authoritative registry."""
    registry = _read_json(DEFAULT_REGISTRY_FILE)
    devices = registry.get("devices", []) if isinstance(registry, dict) else []
    models: set[str] = set()
    for device in devices if isinstance(devices, list) else []:
        if not isinstance(device, dict):
            continue
        vendor = str(device.get("vendor") or "").strip().casefold()
        model = str(device.get("model") or "").strip()
        if (
            model
            and vendor != "ubiquiti"
            and bool(device.get("discovery_support"))
            and str(device.get("mapping_profile") or "").strip()
        ):
            models.add(model)
    # Keep configuration import usable if the registry is temporarily unreadable.
    return models or {
        "WS-C3650-48PD-E", "WS-C3650-48PD-L", "WS-C2960X-48FPD-L",
        "WS-C2960X-24PS-L", "WS-C2960X-24TS-L", "WS-C2960XR-48LPS-I", "WS-C2960S-48FPD-L",
        "WS-C3560CG-8PC-S", "WS-C3750-48P", "WS-C3750X-48P", "WS-C3750X-48P-S",
        "WS-C3850-12XS-E", "EX3300-48P", "SG500X-24", "SG350-20",
        "S5720-12TP-LI-AC", "S5735-L8P4X-A1", "CRS328-24P-4S+RM", "XS1930-10",
        "N4032F", "N2128PX-ON", "PowerConnect 5548P", "HP J8693A Switch 3500yl-48G",
        "HP 1810-24G", "HP J9774A 2530-8G-PoEP", "HP ProCurve 1810G-24", "GS1900-24E", "GS1900-8",
        "GS1915-24EP", "3524GT-PWR+", "SR-S25G3420F",
    }


def _validate_switch_row(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"Switch entry {index} must be an object.")
    required = {"switch_name", "switch_host", "sensor_prefix", "snmp_community"}
    missing = [key for key in required if key not in item]
    if missing:
        raise ValueError(f"Switch entry {index} is missing {missing[0]}.")
    row = dict(item)
    switch_name = _plain_text(row.get("switch_name"), f"Switch entry {index} switch_name", max_length=64).strip()
    switch_host = _plain_text(row.get("switch_host"), f"Switch entry {index} switch_host", max_length=255).strip()
    sensor_prefix = _plain_text(row.get("sensor_prefix"), f"Switch entry {index} sensor_prefix", max_length=64).strip()
    community = _plain_text(row.get("snmp_community"), f"Switch entry {index} snmp_community", max_length=256, allow_empty=False)

    # A row with no name and no host is the Home Assistant UI placeholder.
    # Older/stale Supervisor state may leave a generated sensor_prefix behind;
    # that must not turn the placeholder into a real switch identity.
    if not switch_name and not switch_host:
        sensor_prefix = ""
    if switch_name and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,63}", switch_name):
        raise ValueError(
            f"Switch entry {index} switch_name contains unsupported characters. "
            "Use letters, numbers, spaces, '.', '_' or '-'."
        )
    if switch_host and (any(ch.isspace() for ch in switch_host) or "/" in switch_host):
        raise ValueError(f"Switch entry {index} switch_host is not a valid host value.")
    if sensor_prefix and not re.fullmatch(r"[A-Za-z0-9_-]+", sensor_prefix):
        raise ValueError(f"Switch entry {index} sensor_prefix contains unsupported characters.")
    if (switch_name or switch_host or sensor_prefix) and (not switch_name or not switch_host):
        raise ValueError(f"Switch entry {index} requires both switch_name and switch_host.")
    row["switch_name"] = switch_name
    row["switch_host"] = switch_host
    row["sensor_prefix"] = sensor_prefix
    row["snmp_community"] = community
    # v2.1.8: switch rows are persistent. Missing enabled state is treated as
    # enabled for backward compatibility with every pre-v2.1.8 configuration.
    row["enabled"] = _switch_enabled_state(row.get("enabled", "enabled"), f"Switch entry {index} enabled")
    walk_mode = str(row.get("walk_mode", "targeted")).strip().lower()
    if walk_mode not in {"targeted", "full"}:
        raise ValueError(f"Switch entry {index} walk_mode must be targeted or full.")
    row["walk_mode"] = walk_mode
    allowed_models = {"auto"} | _manual_snmp_override_models()
    model = str(row.get("switch_model", "auto")).strip() or "auto"
    if model not in allowed_models:
        raise ValueError(f"Switch entry {index} switch_model is not supported by this build.")
    row["switch_model"] = model
    for key in ("display_name", "card_header_title"):
        if key in row:
            row[key] = _plain_text(row[key], f"Switch entry {index} {key}", max_length=120)
    if "output_dir" in row and str(row.get("output_dir") or "").strip():
        output = _share_path(row["output_dir"], f"Switch entry {index} output_dir")
        if not (output == "/share/switch_vision/snmpwalks" or output.startswith("/share/switch_vision/snmpwalks/")):
            raise ValueError(f"Switch entry {index} output_dir must stay under /share/switch_vision/snmpwalks.")
        row["output_dir"] = output
    return row


def _validate_stack_row(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"Stack member entry {index} must be an object.")
    row = dict(item)
    switch_name = _plain_text(row.get("switch_name", ""), f"Stack member entry {index} switch_name", max_length=64).strip()
    member = _plain_text(row.get("member", ""), f"Stack member entry {index} member", max_length=8).strip()
    if not switch_name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,63}", switch_name):
        raise ValueError(
            f"Stack member entry {index} has an invalid switch_name. "
            "Use letters, numbers, spaces, '.', '_' or '-'."
        )
    if not re.fullmatch(r"\d+", member) or not (1 <= int(member) <= 64):
        raise ValueError(f"Stack member entry {index} member must be between 1 and 64.")
    row["switch_name"] = switch_name
    row["member"] = member
    for key, limit in (("display_name", 120), ("sensor_prefix", 64), ("card_header_title", 120)):
        if key in row:
            row[key] = _plain_text(row[key], f"Stack member entry {index} {key}", max_length=limit)
    if row.get("sensor_prefix") and not re.fullmatch(r"[A-Za-z0-9_-]+", str(row["sensor_prefix"])):
        raise ValueError(f"Stack member entry {index} sensor_prefix contains unsupported characters.")
    return row



def _switch_name_identity(value: str) -> str:
    """Return the collision key used by filesystem/internal switch identities.

    Discovery preserves the user's saved switch_name, including spaces, while
    folders and contract lookups normalise whitespace/unsafe separators to
    underscores. Uniqueness therefore has to be checked after the same
    normalisation so two saved names cannot collapse onto one internal key.
    """
    text = re.sub(r"\s+", "_", str(value or "").strip())
    text = re.sub(r"[^A-Za-z0-9._-]", "_", text)
    text = re.sub(r"_+", "_", text).strip("_ .-")
    return text.casefold()


def _ha_prefix_identity(value: str) -> str:
    """Return the Home Assistant/SNMP2MQTT identity key for a sensor prefix."""
    text = value.strip().casefold().replace("-", "_")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def _validate_inventory_identities(configuration: dict[str, Any]) -> None:
    """Reject switch/folder and generated entity identity collisions.

    Disabled rows are intentionally included: a saved disabled row can be
    re-enabled later and must not reserve an identity already used elsewhere.
    """
    switches = configuration.get("switches")
    if not isinstance(switches, list):
        switches = []
    stack_rows = configuration.get("stack_member_prefixes")
    if not isinstance(stack_rows, list):
        stack_rows = []

    switch_names: dict[str, str] = {}
    switch_identity_owners: dict[str, tuple[str, str]] = {}
    prefix_owners: dict[str, tuple[str, str, str]] = {}
    parent_prefixes: dict[str, str] = {}

    for index, raw in enumerate(switches, start=1):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("switch_name") or "").strip()
        host = str(raw.get("switch_host") or "").strip()
        configured_prefix = str(raw.get("sensor_prefix") or "").strip()
        if not (name or host):
            continue
        if not name:
            raise ValueError(f"Switch entry {index} requires switch_name for a stable identity.")
        name_key = name.casefold()
        previous = switch_names.get(name_key)
        if previous is not None:
            raise ValueError(
                f"Switch entry {index} switch_name '{name}' duplicates {previous}. "
                "Every saved switch_name must be unique, including disabled rows."
            )

        identity_key = _switch_name_identity(name)
        if not identity_key:
            raise ValueError(f"Switch entry {index} does not produce a usable internal identity.")
        previous_identity = switch_identity_owners.get(identity_key)
        if previous_identity is not None:
            raise ValueError(
                f"Switch entry {index} switch_name '{name}' normalizes to internal key "
                f"'{identity_key}', already used by {previous_identity[0]} "
                f"switch_name '{previous_identity[1]}'. Choose a distinct stable switch_name."
            )

        switch_names[name_key] = f"Switch entry {index}"
        switch_identity_owners[identity_key] = (f"Switch entry {index}", name)

        effective_prefix = configured_prefix or name
        prefix_key = _ha_prefix_identity(effective_prefix)
        if not prefix_key:
            raise ValueError(f"Switch entry {index} does not produce a usable sensor_prefix identity.")
        previous_prefix = prefix_owners.get(prefix_key)
        if previous_prefix is not None:
            raise ValueError(
                f"Switch entry {index} sensor_prefix '{effective_prefix}' collides with "
                f"{previous_prefix[0]} prefix '{previous_prefix[1]}'."
            )
        owner = f"Switch entry {index}"
        prefix_owners[prefix_key] = (owner, effective_prefix, name_key)
        parent_prefixes[name_key] = prefix_key

    member_keys: dict[tuple[str, str], str] = {}
    for index, raw in enumerate(stack_rows, start=1):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("switch_name") or "").strip()
        member = str(raw.get("member") or raw.get("member_number") or "").strip()
        prefix = str(raw.get("sensor_prefix") or "").strip()
        if not (name or member or prefix):
            continue
        name_key = name.casefold()
        if name_key not in switch_names:
            raise ValueError(
                f"Stack member entry {index} references unknown switch_name '{name}'."
            )
        member_key = (name_key, member)
        previous_member = member_keys.get(member_key)
        if previous_member is not None:
            raise ValueError(
                f"Stack member entry {index} duplicates member {member} for switch '{name}' "
                f"already used by {previous_member}."
            )
        member_keys[member_key] = f"Stack member entry {index}"

        if not prefix:
            continue
        prefix_key = _ha_prefix_identity(prefix)
        if not prefix_key:
            raise ValueError(f"Stack member entry {index} does not produce a usable sensor_prefix identity.")
        previous_prefix = prefix_owners.get(prefix_key)
        if previous_prefix is None:
            prefix_owners[prefix_key] = (f"Stack member entry {index}", prefix, name_key)
            continue

        # Member 1 may deliberately reuse its own parent switch prefix. The
        # parent row is a management target/base identity, not a second set of
        # entities when stack-member prefixes are configured.
        own_parent_alias = (
            member == "1"
            and previous_prefix[2] == name_key
            and parent_prefixes.get(name_key) == prefix_key
        )
        if not own_parent_alias:
            raise ValueError(
                f"Stack member entry {index} sensor_prefix '{prefix}' collides with "
                f"{previous_prefix[0]} prefix '{previous_prefix[1]}'."
            )


def _saved_switch_text(
    row: dict[str, Any],
    primary: str,
    *legacy_aliases: str,
    default: str = "",
) -> str:
    """Resolve one saved switch field without allowing stale aliases to override it."""
    values = [
        str(row.get(key) or "").strip()
        for key in (primary, *legacy_aliases)
        if key in row and str(row.get(key) or "").strip()
    ]
    if not values:
        return default
    selected = values[0]
    if any(value != selected for value in values[1:]):
        raise ValueError(f"{primary} has conflicting saved aliases.")
    return selected


def _effective_discovery_switch_row(raw: Any, index: int) -> dict[str, Any]:
    """Canonicalize one saved row from the current Supervisor options snapshot."""
    if not isinstance(raw, dict):
        raise ValueError(f"Switch entry {index} must be an object.")

    row: dict[str, Any] = {
        "switch_name": _saved_switch_text(
            raw, "switch_name", "switch", "selected_switch", "name"
        ),
        "switch_host": _saved_switch_text(
            raw, "switch_host", "host", "manual_switch_host"
        ),
        "sensor_prefix": _saved_switch_text(
            raw, "sensor_prefix", "entity_prefix", "prefix"
        ),
        "snmp_community": _saved_switch_text(
            raw, "snmp_community", "community"
        ),
        "enabled": raw.get("enabled", "enabled"),
        "walk_mode": _saved_switch_text(
            raw, "walk_mode", "mode", default="targeted"
        ) or "targeted",
        "switch_model": _saved_switch_text(
            raw, "switch_model", "model_override", default="auto"
        ) or "auto",
    }
    if "card_header_title" in raw:
        row["card_header_title"] = _saved_switch_text(raw, "card_header_title")
    if "display_name" in raw or "card_title" in raw:
        row["display_name"] = _saved_switch_text(
            raw, "display_name", "card_title"
        )
    if "output_dir" in raw:
        row["output_dir"] = raw.get("output_dir")
    return _validate_switch_row(row, index)


def _effective_discovery_options(options: dict[str, Any]) -> dict[str, Any]:
    """Return the deterministic effective config consumed by every Discovery run."""
    if not isinstance(options, dict):
        raise RuntimeError("Discovery options must be an object.")
    effective = dict(options)
    rows = options.get("switches")
    if not isinstance(rows, list):
        rows = []
    effective["switches"] = [
        _effective_discovery_switch_row(raw, index)
        for index, raw in enumerate(rows, start=1)
    ]
    _validate_inventory_identities(effective)
    return effective


def _discovery_effective_config_provenance(
    options: dict[str, Any],
    *,
    source: str = "supervisor",
) -> dict[str, Any]:
    """Expose credential-safe proof of the exact switch values used for a run."""
    effective = _effective_discovery_options(options)
    safe_switches: list[dict[str, Any]] = []
    for index, row in enumerate(effective.get("switches", []), start=1):
        if not isinstance(row, dict):
            continue
        community = str(row.get("snmp_community") or "")
        safe_switches.append({
            "index": index,
            "switch_name": str(row.get("switch_name") or ""),
            "switch_host": str(row.get("switch_host") or ""),
            "sensor_prefix": str(row.get("sensor_prefix") or ""),
            "switch_model": str(row.get("switch_model") or "auto"),
            "enabled": str(row.get("enabled") or "enabled"),
            "walk_mode": str(row.get("walk_mode") or "targeted"),
            "credential_configured": bool(community),
        })
    material = {
        "enable_switch_list": str(effective.get("enable_switch_list") or ""),
        "snmp_timeout": str(effective.get("snmp_timeout") or ""),
        "snmp_retries": str(effective.get("snmp_retries") or ""),
        "switches": safe_switches,
    }
    revision = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "source": source,
        "revision": revision,
        "revision_scope": "non_secret_effective_config",
        "credential_evidence": "configured_state_only",
        "switches": safe_switches,
    }


def _validate_discovery_import(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Configuration file must contain a JSON object.")
    if data.get("format") not in DISCOVERY_IMPORT_FORMATS:
        raise ValueError("This is not a supported Switch Vision Discovery export.")
    configuration = data.get("configuration")
    if not isinstance(configuration, dict):
        raise ValueError("The export does not contain a configuration object.")
    unknown = sorted(set(configuration) - DISCOVERY_CONFIG_KEYS)
    if unknown:
        raise ValueError(f"Unsupported configuration field: {unknown[0]}")

    validated = dict(configuration)
    path_fields = {
        "input_path", "snmpwalks_dir", "report_path", "targets_csv", "last_run_summary_path",
        "generated_yaml_path", "generated_card_path", "snmp_log_path",
    }
    for key in path_fields:
        if key in validated:
            validated[key] = _share_path(validated[key], key)
    if "snmpwalks_dir" in validated:
        walk_root = validated["snmpwalks_dir"]
        if not (walk_root == "/share/switch_vision/snmpwalks" or walk_root.startswith("/share/switch_vision/snmpwalks/")):
            raise ValueError("snmpwalks_dir must stay under /share/switch_vision/snmpwalks.")

    for key in {"run_snmp_walks", "enable_switch_list", "parse_all_walks", "generate_snmp2mqtt", "clean_output_before_walk", "backup_retention_enabled"}:
        if key in validated:
            validated[key] = _bool_string(validated[key], key)
    if "snmp_timeout" in validated:
        validated["snmp_timeout"] = _bounded_int_string(validated["snmp_timeout"], "snmp_timeout", 1, 30)
    if "snmp_retries" in validated:
        validated["snmp_retries"] = _bounded_int_string(validated["snmp_retries"], "snmp_retries", 0, 10)
    if "minimum_valid_walk_lines" in validated:
        validated["minimum_valid_walk_lines"] = _bounded_int_string(validated["minimum_valid_walk_lines"], "minimum_valid_walk_lines", 1, 1000000)
    if "backup_retention_count" in validated:
        validated["backup_retention_count"] = int(
            _bounded_int_string(validated["backup_retention_count"], "backup_retention_count", 1, 10)
        )

    switches = validated.get("switches", [])
    if not isinstance(switches, list):
        raise ValueError("switches must be a list.")
    if len(switches) > 256:
        raise ValueError("The configuration contains too many switches.")
    validated["switches"] = [_validate_switch_row(item, index) for index, item in enumerate(switches, start=1)]

    if "autodiscover_networks" in validated:
        validated["autodiscover_networks"] = _validated_autodiscover_networks(validated["autodiscover_networks"])

    stack = validated.get("stack_member_prefixes", [])
    if not isinstance(stack, list):
        raise ValueError("stack_member_prefixes must be a list.")
    if len(stack) > 512:
        raise ValueError("The configuration contains too many stack members.")
    validated["stack_member_prefixes"] = [_validate_stack_row(item, index) for index, item in enumerate(stack, start=1)]
    _validate_inventory_identities(validated)
    return validated


def _configured_switch_count(rows: Any) -> int:
    """Count real configured switch rows, excluding the blank UI placeholder."""
    if not isinstance(rows, list):
        return 0
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if any(
            str(row.get(key) or "").strip()
            for key in ("switch_name", "switch_host")
        ):
            count += 1
    return count


def _import_discovery_options(imported: dict[str, Any]) -> None:
    """Persist imported Discovery configuration through Supervisor only."""
    with _OPTIONS_UPDATE_LOCK:
        current = _self_addon_options()
        merged = _discovery_options_with_required_defaults(current)
        merged.update(imported)
        _validate_inventory_identities(merged)
        create_pre_mutation_backup(current, reason="configuration_import")
        _supervisor_json(
            "/addons/self/options",
            method="POST",
            timeout=20.0,
            payload={"options": merged},
        )
        confirmed = _self_addon_options()
        for key, expected in imported.items():
            if confirmed.get(key) != expected:
                raise RuntimeError(
                    f"Home Assistant did not confirm imported Discovery option '{key}'."
                )
        if "switches" in imported:
            _reconcile_device_added_at(confirmed)
        enforce_retention(confirmed)


_STATE_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "success": None,
    "message": "Ready",
    "log_tail": [],
}

_DISCOVERY_STATE_LOCK = threading.Lock()
_OPTIONS_UPDATE_LOCK = threading.Lock()
_DISCOVERY_PROCESS_LOCK = threading.Lock()
_OPERATION_LOCK = threading.Lock()
_DEVICE_MUTATION_LOCK = threading.Lock()
_DEVICE_STATE_RECONCILE_LOCK = threading.Lock()
_OPERATION_ACTIVE: dict[str, Any] = {"name": None, "started_at": None}
_DISCOVERY_PROCESS: subprocess.Popen[str] | None = None
_DISCOVERY_STOP_REQUESTED = threading.Event()
_DEVICE_STATE_RECONCILE_REQUESTED = 0
_DEVICE_STATE_RECONCILE_RUNNING = False
_DEVICE_STATE_RECONCILE_DEBOUNCE_SECONDS = 0.35
_DEVICE_STATE_RECONCILE_RETRY_SECONDS = 0.20

_DISCOVERY_STATE: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "success": None,
    "message": "Idle / Ready",
    "log_tail": [],
    "stage": "Ready",
    "switch": "",
    "target": "",
    "command": "",
    "activity": "",
    "phase": "idle",
    "snmp2mqtt": {"status": "Not checked", "action": "none", "slug": None, "state": None, "message": "Waiting for Discovery"},
}



class OperationConflict(RuntimeError):
    """Raised when a conflicting Discovery/Support mutation is active."""


def _claim_operation(name: str) -> None:
    with _OPERATION_LOCK:
        active = _OPERATION_ACTIVE.get("name")
        if active:
            raise OperationConflict(
                f"{active} is already running. Wait for it to finish before starting {name}."
            )
        _OPERATION_ACTIVE["name"] = name
        _OPERATION_ACTIVE["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _release_operation(name: str) -> None:
    with _OPERATION_LOCK:
        if _OPERATION_ACTIVE.get("name") == name:
            _OPERATION_ACTIVE["name"] = None
            _OPERATION_ACTIVE["started_at"] = None


@contextmanager
def _exclusive_operation(name: str):
    _claim_operation(name)
    try:
        yield
    finally:
        _release_operation(name)


@contextmanager
def _device_configuration_update(name: str):
    """Serialize short device mutations while a background state apply runs.

    Full Discovery/regeneration operations still block device mutation. A device
    state application is different: it consumes a snapshot of saved state, so
    later device mutations are safe as long as they are serialized and a fresh
    reconciliation pass is queued afterward.
    """
    short_claimed = False
    with _DEVICE_MUTATION_LOCK:
        with _OPERATION_LOCK:
            active = _OPERATION_ACTIVE.get("name")
            if active and active != "Device state application":
                raise OperationConflict(
                    f"{active} is already running. Wait for it to finish before starting {name}."
                )
            if not active:
                _OPERATION_ACTIVE["name"] = name
                _OPERATION_ACTIVE["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                short_claimed = True
        try:
            yield
        finally:
            if short_claimed:
                _release_operation(name)


def _safe_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return default


def _load_options(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _support_settings_from_options(options: dict[str, Any]) -> dict[str, Any]:
    """Return Support My Switch settings without exposing unrelated options."""
    contributor_type = str(options.get("support_contributor_type") or "anonymous")
    if contributor_type not in {"anonymous", "first_name", "full_name", "github", "forum"}:
        contributor_type = "anonymous"
    contributor_value = (
        str(options.get("support_contributor_value") or "")
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()[:120]
    )
    return {
        "mask_management_ips": _safe_bool(options.get("support_mask_management_ips"), True),
        "mask_mac_addresses": _safe_bool(options.get("support_mask_mac_addresses"), True),
        "mask_hostnames": _safe_bool(options.get("support_mask_hostnames"), True),
        "mask_vlan_names": _safe_bool(options.get("support_mask_vlan_names"), False),
        "mask_interface_descriptions": _safe_bool(options.get("support_mask_interface_descriptions"), False),
        "contributor_type": contributor_type,
        "contributor_value": contributor_value,
    }


def _defaults(options_file: Path) -> dict[str, Any]:
    return _support_settings_from_options(_load_options(options_file))


def _zip_member_json(archive: Path, suffix: str) -> Any:
    try:
        with zipfile.ZipFile(archive) as zf:
            candidates = [name for name in zf.namelist() if name.endswith(suffix)]
            if not candidates:
                return None
            return json.loads(zf.read(candidates[0]).decode("utf-8"))
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _latest_contribution(contributions_dir: Path) -> dict[str, Any] | None:
    archives = sorted(
        (
            path for path in contributions_dir.glob("Switch_Vision_Contribution_SV-*.zip")
            if path.is_file() and not path.is_symlink()
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ) if contributions_dir.is_dir() else []
    if not archives:
        return None
    archive = archives[0]
    stem = archive.stem
    email_path = archive.with_suffix(".eml")
    actions_path = archive.with_name(f"{stem}_Actions.html")
    manifest = _zip_member_json(archive, "/MANIFEST.json") or {}
    devices = _zip_member_json(archive, "/DEVICE_SUMMARY.json") or []
    privacy = manifest.get("privacy_options") or {}
    processing = manifest.get("sanitization_processing") or {}
    evidence = manifest.get("evidence") or {}
    return {
        "contribution_id": manifest.get("contribution_id") or "Unknown",
        "version": manifest.get("switch_vision_version") or "Unknown",
        "quality": manifest.get("bundle_quality") or "Unknown",
        "ready_to_send": bool(manifest.get("ready_to_send")),
        "created_at": manifest.get("created_at") or "",
        "archive": archive.name,
        "archive_size": archive.stat().st_size,
        "email": email_path.name if email_path.is_file() and not email_path.is_symlink() else None,
        "actions": actions_path.name if actions_path.is_file() and not actions_path.is_symlink() else None,
        "devices": devices if isinstance(devices, list) else [],
        "privacy": privacy if isinstance(privacy, dict) else {},
        "processing": processing if isinstance(processing, dict) else {},
        "evidence": evidence if isinstance(evidence, dict) else {},
    }


def _contribution_history(contributions_dir: Path) -> list[dict[str, Any]]:
    archives = sorted(
        (
            path for path in contributions_dir.glob("Switch_Vision_Contribution_SV-*.zip")
            if path.is_file() and not path.is_symlink()
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ) if contributions_dir.is_dir() else []
    items: list[dict[str, Any]] = []
    for archive in archives:
        stem = archive.stem
        email_path = archive.with_suffix(".eml")
        actions_path = archive.with_name(f"{stem}_Actions.html")
        manifest = _zip_member_json(archive, "/MANIFEST.json") or {}
        devices = _zip_member_json(archive, "/DEVICE_SUMMARY.json") or []
        models: list[str] = []
        if isinstance(devices, list):
            for row in devices:
                if not isinstance(row, dict):
                    continue
                model = str(row.get("model") or row.get("sys_descr") or "").strip()
                if model and model not in models:
                    models.append(model)
        items.append({
            "contribution_id": str(manifest.get("contribution_id") or "Unknown"),
            "version": str(manifest.get("switch_vision_version") or "Unknown"),
            "quality": str(manifest.get("bundle_quality") or "Unknown"),
            "ready_to_send": bool(manifest.get("ready_to_send")),
            "created_at": str(manifest.get("created_at") or ""),
            "modified_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(archive.stat().st_mtime)
            ),
            "archive": archive.name,
            "archive_size": archive.stat().st_size,
            "email": email_path.name if email_path.is_file() and not email_path.is_symlink() else None,
            "actions": actions_path.name if actions_path.is_file() and not actions_path.is_symlink() else None,
            "device_count": len(devices) if isinstance(devices, list) else 0,
            "models": models[:12],
        })
    return items


def _state_snapshot() -> dict[str, Any]:
    with _STATE_LOCK:
        return json.loads(json.dumps(_STATE))


def _set_state(**updates: Any) -> None:
    with _STATE_LOCK:
        _STATE.update(updates)



def _discovery_state_snapshot() -> dict[str, Any]:
    with _DISCOVERY_STATE_LOCK:
        return json.loads(json.dumps(_DISCOVERY_STATE))


def _set_discovery_state(**updates: Any) -> None:
    with _DISCOVERY_STATE_LOCK:
        _DISCOVERY_STATE.update(updates)


def _reset_current_discovery_debug() -> None:
    """Start a fresh credential-sanitized debug session for one operation."""
    DEFAULT_CURRENT_DISCOVERY_DEBUG.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_CURRENT_DISCOVERY_DEBUG.write_text("", encoding="utf-8")
    os.chmod(DEFAULT_CURRENT_DISCOVERY_DEBUG, 0o600)


def _append_current_discovery_debug(value: Any) -> str:
    """Append one sanitized line and return the browser-safe text."""
    safe = sanitize_debug_text(value).replace("\x00", "")
    DEFAULT_CURRENT_DISCOVERY_DEBUG.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_CURRENT_DISCOVERY_DEBUG.open("a", encoding="utf-8") as handle:
        handle.write(safe + "\n")
    try:
        os.chmod(DEFAULT_CURRENT_DISCOVERY_DEBUG, 0o600)
    except OSError:
        pass
    return safe


def _current_discovery_debug_snapshot() -> dict[str, Any]:
    state = _discovery_state_snapshot()
    try:
        text = DEFAULT_CURRENT_DISCOVERY_DEBUG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    # Sanitize again at the browser boundary as defence in depth.
    safe_text = sanitize_debug_text(text).replace("\x00", "")
    return {
        "mode": state.get("mode") or "discovery",
        "running": bool(state.get("running")),
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
        "text": safe_text,
        "line_count": len(safe_text.splitlines()),
    }


class _DiscoveryDebugLines(list[str]):
    """Operation-local lines that are mirrored into the full sanitized session."""

    def append(self, value: Any) -> None:
        super().append(_append_current_discovery_debug(value))


def _parse_status_marker(line: str) -> dict[str, str] | None:
    if not line.startswith("SV_STATUS|"):
        return None
    result: dict[str, str] = {}
    for part in line.split("|")[1:]:
        key, sep, value = part.partition("=")
        if sep and key:
            result[key] = value
    return result


def _ensure_runtime_paths() -> None:
    """Create writable runtime paths required by Discovery and support bundles."""
    DEFAULT_SHARE_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_CONTRIBUTIONS_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_DISCOVERY_LOG.touch(exist_ok=True)


def _request_discovery_stop() -> bool:
    """Request a stop of the active Discovery process group."""
    if not _discovery_state_snapshot().get("running"):
        return False

    _DISCOVERY_STOP_REQUESTED.set()
    _set_discovery_state(
        message="Stopping Discovery",
        stage="Stopping Discovery",
        activity="Waiting for the current Discovery command to stop",
        command="Stop requested",
        phase="stopping",
    )

    with _DISCOVERY_PROCESS_LOCK:
        process = _DISCOVERY_PROCESS

    if process is not None and process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            process.terminate()
    return True


def _generate_automatic_support_bundle(
    settings: dict[str, Any],
    lines: list[str],
    *,
    evidence_quality: str = "complete",
    discovery_result: str = "success",
    snmp2mqtt_handoff: str = "verified",
) -> bool:
    """Capture an automatic contribution with the exact Discovery outcome."""
    if not DEFAULT_SUPPORT_SCRIPT.is_file():
        lines.append(
            "Automatic Support My Switch capture skipped because the support backend is unavailable."
        )
        return False
    DEFAULT_CONTRIBUTIONS_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "SWITCH_VISION_DISCOVERY_VERSION": os.environ.get(
            "SWITCH_VISION_DISCOVERY_VERSION",
            "unknown",
        ),
        "SUPPORT_MASK_MANAGEMENT_IPS": str(settings["mask_management_ips"]).lower(),
        "SUPPORT_MASK_MAC_ADDRESSES": str(settings["mask_mac_addresses"]).lower(),
        "SUPPORT_MASK_HOSTNAMES": str(settings["mask_hostnames"]).lower(),
        "SUPPORT_MASK_VLAN_NAMES": str(settings["mask_vlan_names"]).lower(),
        "SUPPORT_MASK_INTERFACE_DESCRIPTIONS": str(
            settings["mask_interface_descriptions"]
        ).lower(),
        "SUPPORT_CONTRIBUTOR_TYPE": str(settings["contributor_type"]),
        "SUPPORT_CONTRIBUTOR_VALUE": str(settings["contributor_value"]),
        "CONTRIBUTIONS_DIR": str(DEFAULT_CONTRIBUTIONS_DIR),
        "SUPPORT_EVIDENCE_QUALITY": evidence_quality,
        "SUPPORT_DISCOVERY_RESULT": discovery_result,
        "SUPPORT_SNMP2MQTT_HANDOFF": snmp2mqtt_handoff,
    })
    try:
        result = subprocess.run(
            [str(DEFAULT_SUPPORT_SCRIPT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            env=env,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        lines.append(
            "Automatic Support My Switch capture failed after the SNMP2MQTT "
            f"handoff check: {type(exc).__name__}."
        )
        return False
    if result.returncode != 0:
        lines.append(
            "Automatic Support My Switch capture failed after the SNMP2MQTT "
            f"handoff check with exit code {result.returncode}."
        )
        return False
    lines.append(
        "Automatic Support My Switch contribution captured after the "
        "SNMP2MQTT handoff check."
    )
    return True


def _run_discovery(discovery_script: Path, mode: str = "discovery") -> None:
    global _DISCOVERY_PROCESS
    log_path = DEFAULT_DISCOVERY_LOG
    lines: list[str] = _DiscoveryDebugLines()
    regenerate_yaml_only = mode == "regenerate_yaml"
    regenerate_card_only = mode == "regenerate_card"
    apply_device_state = mode == "apply_device_state"
    regenerate_only = regenerate_yaml_only or regenerate_card_only or apply_device_state
    if regenerate_card_only:
        # Card-only regeneration must not inspect or mutate SNMP2MQTT handoff
        # bookkeeping. The live YAML/service plane is intentionally untouched.
        generated_yaml_previous_mtime = None
        generated_yaml_previous_topics: list[str] = []
    else:
        generated_yaml_previous_mtime = DEFAULT_GENERATED_SNMP2MQTT.stat().st_mtime if DEFAULT_GENERATED_SNMP2MQTT.is_file() else None
        generated_yaml_previous_topics = _remember_current_snmp2mqtt_topics() if generated_yaml_previous_mtime is not None else _load_snmp2mqtt_retirement_topics()
    if regenerate_card_only:
        operation_name = "Dashboard Card YAML regeneration"
        preparing_message = "Preparing Dashboard Card YAML regeneration"
        preparing_activity = "Loading saved Discovery state and stored walks"
        waiting_message = "Waiting for Dashboard Card YAML regeneration to complete"
    elif regenerate_yaml_only:
        operation_name = "SNMP2MQTT YAML regeneration"
        preparing_message = "Preparing SNMP2MQTT YAML regeneration"
        preparing_activity = "Loading saved Discovery data and SNMP walks"
        waiting_message = "Waiting for YAML regeneration to complete"
    elif apply_device_state:
        operation_name = "Device state application"
        preparing_message = "Applying device state"
        preparing_activity = "Updating SNMP polling and dashboard from saved state"
        waiting_message = "Waiting for device state application to complete"
    else:
        operation_name = "Discovery"
        preparing_message = "Preparing Discovery"
        preparing_activity = "Validating configured switches"
        waiting_message = "Waiting for Discovery to complete"
    _reset_current_discovery_debug()
    _set_discovery_state(
        running=True,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        finished_at=None,
        success=None,
        message=preparing_message,
        log_tail=[],
        stage=preparing_message,
        mode=mode,
        switch="",
        target="",
        command="",
        activity=preparing_activity,
        phase="preparing",
        snmp2mqtt=(
            {
                "status": "Not touched",
                "action": "none",
                "slug": None,
                "state": None,
                "message": "SNMP2MQTT is outside Dashboard Card YAML regeneration.",
            }
            if regenerate_card_only
            else {"status": "Waiting", "action": "none", "slug": None, "state": None, "message": waiting_message}
        ),
    )
    try:
        _ensure_runtime_paths()
        if regenerate_card_only:
            auto_bundle_settings = None
            options_snapshot = _write_dashboard_card_regeneration_options_snapshot()
        elif regenerate_yaml_only:
            auto_bundle_settings = None
            options_snapshot = _write_snmp2mqtt_regeneration_options_snapshot()
        elif apply_device_state:
            auto_bundle_settings = None
            options_snapshot = _write_device_state_application_options_snapshot()
        else:
            authoritative_options = _self_addon_options()
            auto_bundle_settings = (
                _support_settings_from_options(authoritative_options)
                if _safe_bool(
                    authoritative_options.get("generate_support_my_switch_bundle"),
                    True,
                )
                else None
            )
            options_snapshot = _write_authoritative_discovery_options_snapshot(
                options=authoritative_options,
            )
            _set_discovery_state(
                effective_config=_discovery_effective_config_provenance(
                    authoritative_options,
                    source="supervisor",
                )
            )
        discovery_env = os.environ.copy()
        discovery_env["SWITCH_VISION_OPTIONS_FILE"] = str(options_snapshot)
        if regenerate_card_only:
            discovery_env["SWITCH_VISION_CAPABILITIES_DIR"] = "/tmp/switch_vision_regenerate_card_capabilities"
        elif regenerate_yaml_only:
            discovery_env["SWITCH_VISION_CAPABILITIES_DIR"] = "/tmp/switch_vision_regenerate_capabilities"
        elif apply_device_state:
            discovery_env["SWITCH_VISION_CAPABILITIES_DIR"] = "/tmp/switch_vision_device_state_capabilities"
        with log_path.open("a", encoding="utf-8") as log_file:
            action_label = operation_name
            log_file.write(f"\n=== {action_label} started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            log_file.write(
                "Discovery configuration: stored-state regeneration snapshot\n"
                if regenerate_only
                else "Discovery configuration: authoritative Supervisor snapshot\n"
            )
            process = subprocess.Popen(
                [str(discovery_script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=discovery_env,
                start_new_session=True,
            )
            with _DISCOVERY_PROCESS_LOCK:
                _DISCOVERY_PROCESS = process
            if _DISCOVERY_STOP_REQUESTED.is_set() and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            assert process.stdout is not None
            for line in process.stdout:
                clean = line.rstrip()
                log_file.write(line)
                log_file.flush()
                marker = _parse_status_marker(clean)
                if marker is not None:
                    if _DISCOVERY_STOP_REQUESTED.is_set():
                        _set_discovery_state(
                            message="Stopping Discovery",
                            stage="Stopping Discovery",
                            activity="Waiting for the current Discovery command to stop",
                            command="Stop requested",
                            phase="stopping",
                        )
                    else:
                        _set_discovery_state(
                            stage=marker.get("stage", "Discovery"),
                            switch=marker.get("switch", ""),
                            target=marker.get("target", ""),
                            command=marker.get("command", ""),
                            activity=marker.get("activity", ""),
                            message=marker.get("stage", "Discovery running"),
                            phase="running",
                        )
                    continue
                debug_line = clean.removeprefix("SV_DEBUG|")
                lines.append(debug_line)
                _set_discovery_state(log_tail=lines[-300:])
            return_code = process.wait()
        if _DISCOVERY_STOP_REQUESTED.is_set():
            stopped_label = (
                "Dashboard Card YAML regeneration"
                if regenerate_card_only
                else (
                    "SNMP2MQTT YAML regeneration"
                    if regenerate_yaml_only
                    else ("Device state application" if apply_device_state else "Discovery")
                )
            )
            lines.append(f"{stopped_label} stopped by user request.")
            _set_discovery_state(
                success=None,
                message=f"{stopped_label} stopped",
                stage="Stopped",
                activity=f"{stopped_label} stopped by user",
                command="",
                phase="stopped",
                log_tail=lines[-300:],
                snmp2mqtt={"status": "Not started", "action": "none", "slug": None, "state": None, "message": "Discovery was stopped before completion"},
            )
            return
        result_markers = [line for line in lines if line.startswith("SV_RESULT|")]
        soft_warning_result = any("warnings=true" in line for line in result_markers)
        soft_degraded_result = any("degraded=true" in line for line in result_markers)
        snmp2mqtt_required = not any(
            "snmp2mqtt_required=false" in line for line in result_markers
        )
        degraded_result = return_code == 10 or soft_degraded_result
        partial_result = return_code == 11 or soft_warning_result
        if return_code not in {0, 10, 11}:
            raise RuntimeError(f"{operation_name} exited with code {return_code}.")
        if regenerate_card_only:
            card_warning = degraded_result or partial_result
            card_message = (
                "Dashboard Card YAML regeneration completed with warnings from stored evidence."
                if card_warning
                else "Dashboard Card YAML regenerated from saved Discovery state and stored walks."
            )
            if card_warning:
                lines.append(card_message)
            snmp2mqtt_result = {
                "status": "Not touched",
                "action": "none",
                "slug": None,
                "state": None,
                "activation_verified": False,
                "handoff_failed": False,
                "degraded": card_warning,
                "message": "SNMP2MQTT was not started or restarted during Dashboard Card YAML regeneration.",
            }
            _set_discovery_state(
                stage="Complete with warnings" if card_warning else "Finalizing Dashboard Card YAML",
                activity=card_message,
                command="",
                phase="running",
                snmp2mqtt=snmp2mqtt_result,
            )
        elif not snmp2mqtt_required:
            snmp2mqtt_result = {
                "status": "Not required",
                "action": "not_required",
                "slug": None,
                "state": None,
                "activation_verified": False,
                "handoff_failed": False,
                "degraded": False,
                "message": "SNMP2MQTT is not required for this API/UniFi-only Discovery run.",
            }
            _set_discovery_state(
                stage="Finalizing API/UniFi-only Discovery",
                activity=snmp2mqtt_result["message"],
                command="",
                phase="running",
                snmp2mqtt=snmp2mqtt_result,
            )
        elif degraded_result:
            warning_message = (
                f"{operation_name} completed with warnings; validated physical evidence was preserved "
                "and the SNMP2MQTT handoff was blocked."
            )
            lines.append(warning_message)
            snmp2mqtt_result = {
                "status": "Warning",
                "action": "blocked_degraded",
                "slug": None,
                "state": None,
                "activation_verified": False,
                "handoff_failed": False,
                "degraded": True,
                "message": warning_message,
            }
            _set_discovery_state(
                stage="Complete with warnings",
                activity=warning_message,
                command="SNMP2MQTT handoff blocked",
                phase="running",
                snmp2mqtt=snmp2mqtt_result,
            )
        else:
            _set_discovery_state(stage="Starting SNMP2MQTT", activity="Validating generated SNMP2MQTT YAML", command="Supervisor app action", phase="running")
            snmp2mqtt_result = _ensure_snmp2mqtt_running(lines, generated_yaml_previous_mtime, generated_yaml_previous_topics)
        if auto_bundle_settings is not None:
            _set_discovery_state(
                stage="Capturing Support My Switch",
                activity="Capturing diagnostics after the SNMP2MQTT handoff check",
                command="Support My Switch",
                phase="running",
            )
            bundle_captured = _generate_automatic_support_bundle(
                auto_bundle_settings,
                lines,
                evidence_quality="degraded" if (degraded_result or partial_result) else "complete",
                discovery_result="complete_with_warnings" if (degraded_result or partial_result) else "success",
                snmp2mqtt_handoff=(
                    "not_required"
                    if not snmp2mqtt_required
                    else (
                        "blocked_degraded"
                        if degraded_result
                        else ("failed" if snmp2mqtt_result.get("handoff_failed") else "verified")
                    )
                ),
            )
            snmp2mqtt_result["support_bundle_after_handoff"] = (
                "captured" if bundle_captured else "failed"
            )
        handoff_warning = bool(snmp2mqtt_result.get("handoff_failed"))
        if handoff_warning:
            warning_message = str(
                snmp2mqtt_result.get("message")
                or "SNMP2MQTT generated-configuration handoff could not be verified."
            )
            lines.append(
                "Discovery completed successfully; SNMP2MQTT handoff warning: " + warning_message
            )
        operation_warning = degraded_result or partial_result or handoff_warning
        if regenerate_card_only:
            auto_message = (
                "Dashboard Card YAML regeneration complete with warnings"
                if operation_warning
                else "Dashboard Card YAML regeneration complete"
            )
        elif regenerate_yaml_only:
            auto_message = (
                "SNMP2MQTT YAML regeneration complete with warnings"
                if operation_warning
                else "SNMP2MQTT YAML regeneration complete"
            )
        elif apply_device_state:
            auto_message = (
                "Device state applied with warnings"
                if operation_warning
                else "Device state applied"
            )
        else:
            auto_message = (
                "Discovery complete with warnings"
                if operation_warning
                else "Discovery complete"
            )
        _set_discovery_state(
            success=True,
            message=auto_message,
            stage="Complete with warnings" if operation_warning else "Complete",
            activity=auto_message if regenerate_card_only else (snmp2mqtt_result.get("message") or auto_message),
            command="",
            phase="complete",
            log_tail=lines[-300:],
            snmp2mqtt=snmp2mqtt_result,
        )
    except Exception as exc:
        lines.append(str(exc))
        _set_discovery_state(success=False, message=str(exc), log_tail=lines[-300:], phase="failed")
        try:
            with log_path.open("a", encoding="utf-8") as log_file:
                traceback.print_exc(file=log_file)
        except OSError:
            pass
    finally:
        with _DISCOVERY_PROCESS_LOCK:
            _DISCOVERY_PROCESS = None
        _DISCOVERY_STOP_REQUESTED.clear()
        _set_discovery_state(running=False, finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        if not apply_device_state:
            try:
                append_discovery_history(_discovery_state_snapshot())
            except Exception:  # History is non-authoritative and must not block operation cleanup.
                pass
        _release_operation(operation_name)





def _start_dashboard_card_regeneration(discovery_script: Path = DEFAULT_DISCOVERY_SCRIPT) -> dict[str, Any]:
    """Queue the existing stored-state card regeneration path exactly once."""
    operation_name = "Dashboard Card YAML regeneration"
    _claim_operation(operation_name)
    _DISCOVERY_STOP_REQUESTED.clear()
    _set_discovery_state(
        running=True,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        finished_at=None,
        success=None,
        message="Preparing Dashboard Card YAML regeneration",
        log_tail=[],
        stage="Preparing Dashboard Card YAML regeneration",
        switch="",
        target="",
        command="",
        activity="Applying saved device state and order",
        phase="preparing",
        mode="regenerate_card",
        snmp2mqtt={
            "status": "Not touched",
            "action": "none",
            "slug": None,
            "state": None,
            "message": "SNMP2MQTT will not be started or restarted for Card YAML regeneration",
        },
    )
    thread = threading.Thread(
        target=_run_discovery,
        args=(discovery_script, "regenerate_card"),
        daemon=True,
    )
    try:
        thread.start()
    except Exception:
        _release_operation(operation_name)
        raise
    return {"started": True, "mode": "regenerate_card"}


def _device_state_application_worker(discovery_script: Path) -> None:
    """Converge SNMP polling to the newest saved state, coalescing rapid changes."""
    global _DEVICE_STATE_RECONCILE_RUNNING
    operation_name = "Device state application"
    quiesced = False
    try:
        while True:
            # A short debounce collapses a burst of UI changes into one expensive
            # stored-state regeneration. Changes made during a running pass bump
            # the generation and automatically trigger one more latest-state pass.
            time.sleep(_DEVICE_STATE_RECONCILE_DEBOUNCE_SECONDS)
            with _DEVICE_STATE_RECONCILE_LOCK:
                target_generation = _DEVICE_STATE_RECONCILE_REQUESTED

            while True:
                try:
                    _claim_operation(operation_name)
                    break
                except OperationConflict:
                    time.sleep(_DEVICE_STATE_RECONCILE_RETRY_SECONDS)

            _DISCOVERY_STOP_REQUESTED.clear()
            _run_discovery(discovery_script, "apply_device_state")

            # A pass may have rendered an older SNMP snapshot while newer UI
            # changes were being saved. Re-project the dashboard from the current
            # authoritative state immediately before deciding whether another pass
            # is required, so stale work cannot leave a stale visible card.
            projection_error: OSError | RuntimeError | ValueError | None = None
            try:
                _apply_saved_device_order_to_dashboard()
            except (OSError, RuntimeError, ValueError) as exc:
                projection_error = exc

            with _DEVICE_STATE_RECONCILE_LOCK:
                if _DEVICE_STATE_RECONCILE_REQUESTED == target_generation:
                    # Publish the final visible-card result before quiescence so a
                    # later request cannot be overwritten by this worker's stale
                    # completion state.
                    if projection_error is not None:
                        message = (
                            "Device state polling applied, but the dashboard refresh failed: "
                            f"{projection_error}"
                        )
                        _set_discovery_state(
                            success=False,
                            message=message,
                            stage="Dashboard refresh failed",
                            activity=message,
                            phase="failed",
                        )
                    try:
                        append_discovery_history(_discovery_state_snapshot())
                    except Exception:
                        # History is non-authoritative and must not block device
                        # state cleanup or a later state-change request.
                        pass
                    # Publish quiescence atomically with the generation check. A
                    # new request after this point starts a new worker; this worker
                    # must not clear that newer worker's running flag or operation.
                    _DEVICE_STATE_RECONCILE_RUNNING = False
                    quiesced = True
                    return
    finally:
        if not quiesced:
            # Unexpected worker failure: no replacement worker can have started
            # while our running flag is still true, so cleanup is safe here.
            _release_operation(operation_name)
            with _DEVICE_STATE_RECONCILE_LOCK:
                _DEVICE_STATE_RECONCILE_RUNNING = False


def _start_device_state_application(discovery_script: Path = DEFAULT_DISCOVERY_SCRIPT) -> dict[str, Any]:
    """Queue/coalesce saved SNMP state application without blocking device controls."""
    global _DEVICE_STATE_RECONCILE_REQUESTED, _DEVICE_STATE_RECONCILE_RUNNING
    with _DEVICE_STATE_RECONCILE_LOCK:
        _DEVICE_STATE_RECONCILE_REQUESTED += 1
        generation = _DEVICE_STATE_RECONCILE_REQUESTED
        if _DEVICE_STATE_RECONCILE_RUNNING:
            return {
                "started": False,
                "queued": True,
                "coalesced": True,
                "generation": generation,
                "mode": "apply_device_state",
            }
        _DEVICE_STATE_RECONCILE_RUNNING = True
        thread = threading.Thread(
            target=_device_state_application_worker,
            args=(discovery_script,),
            daemon=True,
        )
        try:
            thread.start()
        except Exception:
            _DEVICE_STATE_RECONCILE_RUNNING = False
            raise
    return {
        "started": True,
        "queued": True,
        "coalesced": False,
        "generation": generation,
        "mode": "apply_device_state",
    }


def _read_supervisor_token() -> str:
    """Return the Supervisor bearer token supplied to the app container."""
    for name in ("SUPERVISOR_TOKEN", "HASSIO_TOKEN"):
        token = os.environ.get(name, "").strip()
        if token:
            return token

    # s6 exposes container environment values as files on some base-image versions.
    for path in (
        Path("/run/s6/container_environment/SUPERVISOR_TOKEN"),
        Path("/var/run/s6/container_environment/SUPERVISOR_TOKEN"),
        Path("/run/s6/container_environment/HASSIO_TOKEN"),
        Path("/var/run/s6/container_environment/HASSIO_TOKEN"),
    ):
        try:
            token = path.read_text(encoding="utf-8").strip().strip("\x00")
        except OSError:
            continue
        if token:
            return token
    return ""


def _supervisor_json(
    path: str, *, method: str = "GET", timeout: float = 12.0, payload: Any | None = None
) -> dict[str, Any]:
    token = _read_supervisor_token()
    if not token:
        raise RuntimeError(
            "Supervisor API token is unavailable. Rebuild/reinstall the Discovery app "
            "with hassio_api: true and hassio_role: manager."
        )
    body = None
    if method != "GET":
        body = json.dumps({} if payload is None else payload).encode("utf-8")
    request = Request(
        f"http://supervisor{path}",
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=body,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supervisor API returned HTTP {exc.code}: {detail[:240]}") from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Supervisor API request failed: {exc}") from exc
    if isinstance(payload, dict) and payload.get("result") == "error":
        raise RuntimeError(str(payload.get("message") or "Supervisor API reported an error."))
    return payload if isinstance(payload, dict) else {}


INSTALLER_MAINTENANCE_SCHEMA = "switch-vision-installer-maintenance-v1"
_INSTALLER_MAINTENANCE_LOCK = threading.Lock()


def _installer_maintenance_request(
    action: str,
    *,
    response_path: Path = DEFAULT_INSTALLER_MAINTENANCE_RESPONSE,
    timeout: float = 5.0,
    **fields: Any,
) -> dict[str, Any]:
    """Send one narrow Maintenance command to Installer through Supervisor STDIN."""
    if action not in {
        "status",
        "set_policy",
        "create_backup",
        "validate_backup",
        "restore_backup",
        "delete_backup",
        "apply_retention",
    }:
        raise ValueError("Unsupported Installer maintenance action.")

    with _INSTALLER_MAINTENANCE_LOCK:
        links = _installed_switch_vision_app_links()
        installer = links.get("installer") if isinstance(links, dict) else None
        if not isinstance(installer, dict) or not installer.get("found"):
            raise RuntimeError(
                "Switch Vision Installer is not installed. Install or update Installer "
                "before managing recovery backups from Maintenance."
            )
        slug = str(installer.get("slug") or "").strip()
        if not slug:
            raise RuntimeError("Switch Vision Installer slug could not be resolved.")

        info_path = f"/addons/{quote(slug, safe='')}/info"
        info_payload = _supervisor_json(info_path)
        info = (
            info_payload.get("data")
            if isinstance(info_payload.get("data"), dict)
            else info_payload
        )
        if not isinstance(info, dict) or info.get("stdin") is not True:
            raise RuntimeError(
                "Switch Vision Installer 2.1.31 or later is required for "
                "Maintenance backup controls."
            )

        state = str(info.get("state") or "").strip().lower()
        if state not in {"started", "running"}:
            _supervisor_json(
                f"/addons/{quote(slug, safe='')}/start",
                method="POST",
                timeout=30.0,
            )
            start_deadline = time.monotonic() + 20.0
            while time.monotonic() < start_deadline:
                refreshed_payload = _supervisor_json(info_path)
                refreshed = (
                    refreshed_payload.get("data")
                    if isinstance(refreshed_payload.get("data"), dict)
                    else refreshed_payload
                )
                state = (
                    str(refreshed.get("state") or "").strip().lower()
                    if isinstance(refreshed, dict)
                    else ""
                )
                if state in {"started", "running"}:
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError(
                    "Switch Vision Installer did not reach a running state after "
                    "Maintenance requested its start."
                )

        request_id = f"maintenance-{time.monotonic_ns()}"
        command = {
            "schema": INSTALLER_MAINTENANCE_SCHEMA,
            "request_id": request_id,
            "action": action,
            **fields,
        }
        _supervisor_json(
            f"/addons/{quote(slug, safe='')}/stdin",
            method="POST",
            payload=command,
        )

        deadline = time.monotonic() + max(0.5, min(float(timeout), 15.0))
        while time.monotonic() < deadline:
            try:
                if response_path.is_symlink():
                    raise RuntimeError(
                        "Installer Maintenance response path must not be a symbolic link."
                    )
                if not response_path.is_file():
                    time.sleep(0.05)
                    continue
                if response_path.stat().st_size > 1024 * 1024:
                    raise RuntimeError("Installer Maintenance response is unexpectedly large.")
                document = json.loads(response_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                time.sleep(0.05)
                continue
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"Installer Maintenance response could not be read safely: {exc}"
                ) from exc

            if not isinstance(document, dict):
                raise RuntimeError("Installer Maintenance response is invalid.")
            if (
                document.get("schema") != INSTALLER_MAINTENANCE_SCHEMA
                or document.get("request_id") != request_id
            ):
                time.sleep(0.05)
                continue
            if document.get("ok") is not True:
                raise RuntimeError(
                    str(document.get("error") or "Installer Maintenance request failed.")
                )
            return document

        raise RuntimeError(
            "Timed out waiting for Switch Vision Installer Maintenance response."
        )


def _installer_maintenance_browser_request(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Installer backup request must contain a JSON object.")
    action = str(data.get("action") or "").strip()
    if action == "set_policy":
        automatic = data.get("automatic_retention")
        count = data.get("retention_count")
        if not isinstance(automatic, bool):
            raise ValueError("Automatic retention must be true or false.")
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10:
            raise ValueError("Retained backup count must be between 1 and 10.")
        return _installer_maintenance_request(
            action,
            automatic_retention=automatic,
            retention_count=count,
        )
    if action in {"validate_backup", "restore_backup", "delete_backup"}:
        name = data.get("name")
        if not isinstance(name, str) or not name or len(name) > 160 or Path(name).name != name:
            raise ValueError("Backup name is invalid.")
        return _installer_maintenance_request(action, name=name)
    if action in {"create_backup", "apply_retention"}:
        return _installer_maintenance_request(action)
    raise ValueError("Unsupported Installer backup request.")


def _self_addon_options() -> dict[str, Any]:
    """Return the authoritative Discovery options from Home Assistant Supervisor."""
    payload = _supervisor_json("/addons/self/info")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    options = data.get("options") if isinstance(data, dict) else None
    if not isinstance(options, dict):
        raise RuntimeError("Home Assistant Supervisor did not expose the Discovery app options.")
    return dict(options)


def _write_authoritative_discovery_options_snapshot(
    destination: Path = Path("/tmp/switch_vision_discovery_options.json"),
    *,
    options: dict[str, Any] | None = None,
) -> Path:
    """Write one fail-closed Supervisor snapshot for the shell Discovery stage.

    Automatic Support My Switch capture is suppressed in this run-local copy.
    The Hub creates that bundle only after the SNMP2MQTT handoff has been checked.
    """
    source_options = dict(options) if isinstance(options, dict) else _self_addon_options()
    snapshot_options = _effective_discovery_options(source_options)
    snapshot_options["generate_support_my_switch_bundle"] = False
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(snapshot_options, indent=2) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(destination)
        os.chmod(destination, 0o600)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(f"Could not prepare the authoritative Discovery configuration snapshot: {exc}") from exc
    return destination


def _write_snmp2mqtt_regeneration_options_snapshot(
    destination: Path = Path("/tmp/switch_vision_regenerate_options.json"),
) -> Path:
    """Prepare a safe stored-walk-only snapshot for SNMP2MQTT YAML regeneration."""
    options = _self_addon_options()
    _validate_inventory_identities(options)
    regenerated = dict(options)
    rows = regenerated.get("switches")
    has_inventory = isinstance(rows, list) and any(
        isinstance(row, dict)
        and (str(row.get("switch_name") or "").strip() or str(row.get("switch_host") or "").strip())
        for row in rows
    )
    if has_inventory:
        regenerated["enable_switch_list"] = True
    regenerated["run_snmp_walks"] = False
    regenerated["run_live_snmpwalk"] = False
    regenerated["clean_output_before_walk"] = False
    regenerated["parse_all_walks"] = True
    regenerated["generate_snmp2mqtt"] = True
    regenerated["generate_support_my_switch_bundle"] = False
    regenerated["report_path"] = "/tmp/switch_vision_regenerate_report.txt"
    regenerated["last_run_summary_path"] = "/tmp/switch_vision_regenerate_summary.txt"
    regenerated["generated_card_path"] = "/tmp/switch_vision_regenerate_dashboard.yaml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(regenerated, indent=2) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(destination)
        os.chmod(destination, 0o600)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(f"Could not prepare SNMP2MQTT regeneration configuration: {exc}") from exc
    return destination


def _write_device_state_application_options_snapshot(
    destination: Path = Path("/tmp/switch_vision_apply_device_state_options.json"),
) -> Path:
    """Apply saved enable/disable state to SNMP polling and dashboard outputs without new walks."""
    options = _effective_discovery_options(_self_addon_options())
    _validate_inventory_identities(options)
    regenerated = dict(options)
    rows = regenerated.get("switches")
    has_inventory = isinstance(rows, list) and any(
        isinstance(row, dict)
        and (str(row.get("switch_name") or "").strip() or str(row.get("switch_host") or "").strip())
        for row in rows
    )
    if has_inventory:
        regenerated["enable_switch_list"] = True
    regenerated["run_snmp_walks"] = False
    regenerated["run_live_snmpwalk"] = False
    regenerated["clean_output_before_walk"] = False
    regenerated["parse_all_walks"] = True
    regenerated["generate_snmp2mqtt"] = True
    regenerated["generate_support_my_switch_bundle"] = False
    regenerated["report_path"] = "/tmp/switch_vision_apply_device_state_report.txt"
    regenerated["last_run_summary_path"] = "/tmp/switch_vision_apply_device_state_summary.txt"
    regenerated["generated_yaml_path"] = str(DEFAULT_GENERATED_SNMP2MQTT)
    regenerated["generated_card_path"] = str(DEFAULT_GENERATED_CARD)
    regenerated["snmp_log_path"] = "/tmp/switch_vision_apply_device_state_snmp.log"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(regenerated, indent=2) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(destination)
        os.chmod(destination, 0o600)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(f"Could not prepare device-state application configuration: {exc}") from exc
    return destination


def _write_dashboard_card_regeneration_options_snapshot(
    destination: Path = Path("/tmp/switch_vision_regenerate_card_options.json"),
) -> Path:
    """Prepare a stored-state-only snapshot for dashboard Card YAML regeneration."""
    options = _effective_discovery_options(_self_addon_options())
    _validate_inventory_identities(options)
    regenerated = dict(options)
    rows = regenerated.get("switches")
    has_inventory = isinstance(rows, list) and any(
        isinstance(row, dict)
        and (str(row.get("switch_name") or "").strip() or str(row.get("switch_host") or "").strip())
        for row in rows
    )
    if has_inventory:
        regenerated["enable_switch_list"] = True
    regenerated["run_snmp_walks"] = False
    regenerated["run_live_snmpwalk"] = False
    regenerated["clean_output_before_walk"] = False
    regenerated["parse_all_walks"] = True
    regenerated["generate_snmp2mqtt"] = False
    regenerated["generate_support_my_switch_bundle"] = False
    regenerated["report_path"] = "/tmp/switch_vision_regenerate_card_report.txt"
    regenerated["last_run_summary_path"] = "/tmp/switch_vision_regenerate_card_summary.txt"
    regenerated["generated_yaml_path"] = "/tmp/switch_vision_regenerate_card_snmp2mqtt.yaml"
    regenerated["generated_card_path"] = str(DEFAULT_GENERATED_CARD)
    regenerated["snmp_log_path"] = "/tmp/switch_vision_regenerate_card_snmp.log"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(regenerated, indent=2) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(destination)
        os.chmod(destination, 0o600)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(f"Could not prepare Dashboard Card regeneration configuration: {exc}") from exc
    return destination


def _hub_device_control_runtime() -> hub_device_control.HubDeviceControlRuntime:
    return hub_device_control.HubDeviceControlRuntime(
        self_addon_options=_self_addon_options,
        load_options=_load_options,
        read_json=_read_json,
        safe_bool=_safe_bool,
        switch_enabled_state=_switch_enabled_state,
        effective_discovery_switch_row=_effective_discovery_switch_row,
        plain_text=_plain_text,
        discovery_options_with_required_defaults=_discovery_options_with_required_defaults,
        validate_inventory_identities=_validate_inventory_identities,
        create_pre_mutation_backup=create_pre_mutation_backup,
        supervisor_json=_supervisor_json,
        options_update_lock=_OPTIONS_UPDATE_LOCK,
        unifi_snapshot=DEFAULT_UNIFI_SNAPSHOT,
        device_control_path=DEFAULT_DEVICE_CONTROL,
    )


def _current_unified_device_keys(options: dict[str, Any]) -> list[str]:
    return hub_device_control.current_unified_device_keys(
        options,
        runtime=_hub_device_control_runtime(),
    )


def _reconcile_device_added_at(options: dict[str, Any]) -> dict[str, Any]:
    return hub_device_control.reconcile_device_added_at(
        options,
        runtime=_hub_device_control_runtime(),
    )


def _configured_devices_snapshot(options_file: Path) -> dict[str, Any]:
    return hub_device_control.configured_devices_snapshot(
        options_file,
        runtime=_hub_device_control_runtime(),
    )


def _set_configured_device_state(options_file: Path, request_data: Any) -> dict[str, Any]:
    return hub_device_control.set_configured_device_state(
        options_file,
        request_data,
        runtime=_hub_device_control_runtime(),
    )


def _move_configured_device(options_file: Path, request_data: Any) -> dict[str, Any]:
    return hub_device_control.move_configured_device(
        options_file,
        request_data,
        runtime=_hub_device_control_runtime(),
    )


def _reset_configured_device_order(options_file: Path) -> dict[str, Any]:
    return hub_device_control.reset_configured_device_order(
        options_file,
        runtime=_hub_device_control_runtime(),
    )


def _ensure_full_dashboard_source() -> tuple[Path | None, bool]:
    """Ensure a non-destructive full-card source exists for dashboard projection."""
    if DEFAULT_GENERATED_CARD_FULL.is_file():
        return DEFAULT_GENERATED_CARD_FULL, False
    if not DEFAULT_GENERATED_CARD.is_file():
        return None, False
    try:
        DEFAULT_GENERATED_CARD_FULL.parent.mkdir(parents=True, exist_ok=True)
        temporary = DEFAULT_GENERATED_CARD_FULL.with_name(
            f".{DEFAULT_GENERATED_CARD_FULL.name}.{os.getpid()}.tmp"
        )
        shutil.copyfile(DEFAULT_GENERATED_CARD, temporary)
        os.chmod(temporary, 0o600)
        temporary.replace(DEFAULT_GENERATED_CARD_FULL)
        os.chmod(DEFAULT_GENERATED_CARD_FULL, 0o600)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except (OSError, UnboundLocalError):
            pass
        raise RuntimeError(f"Could not preserve the full Native dashboard source: {exc}") from exc
    return DEFAULT_GENERATED_CARD_FULL, True


def _apply_saved_device_order_to_dashboard(
    *,
    touch_if_unchanged: bool = True,
) -> dict[str, Any]:
    """Project current order/state from the preserved full-card dashboard source."""
    source, seeded = _ensure_full_dashboard_source()
    if source is None:
        return {"updated": False, "reason": "generated_dashboard_missing"}
    try:
        options = _self_addon_options()
    except RuntimeError:
        options = _load_options(DEFAULT_OPTIONS_FILE)
    rows = options.get("switches")
    if not isinstance(rows, list):
        rows = options.get("multi_switch_walks")
    if not isinstance(rows, list):
        raise RuntimeError("Authoritative saved SNMP switch inventory is unavailable.")
    result = dashboard_device_order.apply_dashboard_order(
        DEFAULT_GENERATED_CARD,
        DEFAULT_DEVICE_CONTROL,
        source_path=source,
        snmp_states=dashboard_device_order.snmp_states_from_options(options),
        touch_if_unchanged=touch_if_unchanged,
    )
    return {"updated": True, "full_source_seeded": seeded, **result}


def _home_assistant_service(domain: str, service: str, payload: dict[str, Any]) -> None:
    """Call a Home Assistant service through the supported Supervisor Core proxy."""
    token = _read_supervisor_token()
    if not token:
        raise RuntimeError(
            "Home Assistant API token is unavailable. Rebuild/reinstall the Discovery app "
            "with homeassistant_api: true."
        )
    request = Request(
        f"http://supervisor/core/api/services/{quote(domain, safe='')}/{quote(service, safe='')}",
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8"),
    )
    try:
        with urlopen(request, timeout=12.0) as response:
            response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Home Assistant API returned HTTP {exc.code}: {detail[:240]}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Home Assistant API request failed: {exc}") from exc


def _home_assistant_ws(command: dict[str, Any], *, max_size: int = 4 * 1024 * 1024) -> Any:
    """Call a Switch Vision WebSocket command through Supervisor."""
    command_type = str(
        command.get("type") or ""
    ).strip()

    if not command_type.startswith(
        "switch_vision/"
    ):
        raise ValueError(
            "Unsupported Home Assistant WebSocket command."
        )

    token = _read_supervisor_token()

    if not token:
        raise RuntimeError(
            "Home Assistant API token is unavailable."
        )

    try:
        with websocket_connect(
            "ws://supervisor/core/websocket",
            open_timeout=12,
            close_timeout=5,
            max_size=max_size,
        ) as connection:

            required = json.loads(
                connection.recv(timeout=12)
            )

            if (
                required.get("type")
                != "auth_required"
            ):
                raise RuntimeError(
                    "Home Assistant WebSocket did not "
                    "request authentication."
                )

            connection.send(
                json.dumps(
                    {
                        "type": "auth",
                        "access_token": token,
                    }
                )
            )

            authenticated = json.loads(
                connection.recv(timeout=12)
            )

            if (
                authenticated.get("type")
                != "auth_ok"
            ):
                raise RuntimeError(
                    str(
                        authenticated.get(
                            "message"
                        )
                        or
                        "Home Assistant WebSocket "
                        "authentication failed."
                    )
                )

            payload = dict(command)
            payload["id"] = 1

            connection.send(
                json.dumps(payload)
            )

            while True:
                response = json.loads(
                    connection.recv(
                        timeout=12
                    )
                )

                if response.get("id") != 1:
                    continue

                if (
                    response.get("type")
                    != "result"
                    or
                    response.get("success")
                    is not True
                ):
                    error = response.get(
                        "error"
                    )

                    if isinstance(
                        error,
                        dict,
                    ):
                        detail = (
                            error.get("message")
                            or
                            error.get("code")
                        )
                    else:
                        detail = error

                    raise RuntimeError(
                        str(
                            detail
                            or
                            "Home Assistant WebSocket "
                            "command failed."
                        )
                    )

                return response.get(
                    "result"
                )

    except RuntimeError:
        raise

    except Exception as exc:
        raise RuntimeError(
            "Home Assistant WebSocket "
            f"request failed: {exc}"
        ) from exc


def _calibration_profile_name(
    value: Any,
) -> str:
    profile = _plain_text(
        value,
        "Calibration profile",
        max_length=128,
        allow_empty=False,
    ).strip()

    if not profile:
        raise ValueError(
            "Calibration profile cannot be empty."
        )

    return profile


def _set_discovery_ui_density(value: Any) -> dict[str, str]:
    density = str(value or "").strip().lower()
    if density not in _UI_ALLOWED["density"]:
        raise ValueError("UI density must be spacious, comfortable, compact, dense, or ultra_dense.")
    _home_assistant_service("switch_vision", "set_ui_density", {"density": density})
    preferences = _discovery_ui_preferences()
    # The integration writes the shared preference file synchronously as part of
    # the service call. Fall back to the requested value only if storage is slow.
    if preferences.get("density") != density:
        preferences["density"] = density
    return preferences


def _find_snmp2mqtt_addon() -> dict[str, Any] | None:
    payload = _supervisor_json("/addons")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    addons = data.get("addons", []) if isinstance(data, dict) else []
    candidates: list[tuple[int, dict[str, Any]]] = []
    for addon in addons if isinstance(addons, list) else []:
        if not isinstance(addon, dict):
            continue
        slug = str(addon.get("slug") or "")
        name = str(addon.get("name") or "")
        haystack = f"{slug} {name}".lower().replace("-", "_")
        if "snmp2mqtt" not in haystack or "discovery" in haystack:
            continue
        score = 0
        if "switch_vision" in haystack or "switch vision" in haystack:
            score += 10
        if slug.endswith("switch_vision_snmp2mqtt") or slug.endswith("switch_vision_snmp2mqtt_addon"):
            score += 10
        if name.strip().lower() == "switch vision snmp2mqtt":
            score += 20
        candidates.append((score, addon))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _snmp2mqtt_runtime_info() -> dict[str, Any]:
    """Return non-secret SNMP2MQTT runtime details needed for safe retirement."""
    try:
        addon = _find_snmp2mqtt_addon()
    except RuntimeError:
        addon = None
    if addon is None:
        return {
            "installed": False,
            "slug": None,
            "state": "not_installed",
            "options_readable": False,
            "homeassistant_prefix": None,
            "base_topic": None,
            "host_name_as_target": None,
            "wrapper_options_readable": False,
            "use_switch_vision_generated_yaml": None,
            "switch_vision_generated_yaml_path": None,
        }
    slug = str(addon.get("slug") or "").strip()
    state = str(addon.get("state") or addon.get("status") or "unknown").lower()
    result: dict[str, Any] = {
        "installed": bool(slug),
        "slug": slug or None,
        "state": state,
        "options_readable": False,
        "homeassistant_prefix": None,
        "base_topic": None,
        "host_name_as_target": None,
        "wrapper_options_readable": False,
        "use_switch_vision_generated_yaml": None,
        "switch_vision_generated_yaml_path": None,
    }
    if not slug:
        return result
    try:
        info = _supervisor_json(f"/addons/{quote(slug, safe='')}/info")
        data = info.get("data") if isinstance(info.get("data"), dict) else info
        if not isinstance(data, dict):
            return result
        result["state"] = str(data.get("state") or state).lower()
        options = data.get("options")
        if not isinstance(options, dict):
            return result
        result["wrapper_options_readable"] = True
        generated_mode = options.get("use_switch_vision_generated_yaml")
        if isinstance(generated_mode, bool):
            result["use_switch_vision_generated_yaml"] = generated_mode
        elif isinstance(generated_mode, str):
            normalized_mode = generated_mode.strip().casefold()
            if normalized_mode in {"true", "1", "yes", "on", "enabled"}:
                result["use_switch_vision_generated_yaml"] = True
            elif normalized_mode in {"false", "0", "no", "off", "disabled"}:
                result["use_switch_vision_generated_yaml"] = False
        generated_path = str(
            options.get("switch_vision_generated_yaml_path")
            or DEFAULT_GENERATED_SNMP2MQTT
        ).strip()
        result["switch_vision_generated_yaml_path"] = generated_path
        mqtt = options.get("mqtt") if isinstance(options.get("mqtt"), dict) else {}
        homeassistant = options.get("homeassistant") if isinstance(options.get("homeassistant"), dict) else {}
        prefix = str(homeassistant.get("prefix") or "homeassistant").strip().strip("/")
        base_topic = str(mqtt.get("base_topic") or "snmp2mqtt").strip().strip("/")
        if not prefix or not base_topic or "+" in prefix or "#" in prefix:
            return result
        result.update({
            "options_readable": True,
            "homeassistant_prefix": prefix,
            "base_topic": base_topic,
            "host_name_as_target": bool(mqtt.get("host_name_as_target", False)),
        })
    except RuntimeError:
        pass
    return result


def _core_settings_status() -> dict[str, Any]:
    return hub_component_settings.core_settings_status(
        home_assistant_ws=_home_assistant_ws,
    )


def _save_core_settings(data: Any) -> dict[str, Any]:
    return hub_component_settings.save_core_settings(
        data,
        home_assistant_ws=_home_assistant_ws,
    )


def _hub_app_path(value: Any, field: str) -> str:
    return hub_component_settings.hub_app_path(
        value,
        field,
        plain_text=_plain_text,
    )


def _snmp2mqtt_addon_options() -> tuple[str, str, dict[str, Any]]:
    return hub_component_settings.snmp2mqtt_addon_options(
        find_snmp2mqtt_addon=_find_snmp2mqtt_addon,
        supervisor_json=_supervisor_json,
    )


def _snmp2mqtt_settings_status() -> dict[str, Any]:
    return hub_component_settings.snmp2mqtt_settings_status(
        snmp2mqtt_addon_options=_snmp2mqtt_addon_options,
    )


def _save_snmp2mqtt_settings(data: Any) -> dict[str, Any]:
    return hub_component_settings.save_snmp2mqtt_settings(
        data,
        snmp2mqtt_addon_options=_snmp2mqtt_addon_options,
        supervisor_json=_supervisor_json,
        plain_text=_plain_text,
        settings_status=_snmp2mqtt_settings_status,
    )


_DISCOVERY_HUB_SUPPORT_KEYS = {"generate_support_my_switch_bundle", "support_mask_management_ips", "support_mask_mac_addresses", "support_mask_hostnames", "support_mask_vlan_names", "support_mask_interface_descriptions", "support_contributor_type", "support_contributor_value"}

_DISCOVERY_HUB_KEYS = DISCOVERY_CONFIG_KEYS | _DISCOVERY_HUB_SUPPORT_KEYS
_DISCOVERY_HUB_BOOL_KEYS = {"run_snmp_walks", "enable_switch_list", "parse_all_walks", "generate_snmp2mqtt", "clean_output_before_walk", "backup_retention_enabled", "generate_support_my_switch_bundle", "support_mask_management_ips", "support_mask_mac_addresses", "support_mask_hostnames", "support_mask_vlan_names", "support_mask_interface_descriptions"}
_DISCOVERY_HUB_PATH_KEYS = {"input_path", "snmpwalks_dir", "report_path", "targets_csv", "last_run_summary_path", "generated_yaml_path", "generated_card_path", "snmp_log_path"}


def _discovery_settings_status() -> dict[str, Any]:
    options = _effective_discovery_options(_self_addon_options())
    defaults = {
        "input_path": "/share/switch_vision/snmpwalk.txt", "snmpwalks_dir": "/share/switch_vision/snmpwalks", "report_path": "/share/switch_vision/discovery-report.txt",
        "run_snmp_walks": "true", "enable_switch_list": "true", "switches": [], "stack_member_prefixes": [], "autodiscover_networks": [], "parse_all_walks": "false", "generate_snmp2mqtt": "true", "clean_output_before_walk": "false",
        "targets_csv": "/share/switch_vision/discovery-targets.csv", "last_run_summary_path": "/share/switch_vision/last-discovery-run.txt", "generated_yaml_path": "/share/switch_vision/generated-snmp2mqtt.yaml", "generated_card_path": "/share/switch_vision/generated-dashboard-card.yaml",
        "snmp_timeout": "3", "snmp_retries": "1", "snmp_log_path": "/share/switch_vision/snmpwalk.log", "minimum_valid_walk_lines": "100", "backup_retention_enabled": "true", "backup_retention_count": 5,
        "generate_support_my_switch_bundle": "true", "support_mask_management_ips": "true", "support_mask_mac_addresses": "true", "support_mask_hostnames": "true", "support_mask_vlan_names": "true", "support_mask_interface_descriptions": "true",
        "support_contributor_type": "anonymous", "support_contributor_value": "",
    }
    settings = {key: options.get(key, defaults.get(key)) for key in _DISCOVERY_HUB_KEYS}
    safe_switches: list[dict[str, Any]] = []
    for raw in settings.get("switches") if isinstance(settings.get("switches"), list) else []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        original_name = str(row.get("switch_name") or "").strip()
        row["snmp_community_configured"] = bool(str(row.get("snmp_community") or ""))
        row["snmp_community"] = ""
        row["original_switch_name"] = original_name
        safe_switches.append(row)
    pending_restore = _load_configuration_restore_pending()
    pending_switches = pending_restore.get("discovery_switches", [])
    if pending_switches:
        current_by_name = {
            str(row.get("switch_name") or "").strip(): row
            for row in safe_switches
            if isinstance(row, dict) and str(row.get("switch_name") or "").strip()
        }

        # A restored row stops being pending as soon as the live Supervisor
        # configuration contains that same switch with a saved community.
        # Do not let stale restore metadata shadow newer enabled/disabled or
        # presentation state indefinitely after an import/restore completes.
        resolved_pending_names = {
            str(row.get("switch_name") or "").strip()
            for row in pending_switches
            if isinstance(row, dict)
            and str(row.get("switch_name") or "").strip()
            and bool(
                current_by_name.get(str(row.get("switch_name") or "").strip(), {}).get(
                    "snmp_community_configured"
                )
            )
        }
        if resolved_pending_names:
            pending_restore["discovery_switches"] = [
                dict(row)
                for row in pending_switches
                if isinstance(row, dict)
                and str(row.get("switch_name") or "").strip() not in resolved_pending_names
            ]
            _save_configuration_restore_pending(pending_restore)
            pending_switches = pending_restore["discovery_switches"]

        if pending_switches:
            if not current_by_name:
                # Replace the blank Home Assistant placeholder with the backed-up
                # rows so a fresh install only needs its communities entered.
                safe_switches = []
            else:
                pending_names = {
                    str(row.get("switch_name") or "").strip()
                    for row in pending_switches
                    if isinstance(row, dict) and str(row.get("switch_name") or "").strip()
                }
                safe_switches = [
                    row
                    for row in safe_switches
                    if str(row.get("switch_name") or "").strip() not in pending_names
                ]
            for raw in pending_switches:
                if not isinstance(raw, dict):
                    continue
                name = str(raw.get("switch_name") or "").strip()
                current_row = current_by_name.get(name)
                row = dict(raw)
                row["snmp_community"] = ""
                row["snmp_community_configured"] = bool(
                    current_row and current_row.get("snmp_community_configured")
                )
                row["original_switch_name"] = name
                row["restore_pending"] = not row["snmp_community_configured"]
                safe_switches.append(row)
    settings["switches"] = safe_switches

    stack = settings.get("stack_member_prefixes")
    safe_stack = [dict(item) for item in stack if isinstance(item, dict)] if isinstance(stack, list) else []
    pending_stack = pending_restore.get("discovery_stack_member_prefixes", [])
    if pending_stack:
        pending_stack_keys = {
            (
                str(row.get("switch_name") or "").strip().casefold(),
                str(row.get("member") or row.get("member_number") or "").strip(),
            )
            for row in pending_stack
            if isinstance(row, dict)
        }
        safe_stack = [
            row
            for row in safe_stack
            if (
                str(row.get("switch_name") or "").strip().casefold(),
                str(row.get("member") or row.get("member_number") or "").strip(),
            ) not in pending_stack_keys
        ]
        safe_stack.extend(dict(raw) for raw in pending_stack if isinstance(raw, dict))
    settings["stack_member_prefixes"] = safe_stack
    settings["support_contributor_value_configured"] = bool(str(options.get("support_contributor_value") or ""))
    settings["support_contributor_value"] = ""
    return {
        "schema_version": 1,
        "settings": settings,
        "models": sorted({"auto"} | _manual_snmp_override_models()),
        "secret_policy": {
            "snmp_community": "redacted_default_reveal_on_demand_blank_preserves",
            "support_contributor_value": "write_only_blank_preserves",
        },
        "effective_config": _discovery_effective_config_provenance(options),
    }


def _save_discovery_settings(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("settings"), dict):
        raise ValueError("Discovery settings request must contain a settings object.")
    if sorted(set(data) - {"settings"}):
        raise ValueError("Discovery settings request contains unsupported fields.")
    requested = dict(data["settings"])
    requested.pop("support_contributor_value_configured", None)
    unknown = sorted(set(requested) - _DISCOVERY_HUB_KEYS)
    if unknown:
        raise ValueError(f"Unsupported Discovery setting: {unknown[0]}")
    with _OPTIONS_UPDATE_LOCK:
        current = _self_addon_options()
        current_effective = _effective_discovery_options(current)
        updated = _discovery_options_with_required_defaults(current)
        for key in _DISCOVERY_HUB_PATH_KEYS:
            if key in requested:
                updated[key] = _share_path(requested[key], key)
        walk_root = str(updated.get("snmpwalks_dir") or "")
        if walk_root and not (walk_root == "/share/switch_vision/snmpwalks" or walk_root.startswith("/share/switch_vision/snmpwalks/")):
            raise ValueError("snmpwalks_dir must stay under /share/switch_vision/snmpwalks.")
        for key in _DISCOVERY_HUB_BOOL_KEYS:
            if key in requested:
                updated[key] = _bool_string(requested[key], key)
        if "snmp_timeout" in requested:
            updated["snmp_timeout"] = _bounded_int_string(requested["snmp_timeout"], "snmp_timeout", 1, 30)
        if "snmp_retries" in requested:
            updated["snmp_retries"] = _bounded_int_string(requested["snmp_retries"], "snmp_retries", 0, 10)
        if "minimum_valid_walk_lines" in requested:
            updated["minimum_valid_walk_lines"] = _bounded_int_string(requested["minimum_valid_walk_lines"], "minimum_valid_walk_lines", 1, 1000000)
        if "backup_retention_count" in requested:
            updated["backup_retention_count"] = int(_bounded_int_string(requested["backup_retention_count"], "backup_retention_count", 1, 10))
        if "support_contributor_type" in requested:
            contributor_type = str(requested["support_contributor_type"] or "").strip()
            if contributor_type not in {"anonymous", "first_name", "full_name", "github", "forum"}:
                raise ValueError("support_contributor_type is not supported.")
            updated["support_contributor_type"] = contributor_type
        if "support_contributor_value" in requested or "support_contributor_type" in requested:
            contributor_type = str(updated.get("support_contributor_type") or "anonymous")
            value = _plain_text(requested.get("support_contributor_value", ""), "support_contributor_value", max_length=120).strip()
            current_type = str(current.get("support_contributor_type") or "anonymous")
            current_value = str(current.get("support_contributor_value") or "")
            if contributor_type == "anonymous":
                updated["support_contributor_value"] = ""
            elif value:
                updated["support_contributor_value"] = value
            elif contributor_type == current_type and current_value:
                updated["support_contributor_value"] = current_value
            else:
                raise ValueError("Enter the name or username for the selected recognition type.")
        if "autodiscover_networks" in requested:
            updated["autodiscover_networks"] = _validated_autodiscover_networks(
                requested["autodiscover_networks"]
            )
        if "switches" in requested:
            rows = requested["switches"]
            if not isinstance(rows, list) or len(rows) > 256:
                raise ValueError("switches must contain at most 256 entries.")
            current_rows = (
                current_effective.get("switches")
                if isinstance(current_effective.get("switches"), list)
                else []
            )
            current_by_name = {
                str(row.get("switch_name") or "").strip(): row
                for row in current_rows
                if isinstance(row, dict) and str(row.get("switch_name") or "").strip()
            }
            validated_rows: list[dict[str, Any]] = []
            for index, raw in enumerate(rows, start=1):
                if not isinstance(raw, dict):
                    raise ValueError(f"Switch entry {index} must be an object.")
                row = dict(raw)
                row.pop("snmp_community_configured", None)
                row.pop("restore_pending", None)
                original_name = str(row.pop("original_switch_name", "") or "").strip()
                community = row.get("snmp_community", "")
                if not isinstance(community, str):
                    raise ValueError(f"Switch entry {index} snmp_community must be text.")
                # The Hub intentionally never returns a saved community.  Treat
                # whitespace-only edits as blank so a harmless settings save
                # cannot replace a working write-only value with whitespace.
                community = community.strip()
                row["snmp_community"] = community
                if not community:
                    previous = current_by_name.get(original_name or str(row.get("switch_name") or "").strip())
                    preserved = str(previous.get("snmp_community") or "").strip() if previous else ""
                    if not preserved:
                        raise ValueError(f"Switch entry {index} requires an SNMP community for a new or renamed switch.")
                    row["snmp_community"] = preserved
                validated_rows.append(_validate_switch_row(row, index))
            updated["switches"] = validated_rows
        if "stack_member_prefixes" in requested:
            stack = requested["stack_member_prefixes"]
            if not isinstance(stack, list) or len(stack) > 512:
                raise ValueError("stack_member_prefixes must contain at most 512 entries.")
            updated["stack_member_prefixes"] = [_validate_stack_row(item, index) for index, item in enumerate(stack, start=1)]
        _validate_inventory_identities(updated)
        changed = updated != current
        if changed:
            create_pre_mutation_backup(current, reason="hub_settings_update")
            _supervisor_json("/addons/self/options", method="POST", timeout=20.0, payload={"options": updated})
            confirmed = _self_addon_options()
            if confirmed != updated:
                raise RuntimeError("Home Assistant did not confirm the complete Discovery settings update.")
            if "switches" in requested:
                _reconcile_device_added_at(confirmed)
            enforce_retention(confirmed)
    if "switches" in requested:
        _clear_configuration_restore_pending("discovery_switches")
    if "stack_member_prefixes" in requested:
        _clear_configuration_restore_pending("discovery_stack_member_prefixes")
    result = _discovery_settings_status()
    result.update({"saved": True, "changed": changed})
    return result


def _reveal_hub_secret(data: Any) -> dict[str, Any]:
    """Return exactly one saved Hub credential after an explicit operator request."""
    if not isinstance(data, dict):
        raise ValueError("Secret reveal request must be a JSON object.")
    unknown = sorted(set(data) - {"scope", "kind", "identifier"})
    if unknown:
        raise ValueError(f"Unsupported secret reveal field: {unknown[0]}")
    scope = _plain_text(data.get("scope", ""), "scope", max_length=64, allow_empty=False).strip().lower()
    kind = _plain_text(data.get("kind", ""), "kind", max_length=64, allow_empty=False).strip().lower()
    identifier = _plain_text(data.get("identifier", ""), "identifier", max_length=256).strip()
    value = ""

    if scope == "discovery":
        if kind != "snmp_community":
            raise ValueError("Unsupported Discovery credential type.")
        if not identifier:
            raise ValueError("A saved switch name is required.")
        options = _effective_discovery_options(_self_addon_options())
        rows = options.get("switches") if isinstance(options.get("switches"), list) else []
        matches = [
            row for row in rows
            if isinstance(row, dict) and str(row.get("switch_name") or "").strip() == identifier
        ]
        if len(matches) != 1:
            raise ValueError("The saved switch could not be uniquely resolved.")
        value = str(matches[0].get("snmp_community") or "")

    elif scope == "snmp2mqtt":
        if kind != "mqtt_password":
            raise ValueError("Unsupported SNMP2MQTT credential type.")
        _slug, _state, options = _snmp2mqtt_addon_options()
        mqtt = options.get("mqtt") if isinstance(options.get("mqtt"), dict) else {}
        value = str(mqtt.get("password") or "")

    elif scope == "unifi2mqtt":
        addon = _find_unifi2mqtt_addon(include_store=True)
        if addon is None or not addon.get("slug"):
            raise RuntimeError("Switch Vision UniFi2MQTT is not installed.")
        slug = str(addon.get("slug") or "").strip()
        info = _supervisor_json(f"/addons/{quote(slug, safe='')}/info")
        info_data = info.get("data") if isinstance(info.get("data"), dict) else info
        options = info_data.get("options") if isinstance(info_data, dict) else None
        if not isinstance(options, dict):
            raise RuntimeError("Home Assistant did not expose the current UniFi2MQTT options.")
        legacy_transport = str(options.get("transport") or "local").strip().lower()
        legacy_value = str(options.get("api_key") or "")
        if kind == "local_api_key":
            value = str(options.get("local_api_key") or "")
            if not value and legacy_transport == "local":
                value = legacy_value
        elif kind == "remote_api_key":
            value = str(options.get("remote_api_key") or "")
            if not value and legacy_transport == "remote":
                value = legacy_value
        elif kind == "mqtt_password":
            value = str(options.get("mqtt_password") or "")
        elif kind == "controller_api_key":
            if not identifier:
                raise ValueError("A saved controller ID is required.")
            rows = options.get("controllers") if isinstance(options.get("controllers"), list) else []
            matches = [
                row for row in rows
                if isinstance(row, dict) and str(row.get("id") or "").strip() == identifier
            ]
            if len(matches) != 1:
                raise ValueError("The saved UniFi controller could not be uniquely resolved.")
            value = str(matches[0].get("api_key") or "")
        else:
            raise ValueError("Unsupported UniFi2MQTT credential type.")
    else:
        raise ValueError("Unsupported secret reveal scope.")

    if not value:
        raise ValueError("No saved credential is configured for this field.")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise RuntimeError("The saved credential contains invalid control characters and cannot be revealed.")
    return {"ok": True, "secret": value}


def _snmp2mqtt_slug(value: Any) -> str:
    """Match Switch Vision SNMP2MQTT's generated ASCII sensor-name slugs."""
    text = str(value or "").lower().replace("-", "_").replace("~", "_")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    return text.strip("_")


def _snmp2mqtt_discovery_topics(path: Path, prefix: str) -> list[str]:
    """Enumerate HA MQTT Discovery topics emitted from a generated target file."""
    if not path.is_file():
        return []
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return []
    if not isinstance(document, dict) or not isinstance(document.get("targets"), list):
        return []
    topics: set[str] = set()
    safe_prefix = str(prefix or "").strip().strip("/")
    if not safe_prefix or "+" in safe_prefix or "#" in safe_prefix:
        return []
    for target in document["targets"]:
        if not isinstance(target, dict):
            continue
        sensors = target.get("sensors")
        if not isinstance(sensors, list):
            continue
        for sensor in sensors:
            if not isinstance(sensor, dict):
                continue
            component = "binary_sensor" if bool(sensor.get("binary_sensor")) else "sensor"
            topic_name = str(sensor.get("object_id") or "").strip() or _snmp2mqtt_slug(sensor.get("name"))
            if not topic_name or "/" in topic_name or "+" in topic_name or "#" in topic_name:
                continue
            topics.add(f"{safe_prefix}/{component}/snmp2mqtt/{topic_name}/config")
    return sorted(topics)


def _load_snmp2mqtt_retirement_topics() -> list[str]:
    """Load the last known generated HA MQTT Discovery topics (never secrets)."""
    if not DEFAULT_SNMP_RETIREMENT_STATE.is_file():
        return []
    try:
        data = json.loads(DEFAULT_SNMP_RETIREMENT_STATE.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    raw_topics = data.get("topics") if isinstance(data, dict) else None
    if not isinstance(raw_topics, list):
        return []
    topics: set[str] = set()
    for value in raw_topics:
        topic = str(value or "").strip().strip("/")
        if not topic or "+" in topic or "#" in topic or not topic.endswith("/config"):
            continue
        topics.add(topic)
    return sorted(topics)


def _save_snmp2mqtt_retirement_topics(topics: list[str]) -> None:
    """Persist only exact discovery topic names so cleanup survives app restarts."""
    clean = sorted({str(topic).strip().strip("/") for topic in topics if str(topic).strip()})
    DEFAULT_SNMP_RETIREMENT_STATE.parent.mkdir(parents=True, exist_ok=True)
    if not clean:
        DEFAULT_SNMP_RETIREMENT_STATE.unlink(missing_ok=True)
        return
    payload = {
        "version": 1,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "topics": clean,
    }
    tmp = DEFAULT_SNMP_RETIREMENT_STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, DEFAULT_SNMP_RETIREMENT_STATE)


def _remember_current_snmp2mqtt_topics() -> list[str]:
    """Snapshot active generated discovery topics for later retirement."""
    if not DEFAULT_GENERATED_SNMP2MQTT.is_file():
        return _load_snmp2mqtt_retirement_topics()
    runtime = _snmp2mqtt_runtime_info()
    if runtime.get("options_readable") and runtime.get("homeassistant_prefix"):
        topics = _snmp2mqtt_discovery_topics(
            DEFAULT_GENERATED_SNMP2MQTT,
            str(runtime["homeassistant_prefix"]),
        )
        if topics:
            _save_snmp2mqtt_retirement_topics(topics)
            return topics
    return _load_snmp2mqtt_retirement_topics()


def _stop_snmp2mqtt_for_reset(info: dict[str, Any]) -> bool:
    slug = str(info.get("slug") or "").strip()
    state = str(info.get("state") or "").lower()
    if not slug or state not in {"started", "running"}:
        return False
    _supervisor_json(f"/addons/{quote(slug, safe='')}/stop", method="POST", timeout=30.0)
    return True


def _clear_retained_snmp2mqtt_discovery(topics: list[str]) -> tuple[int, list[str]]:
    cleared = 0
    warnings: list[str] = []
    for topic in topics:
        try:
            # Home Assistant MQTT treats an empty retained payload as deletion of
            # the retained discovery configuration, which removes the entity.
            _home_assistant_service(
                "mqtt",
                "publish",
                {"topic": topic, "payload": "", "qos": 0, "retain": True},
            )
            cleared += 1
        except RuntimeError as exc:
            warnings.append(f"Could not clear {topic}: {exc}")
            if len(warnings) >= 8:
                break
    return cleared, warnings


def _clear_generated_directory(path: Path) -> int:
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        return 0
    removed = 0
    for child in list(path.iterdir()):
        try:
            if child.is_dir() and not child.is_symlink():
                removed += sum(1 for item in child.rglob("*") if item.is_file() or item.is_symlink())
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
                removed += 1
        except OSError as exc:
            raise RuntimeError(f"Could not remove generated SNMP data {child}: {exc}") from exc
    path.mkdir(parents=True, exist_ok=True)
    return removed


def _reset_snmp_discovery_data() -> dict[str, Any]:
    """Retire SNMP-generated state without touching UniFi API data or config."""
    if _discovery_state_snapshot().get("running"):
        raise RuntimeError("Stop Discovery before resetting SNMP Discovery data.")

    runtime = _snmp2mqtt_runtime_info()
    topics: set[str] = set(_load_snmp2mqtt_retirement_topics())
    warnings: list[str] = []
    if DEFAULT_GENERATED_SNMP2MQTT.is_file():
        if runtime.get("options_readable") and runtime.get("homeassistant_prefix"):
            topics.update(_snmp2mqtt_discovery_topics(
                DEFAULT_GENERATED_SNMP2MQTT,
                str(runtime["homeassistant_prefix"]),
            ))
        elif runtime.get("installed") and not topics:
            warnings.append(
                "SNMP2MQTT settings could not be read safely, so retained MQTT discovery topics were not guessed or removed."
            )
    topic_list = sorted(topics)

    stopped = False
    safe_to_clear_mqtt = str(runtime.get("state") or "").lower() not in {"started", "running"}
    try:
        stopped = _stop_snmp2mqtt_for_reset(runtime)
        if stopped:
            safe_to_clear_mqtt = True
    except RuntimeError as exc:
        safe_to_clear_mqtt = False
        warnings.append(f"Could not stop Switch Vision SNMP2MQTT: {exc}")

    mqtt_cleared = 0
    if topic_list and safe_to_clear_mqtt:
        mqtt_cleared, mqtt_warnings = _clear_retained_snmp2mqtt_discovery(topic_list)
        warnings.extend(mqtt_warnings)
        if mqtt_cleared == len(topic_list) and not mqtt_warnings:
            _save_snmp2mqtt_retirement_topics([])
    elif topic_list and not safe_to_clear_mqtt:
        warnings.append("Retained MQTT discovery entries were left in place because SNMP2MQTT could not be stopped safely.")

    removed_files: list[str] = []
    for path in SNMP_RESET_FILES:
        try:
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
                removed_files.append(path.name)
        except OSError as exc:
            raise RuntimeError(f"Could not remove {path}: {exc}") from exc

    walk_entries = _clear_generated_directory(DEFAULT_SNMPWALKS_DIR)
    capability_entries = _clear_generated_directory(DEFAULT_CAPABILITIES_DIR)

    return {
        "reset": True,
        "snmp2mqtt_stopped": stopped,
        "mqtt_topics_found": len(topic_list),
        "mqtt_topics_cleared": mqtt_cleared,
        "removed_files": removed_files,
        "walk_entries_removed": walk_entries,
        "capability_entries_removed": capability_entries,
        "unifi_snapshot_preserved": DEFAULT_UNIFI_SNAPSHOT.is_file(),
        "warnings": warnings,
        "message": (
            "SNMP Discovery data reset. Run Discovery again to rebuild the dashboard from the currently enabled sources."
        ),
    }


def _unifi_mqtt_slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_") or "unifi_switch"


def _unifi_retirement_topics_from_snapshot(
    snapshot: Any,
    options: dict[str, Any],
) -> list[str]:
    """Return only retained MQTT topics proven to belong to current UniFi snapshot rows."""
    if not isinstance(snapshot, dict):
        return []
    devices = snapshot.get("devices")
    if not isinstance(devices, list):
        return []
    topic_prefix = str(options.get("mqtt_topic_prefix") or "switch_vision/unifi").strip().strip("/")
    discovery_prefix = str(options.get("mqtt_discovery_prefix") or "homeassistant").strip().strip("/")
    if not topic_prefix or not discovery_prefix or any(mark in topic_prefix + discovery_prefix for mark in "+#"):
        return []

    topics: set[str] = {f"{topic_prefix}/status"}
    for raw in devices:
        if not isinstance(raw, dict):
            continue
        did = _unifi_mqtt_slug(raw.get("id") or raw.get("name"))
        base = f"{topic_prefix}/{did}"
        topics.add(f"{base}/available")

        def sensor(key: str) -> None:
            uid = f"switch_vision_unifi_{did}_{_unifi_mqtt_slug(key)}"
            topics.add(f"{base}/{key}")
            topics.add(f"{discovery_prefix}/sensor/{uid}/config")

        def binary(key: str) -> None:
            uid = f"switch_vision_unifi_{did}_{_unifi_mqtt_slug(key)}"
            topics.add(f"{base}/{key}")
            topics.add(f"{discovery_prefix}/binary_sensor/{uid}/config")

        for key in ("model", "firmware"):
            sensor(key)
        binary("online")
        for key in ("cpu", "memory", "uptime", "uplink_rx_rate", "uplink_tx_rate"):
            sensor(key)

        ports = raw.get("ports")
        for port in ports if isinstance(ports, list) else []:
            if not isinstance(port, dict) or port.get("idx") is None:
                continue
            try:
                number = int(port["idx"])
            except (TypeError, ValueError):
                continue
            prefix = f"port/{number}"
            binary(f"{prefix}/status")
            for key in ("speed", "max_speed", "connector"):
                sensor(f"{prefix}/{key}")
            binary(f"{prefix}/poe_enabled")
            binary(f"{prefix}/poe_active")
            sensor(f"{prefix}/poe_standard")
            for key in ("traffic_available", "activity", "activity_at", "rx_bytes", "tx_bytes"):
                topics.add(f"{base}/{prefix}/{key}")
            activity_uid = f"switch_vision_unifi_{did}_{_unifi_mqtt_slug(prefix + '/activity')}"
            topics.add(f"{discovery_prefix}/binary_sensor/{activity_uid}/config")
    return sorted(topics)


def _reset_everything() -> dict[str, Any]:
    """Reset mutable Switch Vision configuration/runtime state, preserving user recovery/content."""
    if _discovery_state_snapshot().get("running"):
        raise RuntimeError("Stop Discovery before using Reset Everything.")

    current_discovery = _self_addon_options()
    create_pre_mutation_backup(current_discovery, reason="reset_everything")

    unifi_status = _unifi2mqtt_settings_status()
    unifi_snapshot = _read_json(DEFAULT_UNIFI_SNAPSHOT)
    unifi_options = dict(UNIFI2MQTT_DEFAULT_OPTIONS)
    unifi_slug = str(unifi_status.get("slug") or "").strip()
    if unifi_status.get("installed") and unifi_slug:
        try:
            info = _supervisor_json(f"/addons/{quote(unifi_slug, safe='')}/info")
            info_data = info.get("data") if isinstance(info.get("data"), dict) else info
            stored = info_data.get("options") if isinstance(info_data, dict) else None
            if isinstance(stored, dict):
                unifi_options.update(stored)
            if str(info_data.get("state") or "").lower() in {"started", "running"}:
                _supervisor_json(
                    f"/addons/{quote(unifi_slug, safe='')}/stop",
                    method="POST",
                    timeout=30.0,
                )
        except RuntimeError as exc:
            raise RuntimeError(f"Could not stop UniFi2MQTT safely before reset: {exc}") from exc

    snmp_result = _reset_snmp_discovery_data()

    unifi_topics = _unifi_retirement_topics_from_snapshot(unifi_snapshot, unifi_options)
    unifi_cleared = 0
    unifi_warnings: list[str] = []
    for topic in unifi_topics:
        try:
            _home_assistant_service(
                "mqtt",
                "publish",
                {"topic": topic, "payload": "", "qos": 0, "retain": True},
            )
            unifi_cleared += 1
        except RuntimeError as exc:
            unifi_warnings.append(f"Could not clear {topic}: {exc}")
            if len(unifi_warnings) >= 8:
                break

    _home_assistant_service(
        "switch_vision",
        "reset_calibrations",
        {"scope": "all"},
    )
    _save_core_settings({"reset_to_defaults": True})

    installer_reset = False
    try:
        installer = _installer_settings_status()
        if installer.get("installed"):
            _save_installer_settings(INSTALLER_RESET_SETTINGS)
            installer_reset = True
    except RuntimeError as exc:
        raise RuntimeError(f"Could not reset Installer settings: {exc}") from exc

    snmp_addon = _find_snmp2mqtt_addon()
    snmp_settings_reset = False
    if snmp_addon is not None:
        snmp_slug = str(snmp_addon.get("slug") or "").strip()
        if snmp_slug:
            _supervisor_json(
                f"/addons/{quote(snmp_slug, safe='')}/options",
                method="POST",
                timeout=20.0,
                payload={"options": copy.deepcopy(SNMP2MQTT_RESET_OPTIONS)},
            )
            snmp_settings_reset = True

    unifi_settings_reset = False
    if unifi_status.get("installed") and unifi_slug:
        _supervisor_json(
            f"/addons/{quote(unifi_slug, safe='')}/options",
            method="POST",
            timeout=20.0,
            payload={"options": copy.deepcopy(UNIFI2MQTT_DEFAULT_OPTIONS)},
        )
        unifi_settings_reset = True

    _supervisor_json(
        "/addons/self/options",
        method="POST",
        timeout=20.0,
        payload={"options": copy.deepcopy(DISCOVERY_RESET_OPTIONS)},
    )

    removed_runtime: list[str] = []
    for path in (
        DEFAULT_UNIFI_SNAPSHOT,
        DEFAULT_UNIFI_DIAGNOSTICS,
        DEFAULT_DEVICE_CONTROL,
        DEFAULT_CONFIGURATION_RESTORE_PENDING,
        UI_PREFERENCES_PATH,
        DEFAULT_DISCOVERY_HISTORY,
        DEFAULT_INSTALLER_MAINTENANCE_RESPONSE,
        DEFAULT_DISCOVERY_LOG,
        DEFAULT_CURRENT_DISCOVERY_DEBUG,
    ):
        try:
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
                removed_runtime.append(str(path))
        except OSError as exc:
            raise RuntimeError(f"Could not remove mutable Switch Vision runtime state {path}: {exc}") from exc

    return {
        "reset": True,
        "core_settings_reset": True,
        "core_calibrations_reset": True,
        "discovery_settings_reset": True,
        "snmp2mqtt_settings_reset": snmp_settings_reset,
        "unifi2mqtt_settings_reset": unifi_settings_reset,
        "installer_settings_reset": installer_reset,
        "snmp": snmp_result,
        "unifi_mqtt_topics_found": len(unifi_topics),
        "unifi_mqtt_topics_cleared": unifi_cleared,
        "warnings": list(snmp_result.get("warnings") or []) + unifi_warnings,
        "removed_runtime": removed_runtime,
        "preserved": [
            "installed Switch Vision apps",
            "Installer recovery backups",
            "Discovery configuration backups",
            "Support My Switch contribution archives",
            "custom faceplate and logo files",
            "protected contribution/source originals",
        ],
        "message": (
            "Switch Vision mutable settings and runtime state were reset. "
            "Installed apps, backup sets, contribution archives, and custom visual assets were preserved."
        ),
    }


def _addon_payload_list(path: str) -> list[dict[str, Any]]:
    payload = _supervisor_json(path)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if isinstance(data, dict):
        items = data.get("addons", [])
    elif isinstance(data, list):
        items = data
    else:
        items = []
    return [item for item in items if isinstance(item, dict)]


def _unifi2mqtt_score(addon: dict[str, Any]) -> int:
    slug = str(addon.get("slug") or "").strip()
    name = str(addon.get("name") or "").strip()
    haystack = f"{slug} {name}".casefold().replace("-", "_")
    if "unifi2mqtt" not in haystack:
        return -1
    score = 0
    if "switch_vision" in haystack or "switch vision" in haystack:
        score += 20
    normalized_slug = slug.casefold().replace("-", "_")
    if normalized_slug.endswith("switch_vision_unifi2mqtt"):
        score += 20
    if name.casefold() == "switch vision unifi2mqtt":
        score += 40
    if addon.get("installed") not in (False, None, "", 0):
        score += 5
    return score


def _find_unifi2mqtt_addon(*, include_store: bool = True) -> dict[str, Any] | None:
    candidates: list[tuple[int, dict[str, Any]]] = []
    try:
        for addon in _addon_payload_list("/addons"):
            score = _unifi2mqtt_score(addon)
            if score >= 0:
                copy = dict(addon)
                copy["_source"] = "addons"
                candidates.append((score + 100, copy))
    except RuntimeError:
        pass
    if include_store:
        try:
            for addon in _addon_payload_list("/store/addons"):
                score = _unifi2mqtt_score(addon)
                if score >= 0:
                    copy = dict(addon)
                    copy["_source"] = "store"
                    candidates.append((score, copy))
        except RuntimeError:
            pass
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _unifi2mqtt_snapshot_status() -> dict[str, Any]:
    info = _file_info(DEFAULT_UNIFI_SNAPSHOT)
    count = 0
    generated_at = None
    snapshot = _read_json(DEFAULT_UNIFI_SNAPSHOT)
    if isinstance(snapshot, dict):
        devices = snapshot.get("devices")
        if isinstance(devices, list):
            count = len([item for item in devices if isinstance(item, dict)])
        generated_at = snapshot.get("generated_at")
    return {**info, "device_count": count, "generated_at": generated_at}


def _safe_unifi_diagnostic_text(
    value: Any,
    *,
    max_length: int = 128,
) -> str | None:
    text = str(value or "").strip()
    if not text or len(text) > max_length:
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        return None
    return text


def _unifi2mqtt_diagnostics_status() -> dict[str, Any]:
    """Return only privacy-safe UniFi2MQTT diagnostic evidence."""
    info = _file_info(DEFAULT_UNIFI_DIAGNOSTICS)
    payload = _read_json(DEFAULT_UNIFI_DIAGNOSTICS)

    if not isinstance(payload, dict):
        return {
            **info,
            "valid": False,
            "version": None,
            "status": None,
            "stage": None,
            "adopted_devices": 0,
            "switching_devices": 0,
            "rejected_devices": 0,
            "empty_switch_polls": 0,
            "error_type": None,
            "connection_mode": None,
            "priority_transport": None,
            "fallback_transport": None,
            "active_transport": None,
            "failover_active": False,
            "transports_attempted": [],
            "device_classification": [],
        }

    classifications: list[dict[str, Any]] = []

    raw_rows = payload.get("device_classification")
    if isinstance(raw_rows, list):
        for raw in raw_rows[:256]:
            if not isinstance(raw, dict):
                continue

            model = _safe_unifi_diagnostic_text(
                raw.get("model"),
                max_length=128,
            ) or "Unknown"

            features: list[str] = []
            raw_features = raw.get("features")
            if isinstance(raw_features, list):
                for value in raw_features[:64]:
                    feature = _safe_unifi_diagnostic_text(
                        value,
                        max_length=64,
                    )
                    if (
                        feature
                        and re.fullmatch(
                            r"[A-Za-z0-9_.:+-]+",
                            feature,
                        )
                    ):
                        features.append(feature)

            reason = _safe_unifi_diagnostic_text(
                raw.get("reason"),
                max_length=64,
            )

            classifications.append(
                {
                    "model": model,
                    "features": sorted(
                        set(features),
                        key=str.casefold,
                    ),
                    "accepted": bool(
                        raw.get("accepted")
                    ),
                    "reason": reason,
                }
            )

    def safe_count(key: str) -> int:
        value = payload.get(key)
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return max(0, min(value, 100000))
        return 0

    return {
        **info,
        "valid": True,
        "version": _safe_unifi_diagnostic_text(
            payload.get("version"),
            max_length=32,
        ),
        "status": _safe_unifi_diagnostic_text(
            payload.get("status"),
            max_length=32,
        ),
        "stage": _safe_unifi_diagnostic_text(
            payload.get("stage"),
            max_length=64,
        ),
        "adopted_devices": safe_count(
            "adopted_devices"
        ),
        "switching_devices": safe_count(
            "switching_devices"
        ),
        "rejected_devices": safe_count(
            "rejected_devices"
        ),
        "empty_switch_polls": safe_count(
            "empty_switch_polls"
        ),
        "error_type": _safe_unifi_diagnostic_text(
            payload.get("error_type"),
            max_length=128,
        ),
        "connection_mode": _safe_unifi_diagnostic_text(
            payload.get("connection_mode"),
            max_length=32,
        ),
        "priority_transport": _safe_unifi_diagnostic_text(
            payload.get("priority_transport"),
            max_length=16,
        ),
        "fallback_transport": _safe_unifi_diagnostic_text(
            payload.get("fallback_transport"),
            max_length=16,
        ),
        "active_transport": _safe_unifi_diagnostic_text(
            payload.get("active_transport"),
            max_length=16,
        ),
        "failover_active": bool(payload.get("failover_active")),
        "transports_attempted": [
            value
            for value in (
                _safe_unifi_diagnostic_text(item, max_length=16)
                for item in (payload.get("transports_attempted") or [])[:4]
            )
            if value in {"local", "remote"}
        ] if isinstance(payload.get("transports_attempted"), list) else [],
        "device_classification": classifications,
    }


def _unifi_connection_transport(value: Any, field: str, *, allow_none: bool = False) -> str:
    text = str(value or ("none" if allow_none else "local")).strip().lower()
    allowed = {"local", "remote"} | ({"none"} if allow_none else set())
    if text not in allowed:
        expected = "local, remote or none" if allow_none else "local or remote"
        raise ValueError(f"{field} must be {expected}.")
    return text


def _unifi_origin(value: Any, field: str, *, allow_http: bool = False) -> str:
    text = _plain_text(str(value or ""), field, max_length=512, allow_empty=False).strip().rstrip("/")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field} must be a valid http:// or https:// controller URL.")
    if parsed.username or parsed.password:
        raise ValueError(f"{field} must not contain embedded credentials.")
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError(f"{field} must identify the controller origin without an extra path, query or fragment.")
    if parsed.scheme == "http" and not allow_http:
        raise ValueError(f"{field} uses plaintext HTTP. Enable the explicit insecure-HTTP option only when that risk is accepted.")
    return text


def _unifi_controller_browser_rows(options: dict[str, Any]) -> list[dict[str, Any]]:
    rows = options.get("controllers")
    if not isinstance(rows, list):
        return []
    safe: list[dict[str, Any]] = []
    for raw in rows[:32]:
        if not isinstance(raw, dict):
            continue
        transport = str(raw.get("transport") or "local").strip().lower()
        if transport not in {"local", "remote"}:
            transport = "local"
        safe.append({
            "id": str(raw.get("id") or "")[:64],
            "transport": transport,
            "controller_url": str(raw.get("controller_url") or "")[:512],
            "host_id": str(raw.get("host_id") or "auto")[:256],
            "site_id": str(raw.get("site_id") or "auto")[:256],
            "verify_ssl": str(raw.get("verify_ssl", "true")).lower() in {"1", "true", "yes", "on"},
            "allow_insecure_http": str(raw.get("allow_insecure_http", "false")).lower() in {"1", "true", "yes", "on"},
            "api_key_configured": bool(str(raw.get("api_key") or "").strip()),
        })
    return safe


def _unifi2mqtt_settings_status() -> dict[str, Any]:
    addon = _find_unifi2mqtt_addon(include_store=True)
    snapshot = _unifi2mqtt_snapshot_status()
    diagnostics = _unifi2mqtt_diagnostics_status()
    options = dict(UNIFI2MQTT_DEFAULT_OPTIONS)
    options_readable = False
    installed = False
    available = addon is not None
    state = "not_installed"
    slug: str | None = None

    if addon is not None:
        slug = str(addon.get("slug") or "").strip() or None
        installed_value = addon.get("installed")
        installed = addon.get("_source") == "addons" or installed_value not in (False, None, "", 0)
        state = str(addon.get("state") or ("stopped" if installed else "not_installed"))
        if installed and slug:
            try:
                info = _supervisor_json(f"/addons/{quote(slug, safe='')}/info")
                info_data = info.get("data") if isinstance(info.get("data"), dict) else info
                if isinstance(info_data, dict):
                    state = str(info_data.get("state") or state)
                    stored = info_data.get("options")
                    if isinstance(stored, dict):
                        options.update(stored)
                        options_readable = True
            except RuntimeError:
                pass

    safe_options = {
        key: value
        for key, value in options.items()
        if key not in UNIFI2MQTT_SECRET_FIELDS and key != "controllers"
    }
    safe_controllers = _unifi_controller_browser_rows(options)
    pending_controllers = _load_configuration_restore_pending().get("unifi_controllers", [])
    if pending_controllers:
        known_ids = {str(row.get("id") or "").strip() for row in safe_controllers}
        for raw in pending_controllers:
            if not isinstance(raw, dict):
                continue
            controller_id = str(raw.get("id") or "").strip()
            if controller_id and controller_id in known_ids:
                continue
            row = dict(raw)
            row["api_key_configured"] = False
            row["restore_pending"] = True
            safe_controllers.append(row)
            if controller_id:
                known_ids.add(controller_id)
    safe_options["controllers"] = safe_controllers

    legacy_transport = str(options.get("transport") or "local").strip().lower()
    legacy_key = bool(str(options.get("api_key") or "").strip())
    local_key = bool(str(options.get("local_api_key") or "").strip()) or (
        legacy_transport == "local" and legacy_key
    )
    remote_key = bool(str(options.get("remote_api_key") or "").strip()) or (
        legacy_transport == "remote" and legacy_key
    )
    controller_credentials_configured = bool(safe_controllers) and all(
        bool(row.get("api_key_configured")) for row in safe_controllers
    )
    multi_controller_enabled = bool(safe_controllers)
    connection_ready = controller_credentials_configured if multi_controller_enabled else (local_key or remote_key)

    return {
        "installed": installed,
        "available": available,
        "state": state,
        "slug": slug,
        "config_url": f"/config/app/{quote(slug, safe='')}/config" if installed and slug else None,
        "options": safe_options,
        "api_key_configured": legacy_key,
        "local_api_key_configured": local_key,
        "remote_api_key_configured": remote_key,
        "mqtt_password_configured": bool(str(options.get("mqtt_password") or "").strip()),
        "multi_controller_enabled": multi_controller_enabled,
        "controller_count": len(safe_controllers),
        "controller_credentials_configured": controller_credentials_configured,
        "connection_ready": connection_ready,
        "active_transport": diagnostics.get("active_transport"),
        "failover_active": bool(diagnostics.get("failover_active")),
        "connection_diagnostics": diagnostics,
        "options_readable": options_readable,
        "snapshot": snapshot,
    }


def _validate_unifi_controller_rows(data: Any, current: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise ValueError("controllers must be a list.")
    if len(data) > 32:
        raise ValueError("No more than 32 UniFi controller entries are supported.")
    current_rows = current.get("controllers") if isinstance(current.get("controllers"), list) else []
    current_by_id = {
        str(row.get("id") or "").strip(): row
        for row in current_rows
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for position, raw in enumerate(data, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Controller {position} must be an object.")
        controller_id = _plain_text(str(raw.get("id") or ""), f"controllers[{position}].id", max_length=64, allow_empty=False).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", controller_id):
            raise ValueError(f"Controller {position} ID must use letters, digits, hyphen or underscore and start with a letter or digit.")
        normalized = controller_id.casefold()
        if normalized in seen:
            raise ValueError(f"Controller ID {controller_id!r} is duplicated.")
        seen.add(normalized)
        previous = current_by_id.get(controller_id, {})
        transport = _unifi_connection_transport(raw.get("transport", previous.get("transport", "local")), f"controllers[{position}].transport")
        api_key = str(raw.get("api_key") or "") or str(previous.get("api_key") or "")
        if not api_key:
            raise ValueError(f"Controller {controller_id} requires an API key.")
        api_key = _plain_text(api_key, f"controllers[{position}].api_key", max_length=4096, allow_empty=False)
        site_id = _plain_text(str(raw.get("site_id", previous.get("site_id", "auto")) or "auto"), f"controllers[{position}].site_id", max_length=256, allow_empty=False).strip()
        if transport == "local":
            allow_http = _bool_string(raw.get("allow_insecure_http", previous.get("allow_insecure_http", "false")), f"controllers[{position}].allow_insecure_http")
            controller_url = _unifi_origin(raw.get("controller_url", previous.get("controller_url", "")), f"controllers[{position}].controller_url", allow_http=allow_http == "true")
            verify_ssl = _bool_string(raw.get("verify_ssl", previous.get("verify_ssl", "true")), f"controllers[{position}].verify_ssl")
            host_id = "auto"
        else:
            controller_url = ""
            host_id = _plain_text(str(raw.get("host_id", previous.get("host_id", "auto")) or "auto"), f"controllers[{position}].host_id", max_length=256, allow_empty=False).strip()
            verify_ssl = "true"
            allow_http = "false"
        result.append({
            "id": controller_id,
            "transport": transport,
            "controller_url": controller_url,
            "host_id": host_id,
            "site_id": site_id,
            "api_key": api_key,
            "verify_ssl": verify_ssl,
            "allow_insecure_http": allow_http,
        })
    return result


def _validate_unifi2mqtt_options(data: Any, current: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("UniFi2MQTT settings must be a JSON object.")
    result = dict(current)

    priority = _unifi_connection_transport(
        data.get("priority_transport", result.get("priority_transport", result.get("transport", "local"))),
        "priority_transport",
    )
    fallback = _unifi_connection_transport(
        data.get("fallback_transport", result.get("fallback_transport", "none")),
        "fallback_transport",
        allow_none=True,
    )
    if fallback == priority:
        raise ValueError("Fallback must differ from Priority, or be None.")
    result["priority_transport"] = priority
    result["fallback_transport"] = fallback

    local_allow_http = _bool_string(
        data.get("local_allow_insecure_http", result.get("local_allow_insecure_http", "false")),
        "local_allow_insecure_http",
    )
    result["local_allow_insecure_http"] = local_allow_http
    result["local_controller_url"] = _unifi_origin(
        data.get("local_controller_url", result.get("local_controller_url", "https://192.168.1.1:11443")),
        "local_controller_url",
        allow_http=local_allow_http == "true",
    )
    result["local_site_id"] = _plain_text(
        str(data.get("local_site_id", result.get("local_site_id", "auto")) or "auto"),
        "local_site_id",
        max_length=256,
        allow_empty=False,
    ).strip()
    result["local_verify_ssl"] = _bool_string(
        data.get("local_verify_ssl", result.get("local_verify_ssl", "false")),
        "local_verify_ssl",
    )
    result["remote_host_id"] = _plain_text(
        str(data.get("remote_host_id", result.get("remote_host_id", "auto")) or "auto"),
        "remote_host_id",
        max_length=256,
        allow_empty=False,
    ).strip()
    result["remote_site_id"] = _plain_text(
        str(data.get("remote_site_id", result.get("remote_site_id", "auto")) or "auto"),
        "remote_site_id",
        max_length=256,
        allow_empty=False,
    ).strip()

    for key in ("local_api_key", "remote_api_key", "mqtt_password"):
        if key in data and str(data.get(key) or ""):
            result[key] = _plain_text(str(data[key]), key, max_length=4096)

    if "controllers" in data:
        result["controllers"] = _validate_unifi_controller_rows(data["controllers"], current)

    result["poll_interval"] = _bounded_int_string(
        data.get("poll_interval", result.get("poll_interval", "30")),
        "poll_interval",
        10,
        300,
    )
    host = _plain_text(
        str(data.get("mqtt_host", result.get("mqtt_host", ""))),
        "mqtt_host",
        max_length=255,
        allow_empty=False,
    ).strip()
    if any(ch.isspace() for ch in host):
        raise ValueError("mqtt_host cannot contain whitespace.")
    result["mqtt_host"] = host
    result["mqtt_port"] = _bounded_int_string(
        data.get("mqtt_port", result.get("mqtt_port", "1883")),
        "mqtt_port",
        1,
        65535,
    )
    result["mqtt_username"] = _plain_text(
        str(data.get("mqtt_username", result.get("mqtt_username", ""))),
        "mqtt_username",
        max_length=256,
    )
    result["mqtt_tls"] = _bool_string(
        data.get("mqtt_tls", result.get("mqtt_tls", "false")),
        "mqtt_tls",
    )
    result["mqtt_verify_ssl"] = _bool_string(
        data.get("mqtt_verify_ssl", result.get("mqtt_verify_ssl", "true")),
        "mqtt_verify_ssl",
    )
    result["mqtt_ca"] = _plain_text(
        str(data.get("mqtt_ca", result.get("mqtt_ca", ""))),
        "mqtt_ca",
        max_length=512,
    ).strip()
    for key in ("mqtt_topic_prefix", "mqtt_discovery_prefix"):
        value = _plain_text(
            str(data.get(key, result.get(key, ""))),
            key,
            max_length=256,
            allow_empty=False,
        ).strip().strip("/")
        if not value or "+" in value or "#" in value:
            raise ValueError(f"{key} must be a plain MQTT topic prefix without + or # wildcards.")
        result[key] = value
    return result



def _unifi_test_rows(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            for nested in keys:
                nested_value = value.get(nested)
                if isinstance(nested_value, list):
                    return [row for row in nested_value if isinstance(row, dict)]
    data = payload.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _unifi_test_safe_reason(value: Any, *secrets: str) -> str:
    text = str(value or "").strip()
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    text = sanitize_debug_text(text)
    return _safe_unifi_diagnostic_text(text, max_length=512) or "Unknown connection error"


def _unifi_test_get_json(
    url: str,
    api_key: str,
    *,
    verify_ssl: bool,
    timeout: float = 12.0,
) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "X-API-Key": api_key,
            "User-Agent": "Switch-Vision-Discovery/UniFi-Test",
        },
        method="GET",
    )
    context = ssl.create_default_context()
    if url.lower().startswith("https://") and not verify_ssl:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    try:
        with urlopen(request, context=context, timeout=timeout) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise RuntimeError(f"authentication|HTTP {exc.code}: API key was rejected or is not authorized") from exc
        if exc.code == 404:
            raise RuntimeError("api_endpoint|HTTP 404: expected UniFi API endpoint was not found") from exc
        raise RuntimeError(f"api_endpoint|HTTP {exc.code}: UniFi API request failed") from exc
    except URLError as exc:
        reason = exc.reason
        if isinstance(reason, ssl.SSLCertVerificationError):
            raise RuntimeError(f"tls|TLS certificate verification failed: {reason}") from exc
        raise RuntimeError(f"network|Connection failed: {reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("network|Connection timed out") from exc
    except ssl.SSLError as exc:
        raise RuntimeError(f"tls|TLS negotiation failed: {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"network|Connection failed: {exc}") from exc
    if len(raw) > 4 * 1024 * 1024:
        raise RuntimeError("api_response|UniFi API response exceeded the 4 MiB safety limit")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("api_response|UniFi API returned invalid JSON") from exc


def _unifi_test_select_site(sites: list[dict[str, Any]], requested: Any) -> dict[str, Any]:
    usable = [site for site in sites if str(site.get("id") or "").strip()]
    if not usable:
        raise RuntimeError("site_resolution|UniFi Network API returned no sites")
    requested_text = str(requested or "auto").strip() or "auto"
    key = requested_text.casefold()
    if key in {"auto", "default"}:
        defaults = [
            site for site in usable
            if str(site.get("internalReference") or "").strip().casefold() == "default"
            or str(site.get("name") or "").strip().casefold() == "default"
        ]
        if len(defaults) == 1:
            return defaults[0]
        if len(usable) == 1:
            return usable[0]
        raise RuntimeError(
            "site_resolution|Multiple UniFi Network sites were returned; select the required site ID, internal reference, or exact site name"
        )
    matches = [
        site for site in usable
        if str(site.get("id") or "").strip() == requested_text
        or str(site.get("internalReference") or "").strip().casefold() == key
        or str(site.get("name") or "").strip().casefold() == key
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise RuntimeError("site_resolution|Configured site did not match any UniFi Network Integration site")
    raise RuntimeError("site_resolution|Configured site matched multiple UniFi Network Integration sites")


def _unifi_test_network_host(row: dict[str, Any]) -> bool:
    if bool(row.get("isBlocked")):
        return False
    kind = str(row.get("type") or "").strip().casefold()
    return kind in {"network-server", "console", "ucore"}


def _unifi2mqtt_current_options() -> tuple[str, dict[str, Any]]:
    status = _unifi2mqtt_settings_status()
    if not status.get("installed") or not status.get("slug"):
        raise RuntimeError("Switch Vision UniFi2MQTT is not installed.")
    slug = str(status["slug"])
    info = _supervisor_json(f"/addons/{quote(slug, safe='')}/info")
    info_data = info.get("data") if isinstance(info.get("data"), dict) else info
    stored = info_data.get("options") if isinstance(info_data, dict) else None
    if not isinstance(stored, dict):
        raise RuntimeError("Home Assistant did not expose the current UniFi2MQTT options to the Hub.")
    current = dict(UNIFI2MQTT_DEFAULT_OPTIONS)
    current.update(stored)
    return slug, current


def _test_unifi2mqtt_connection(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("UniFi connection test request must be a JSON object.")
    transport = _unifi_connection_transport(data.get("transport"), "transport")
    _slug, current = _unifi2mqtt_current_options()
    legacy_transport = str(current.get("transport") or "local").strip().lower()
    legacy_key = str(current.get("api_key") or "").strip()
    debug: list[str] = [f"{transport.title()} test: validating profile"]
    if transport == "local":
        allow_http = _bool_string(
            data.get("allow_insecure_http", current.get("local_allow_insecure_http", "false")),
            "local_allow_insecure_http",
        ) == "true"
        controller_url = _unifi_origin(
            data.get("controller_url", current.get("local_controller_url", "https://192.168.1.1:11443")),
            "local_controller_url",
            allow_http=allow_http,
        )
        site_request = _plain_text(
            str(data.get("site_id", current.get("local_site_id", "auto")) or "auto"),
            "local_site_id",
            max_length=256,
            allow_empty=False,
        ).strip()
        api_key = str(data.get("api_key") or "").strip() or str(current.get("local_api_key") or "").strip()
        if not api_key and legacy_transport == "local":
            api_key = legacy_key
        if not api_key:
            raise ValueError("Local Integration API key is not configured.")
        verify_ssl = _bool_string(
            data.get("verify_ssl", current.get("local_verify_ssl", "false")),
            "local_verify_ssl",
        ) == "true"
        base = controller_url
        debug.append(f"Local test: connecting to {controller_url}")
        host_id = ""
    else:
        host_request = _plain_text(
            str(data.get("host_id", current.get("remote_host_id", "auto")) or "auto"),
            "remote_host_id",
            max_length=256,
            allow_empty=False,
        ).strip()
        site_request = _plain_text(
            str(data.get("site_id", current.get("remote_site_id", "auto")) or "auto"),
            "remote_site_id",
            max_length=256,
            allow_empty=False,
        ).strip()
        api_key = str(data.get("api_key") or "").strip() or str(current.get("remote_api_key") or "").strip()
        if not api_key and legacy_transport == "remote":
            api_key = legacy_key
        if not api_key:
            raise ValueError("Remote Site Manager API key is not configured.")
        verify_ssl = True
        debug.append("Remote test: contacting official UniFi Site Manager API")
        try:
            if host_request.casefold() == "auto":
                payload = _unifi_test_get_json(
                    "https://api.ui.com/v1/hosts?pageSize=100",
                    api_key,
                    verify_ssl=True,
                )
                hosts = [row for row in _unifi_test_rows(payload, ("data", "hosts")) if _unifi_test_network_host(row)]
                if len(hosts) == 1:
                    selected_host = hosts[0]
                elif not hosts:
                    raise RuntimeError("host_resolution|Site Manager returned no usable UniFi Network hosts")
                else:
                    raise RuntimeError("host_resolution|Multiple usable UniFi Network hosts were returned; configure Remote host ID")
            else:
                payload = _unifi_test_get_json(
                    "https://api.ui.com/v1/hosts/" + quote(host_request, safe=""),
                    api_key,
                    verify_ssl=True,
                )
                selected_host = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
                if not isinstance(selected_host, dict) or str(selected_host.get("id") or "").strip() != host_request:
                    raise RuntimeError("host_resolution|Configured Remote host ID did not match the Site Manager response")
                if not _unifi_test_network_host(selected_host):
                    raise RuntimeError("host_resolution|Configured Remote host is not a usable UniFi Network host")
            host_id = str(selected_host.get("id") or "").strip()
            if not host_id:
                raise RuntimeError("host_resolution|Resolved Site Manager host did not contain an ID")
            debug.append("Remote test: Site Manager host resolved")
        except RuntimeError as exc:
            raw = str(exc)
            stage, sep, reason = raw.partition("|")
            stage = stage if sep else "host_resolution"
            reason = reason if sep else raw
            safe = _unifi_test_safe_reason(reason, api_key)
            debug.append(f"Remote test: FAILED at {stage}: {safe}")
            return {"ok": False, "transport": transport, "stage": stage, "reason": safe, "debug": debug}
        base = "https://api.ui.com/v1/connector/consoles/" + quote(host_id, safe="")

    try:
        debug.append(f"{transport.title()} test: requesting Network Integration sites")
        sites_payload = _unifi_test_get_json(
            base + "/proxy/network/integration/v1/sites",
            api_key,
            verify_ssl=verify_ssl,
        )
        sites = _unifi_test_rows(sites_payload, ("data", "sites"))
        site = _unifi_test_select_site(sites, site_request)
        site_id = str(site.get("id") or "").strip()
        if not site_id:
            raise RuntimeError("site_resolution|Resolved UniFi Network site did not contain an ID")
        site_name = str(site.get("name") or site.get("internalReference") or site_id).strip()[:120]
        debug.append(f"{transport.title()} test: authenticated; site resolved ({site_name})")
        devices_payload = _unifi_test_get_json(
            base + "/proxy/network/integration/v1/sites/" + quote(site_id, safe="") + "/devices",
            api_key,
            verify_ssl=verify_ssl,
        )
        devices = _unifi_test_rows(devices_payload, ("data", "devices"))
        debug.append(f"{transport.title()} test: adopted-device read succeeded ({len(devices)} device(s))")
        debug.append(f"{transport.title()} test: PASS")
        return {
            "ok": True,
            "transport": transport,
            "stage": "complete",
            "reason": "Connection test passed",
            "host_id": host_id if transport == "remote" else "",
            "site_id": site_id,
            "site_name": site_name,
            "device_count": len(devices),
            "debug": debug,
        }
    except RuntimeError as exc:
        raw = str(exc)
        stage, sep, reason = raw.partition("|")
        stage = stage if sep else "network_api"
        reason = reason if sep else raw
        safe = _unifi_test_safe_reason(reason, api_key)
        debug.append(f"{transport.title()} test: FAILED at {stage}: {safe}")
        return {"ok": False, "transport": transport, "stage": stage, "reason": safe, "debug": debug}

def _save_unifi2mqtt_settings(data: Any) -> dict[str, Any]:
    status = _unifi2mqtt_settings_status()
    if not status.get("installed") or not status.get("slug"):
        raise RuntimeError("Switch Vision UniFi2MQTT is not installed.")
    slug = str(status["slug"])
    info = _supervisor_json(f"/addons/{quote(slug, safe='')}/info")
    info_data = info.get("data") if isinstance(info.get("data"), dict) else info
    current = dict(UNIFI2MQTT_DEFAULT_OPTIONS)
    stored_options = info_data.get("options") if isinstance(info_data, dict) else None
    if not isinstance(stored_options, dict):
        raise RuntimeError(
            "Home Assistant did not expose the current UniFi2MQTT options to the Hub. "
            "To protect stored secrets, use the Home Assistant App configuration fallback for this change."
        )
    current.update(stored_options)
    merged = _validate_unifi2mqtt_options(data, current)
    _supervisor_json(
        f"/addons/{quote(slug, safe='')}/options",
        method="POST",
        timeout=20.0,
        payload={"options": merged},
    )
    state = str((info_data or {}).get("state") or "") if isinstance(info_data, dict) else ""
    restarted = False
    started = False
    if state in {"started", "running"}:
        _supervisor_json(
            f"/addons/{quote(slug, safe='')}/restart",
            method="POST",
            timeout=30.0,
        )
        restarted = True
    elif state == "stopped":
        _supervisor_json(
            f"/addons/{quote(slug, safe='')}/start",
            method="POST",
            timeout=30.0,
        )
        started = True
    _clear_configuration_restore_pending("unifi_controllers")
    result = _unifi2mqtt_settings_status()
    result["saved"] = True
    result["restarted"] = restarted
    result["started"] = started
    return result



_INSTALLER_BACKUP_OPTION_KEYS = {
    "release_api_url",
    "allow_custom_release_source",
    "release_asset_pattern",
    "preserve_custom_assets",
    "create_backup",
    "allow_prerelease",
    "backup_retention",
}


def _load_configuration_restore_pending() -> dict[str, Any]:
    payload = _read_json(DEFAULT_CONFIGURATION_RESTORE_PENDING)
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return {
            "schema_version": 1,
            "discovery_switches": [],
            "discovery_stack_member_prefixes": [],
            "unifi_controllers": [],
        }
    switches = payload.get("discovery_switches")
    stack_members = payload.get("discovery_stack_member_prefixes")
    controllers = payload.get("unifi_controllers")
    return {
        "schema_version": 1,
        "discovery_switches": [dict(row) for row in switches if isinstance(row, dict)] if isinstance(switches, list) else [],
        "discovery_stack_member_prefixes": [dict(row) for row in stack_members if isinstance(row, dict)] if isinstance(stack_members, list) else [],
        "unifi_controllers": [dict(row) for row in controllers if isinstance(row, dict)] if isinstance(controllers, list) else [],
    }


def _save_configuration_restore_pending(payload: dict[str, Any]) -> None:
    normalized = {
        "schema_version": 1,
        "discovery_switches": [dict(row) for row in payload.get("discovery_switches", []) if isinstance(row, dict)],
        "discovery_stack_member_prefixes": [dict(row) for row in payload.get("discovery_stack_member_prefixes", []) if isinstance(row, dict)],
        "unifi_controllers": [dict(row) for row in payload.get("unifi_controllers", []) if isinstance(row, dict)],
    }
    if (
        not normalized["discovery_switches"]
        and not normalized["discovery_stack_member_prefixes"]
        and not normalized["unifi_controllers"]
    ):
        try:
            DEFAULT_CONFIGURATION_RESTORE_PENDING.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError(
                f"Could not clear pending configuration restore state: {exc}"
            ) from exc
        return
    DEFAULT_CONFIGURATION_RESTORE_PENDING.parent.mkdir(parents=True, exist_ok=True)
    temporary = DEFAULT_CONFIGURATION_RESTORE_PENDING.with_name(
        f".{DEFAULT_CONFIGURATION_RESTORE_PENDING.name}.{os.getpid()}.tmp"
    )
    try:
        temporary.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o644)
        os.replace(temporary, DEFAULT_CONFIGURATION_RESTORE_PENDING)
        os.chmod(DEFAULT_CONFIGURATION_RESTORE_PENDING, 0o644)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _clear_configuration_restore_pending(section: str) -> None:
    pending = _load_configuration_restore_pending()
    if section == "discovery_switches":
        pending["discovery_switches"] = []
    elif section == "discovery_stack_member_prefixes":
        pending["discovery_stack_member_prefixes"] = []
    elif section == "unifi_controllers":
        pending["unifi_controllers"] = []
    else:
        raise ValueError("Unknown pending restore section.")
    _save_configuration_restore_pending(pending)


def _installer_settings_status() -> dict[str, Any]:
    links = _installed_switch_vision_app_links()
    item = links.get("installer") if isinstance(links, dict) else None
    if not isinstance(item, dict) or not item.get("found") or not item.get("slug"):
        return {"installed": False, "settings": None}
    slug = str(item["slug"])
    payload = _supervisor_json(f"/addons/{quote(slug, safe='')}/info")
    info = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    options = info.get("options") if isinstance(info, dict) else None
    if not isinstance(options, dict):
        raise RuntimeError("Home Assistant did not expose Switch Vision Installer options.")
    return {
        "installed": True,
        "slug": slug,
        "state": str(info.get("state") or "unknown") if isinstance(info, dict) else "unknown",
        "settings": {key: copy.deepcopy(options[key]) for key in _INSTALLER_BACKUP_OPTION_KEYS if key in options},
    }


def _save_installer_settings(settings: Any) -> dict[str, Any]:
    if not isinstance(settings, dict):
        raise ValueError("Installer backup settings must contain an object.")
    unknown = sorted(set(settings) - _INSTALLER_BACKUP_OPTION_KEYS)
    if unknown:
        raise ValueError(f"Unsupported Installer backup setting: {unknown[0]}")
    status = _installer_settings_status()
    if not status.get("installed") or not status.get("slug"):
        raise RuntimeError("Switch Vision Installer is not installed.")
    slug = str(status["slug"])
    info_payload = _supervisor_json(f"/addons/{quote(slug, safe='')}/info")
    info = info_payload.get("data") if isinstance(info_payload.get("data"), dict) else info_payload
    current = dict(info.get("options") or {}) if isinstance(info, dict) and isinstance(info.get("options"), dict) else {}
    updated = dict(current)
    for key, value in settings.items():
        if key in {"allow_custom_release_source", "preserve_custom_assets", "create_backup", "allow_prerelease"}:
            if type(value) is not bool:
                raise ValueError(f"Installer setting {key} must be true or false.")
            updated[key] = value
        elif key == "backup_retention":
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10:
                raise ValueError("Installer backup_retention must be between 1 and 10.")
            updated[key] = value
        elif key == "release_api_url":
            text = _plain_text(value, key, max_length=2048, allow_empty=False).strip()
            if not text.startswith(("https://", "http://")):
                raise ValueError("Installer release_api_url must be an HTTP or HTTPS URL.")
            updated[key] = text
        elif key == "release_asset_pattern":
            updated[key] = _plain_text(value, key, max_length=256, allow_empty=False).strip()
    if updated != current:
        _supervisor_json(
            f"/addons/{quote(slug, safe='')}/options",
            method="POST",
            timeout=20.0,
            payload={"options": updated},
        )
    return _installer_settings_status()


def _calibration_profile_management_view(result: dict[str, Any]) -> dict[str, Any]:
    """Annotate Core calibration metadata with safe deletion eligibility."""
    view = copy.deepcopy(result)
    items = view.get("items")
    active_profiles = view.get("active_profiles")
    if not isinstance(items, list):
        return view
    if not isinstance(active_profiles, dict):
        active_profiles = {}

    active_bases = {
        str(base or "").strip()
        for base in active_profiles
        if str(base or "").strip()
    }
    active_targets = {
        str(profile or "").strip()
        for profile in active_profiles.values()
        if str(profile or "").strip()
    }

    for item in items:
        if not isinstance(item, dict):
            continue
        profile = str(item.get("profile") or "").strip()
        scope = str(item.get("scope") or "").strip().lower()
        reason = ""
        if scope == "factory":
            reason = "factory"
        elif item.get("active") is True or profile in active_targets:
            reason = "active"
        elif profile in active_bases:
            reason = "active_base"

        item["deletion_protected"] = bool(reason)
        item["deletion_protection_reason"] = reason

    return view


def _core_calibration_backup() -> dict[str, Any]:
    return complete_backup_runtime.core_calibration_backup(
        home_assistant_ws=_home_assistant_ws,
        calibration_profile_name=_calibration_profile_name,
    )


def _core_asset_backup() -> list[dict[str, Any]]:
    return complete_backup_runtime.core_asset_backup(
        home_assistant_ws=_home_assistant_ws,
    )


def _backup_credential_requirements(
    discovery: dict[str, Any], snmp2mqtt: dict[str, Any], unifi2mqtt: dict[str, Any]
) -> list[dict[str, str]]:
    return complete_backup.backup_credential_requirements(
        discovery, snmp2mqtt, unifi2mqtt
    )


def _switch_vision_backup_export(version: str) -> dict[str, Any]:
    return complete_backup_runtime.export_complete_backup(
        version,
        backup_format=COMPLETE_BACKUP_FORMAT,
        schema_version=COMPLETE_BACKUP_SCHEMA_VERSION,
        core_settings_status=_core_settings_status,
        discovery_settings_status=_discovery_settings_status,
        snmp2mqtt_settings_status=_snmp2mqtt_settings_status,
        unifi2mqtt_settings_status=_unifi2mqtt_settings_status,
        installer_settings_status=_installer_settings_status,
        configured_devices_snapshot=_configured_devices_snapshot,
        options_file=DEFAULT_OPTIONS_FILE,
        load_device_control=device_control_state.load,
        device_control_file=DEFAULT_DEVICE_CONTROL,
        core_calibration_backup=_core_calibration_backup,
        core_asset_backup=_core_asset_backup,
        credential_requirements=_backup_credential_requirements,
        validate_complete_backup=_validate_complete_backup,
    )


def _validate_complete_backup(data: Any) -> dict[str, Any]:
    return complete_backup.validate_complete_backup(
        data,
        validate_stack_row=_validate_stack_row,
        validate_inventory_identities=_validate_inventory_identities,
        calibration_profile_name=_calibration_profile_name,
        unifi_secret_fields=UNIFI2MQTT_SECRET_FIELDS,
        validate_device_control=device_control_state.load_from_object,
    )


def _restore_core_calibrations(calibrations: dict[str, Any]) -> int:
    return complete_backup_restore.restore_core_calibrations(
        calibrations,
        calibration_profile_name=_calibration_profile_name,
        home_assistant_service=_home_assistant_service,
    )


def _restore_core_assets(assets: list[dict[str, Any]]) -> int:
    return complete_backup_restore.restore_core_assets(
        assets,
        home_assistant_ws=_home_assistant_ws,
    )


def _restore_unifi2mqtt_nonsecret(options: dict[str, Any]) -> None:
    complete_backup_restore.restore_unifi2mqtt_nonsecret(
        options,
        unifi2mqtt_settings_status=_unifi2mqtt_settings_status,
        supervisor_json=_supervisor_json,
        validate_unifi2mqtt_options=_validate_unifi2mqtt_options,
        unifi_secret_fields=UNIFI2MQTT_SECRET_FIELDS,
    )


def _restore_complete_backup(data: Any) -> dict[str, Any]:
    return complete_backup_restore.restore_complete_backup(
        data,
        backup_format=COMPLETE_BACKUP_FORMAT,
        validate_complete_backup=_validate_complete_backup,
        home_assistant_ws=_home_assistant_ws,
        save_core_settings=_save_core_settings,
        restore_core_assets=_restore_core_assets,
        restore_core_calibrations=_restore_core_calibrations,
        save_installer_settings=_save_installer_settings,
        save_snmp2mqtt_settings=_save_snmp2mqtt_settings,
        load_configuration_restore_pending=_load_configuration_restore_pending,
        restore_unifi2mqtt_nonsecret=_restore_unifi2mqtt_nonsecret,
        save_discovery_settings=_save_discovery_settings,
        save_configuration_restore_pending=_save_configuration_restore_pending,
        load_device_control_from_object=device_control_state.load_from_object,
        save_device_control=device_control_state.save,
        device_control_file=DEFAULT_DEVICE_CONTROL,
    )


def _install_unifi2mqtt() -> dict[str, Any]:
    status = _unifi2mqtt_settings_status()
    if status.get("installed"):
        return status
    addon = _find_unifi2mqtt_addon(include_store=True)
    if addon is None or not addon.get("slug"):
        raise RuntimeError(
            "Switch Vision UniFi2MQTT is not available in the Home Assistant app store yet. "
            "Open Switch Vision Installer and install UniFi2MQTT, then reload the App Store and try again."
        )
    slug = str(addon["slug"])
    _supervisor_json(
        f"/store/addons/{quote(slug, safe='')}/install",
        method="POST",
        timeout=120.0,
        payload={"background": False},
    )
    return _unifi2mqtt_settings_status()


def _installed_switch_vision_app_links() -> dict[str, Any]:
    """Resolve installed Switch Vision app routes without hard-coded repository hashes."""
    links: dict[str, Any] = {
        "discovery": {"found": False, "slug": None, "config_url": None},
        "snmp2mqtt": {"found": False, "slug": None, "config_url": None},
        "unifi2mqtt": {"found": False, "available": False, "slug": None, "config_url": None},
        "installer": {"found": False, "slug": None, "ingress_url": None},
    }
    try:
        payload = _supervisor_json("/addons")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        addons = data.get("addons", []) if isinstance(data, dict) else []
        for addon in addons if isinstance(addons, list) else []:
            if not isinstance(addon, dict):
                continue
            slug = str(addon.get("slug") or "").strip()
            if not slug:
                continue
            normalized = slug.lower().replace("-", "_")
            name = str(addon.get("name") or "").lower().replace("-", "_")
            haystack = f"{normalized} {name}"
            if (
                normalized.endswith("switch_vision_discovery")
                or ("switch_vision" in haystack and "discovery" in haystack)
            ):
                links["discovery"] = {
                    "found": True,
                    "slug": slug,
                    "config_url": f"/config/app/{quote(slug, safe='')}/config",
                }
            if (
                normalized.endswith("switch_vision_snmp2mqtt")
                or normalized.endswith("switch_vision_snmp2mqtt_addon")
                or ("switch_vision" in haystack and "snmp2mqtt" in haystack and "discovery" not in haystack)
            ):
                links["snmp2mqtt"] = {
                    "found": True,
                    "slug": slug,
                    "config_url": f"/config/app/{quote(slug, safe='')}/config",
                }
            if normalized.endswith("switch_vision_installer") or (
                "switch_vision" in haystack and "installer" in haystack
            ):
                links["installer"] = {
                    "found": True,
                    "slug": slug,
                    "ingress_url": f"/app/{quote(slug, safe='')}",
                }
    except RuntimeError as exc:
        links["error"] = str(exc)
    try:
        unifi = _unifi2mqtt_settings_status()
        links["unifi2mqtt"] = {
            "found": bool(unifi.get("installed")),
            "available": bool(unifi.get("available")),
            "slug": unifi.get("slug"),
            "config_url": unifi.get("config_url"),
            "state": unifi.get("state"),
        }
    except RuntimeError as exc:
        links["unifi2mqtt"]["error"] = str(exc)
    return links


def _snmp2mqtt_handoff_mode(runtime: dict[str, Any]) -> tuple[str, str | None]:
    """Return the generated/manual handoff mode without exposing credentials."""
    if not runtime.get("wrapper_options_readable"):
        return "unknown", None
    configured = runtime.get("use_switch_vision_generated_yaml")
    if configured is False:
        return (
            "manual",
            "Switch Vision SNMP2MQTT is configured for manual targets. "
            "Discovery generated a new YAML file but will not override deliberate manual mode. "
            "Enable Use Switch Vision generated YAML in the SNMP2MQTT app configuration, then run Discovery again.",
        )
    generated_path = str(
        runtime.get("switch_vision_generated_yaml_path")
        or DEFAULT_GENERATED_SNMP2MQTT
    ).strip()
    if Path(generated_path) != DEFAULT_GENERATED_SNMP2MQTT:
        return (
            "generated_path_mismatch",
            "Switch Vision SNMP2MQTT is configured to read generated YAML from a different path. "
            f"Set its generated YAML path to {DEFAULT_GENERATED_SNMP2MQTT}, then run Discovery again.",
        )
    return ("generated" if configured is True else "generated_default"), None


def _verify_snmp2mqtt_activation(
    lines: list[str],
    *,
    attempts: int = 3,
    retry_delay: float = 2.0,
) -> dict[str, Any]:
    """Prove the generated MQTT discovery identity set is retained and current."""
    last = {
        "activation_verified": False,
        "mqtt_current_expected": None,
        "mqtt_current_retained": None,
        "mqtt_current_missing": None,
        "mqtt_stale_count": None,
        "verification_status": "unavailable",
    }
    for attempt in range(1, max(1, attempts) + 1):
        if attempt > 1 and retry_delay > 0:
            time.sleep(retry_delay)
        try:
            scan = scan_mqtt_entities()
        except Exception as exc:
            lines.append(
                f"SNMP2MQTT activation verification attempt {attempt} unavailable: "
                f"{type(exc).__name__}."
            )
            continue
        if not isinstance(scan, dict):
            lines.append(
                f"SNMP2MQTT activation verification attempt {attempt} returned invalid data."
            )
            continue

        def safe_count(key: str) -> int | None:
            value = scan.get(key)
            return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

        expected = safe_count("current_expected_count")
        retained = safe_count("current_retained_count")
        missing = safe_count("current_missing_retained_count")
        stale = safe_count("stale_count")
        last = {
            "activation_verified": bool(
                expected is not None
                and expected > 0
                and retained == expected
                and missing == 0
            ),
            "mqtt_current_expected": expected,
            "mqtt_current_retained": retained,
            "mqtt_current_missing": missing,
            "mqtt_stale_count": stale,
            "verification_status": "verified" if (
                expected is not None
                and expected > 0
                and retained == expected
                and missing == 0
            ) else "incomplete",
        }
        if last["activation_verified"]:
            lines.append(
                "SNMP2MQTT activation verified from retained MQTT discovery counts: "
                f"{retained}/{expected} current."
            )
            return last
        lines.append(
            "SNMP2MQTT activation verification incomplete: "
            f"{retained if retained is not None else 'unknown'}/"
            f"{expected if expected is not None else 'unknown'} current; "
            f"missing {missing if missing is not None else 'unknown'}."
        )
    return last


def _verify_snmp2mqtt_generated_config_loaded(
    lines: list[str], runtime: dict[str, Any]
) -> bool:
    generation_id = generated_yaml_generation_id(DEFAULT_GENERATED_SNMP2MQTT)
    base_topic = str(runtime.get("base_topic") or "").strip().strip("/")
    if not generation_id:
        lines.append("SNMP2MQTT exact-load verification unavailable: generated YAML has no generation ID.")
        return False
    # The HA app can reach Supervisor's running state before its retained
    # runtime config marker is visible on MQTT. Give that asynchronous
    # publication a small bounded window instead of recording a false handoff
    # warning immediately after a clean start/restart.
    attempts = 6
    for attempt in range(attempts):
        try:
            verified = verify_generated_yaml_loaded(base_topic, generation_id)
        except Exception as exc:
            lines.append(f"SNMP2MQTT exact-load verification unavailable: {type(exc).__name__}.")
            return False
        if verified:
            lines.append(
                "SNMP2MQTT exact generated configuration load verified"
                + (f" after {attempt + 1} checks." if attempt else ".")
            )
            return True
        if attempt + 1 < attempts:
            time.sleep(1.0)
    lines.append("SNMP2MQTT exact generated configuration load was not verified after the bounded retry window.")
    return False


def _ensure_snmp2mqtt_running(
    lines: list[str],
    previous_mtime: float | None,
    previous_topics: list[str] | None = None,
) -> dict[str, Any]:
    if not DEFAULT_GENERATED_SNMP2MQTT.is_file():
        # If Discovery retired a previously generated YAML, stop the bridge and
        # retire exactly the retained HA MQTT Discovery configs we recorded
        # before the shell removed the active file.
        if previous_mtime is not None:
            runtime = _snmp2mqtt_runtime_info()
            stopped = False
            try:
                stopped = _stop_snmp2mqtt_for_reset(runtime)
            except RuntimeError as exc:
                message = f"Generated SNMP2MQTT YAML was retired, but Switch Vision could not stop SNMP2MQTT: {exc}"
                lines.append(message)
                return {"status": "Warning", "action": "stop_failed", "slug": runtime.get("slug"), "state": runtime.get("state"), "message": message}

            topics = sorted(set(previous_topics or _load_snmp2mqtt_retirement_topics()))
            mqtt_cleared = 0
            mqtt_warnings: list[str] = []
            if topics:
                mqtt_cleared, mqtt_warnings = _clear_retained_snmp2mqtt_discovery(topics)
                if mqtt_cleared == len(topics) and not mqtt_warnings:
                    _save_snmp2mqtt_retirement_topics([])
            if mqtt_warnings:
                lines.extend(mqtt_warnings)
            action_text = "stopped" if stopped else "already stopped/not running"
            message = (
                f"SNMP-generated YAML retired; Switch Vision SNMP2MQTT {action_text}. "
                f"Retained Home Assistant MQTT discovery entries retired: {mqtt_cleared}/{len(topics)}."
            )
            if mqtt_warnings:
                message += " Some retained discovery entries could not be cleared; use Reset SNMP Discovery Data to retry."
            lines.append(message)
            return {
                "status": "Stopped" if not mqtt_warnings else "Warning",
                "action": "retire",
                "slug": runtime.get("slug"),
                "state": "stopped" if stopped else runtime.get("state"),
                "mqtt_topics_found": len(topics),
                "mqtt_topics_cleared": mqtt_cleared,
                "message": message,
            }
        message = "SNMP2MQTT was not started because Discovery has no active SNMP-generated YAML."
        lines.append(message)
        return {"status": "Not used", "action": "none", "slug": None, "state": None, "message": message}
    current_mtime = DEFAULT_GENERATED_SNMP2MQTT.stat().st_mtime
    if previous_mtime is not None and current_mtime <= previous_mtime:
        message = "SNMP2MQTT was not restarted because generated-snmp2mqtt.yaml was not updated by this Discovery run."
        lines.append(message)
        return {"status": "Not changed", "action": "none", "slug": None, "state": None, "message": message}
    validation = _validate_snmp2mqtt_yaml(DEFAULT_GENERATED_SNMP2MQTT)
    if not validation.get("valid"):
        message = f"Generated SNMP2MQTT YAML was not applied: {validation.get('error')}"
        lines.append(message)
        return {"status": "Warning", "action": "none", "slug": None, "state": None, "message": message}

    try:
        runtime = _snmp2mqtt_runtime_info()
        if not runtime.get("installed") or not runtime.get("slug"):
            message = "Switch Vision SNMP2MQTT app is not installed; Discovery completed without restarting it."
            lines.append(message)
            return {"status": "Warning", "action": "none", "slug": None, "state": "not_installed", "message": message}

        configuration_mode, mode_issue = _snmp2mqtt_handoff_mode(runtime)
        slug = str(runtime.get("slug") or "")
        state = str(runtime.get("state") or "unknown").lower()
        if mode_issue:
            lines.append(mode_issue)
            return {
                "status": "Warning",
                "action": "blocked_configuration",
                "slug": slug,
                "state": state,
                "configuration_mode": configuration_mode,
                "activation_verified": False,
                "handoff_failed": True,
                "message": mode_issue,
            }

        action = "restart" if state in {"started", "running"} else "start"
        lines.append(f"SNMP2MQTT app found: {slug} ({state}); requesting {action}.")
        _supervisor_json(f"/addons/{quote(slug, safe='')}/{action}", method="POST", timeout=20.0)

        # Supervisor accepting a restart request is not proof that the new
        # generated file was consumed. Wait briefly, inspect state, then check
        # the exact generated configuration identity. Retained MQTT discovery
        # publication is asynchronous (and some entities intentionally publish
        # on slower timers), so entity counts are never a Discovery success gate.
        time.sleep(2.0)
        resulting_state = "requested"
        try:
            info = _supervisor_json(f"/addons/{quote(slug, safe='')}/info")
            info_data = info.get("data") if isinstance(info.get("data"), dict) else info
            if isinstance(info_data, dict):
                resulting_state = str(info_data.get("state") or resulting_state)
        except Exception as exc:
            lines.append(f"SNMP2MQTT status refresh warning: {type(exc).__name__}.")

        exact_load_verified = _verify_snmp2mqtt_generated_config_loaded(lines, runtime)
        activation = {
            "activation_verified": exact_load_verified,
            "mqtt_current_expected": None,
            "mqtt_current_retained": None,
            "mqtt_current_missing": None,
            "mqtt_stale_count": None,
            "verification_status": "not_required",
        }
        try:
            info = _supervisor_json(f"/addons/{quote(slug, safe='')}/info")
            info_data = info.get("data") if isinstance(info.get("data"), dict) else info
            if isinstance(info_data, dict):
                resulting_state = str(info_data.get("state") or resulting_state)
        except Exception as exc:
            lines.append(f"SNMP2MQTT final status refresh warning: {type(exc).__name__}.")

        if resulting_state not in {"started", "running"}:
            message = (
                f"Switch Vision SNMP2MQTT {action} was requested, but the app did not "
                "return to a running state. Previous retained identities were preserved."
            )
            lines.append(message)
            return {
                "status": "Warning",
                "action": action,
                "slug": slug,
                "state": resulting_state,
                "configuration_mode": configuration_mode,
                **activation,
                "activation_verified": False,
                "handoff_failed": True,
                "message": message,
            }

        if not exact_load_verified:
            message = (
                f"Switch Vision SNMP2MQTT {action} was requested and the app is running, "
                "but exact generated-configuration load was not verified yet. "
                "Discovery output remains valid; review the SNMP2MQTT app status/log if entities do not appear."
            )
            lines.append(message)
            return {
                "status": "Warning",
                "action": action,
                "slug": slug,
                "state": resulting_state,
                "configuration_mode": configuration_mode,
                **activation,
                "config_load_verified": False,
                "activation_verified": False,
                "handoff_failed": True,
                "message": message,
            }

        # The replacement configuration is proven loaded. Retained Home
        # Assistant discovery publication is runtime health evidence and can
        # lag a working poller, so it must not turn this successful handoff
        # into a false activation failure.
        refreshed_runtime = _snmp2mqtt_runtime_info()
        prefix = str(
            refreshed_runtime.get("homeassistant_prefix")
            or runtime.get("homeassistant_prefix")
            or ""
        ).strip().strip("/")
        current_topics = (
            _snmp2mqtt_discovery_topics(DEFAULT_GENERATED_SNMP2MQTT, prefix)
            if prefix
            else []
        )
        retired_topics = sorted(set(previous_topics or []) - set(current_topics))
        retired_cleared = 0
        retired_warnings: list[str] = []
        if retired_topics:
            retired_cleared, retired_warnings = _clear_retained_snmp2mqtt_discovery(retired_topics)
            lines.extend(retired_warnings)

        if current_topics:
            retirement_state = current_topics if not retired_warnings else sorted(
                set(current_topics) | set(retired_topics)
            )
            _save_snmp2mqtt_retirement_topics(retirement_state)

        message = f"Switch Vision SNMP2MQTT {action} verified active from exact generated configuration load."
        if retired_topics:
            message += (
                f" Previous generated discovery entries retired: "
                f"{retired_cleared}/{len(retired_topics)}."
            )
        if retired_warnings:
            message += " Some previous generated discovery entries could not be retired."
        lines.append(message)
        return {
            "status": "Warning" if retired_warnings else "Running",
            "action": action,
            "slug": slug,
            "state": resulting_state,
            "configuration_mode": configuration_mode,
            **activation,
            "config_load_verified": True,
            "activation_verified": True,
            "handoff_failed": False,
            "mqtt_topics_retired": retired_cleared,
            "mqtt_topics_retired_found": len(retired_topics),
            "message": message,
        }
    except Exception as exc:
        message = f"Could not start or restart Switch Vision SNMP2MQTT: {exc}"
        lines.append(message)
        return {
            "status": "Warning",
            "action": "failed",
            "slug": None,
            "state": None,
            "activation_verified": False,
            "handoff_failed": True,
            "message": message,
        }


def _validate_snmp2mqtt_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"valid": False, "error": "Generated SNMP2MQTT YAML was not found."}
    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        return {"valid": False, "error": f"YAML validation failed: {exc}"}
    if not isinstance(data, (dict, list)) or not data:
        return {"valid": False, "error": "Generated YAML is empty or does not contain a YAML mapping/list."}

    targets = data.get("targets") if isinstance(data, dict) else data
    if not isinstance(targets, list) or not targets:
        return {"valid": False, "error": "Generated YAML does not contain a non-empty targets list."}
    total_sensors = 0
    for index, target in enumerate(targets, start=1):
        if not isinstance(target, dict):
            return {"valid": False, "error": f"Generated YAML target {index} is not a mapping."}
        host = target.get("host") or target.get("target")
        if not isinstance(host, str) or not host.strip():
            return {"valid": False, "error": f"Generated YAML target {index} has no management host/target."}
        sensors = target.get("sensors")
        # Discovery intentionally emits some empty polling chunks for models
        # that do not expose a sensor family (for example Huawei VLAN/trunk
        # chunks).  Empty chunks are valid, but null/non-list sensor blocks are
        # not, and a generated file must contain at least one sensor overall.
        if not isinstance(sensors, list):
            return {"valid": False, "error": f"Generated YAML target {index} sensors must be a list."}
        total_sensors += len(sensors)
        for sensor_index, sensor in enumerate(sensors, start=1):
            if not isinstance(sensor, dict):
                return {"valid": False, "error": f"Generated YAML target {index} sensor {sensor_index} is not a mapping."}

            sensor_source = str(sensor.get("source") or "").strip()
            oid = str(sensor.get("oid") or "").strip()

            if sensor_source in {"juniper_ex_vlan", "interface"}:
                if oid:
                    return {
                        "valid": False,
                        "error": (
                            f"Generated YAML target {index} sensor {sensor_index} "
                            f"named-interface source {sensor_source} must not define an OID."
                        ),
                    }

                interface_name = str(sensor.get("interface") or "").strip()
                interfaces_value = sensor.get("interfaces")
                interface_candidates: list[str] = []

                if interfaces_value is not None:
                    if not isinstance(interfaces_value, list) or not interfaces_value:
                        return {
                            "valid": False,
                            "error": (
                                f"Generated YAML target {index} sensor {sensor_index} "
                                f"has invalid interfaces candidate list."
                            ),
                        }
                    for candidate in interfaces_value:
                        if not isinstance(candidate, str) or not candidate.strip():
                            return {
                                "valid": False,
                                "error": (
                                    f"Generated YAML target {index} sensor {sensor_index} "
                                    f"has invalid interfaces candidate list."
                                ),
                            }
                        interface_candidates.append(candidate.strip())

                if not interface_name and not interface_candidates:
                    return {
                        "valid": False,
                        "error": (
                            f"Generated YAML target {index} sensor {sensor_index} "
                            f"has no interface or interface candidates."
                        ),
                    }

                attribute = str(sensor.get("attribute") or "").strip()

                if sensor_source == "juniper_ex_vlan":
                    source_label = "Juniper VLAN"
                    allowed_attributes = {
                        "mode",
                        "native_vlan",
                        "vlans",
                        "tagged_vlans",
                        "untagged_vlans",
                        "summary",
                    }
                else:
                    source_label = "Interface"
                    allowed_attributes = {
                        "oper_status",
                        "admin_status",
                        "speed_mbps",
                        "rx_bytes",
                        "tx_bytes",
                        "alias",
                    }

                if not attribute:
                    return {
                        "valid": False,
                        "error": (
                            f"Generated YAML target {index} sensor {sensor_index} "
                            f"{source_label} sensor has no attribute."
                        ),
                    }

                if attribute not in allowed_attributes:
                    return {
                        "valid": False,
                        "error": (
                            f"Generated YAML target {index} sensor {sensor_index} "
                            f"{source_label} sensor has unsupported attribute: {attribute}"
                        ),
                    }
                continue

            if oid:
                continue

            if sensor_source:
                return {
                    "valid": False,
                    "error": (
                        f"Generated YAML target {index} sensor {sensor_index} "
                        f"uses unsupported OID-less source: {sensor_source}"
                    ),
                }

            return {"valid": False, "error": f"Generated YAML target {index} sensor {sensor_index} has no OID."}
    if total_sensors <= 0:
        return {"valid": False, "error": "Generated YAML contains no SNMP sensors."}

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {"valid": True, "error": None, "size": len(text.encode("utf-8")), "sha256": digest, "text": text}


def _snmp2mqtt_applicability() -> dict[str, Any]:
    """Return whether generated SNMP2MQTT YAML is relevant to this installation."""
    try:
        options = _self_addon_options()
    except RuntimeError:
        options = _load_options(DEFAULT_OPTIONS_FILE)

    generate_value = options.get("generate_snmp2mqtt", "true")
    if isinstance(generate_value, bool):
        generator_enabled = generate_value
    else:
        generator_enabled = str(generate_value).strip().lower() not in {
            "false", "0", "no", "off", "disabled", "disable",
        }
    if not generator_enabled:
        return {
            "applicable": False,
            "reason": "SNMP2MQTT YAML generation is disabled in Discovery options.",
        }

    rows = options.get("switches")
    if not isinstance(rows, list):
        rows = options.get("multi_switch_walks")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            enabled_value = row.get("enabled", "enabled")
            if isinstance(enabled_value, bool):
                enabled = enabled_value
            else:
                state = str(enabled_value).strip().lower()
                enabled = state not in {
                    "false", "disabled", "disable", "off", "no", "0",
                }
            if not enabled:
                continue
            switch_name = str(
                row.get("switch_name")
                or row.get("switch")
                or row.get("selected_switch")
                or row.get("name")
                or ""
            ).strip()
            switch_host = str(
                row.get("switch_host")
                or row.get("host")
                or row.get("manual_switch_host")
                or ""
            ).strip()
            if switch_name and switch_host:
                return {
                    "applicable": True,
                    "reason": "At least one enabled SNMP switch target is configured.",
                }

    parse_value = options.get("parse_all_walks", "false")
    if isinstance(parse_value, bool):
        parse_all = parse_value
    else:
        parse_all = str(parse_value).strip().lower() in {
            "true", "1", "yes", "on", "enabled", "enable",
        }
    input_path = Path(
        str(options.get("input_path") or (DEFAULT_SHARE_DIR / "snmpwalk.txt"))
    )
    if parse_all and input_path.is_file():
        return {
            "applicable": True,
            "reason": "Legacy SNMP walk parsing is enabled with an available input walk.",
        }

    return {
        "applicable": False,
        "reason": (
            "No enabled SNMP targets are configured. "
            "UniFi2MQTT-only installations do not require generated SNMP2MQTT YAML."
        ),
    }


def _generated_yaml_status() -> dict[str, Any]:
    applicability = _snmp2mqtt_applicability()
    generated = _file_info(DEFAULT_GENERATED_SNMP2MQTT)
    if not applicability["applicable"]:
        return {
            "applicable": False,
            "reason": applicability["reason"],
            "generated": generated,
            "validation": {"valid": None, "error": None},
            "import_note": (
                "SNMP2MQTT YAML is not required while no enabled SNMP targets are configured. "
                "UniFi API devices continue through UniFi2MQTT independently."
            ),
        }
    validation = _validate_snmp2mqtt_yaml(DEFAULT_GENERATED_SNMP2MQTT)
    return {
        "applicable": True,
        "reason": applicability["reason"],
        "generated": generated,
        "validation": {key: value for key, value in validation.items() if key != "text"},
        "import_note": "A valid changed generated YAML is applied to Switch Vision SNMP2MQTT automatically when that app is available; invalid candidates are never published.",
    }

def _validate_generated_card_yaml(path: Path) -> dict[str, Any]:
    """Validate and return the Discovery-generated dashboard YAML preview."""
    if not path.is_file():
        return {"valid": False, "error": "Generated Card YAML was not found."}
    try:
        text = path.read_text(encoding="utf-8")
        documents = list(yaml.safe_load_all(text))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        return {"valid": False, "error": f"Card YAML validation failed: {exc}"}

    meaningful = [document for document in documents if document not in (None, {}, [])]
    if not meaningful:
        return {"valid": False, "error": "Generated Card YAML is empty."}
    if not all(isinstance(document, (dict, list)) for document in meaningful):
        return {"valid": False, "error": "Generated Card YAML contains an unsupported top-level value."}

    first = meaningful[0]
    if isinstance(first, dict) and not ({"views", "cards", "type"} & set(first)):
        return {"valid": False, "error": "Generated Card YAML does not contain a dashboard, card list, or card type."}

    encoded = text.encode("utf-8")
    return {
        "valid": True,
        "error": None,
        "size": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "documents": len(meaningful),
        "text": text,
    }


def _generated_card_yaml_status() -> dict[str, Any]:
    validation = _validate_generated_card_yaml(DEFAULT_GENERATED_CARD)
    return {
        "generated": _file_info(DEFAULT_GENERATED_CARD),
        "validation": {key: value for key, value in validation.items() if key != "text"},
        "note": "Review or export this dashboard YAML. Discovery does not install it automatically.",
    }


def _generated_dashboard_export(
    path: Path,
    *,
    cards_only: bool = False,
    custom_dashboard: bool = False,
) -> dict[str, Any]:
    """Return a manual-dashboard export derived from validated Discovery YAML.

    The Native dashboard source intentionally keeps its current layout contract.
    Standard manual exports remove the known third-party vertical-layout wrapper
    so the pasted dashboard has no Layout Card dependency. Custom-dashboard
    exports preserve that reviewed wrapper and its layout metadata so a newly
    created Home Assistant dashboard can match the generated Switch Vision view.
    """
    validation = _validate_generated_card_yaml(path)
    if not validation.get("valid"):
        return {"valid": False, "error": validation.get("error") or "Generated dashboard YAML is invalid."}

    try:
        documents = list(yaml.safe_load_all(validation["text"]))
    except yaml.YAMLError as exc:
        return {"valid": False, "error": f"Dashboard export parse failed: {exc}"}
    meaningful = [document for document in documents if document not in (None, {}, [])]
    if len(meaningful) != 1 or not isinstance(meaningful[0], dict):
        return {"valid": False, "error": "Dashboard export requires exactly one dashboard document."}

    dashboard = copy.deepcopy(meaningful[0])
    views = dashboard.get("views")
    if not isinstance(views, list) or not views:
        return {"valid": False, "error": "Dashboard export requires at least one Home Assistant view."}

    for view in views:
        if not isinstance(view, dict):
            return {"valid": False, "error": "Dashboard export contains an invalid view."}
        view_type = view.get("type")
        if view_type == "custom:vertical-layout":
            if not custom_dashboard:
                view.pop("type", None)
                view.pop("layout", None)
        elif isinstance(view_type, str) and view_type.startswith("custom:"):
            return {"valid": False, "error": f"Dashboard export cannot safely handle unknown custom view dependency: {view_type}"}
        else:
            # Generated layout metadata is only meaningful to custom layout views.
            view.pop("layout", None)

    if cards_only:
        if len(views) != 1:
            return {"valid": False, "error": "Cards-only export requires the generated dashboard to contain exactly one view."}
        cards = views[0].get("cards")
        if not isinstance(cards, list) or not cards:
            return {"valid": False, "error": "Cards-only export found no generated cards."}
        body = yaml.safe_dump(cards, sort_keys=False, allow_unicode=True, default_flow_style=False)
        text = (
            "# Switch Vision cards-only export\n"
            "# Paste these list entries beneath an existing Home Assistant view's cards: key.\n"
            "# This is a snapshot; regenerate and copy again after Discovery changes.\n"
            + body
        )
        mode = "cards"
    else:
        body = yaml.safe_dump(dashboard, sort_keys=False, allow_unicode=True, default_flow_style=False)
        if custom_dashboard:
            text = (
                "# Switch Vision custom dashboard export\n"
                "# Paste into a new Home Assistant dashboard Raw configuration editor.\n"
                "# Preserves the generated custom:vertical-layout view; Layout Card is required.\n"
                "# This is a snapshot; regenerate and copy again after Discovery changes.\n"
                + body
            )
            mode = "custom-dashboard"
        else:
            text = (
                "# Switch Vision dashboard export\n"
                "# Paste into a new Home Assistant dashboard Raw configuration editor.\n"
                "# No third-party Layout Card view dependency is required.\n"
                "# This is a snapshot; regenerate and copy again after Discovery changes.\n"
                + body
            )
            mode = "dashboard"

    encoded = text.encode("utf-8")
    return {
        "valid": True,
        "error": None,
        "mode": mode,
        "text": text,
        "size": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _file_info(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"found": False, "path": str(path), "size": 0, "modified": None}
    stat = path.stat()
    return {
        "found": True,
        "path": str(path),
        "size": stat.st_size,
        "modified": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(stat.st_mtime)),
    }


def _hub_diagnostics_runtime() -> hub_diagnostics.HubDiagnosticsRuntime:
    return hub_diagnostics.HubDiagnosticsRuntime(
        read_json=_read_json,
        registry_lookup=registry_lookup,
        switch_name_identity=_switch_name_identity,
        self_addon_options=_self_addon_options,
        load_options=_load_options,
        unifi2mqtt_diagnostics_status=_unifi2mqtt_diagnostics_status,
        file_info=_file_info,
        snmp2mqtt_applicability=_snmp2mqtt_applicability,
        discovery_state_snapshot=_discovery_state_snapshot,
        default_share_dir=DEFAULT_SHARE_DIR,
        default_registry_file=DEFAULT_REGISTRY_FILE,
        default_unifi_snapshot=DEFAULT_UNIFI_SNAPSHOT,
        default_support_script=DEFAULT_SUPPORT_SCRIPT,
        default_contributions_dir=DEFAULT_CONTRIBUTIONS_DIR,
    )


def _normalized_device_mac(value: Any) -> str:
    return hub_diagnostics.normalized_device_mac(value)


def _normalized_device_ip(value: Any) -> str:
    return hub_diagnostics.normalized_device_ip(value)


def _unique_detected_snmp_identity_match(
    devices: list[dict[str, Any]], *, mac_address: Any = "", ip_address: Any = ""
) -> tuple[dict[str, Any] | None, str]:
    return hub_diagnostics.unique_detected_snmp_identity_match(
        devices,
        mac_address=mac_address,
        ip_address=ip_address,
    )


def _walk_management_target(path: Path) -> str:
    return hub_diagnostics.walk_management_target(path)


def _configured_snmp_diagnostics_inventory(
    options: dict[str, Any],
) -> list[dict[str, str]]:
    return hub_diagnostics.configured_snmp_diagnostics_inventory(
        options,
        runtime=_hub_diagnostics_runtime(),
    )


def _reconcile_snmp_diagnostics_devices(
    devices: list[dict[str, Any]], options: dict[str, Any]
) -> list[dict[str, Any]]:
    return hub_diagnostics.reconcile_snmp_diagnostics_devices(
        devices,
        options,
        runtime=_hub_diagnostics_runtime(),
    )


def _diagnostics_options(options_file: Path | None) -> dict[str, Any]:
    return hub_diagnostics.diagnostics_options(
        options_file,
        runtime=_hub_diagnostics_runtime(),
    )


def _diagnostics_snapshot(
    version: str, options_file: Path | None = None
) -> dict[str, Any]:
    return hub_diagnostics.diagnostics_snapshot(
        version,
        options_file,
        runtime=_hub_diagnostics_runtime(),
    )


def _diagnostics_text(data: dict[str, Any]) -> str:
    return hub_diagnostics.diagnostics_text(data)


def _validate_request(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    contributor_type = str(data.get("contributor_type") or "anonymous")
    if contributor_type not in {"anonymous", "first_name", "full_name", "github", "forum"}:
        raise ValueError("Invalid recognition type.")
    contributor_value = str(data.get("contributor_value") or "").replace("\n", " ").replace("\r", " ").strip()[:120]
    if contributor_type != "anonymous" and not contributor_value:
        raise ValueError("Enter the name or username to use for recognition, or choose Anonymous.")
    return {
        "mask_management_ips": _safe_bool(data.get("mask_management_ips"), True),
        "mask_mac_addresses": _safe_bool(data.get("mask_mac_addresses"), True),
        "mask_hostnames": _safe_bool(data.get("mask_hostnames"), True),
        "mask_vlan_names": _safe_bool(data.get("mask_vlan_names"), False),
        "mask_interface_descriptions": _safe_bool(data.get("mask_interface_descriptions"), False),
        "contributor_type": contributor_type,
        "contributor_value": contributor_value,
    }


def _run_bundle(settings: dict[str, Any], support_script: Path, contributions_dir: Path, version: str) -> None:
    log_path = contributions_dir / "support-my-switch-web.log"
    contributions_dir.mkdir(parents=True, exist_ok=True)
    _set_state(
        running=True,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        finished_at=None,
        success=None,
        message="Preparing contribution bundle…",
        log_tail=[],
    )
    env = os.environ.copy()
    env.update({
        "SWITCH_VISION_DISCOVERY_VERSION": version,
        "SUPPORT_MASK_MANAGEMENT_IPS": str(settings["mask_management_ips"]).lower(),
        "SUPPORT_MASK_MAC_ADDRESSES": str(settings["mask_mac_addresses"]).lower(),
        "SUPPORT_MASK_HOSTNAMES": str(settings["mask_hostnames"]).lower(),
        "SUPPORT_MASK_VLAN_NAMES": str(settings["mask_vlan_names"]).lower(),
        "SUPPORT_MASK_INTERFACE_DESCRIPTIONS": str(settings["mask_interface_descriptions"]).lower(),
        "SUPPORT_CONTRIBUTOR_TYPE": settings["contributor_type"],
        "SUPPORT_CONTRIBUTOR_VALUE": settings["contributor_value"],
        "CONTRIBUTIONS_DIR": str(contributions_dir),
    })
    lines: list[str] = []
    try:
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"\n=== Web UI contribution started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            process = subprocess.Popen(
                [str(support_script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            assert process.stdout is not None
            for line in process.stdout:
                clean = line.rstrip()
                log_file.write(line)
                log_file.flush()
                lines.append(clean)
                lines = lines[-40:]
                _set_state(log_tail=lines, message=clean or "Preparing contribution bundle…")
            return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"Support My Switch exited with code {return_code}.")
        _set_state(success=True, message="Contribution ready")
    except Exception as exc:  # noqa: BLE001 - surface safe failure details in local UI
        lines.append(str(exc))
        _set_state(success=False, message=str(exc), log_tail=lines[-40:])
        try:
            with log_path.open("a", encoding="utf-8") as log_file:
                traceback.print_exc(file=log_file)
        except OSError:
            pass
    finally:
        _set_state(running=False, finished_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        _release_operation("Support My Switch")


HUB_PAGE_PATH = Path(__file__).with_name("support_web.html")
_PAGE = HUB_PAGE_PATH.read_text(encoding="utf-8")



def _autodiscover_registry() -> dict[str, Any]:
    return hub_autodiscover.load_registry(_read_json, DEFAULT_REGISTRY_FILE)


def _autodiscover_unifi_snapshot() -> dict[str, Any]:
    return hub_autodiscover.load_unifi_snapshot(_read_json, DEFAULT_UNIFI_SNAPSHOT)


def _validated_autodiscover_networks(value: Any) -> list[str]:
    return hub_autodiscover.validated_networks(value)


def _hub_autodiscover_runtime() -> hub_autodiscover.HubAutoDiscoverRuntime:
    return hub_autodiscover.HubAutoDiscoverRuntime(
        self_addon_options=_self_addon_options,
        effective_discovery_options=_effective_discovery_options,
        plain_text=_plain_text,
        validate_switch_row=_validate_switch_row,
        save_discovery_settings=_save_discovery_settings,
        registry_loader=_autodiscover_registry,
        unifi_snapshot_loader=_autodiscover_unifi_snapshot,
    )


def _autodiscover_suggested_network(
    options: dict[str, Any],
    unifi_snapshot: dict[str, Any],
) -> str:
    return hub_autodiscover.suggested_network(options, unifi_snapshot)


def _autodiscover_status() -> dict[str, Any]:
    return hub_autodiscover.status(runtime=_hub_autodiscover_runtime())


def _autodiscover_request(data: Any) -> tuple[list[str], bool, str]:
    return hub_autodiscover.parse_request(
        data,
        runtime=_hub_autodiscover_runtime(),
    )


def _autodiscover_scan(data: Any) -> dict[str, Any]:
    return hub_autodiscover.scan(
        data,
        runtime=_hub_autodiscover_runtime(),
    )


def _autodiscover_add(data: Any) -> dict[str, Any]:
    return hub_autodiscover.add(
        data,
        runtime=_hub_autodiscover_runtime(),
    )


class SupportHandler(BaseHTTPRequestHandler):
    server_version = "SwitchVisionSupport/1.0"

    def _allow_ingress_request(self) -> bool:
        if self.client_address[0] == SUPERVISOR_INGRESS_IP:
            return True
        self.send_error(HTTPStatus.FORBIDDEN)
        return False

    @property
    def app(self) -> "SupportServer":
        return self.server  # type: ignore[return-value]

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[Support My Switch Web] {self.address_string()} - {fmt % args}", flush=True)

    def _json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self) -> None:
        body = _page_with_ui_preferences(self.app.version).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _download(self, name: str) -> None:
        safe_name = Path(unquote(name)).name
        if safe_name != unquote(name) or not safe_name.startswith("Switch_Vision_Contribution_"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        path = self.app.contributions_dir / safe_name
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in {".zip", ".eml", ".html"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 128):
                self.wfile.write(chunk)

    def _configuration_download(self) -> None:
        try:
            payload = _discovery_export(self.app.options_file, self.app.version)
        except RuntimeError as exc:
            self._json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        body = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", 'attachment; filename="switch-vision-discovery-configuration.json"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _switches_configuration_download(self) -> None:
        try:
            payload = _switches_export(self.app.version)
        except (ValueError, RuntimeError, OSError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        body = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header(
            "Content-Disposition",
            'attachment; filename="switch-vision-switch-configuration.json"',
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _complete_configuration_download(self) -> None:
        try:
            payload = _switch_vision_backup_export(self.app.version)
        except (ValueError, RuntimeError, OSError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        body = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        if len(body) > MAX_COMPLETE_BACKUP_BYTES:
            self._json(
                {"error": "Complete Switch Vision backup exceeds the 128 MiB safety limit."},
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", 'attachment; filename="switch-vision-complete-backup.json"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _diagnostics_download(self) -> None:
        data = _diagnostics_snapshot(self.app.version, self.app.options_file)
        body = _diagnostics_text(data).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", 'attachment; filename="switch-vision-diagnostics.txt"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if not self._allow_ingress_request():
            return
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/":
            self._html()
        elif path == "/api/status":
            self._json({
                "version": self.app.version,
                "job": _state_snapshot(),
                "latest": _latest_contribution(self.app.contributions_dir),
                "defaults": _defaults(self.app.options_file),
                "discovery": _discovery_state_snapshot(),
                "discovery_history": discovery_history_snapshot(),
                "ui_preferences": _discovery_ui_preferences(),
            })
        elif path == "/api/contributions/history":
            items = _contribution_history(self.app.contributions_dir)
            self._json({"items": items, "count": len(items)})
        elif path == "/api/discovery/debug":
            self._json(_current_discovery_debug_snapshot())
        elif path == "/api/health":
            self._json({"status": "ok", "version": self.app.version})
        elif path == "/api/app-links":
            self._json(_installed_switch_vision_app_links())
        elif path == "/api/settings/core":
            try:
                self._json(_core_settings_status())
            except RuntimeError as exc:
                self._json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
        elif path == "/api/settings/snmp2mqtt":
            try:
                self._json(_snmp2mqtt_settings_status())
            except RuntimeError as exc:
                self._json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
        elif path == "/api/settings/discovery":
            try:
                self._json(_discovery_settings_status())
            except RuntimeError as exc:
                self._json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
        elif path == "/api/maintenance/installer-backups":
            try:
                self._json(_installer_maintenance_request("status"))
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            except RuntimeError as exc:
                self._json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
        elif path == "/api/maintenance/discovery-backups":
            try:
                self._json(discovery_backup_status(_self_addon_options()))
            except (ValueError, RuntimeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        elif path == "/api/maintenance/mqtt/scan":
            try:
                self._json(scan_mqtt_entities())
            except (ValueError, RuntimeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        elif path in {"/calibration_profiles.js", "/calibration_profiles_manager.js", "/maintenance.js", "/custom_theme_manager.js", "/credits_v25.js", "/credits_v25.css"}:
            script_path = Path("/" + Path(path).name)

            if not script_path.is_file():
                self.send_error(
                    HTTPStatus.NOT_FOUND
                )
            else:
                body = script_path.read_bytes()

                self.send_response(
                    HTTPStatus.OK
                )

                self.send_header(
                    "Content-Type",
                    "text/css; charset=utf-8" if script_path.suffix == ".css" else "application/javascript; charset=utf-8",
                )

                self.send_header(
                    "Content-Length",
                    str(len(body)),
                )

                self.send_header(
                    "Cache-Control",
                    "no-store",
                )

                self.end_headers()
                self.wfile.write(body)

        elif path == "/api/calibration-profiles":
            try:
                result = _home_assistant_ws(
                    {
                        "type":
                        "switch_vision/list_calibrations"
                    }
                )

                self._json(
                    _calibration_profile_management_view(result)
                    if isinstance(result, dict)
                    else {}
                )

            except ValueError as exc:
                self._json(
                    {"error": str(exc)},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            except RuntimeError as exc:
                self._json(
                    {"error": str(exc)},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
        elif path == "/api/unifi2mqtt/settings":
            try:
                self._json(_unifi2mqtt_settings_status())
            except RuntimeError as exc:
                self._json({"error": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
        elif path == "/api/autodiscover/status":
            try:
                self._json(_autodiscover_status())
            except (ValueError, RuntimeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        elif path == "/api/configured-devices":
            self._json(_configured_devices_snapshot(self.app.options_file))
        elif path == "/api/diagnostics":
            self._json(_diagnostics_snapshot(self.app.version, self.app.options_file))
        elif path == "/api/generated-card-yaml/status":
            self._json(_generated_card_yaml_status())
        elif path == "/api/generated-card-yaml/preview":
            result = _validate_generated_card_yaml(DEFAULT_GENERATED_CARD)
            if not result.get("valid"):
                self._json({"error": result.get("error")}, HTTPStatus.BAD_REQUEST)
            else:
                self._json({"text": result.get("text"), "sha256": result.get("sha256")})
        elif path == "/api/generated-card-yaml/dashboard-export":
            result = _generated_dashboard_export(DEFAULT_GENERATED_CARD)
            if not result.get("valid"):
                self._json({"error": result.get("error")}, HTTPStatus.BAD_REQUEST)
            else:
                self._json({"text": result.get("text"), "sha256": result.get("sha256"), "mode": "dashboard"})
        elif path == "/api/generated-card-yaml/custom-dashboard-export":
            result = _generated_dashboard_export(DEFAULT_GENERATED_CARD, custom_dashboard=True)
            if not result.get("valid"):
                self._json({"error": result.get("error")}, HTTPStatus.BAD_REQUEST)
            else:
                self._json({"text": result.get("text"), "sha256": result.get("sha256"), "mode": "custom-dashboard"})
        elif path == "/api/generated-card-yaml/cards-export":
            result = _generated_dashboard_export(DEFAULT_GENERATED_CARD, cards_only=True)
            if not result.get("valid"):
                self._json({"error": result.get("error")}, HTTPStatus.BAD_REQUEST)
            else:
                self._json({"text": result.get("text"), "sha256": result.get("sha256"), "mode": "cards"})
        elif path == "/api/generated-yaml/status":
            self._json(_generated_yaml_status())
        elif path == "/api/generated-yaml/preview":
            result = _validate_snmp2mqtt_yaml(DEFAULT_GENERATED_SNMP2MQTT)
            if not result.get("valid"):
                self._json({"error": result.get("error")}, HTTPStatus.BAD_REQUEST)
            else:
                self._json({"text": result.get("text"), "sha256": result.get("sha256")})
        elif path == "/download/switch-vision-dashboard.yaml":
            result = _generated_dashboard_export(DEFAULT_GENERATED_CARD)
            if not result.get("valid"):
                self.send_error(HTTPStatus.BAD_REQUEST, str(result.get("error") or "Dashboard export failed"))
            else:
                body = str(result.get("text") or "").encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/yaml; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Disposition", 'attachment; filename="switch-vision-dashboard.yaml"')
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
        elif path == "/download/switch-vision-custom-dashboard.yaml":
            result = _generated_dashboard_export(DEFAULT_GENERATED_CARD, custom_dashboard=True)
            if not result.get("valid"):
                self.send_error(HTTPStatus.BAD_REQUEST, str(result.get("error") or "Custom dashboard export failed"))
            else:
                body = str(result.get("text") or "").encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/yaml; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Disposition", 'attachment; filename="switch-vision-custom-dashboard.yaml"')
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
        elif path == "/download/generated-dashboard-card.yaml":
            if not DEFAULT_GENERATED_CARD.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
            else:
                body = DEFAULT_GENERATED_CARD.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/yaml; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Disposition", 'attachment; filename="generated-dashboard-card.yaml"')
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
        elif path == "/download/generated-snmp2mqtt.yaml":
            if not DEFAULT_GENERATED_SNMP2MQTT.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
            else:
                body = DEFAULT_GENERATED_SNMP2MQTT.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/yaml; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Disposition", 'attachment; filename="generated-snmp2mqtt.yaml"')
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
        elif path == "/download/switch-vision-backup.json":
            self._complete_configuration_download()
        elif path == "/download/switch-vision-switch-configuration.json":
            self._switches_configuration_download()
        elif path == "/download/discovery-configuration.json":
            self._configuration_download()
        elif path == "/download/diagnostics.txt":
            self._diagnostics_download()
        elif path.startswith("/download/"):
            self._download(path.split("/download/", 1)[1])
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if not self._allow_ingress_request():
            return
        path = urlparse(self.path).path.rstrip("/")

        if path in {
            "/api/calibration-profiles/get",
            "/api/calibration-profiles/save",
            "/api/calibration-profiles/delete",
        }:
            try:
                length = int(
                    self.headers.get(
                        "Content-Length",
                        "0",
                    )
                )

                maximum = (
                    3 * 1024 * 1024
                    if path ==
                    "/api/calibration-profiles/save"
                    else 8192
                )

                if (
                    length <= 0
                    or
                    length > maximum
                ):
                    raise ValueError(
                        "Invalid Calibration Profile "
                        "request size."
                    )

                data = json.loads(
                    self.rfile.read(
                        length
                    ).decode("utf-8")
                )

                if not isinstance(
                    data,
                    dict,
                ):
                    raise ValueError(
                        "Calibration Profile request "
                        "must contain a JSON object."
                    )

                profile = (
                    _calibration_profile_name(
                        data.get("profile")
                    )
                )

                if (
                    path ==
                    "/api/calibration-profiles/get"
                ):
                    result = (
                        _home_assistant_ws(
                            {
                                "type":
                                "switch_vision/get_calibration",
                                "profile":
                                profile,
                            }
                        )
                    )

                    self._json(
                        result
                        if isinstance(
                            result,
                            dict,
                        )
                        else {}
                    )

                    return

                if (
                    path ==
                    "/api/calibration-profiles/delete"
                ):
                    result = _home_assistant_ws(
                        {
                            "type":
                            "switch_vision/delete_calibration",
                            "profile":
                            profile,
                        }
                    )

                    self._json(
                        result
                        if isinstance(
                            result,
                            dict,
                        )
                        else {
                            "ok": True,
                            "profile":
                            profile,
                        }
                    )

                    return

                calibration = data.get(
                    "calibration"
                )

                if not isinstance(
                    calibration,
                    dict,
                ):
                    raise ValueError(
                        "Calibration data must "
                        "contain one JSON object."
                    )

                _home_assistant_service(
                    "switch_vision",
                    "save_calibration",
                    {
                        "profile":
                        profile,
                        "calibration":
                        calibration,
                        "mirror_to_base":
                        False,
                    },
                )

                self._json(
                    {
                        "ok": True,
                        "profile":
                        profile,
                    }
                )

                return

            except (
                ValueError,
                RuntimeError,
                UnicodeDecodeError,
                json.JSONDecodeError,
            ) as exc:
                self._json(
                    {"error": str(exc)},
                    HTTPStatus.BAD_REQUEST,
                )

                return

        if path == "/api/secrets/reveal":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 8192:
                    raise ValueError("Invalid secret reveal request size.")
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                self._json(_reveal_hub_secret(data))
            except (ValueError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        if path in {"/api/settings/core", "/api/settings/snmp2mqtt", "/api/settings/discovery"}:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                maximum = 1024 * 1024 if path == "/api/settings/discovery" else 256 * 1024
                if length <= 0 or length > maximum:
                    raise ValueError("Invalid Hub settings request size.")
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                if path == "/api/settings/core":
                    self._json(_save_core_settings(data))
                elif path == "/api/settings/snmp2mqtt":
                    with _exclusive_operation("SNMP2MQTT settings update"):
                        self._json(_save_snmp2mqtt_settings(data))
                else:
                    with _exclusive_operation("Discovery settings update"):
                        self._json(_save_discovery_settings(data))
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except (ValueError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/ui-density":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 4096:
                    raise ValueError("Invalid UI density request size.")
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                self._json({"preferences": _set_discovery_ui_density(data.get("density"))})
            except (ValueError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/unifi2mqtt/install":
            try:
                with _exclusive_operation("UniFi2MQTT installation"):
                    self._json(_install_unifi2mqtt())
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except RuntimeError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/unifi2mqtt/test-connection":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 16384:
                    raise ValueError("Invalid UniFi connection test request size.")
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                self._json(_test_unifi2mqtt_connection(data))
            except (ValueError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": _unifi_test_safe_reason(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/unifi2mqtt/settings":
            try:
                with _exclusive_operation("UniFi2MQTT settings update"):
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 32768:
                        raise ValueError("Invalid UniFi2MQTT settings request size.")
                    data = json.loads(self.rfile.read(length).decode("utf-8"))
                    self._json(_save_unifi2mqtt_settings(data))
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except (ValueError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/autodiscover/scan":
            try:
                with _exclusive_operation("AutoDiscover scan"):
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 16384:
                        raise ValueError("Invalid AutoDiscover scan request size.")
                    data = json.loads(self.rfile.read(length).decode("utf-8"))
                    self._json(_autodiscover_scan(data))
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except (ValueError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/autodiscover/add":
            try:
                with _device_configuration_update("AutoDiscover add devices"):
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 65536:
                        raise ValueError("Invalid AutoDiscover add request size.")
                    data = json.loads(self.rfile.read(length).decode("utf-8"))
                    self._json(_autodiscover_add(data))
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except (ValueError, RuntimeError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/configured-devices/state":
            try:
                with _device_configuration_update("Device configuration update"):
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 8192:
                        raise ValueError("Invalid device state request size.")
                    data = json.loads(self.rfile.read(length).decode("utf-8"))
                    result = _set_configured_device_state(self.app.options_file, data)
                    key = str(data.get("device_key") or "") if isinstance(data, dict) else ""
                    try:
                        dashboard = _apply_saved_device_order_to_dashboard()
                        result["dashboard_refresh_started"] = bool(dashboard.get("updated"))
                        result["dashboard_refresh_pending"] = not bool(dashboard.get("updated"))
                        result["dashboard_projection"] = dashboard
                    except (OSError, RuntimeError, ValueError) as exc:
                        result["dashboard_refresh_started"] = False
                        result["dashboard_refresh_pending"] = True
                        result["dashboard_refresh_warning"] = str(exc)[:240]
                    result["polling_refresh_started"] = False
                    if key.startswith("snmp:"):
                        queued = _start_device_state_application(self.app.discovery_script)
                        result["polling_refresh_started"] = bool(queued.get("started"))
                        result["polling_refresh_pending"] = True
                        result["polling_refresh_coalesced"] = bool(queued.get("coalesced"))
                        result["polling_refresh_generation"] = queued.get("generation")
                    elif key.startswith("unifi:"):
                        # UniFi2MQTT reads the shared control file on its normal poll loop;
                        # no Discovery/card-regeneration operation is required here.
                        result["polling_refresh_pending"] = True
                    # Keep response ordering aligned with the serialized mutation
                    # order so concurrent UI clicks cannot render an older snapshot
                    # after a newer one has already been returned.
                    self._json(result)
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except (ValueError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/configured-devices/order":
            try:
                with _device_configuration_update("Device order update"):
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 8192:
                        raise ValueError("Invalid device order request size.")
                    data = json.loads(self.rfile.read(length).decode("utf-8"))
                    result = _move_configured_device(self.app.options_file, data)
                    try:
                        dashboard = _apply_saved_device_order_to_dashboard()
                        result["dashboard_refresh_started"] = bool(dashboard.get("updated"))
                        result["dashboard_refresh_pending"] = not bool(dashboard.get("updated"))
                        result["dashboard_projection"] = dashboard
                    except (OSError, RuntimeError, ValueError) as exc:
                        result["dashboard_refresh_started"] = False
                        result["dashboard_refresh_pending"] = True
                        result["dashboard_refresh_warning"] = str(exc)[:240]
                    self._json(result)
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except (ValueError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/configured-devices/reset-order":
            try:
                with _device_configuration_update("Device order reset"):
                    result = _reset_configured_device_order(self.app.options_file)
                    try:
                        dashboard = _apply_saved_device_order_to_dashboard()
                        result["dashboard_refresh_started"] = bool(dashboard.get("updated"))
                        result["dashboard_refresh_pending"] = not bool(dashboard.get("updated"))
                        result["dashboard_projection"] = dashboard
                    except (OSError, RuntimeError, ValueError) as exc:
                        result["dashboard_refresh_started"] = False
                        result["dashboard_refresh_pending"] = True
                        result["dashboard_refresh_warning"] = str(exc)[:240]
                    self._json(result)
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except (ValueError, RuntimeError, OSError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/switches/import":
            try:
                with _exclusive_operation("Switch configuration import"):
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 4 * 1024 * 1024:
                        raise ValueError("Invalid switch configuration size.")
                    data = json.loads(self.rfile.read(length).decode("utf-8"))
                    self._json(_import_switches_only(data))
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except (ValueError, RuntimeError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/configuration/import":
            try:
                with _exclusive_operation("Configuration import"):
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > MAX_COMPLETE_BACKUP_BYTES:
                        raise ValueError("Invalid configuration backup size.")
                    data = json.loads(self.rfile.read(length).decode("utf-8"))
                    if isinstance(data, dict) and data.get("format") == COMPLETE_BACKUP_FORMAT:
                        self._json(_restore_complete_backup(data))
                    else:
                        imported = _validate_discovery_import(data)
                        _import_discovery_options(imported)
                        self._json({
                            "imported": True,
                            "format": "legacy-discovery",
                            "switch_count": _configured_switch_count(imported.get("switches")),
                            "restart_required": False,
                        })
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except (ValueError, RuntimeError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/maintenance/installer-backups":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 8192:
                    raise ValueError("Invalid Installer backup request size.")
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                self._json(_installer_maintenance_browser_request(data))
            except (ValueError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/maintenance/discovery-backups/remove":
            try:
                with _exclusive_operation("Discovery backup removal"):
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 8192:
                        raise ValueError("Invalid Discovery backup removal request size.")
                    data = json.loads(self.rfile.read(length).decode("utf-8"))
                    if not isinstance(data, dict):
                        raise ValueError("Discovery backup removal request must contain a JSON object.")
                    options = _self_addon_options()
                    discovery_backup_status(options)
                    remove_discovery_backup(data.get("name"))
                    self._json(discovery_backup_status(options))
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except (ValueError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/maintenance/mqtt/repair":
            try:
                with _exclusive_operation("MQTT entity repair"):
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 8192:
                        raise ValueError("Invalid MQTT repair request size.")
                    data = json.loads(self.rfile.read(length).decode("utf-8"))
                    self._json(repair_mqtt_entities(data))
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except (ValueError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/maintenance/reset-everything":
            try:
                with _exclusive_operation("Reset Everything"):
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 4096:
                        raise ValueError("Invalid Reset Everything request size.")
                    data = json.loads(self.rfile.read(length).decode("utf-8"))
                    if not isinstance(data, dict):
                        raise ValueError("Reset Everything request must contain a JSON object.")
                    if str(data.get("confirmation") or "") != RESET_EVERYTHING_CONFIRMATION:
                        raise ValueError(
                            f'Type "{RESET_EVERYTHING_CONFIRMATION}" exactly to confirm Reset Everything.'
                        )
                    self._json(_reset_everything())
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except (ValueError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/discovery/reset-snmp":
            try:
                with _exclusive_operation("SNMP Discovery reset"):
                    self._json(_reset_snmp_discovery_data())
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except RuntimeError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/discovery/regenerate-yaml":
            operation_name = "SNMP2MQTT YAML regeneration"
            try:
                _claim_operation(operation_name)
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
                return
            _DISCOVERY_STOP_REQUESTED.clear()
            _set_discovery_state(
                running=True,
                started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                finished_at=None,
                success=None,
                message="Preparing SNMP2MQTT YAML regeneration",
                log_tail=[],
                stage="Preparing SNMP2MQTT YAML regeneration",
                switch="",
                target="",
                command="",
                activity="Loading saved Discovery data and SNMP walks",
                phase="preparing",
                mode="regenerate_yaml",
                snmp2mqtt={"status": "Waiting", "action": "none", "slug": None, "state": None, "message": "Waiting for YAML regeneration to complete"},
            )
            thread = threading.Thread(
                target=_run_discovery,
                args=(self.app.discovery_script, "regenerate_yaml"),
                daemon=True,
            )
            try:
                thread.start()
            except Exception:
                _release_operation(operation_name)
                raise
            self._json({"started": True, "mode": "regenerate_yaml"}, HTTPStatus.ACCEPTED)
            return
        if path == "/api/discovery/regenerate-card":
            try:
                result = _start_dashboard_card_regeneration(self.app.discovery_script)
                self._json(result, HTTPStatus.ACCEPTED)
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return
        if path == "/api/discovery/start":
            try:
                _claim_operation("Discovery")
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
                return
            _DISCOVERY_STOP_REQUESTED.clear()
            _set_discovery_state(
                running=True,
                started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                finished_at=None,
                success=None,
                message="Preparing Discovery",
                log_tail=[],
                stage="Preparing Discovery",
                mode="discovery",
                switch="",
                target="",
                command="",
                activity="Validating configured switches",
                phase="preparing",
                snmp2mqtt={"status": "Waiting", "action": "none", "slug": None, "state": None, "message": "Waiting for Discovery to complete"},
            )
            thread = threading.Thread(target=_run_discovery, args=(self.app.discovery_script,), daemon=True)
            try:
                thread.start()
            except Exception:
                _release_operation("Discovery")
                raise
            self._json({"started": True}, HTTPStatus.ACCEPTED)
            return
        if path == "/api/discovery/stop":
            if not _request_discovery_stop():
                self._json({"error": "Discovery is not running."}, HTTPStatus.CONFLICT)
                return
            self._json({"stopping": True}, HTTPStatus.ACCEPTED)
            return
        if path != "/api/create":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            _claim_operation("Support My Switch")
        except OperationConflict as exc:
            self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65536:
                raise ValueError("Invalid request size.")
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            settings = _validate_request(data)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            _release_operation("Support My Switch")
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        _set_state(
            running=True,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            finished_at=None,
            success=None,
            message="Starting contribution…",
            log_tail=[],
        )
        thread = threading.Thread(
            target=_run_bundle,
            args=(settings, self.app.support_script, self.app.contributions_dir, self.app.version),
            daemon=True,
        )
        try:
            thread.start()
        except Exception:
            _release_operation("Support My Switch")
            raise
        self._json({"started": True}, HTTPStatus.ACCEPTED)


class SupportServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], *, contributions_dir: Path, options_file: Path, support_script: Path, discovery_script: Path, version: str) -> None:
        super().__init__(address, handler)
        self.contributions_dir = contributions_dir
        self.options_file = options_file
        self.support_script = support_script
        self.discovery_script = discovery_script
        self.version = version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--contributions-dir", type=Path, default=DEFAULT_CONTRIBUTIONS_DIR)
    parser.add_argument("--options-file", type=Path, default=DEFAULT_OPTIONS_FILE)
    parser.add_argument("--support-script", type=Path, default=DEFAULT_SUPPORT_SCRIPT)
    parser.add_argument("--discovery-script", type=Path, default=DEFAULT_DISCOVERY_SCRIPT)
    parser.add_argument("--version", default=os.environ.get("SWITCH_VISION_DISCOVERY_VERSION", "unknown"))
    args = parser.parse_args()
    _ensure_runtime_paths()
    args.contributions_dir.mkdir(parents=True, exist_ok=True)
    try:
        startup_projection = _apply_saved_device_order_to_dashboard(
            touch_if_unchanged=False,
        )
        stale_removed = int(startup_projection.get("stale_snmp_cards_removed") or 0)
        if stale_removed:
            print(
                f"[Switch Vision Hub] Removed {stale_removed} stale SNMP dashboard card(s) from the visible projection.",
                flush=True,
            )
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            f"[Switch Vision Hub] Dashboard startup reconciliation skipped: {exc}",
            flush=True,
        )
    server = SupportServer(
        (args.host, args.port),
        SupportHandler,
        contributions_dir=args.contributions_dir,
        options_file=args.options_file,
        support_script=args.support_script,
        discovery_script=args.discovery_script,
        version=args.version,
    )
    print(f"[Support My Switch Web] Listening on {args.host}:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
