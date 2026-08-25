#!/usr/bin/env python3
"""Local Home Assistant Ingress UI for Support My Switch.

The UI creates privacy-processed contribution bundles by invoking the existing
support_my_switch.sh backend. It never sends email or stores mail credentials.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import html
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
from mqtt_maintenance_runtime import repair_mqtt_entities, scan_mqtt_entities
from discovery_backups import (
    create_pre_mutation_backup,
    discovery_backup_status,
    enforce_retention,
    remove_discovery_backup,
)

SUPPORT_ADDRESS = "switch-vision@zemerdon.com"
SUPERVISOR_INGRESS_IP = "172.30.32.2"
GITHUB_SPONSORS_URL = "https://github.com/sponsors/zemerdon"
DEFAULT_CONTRIBUTIONS_DIR = Path("/share/switch_vision/contributions")
DEFAULT_OPTIONS_FILE = Path("/data/options.json")
DEFAULT_SUPPORT_SCRIPT = Path("/support_my_switch.sh")
DEFAULT_DISCOVERY_SCRIPT = Path("/discovery_job.sh")
DEFAULT_SHARE_DIR = Path("/share/switch_vision")
DEFAULT_INSTALLER_MAINTENANCE_RESPONSE = DEFAULT_SHARE_DIR / "installer-maintenance-response.json"
DEFAULT_REGISTRY_FILE = Path("/opt/switch-vision/devices/supported_devices.json")
DEFAULT_GENERATED_SNMP2MQTT = Path("/share/switch_vision/generated-snmp2mqtt.yaml")
DEFAULT_GENERATED_CARD = Path("/share/switch_vision/generated-dashboard-card.yaml")
DEFAULT_UNIFI_SNAPSHOT = Path("/share/switch_vision/unifi/devices.json")
DEFAULT_UNIFI_DIAGNOSTICS = Path("/share/switch_vision/unifi/diagnostics.json")
DEFAULT_DISCOVERY_LOG = DEFAULT_SHARE_DIR / "discovery-web.log"
DEFAULT_SNMPWALKS_DIR = DEFAULT_SHARE_DIR / "snmpwalks"
DEFAULT_CAPABILITIES_DIR = DEFAULT_SHARE_DIR / "capabilities"
DEFAULT_SNMP_RETIREMENT_STATE = Path("/data/snmp2mqtt-retirement-topics.json")
SNMP_RESET_FILES = (
    DEFAULT_SHARE_DIR / "snmpwalk.txt",
    DEFAULT_SHARE_DIR / "generated-snmp2mqtt.yaml",
    DEFAULT_SHARE_DIR / "generated-dashboard-card.yaml",
    DEFAULT_SHARE_DIR / "discovery-report.txt",
    DEFAULT_SHARE_DIR / "last-discovery-run.txt",
    DEFAULT_SHARE_DIR / "snmpwalk.log",
    DEFAULT_SHARE_DIR / "live-snmpwalk.log",
)

UNIFI2MQTT_DEFAULT_OPTIONS = {
    "controller_url": "https://192.168.1.1",
    "site_id": "",
    "api_key": "",
    "verify_ssl": "false",
    "poll_interval": "30",
    "mqtt_host": "core-mosquitto",
    "mqtt_port": "1883",
    "mqtt_username": "",
    "mqtt_password": "",
    "mqtt_topic_prefix": "switch_vision/unifi",
    "mqtt_discovery_prefix": "homeassistant",
}
UNIFI2MQTT_SECRET_FIELDS = {"api_key", "mqtt_password"}

UI_PREFERENCES_PATH = Path("/share/switch_vision/ui-preferences.json")
_UI_DEFAULTS = {
    "density": "comfortable",
    "text_size": "normal",
    "content_width": "standard",
    "show_unifi_integration": True,
}
_UI_ALLOWED = {
    "density": {"comfortable", "compact", "dense"},
    "text_size": {"normal", "small"},
    "content_width": {"standard", "wide", "full"},
}


def _discovery_ui_preferences() -> dict[str, str]:
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
            values["show_unifi_integration"] = bool(
                discovery.get("show_unifi_integration", values["show_unifi_integration"])
            )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    return values


def _page_with_ui_preferences() -> str:
    """Apply the current UI preference classes to the Discovery page."""
    preferences = _discovery_ui_preferences()
    classes = " ".join(
        (
            f"density-{preferences['density']}",
            f"text-{preferences['text_size']}",
            f"width-{preferences['content_width']}",
        )
    )
    return _PAGE.replace("<body><main>", f'<body class="{classes}"><main>', 1)

DISCOVERY_EXPORT_FORMAT = "switch-vision-discovery-config-v2"
DISCOVERY_IMPORT_FORMATS = {
    "switch-vision-discovery-config-v1",
    DISCOVERY_EXPORT_FORMAT,
}
DISCOVERY_CONFIG_KEYS = {
    "input_path", "snmpwalks_dir", "report_path", "run_snmp_walks",
    "enable_switch_list", "switches", "stack_member_prefixes",
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
        "WS-C2960X-24PS-L", "WS-C2960X-24TS-L", "WS-C2960S-48FPD-L",
        "WS-C3560CG-8PC-S", "EX3300-48P", "SG500X-24",
        "S5720-12TP-LI-AC", "S5735-L8P4X-A1",
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
    if switch_name and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", switch_name):
        raise ValueError(f"Switch entry {index} switch_name contains unsupported characters.")
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
    if not switch_name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", switch_name):
        raise ValueError(f"Stack member entry {index} has an invalid switch_name.")
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
        switch_names[name_key] = f"Switch entry {index}"

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
        merged = dict(current)
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
_OPERATION_ACTIVE: dict[str, Any] = {"name": None, "started_at": None}
_DISCOVERY_PROCESS: subprocess.Popen[str] | None = None
_DISCOVERY_STOP_REQUESTED = threading.Event()

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
        contributions_dir.glob("Switch_Vision_Contribution_SV-*.zip"),
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
    return {
        "contribution_id": manifest.get("contribution_id") or "Unknown",
        "version": manifest.get("switch_vision_version") or "Unknown",
        "quality": manifest.get("bundle_quality") or "Unknown",
        "ready_to_send": bool(manifest.get("ready_to_send")),
        "created_at": manifest.get("created_at") or "",
        "archive": archive.name,
        "archive_size": archive.stat().st_size,
        "email": email_path.name if email_path.is_file() else None,
        "actions": actions_path.name if actions_path.is_file() else None,
        "devices": devices if isinstance(devices, list) else [],
        "privacy": privacy if isinstance(privacy, dict) else {},
        "processing": processing if isinstance(processing, dict) else {},
    }


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
) -> bool:
    """Capture an automatic contribution only after the runtime handoff check."""
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
    lines: list[str] = []
    generated_yaml_previous_mtime = DEFAULT_GENERATED_SNMP2MQTT.stat().st_mtime if DEFAULT_GENERATED_SNMP2MQTT.is_file() else None
    generated_yaml_previous_topics = _remember_current_snmp2mqtt_topics() if generated_yaml_previous_mtime is not None else _load_snmp2mqtt_retirement_topics()
    regenerate_only = mode == "regenerate_yaml"
    operation_name = "SNMP2MQTT YAML regeneration" if regenerate_only else "Discovery"
    preparing_message = "Preparing SNMP2MQTT YAML regeneration" if regenerate_only else "Preparing Discovery"
    preparing_activity = "Loading saved Discovery data and SNMP walks" if regenerate_only else "Validating configured switches"
    waiting_message = "Waiting for YAML regeneration to complete" if regenerate_only else "Waiting for Discovery to complete"
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
        snmp2mqtt={"status": "Waiting", "action": "none", "slug": None, "state": None, "message": waiting_message},
    )
    try:
        _ensure_runtime_paths()
        if regenerate_only:
            auto_bundle_settings = None
            options_snapshot = _write_snmp2mqtt_regeneration_options_snapshot()
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
        discovery_env = os.environ.copy()
        discovery_env["SWITCH_VISION_OPTIONS_FILE"] = str(options_snapshot)
        if regenerate_only:
            discovery_env["SWITCH_VISION_CAPABILITIES_DIR"] = "/tmp/switch_vision_regenerate_capabilities"
        with log_path.open("a", encoding="utf-8") as log_file:
            action_label = "SNMP2MQTT YAML regeneration" if regenerate_only else "Discovery"
            log_file.write(f"\n=== {action_label} started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            log_file.write(
                "Discovery configuration: stored-walk regeneration snapshot\n"
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
                lines = lines[-300:]
                _set_discovery_state(log_tail=lines)
            return_code = process.wait()
        if _DISCOVERY_STOP_REQUESTED.is_set():
            stopped_label = "YAML regeneration" if regenerate_only else "Discovery"
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
        if return_code != 0:
            raise RuntimeError(f"{operation_name} exited with code {return_code}.")
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
            )
            snmp2mqtt_result["support_bundle_after_handoff"] = (
                "captured" if bundle_captured else "failed"
            )
        if snmp2mqtt_result.get("handoff_failed"):
            failure_message = str(
                snmp2mqtt_result.get("message")
                or "SNMP2MQTT generated-configuration handoff could not be verified."
            )
            _set_discovery_state(
                success=False,
                message=failure_message,
                stage="SNMP2MQTT handoff not verified",
                activity=failure_message,
                command="",
                phase="failed",
                log_tail=lines[-300:],
                snmp2mqtt=snmp2mqtt_result,
            )
            return
        auto_message = "SNMP2MQTT YAML regeneration complete" if regenerate_only else "Discovery complete"
        _set_discovery_state(
            success=True,
            message=auto_message,
            stage="Complete",
            activity=snmp2mqtt_result.get("message") or auto_message,
            command="",
            phase="complete",
            log_tail=lines[-300:],
            snmp2mqtt=snmp2mqtt_result,
        )
    except Exception as exc:
        lines.append(str(exc))
        _set_discovery_state(success=False, message=str(exc), log_tail=lines[-80:], phase="failed")
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
        _release_operation(operation_name)





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
    _validate_inventory_identities(source_options)
    snapshot_options = dict(source_options)
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


def _configured_devices_snapshot(options_file: Path) -> dict[str, Any]:
    """Return browser-safe persistent switch inventory without exposing SNMP secrets."""
    writable = True
    source = "supervisor"
    warning = ""
    try:
        options = _self_addon_options()
    except RuntimeError as exc:
        # Read-only fallback keeps the Hub informative even if Supervisor API
        # access is temporarily unavailable. Writes always require Supervisor.
        options = _load_options(options_file)
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
        try:
            state = _switch_enabled_state(raw.get("enabled", "enabled"), f"Switch entry {index + 1} enabled")
        except ValueError:
            state = "enabled"
        devices.append({
            "index": index,
            "switch_name": switch_name,
            "display_name": str(raw.get("display_name") or "").strip()[:120],
            "switch_host": switch_host[:255],
            "sensor_prefix": sensor_prefix[:64],
            "switch_model": str(raw.get("switch_model") or "auto").strip()[:120] or "auto",
            "enabled": state,
        })
    return {
        "devices": devices,
        "count": len(devices),
        "writable": writable,
        "source": source,
        "warning": warning,
        "switch_list_enabled": _safe_bool(options.get("enable_switch_list"), True),
    }


def _set_configured_device_state(options_file: Path, request_data: Any) -> dict[str, Any]:
    """Persist one saved switch state through the authoritative Supervisor API."""
    if not isinstance(request_data, dict):
        raise ValueError("Device state request must contain a JSON object.")
    raw_index = request_data.get("index")
    if isinstance(raw_index, bool) or not isinstance(raw_index, int) or raw_index < 0 or raw_index > 255:
        raise ValueError("Device index is invalid. Refresh Devices and try again.")
    expected_name = _plain_text(
        request_data.get("switch_name", ""), "switch_name", max_length=64, allow_empty=False
    ).strip()
    desired = _switch_enabled_state(request_data.get("enabled"), "enabled")

    with _OPTIONS_UPDATE_LOCK:
        options = _self_addon_options()
        rows = options.get("switches")
        if not isinstance(rows, list) or raw_index >= len(rows):
            raise ValueError("The saved device list changed. Refresh Devices and try again.")
        current = rows[raw_index]
        if not isinstance(current, dict):
            raise ValueError("The saved device entry is invalid. Open Discovery Settings to review it.")
        current_name = str(current.get("switch_name") or "").strip()
        if not current_name or current_name != expected_name:
            raise ValueError("The saved device list changed. Refresh Devices and try again.")

        updated_rows = list(rows)
        updated_row = dict(current)
        updated_row["enabled"] = desired
        updated_rows[raw_index] = updated_row
        updated_options = dict(options)
        updated_options["switches"] = updated_rows
        _validate_inventory_identities(updated_options)
        create_pre_mutation_backup(options, reason="device_state_update")

        # Home Assistant Supervisor remains the source of truth. Sending the
        # complete current options dictionary preserves unrelated settings and
        # secrets while changing exactly one per-switch state field.
        _supervisor_json(
            "/addons/self/options",
            method="POST",
            timeout=12.0,
            payload={"options": updated_options},
        )

        # Confirm Supervisor accepted the new value before presenting success.
        confirmed = _self_addon_options()
        confirmed_rows = confirmed.get("switches")
        if not isinstance(confirmed_rows, list) or raw_index >= len(confirmed_rows):
            raise RuntimeError("Home Assistant saved the request but the updated device state could not be confirmed.")
        confirmed_row = confirmed_rows[raw_index]
        if not isinstance(confirmed_row, dict):
            raise RuntimeError("Home Assistant returned an invalid device entry after saving.")
        confirmed_state = _switch_enabled_state(confirmed_row.get("enabled", "enabled"), "enabled")
        if str(confirmed_row.get("switch_name") or "").strip() != expected_name or confirmed_state != desired:
            raise RuntimeError("Home Assistant did not confirm the requested device state.")

    return _configured_devices_snapshot(options_file)


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


def _home_assistant_ws(command: dict[str, Any]) -> Any:
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
            max_size=4 * 1024 * 1024,
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
        raise ValueError("UI density must be comfortable, compact, or dense.")
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
    result = _home_assistant_ws({"type": "switch_vision/get_settings"})
    if not isinstance(result, dict) or not isinstance(result.get("settings"), dict):
        raise RuntimeError("Switch Vision Core did not return a valid settings payload.")
    return result


def _save_core_settings(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Core settings request must contain a JSON object.")
    unknown = sorted(set(data) - {"settings", "reset_to_defaults"})
    if unknown:
        raise ValueError(f"Unsupported Core settings request field: {unknown[0]}")
    reset = data.get("reset_to_defaults", False)
    if not isinstance(reset, bool):
        raise ValueError("reset_to_defaults must be true or false.")
    command: dict[str, Any] = {"type": "switch_vision/set_settings", "reset_to_defaults": reset}
    if not reset:
        settings = data.get("settings")
        if not isinstance(settings, dict):
            raise ValueError("Core settings must contain a settings object.")
        command["settings"] = settings
    result = _home_assistant_ws(command)
    if not isinstance(result, dict) or not isinstance(result.get("settings"), dict):
        raise RuntimeError("Switch Vision Core did not confirm the saved settings.")
    return result


def _hub_app_path(value: Any, field: str) -> str:
    text = _plain_text(value, field, max_length=512, allow_empty=False).strip()
    path = PurePosixPath(text)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field} must be an absolute path without parent traversal.")
    if not (text == "/config" or text.startswith("/config/") or text == "/share" or text.startswith("/share/")):
        raise ValueError(f"{field} must stay under /config or /share.")
    return str(path)


def _snmp2mqtt_addon_options() -> tuple[str, str, dict[str, Any]]:
    addon = _find_snmp2mqtt_addon()
    if addon is None:
        raise RuntimeError("Switch Vision SNMP2MQTT is not installed.")
    slug = str(addon.get("slug") or "").strip()
    if not slug:
        raise RuntimeError("Switch Vision SNMP2MQTT slug could not be resolved.")
    payload = _supervisor_json(f"/addons/{quote(slug, safe='')}/info")
    info = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    options = info.get("options") if isinstance(info, dict) else None
    if not isinstance(options, dict):
        raise RuntimeError("Home Assistant did not expose the SNMP2MQTT app options.")
    state = str(info.get("state") or addon.get("state") or "unknown").strip().lower()
    return slug, state, dict(options)


def _snmp2mqtt_settings_status() -> dict[str, Any]:
    try:
        slug, state, options = _snmp2mqtt_addon_options()
    except RuntimeError as exc:
        if "not installed" in str(exc).lower():
            return {"schema_version": 1, "installed": False, "settings": None, "password_configured": False}
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
            "targets_path": str(options.get("targets_path") or "/config/app_configs/switch_vision_snmp2mqtt/targets.yaml"),
            "use_switch_vision_generated_yaml": bool(options.get("use_switch_vision_generated_yaml", True)),
            "switch_vision_generated_yaml_path": str(options.get("switch_vision_generated_yaml_path") or "/share/switch_vision/generated-snmp2mqtt.yaml"),
            "imported_targets_path": str(options.get("imported_targets_path") or "/config/app_configs/switch_vision_snmp2mqtt/imported/generated-snmp2mqtt.yaml"),
            "backup_existing_config": bool(options.get("backup_existing_config", False)),
            "homeassistant": {"discovery": True, "prefix": "homeassistant"},
            "clear_password": False,
        },
        "enforced": {"homeassistant_discovery": True, "homeassistant_prefix": "homeassistant"},
    }


def _save_snmp2mqtt_settings(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("settings"), dict):
        raise ValueError("SNMP2MQTT settings request must contain a settings object.")
    if sorted(set(data) - {"settings"}):
        raise ValueError("SNMP2MQTT settings request contains unsupported fields.")
    requested = data["settings"]
    allowed = {"mqtt", "targets_path", "use_switch_vision_generated_yaml", "switch_vision_generated_yaml_path", "imported_targets_path", "backup_existing_config", "homeassistant", "clear_password"}
    unknown = sorted(set(requested) - allowed)
    if unknown:
        raise ValueError(f"Unsupported SNMP2MQTT setting: {unknown[0]}")
    ha_requested = requested.get("homeassistant")
    if not isinstance(ha_requested, dict) or sorted(set(ha_requested) - {"discovery", "prefix"}):
        raise ValueError("SNMP2MQTT Home Assistant discovery settings are invalid.")
    if ha_requested.get("discovery") is not True or str(ha_requested.get("prefix") or "") != "homeassistant":
        raise ValueError("Switch Vision requires SNMP2MQTT MQTT Discovery with the homeassistant prefix.")
    slug, app_state, current = _snmp2mqtt_addon_options()
    updated = dict(current)
    current_mqtt = current.get("mqtt") if isinstance(current.get("mqtt"), dict) else {}
    mqtt_requested = requested.get("mqtt")
    if not isinstance(mqtt_requested, dict) or sorted(set(mqtt_requested) - {"host", "port", "username", "password"}):
        raise ValueError("SNMP2MQTT MQTT settings are invalid.")
    host = _plain_text(mqtt_requested.get("host", ""), "MQTT host", max_length=255).strip()
    username = _plain_text(mqtt_requested.get("username", ""), "MQTT username", max_length=256).strip()
    port = mqtt_requested.get("port", 1883)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("MQTT port must be between 1 and 65535.")
    password = _plain_text(mqtt_requested.get("password", ""), "MQTT password", max_length=512)
    clear_password = requested.get("clear_password", False)
    if not isinstance(clear_password, bool):
        raise ValueError("Clear saved MQTT password must be true or false.")
    merged_mqtt = dict(current_mqtt)
    merged_mqtt.update({"host": host, "port": port, "username": username})
    merged_mqtt["password"] = "" if clear_password else (password if password else current_mqtt.get("password", ""))
    updated["mqtt"] = merged_mqtt
    for key in ("targets_path", "switch_vision_generated_yaml_path", "imported_targets_path"):
        if key not in requested:
            raise ValueError(f"SNMP2MQTT setting '{key}' is required by the Hub contract.")
        updated[key] = _hub_app_path(requested[key], key)
    for key in ("use_switch_vision_generated_yaml", "backup_existing_config"):
        value = requested.get(key)
        if type(value) is not bool:
            raise ValueError(f"{key} must be true or false.")
        updated[key] = value
    homeassistant = dict(current.get("homeassistant") or {}) if isinstance(current.get("homeassistant"), dict) else {}
    homeassistant.update({"discovery": True, "prefix": "homeassistant"})
    updated["homeassistant"] = homeassistant
    changed = updated != current
    if changed:
        _supervisor_json(f"/addons/{quote(slug, safe='')}/options", method="POST", timeout=20.0, payload={"options": updated})
        confirmed_slug, _, confirmed = _snmp2mqtt_addon_options()
        if confirmed_slug != slug:
            raise RuntimeError("SNMP2MQTT app identity changed while saving settings.")
        if confirmed != updated:
            raise RuntimeError("Home Assistant did not confirm the complete SNMP2MQTT settings update.")
        if app_state in {"started", "running"}:
            _supervisor_json(f"/addons/{quote(slug, safe='')}/restart", method="POST", timeout=30.0)
    result = _snmp2mqtt_settings_status()
    result.update({"saved": True, "changed": changed, "restart_requested": bool(changed and app_state in {"started", "running"})})
    return result


_DISCOVERY_HUB_SUPPORT_KEYS = {"generate_support_my_switch_bundle", "support_mask_management_ips", "support_mask_mac_addresses", "support_mask_hostnames", "support_mask_vlan_names", "support_mask_interface_descriptions", "support_contributor_type", "support_contributor_value"}
_DISCOVERY_HUB_KEYS = DISCOVERY_CONFIG_KEYS | _DISCOVERY_HUB_SUPPORT_KEYS
_DISCOVERY_HUB_BOOL_KEYS = {"run_snmp_walks", "enable_switch_list", "parse_all_walks", "generate_snmp2mqtt", "clean_output_before_walk", "backup_retention_enabled", "generate_support_my_switch_bundle", "support_mask_management_ips", "support_mask_mac_addresses", "support_mask_hostnames", "support_mask_vlan_names", "support_mask_interface_descriptions"}
_DISCOVERY_HUB_PATH_KEYS = {"input_path", "snmpwalks_dir", "report_path", "targets_csv", "last_run_summary_path", "generated_yaml_path", "generated_card_path", "snmp_log_path"}


def _discovery_settings_status() -> dict[str, Any]:
    options = _self_addon_options()
    defaults = {
        "input_path": "/share/switch_vision/snmpwalk.txt", "snmpwalks_dir": "/share/switch_vision/snmpwalks", "report_path": "/share/switch_vision/discovery-report.txt",
        "run_snmp_walks": "true", "enable_switch_list": "true", "switches": [], "stack_member_prefixes": [], "parse_all_walks": "false", "generate_snmp2mqtt": "true", "clean_output_before_walk": "false",
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
    settings["switches"] = safe_switches
    stack = settings.get("stack_member_prefixes")
    settings["stack_member_prefixes"] = [dict(item) for item in stack if isinstance(item, dict)] if isinstance(stack, list) else []
    settings["support_contributor_value_configured"] = bool(str(options.get("support_contributor_value") or ""))
    settings["support_contributor_value"] = ""
    return {"schema_version": 1, "settings": settings, "models": sorted({"auto"} | _manual_snmp_override_models()), "secret_policy": {"snmp_community": "write_only_blank_preserves", "support_contributor_value": "write_only_blank_preserves"}}


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
        updated = dict(current)
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
        if "switches" in requested:
            rows = requested["switches"]
            if not isinstance(rows, list) or len(rows) > 256:
                raise ValueError("switches must contain at most 256 entries.")
            current_rows = current.get("switches") if isinstance(current.get("switches"), list) else []
            current_by_name = {str(row.get("switch_name") or "").strip(): row for row in current_rows if isinstance(row, dict) and str(row.get("switch_name") or "").strip()}
            validated_rows: list[dict[str, Any]] = []
            for index, raw in enumerate(rows, start=1):
                if not isinstance(raw, dict):
                    raise ValueError(f"Switch entry {index} must be an object.")
                row = dict(raw)
                row.pop("snmp_community_configured", None)
                original_name = str(row.pop("original_switch_name", "") or "").strip()
                community = row.get("snmp_community", "")
                if not isinstance(community, str):
                    raise ValueError(f"Switch entry {index} snmp_community must be text.")
                if not community:
                    previous = current_by_name.get(original_name or str(row.get("switch_name") or "").strip())
                    if previous is None or not str(previous.get("snmp_community") or ""):
                        raise ValueError(f"Switch entry {index} requires an SNMP community for a new or renamed switch.")
                    row["snmp_community"] = str(previous.get("snmp_community"))
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
            enforce_retention(confirmed)
    result = _discovery_settings_status()
    result.update({"saved": True, "changed": changed})
    return result


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
        "device_classification": classifications,
    }


def _unifi2mqtt_settings_status() -> dict[str, Any]:
    addon = _find_unifi2mqtt_addon(include_store=True)
    snapshot = _unifi2mqtt_snapshot_status()
    if addon is None:
        return {
            "installed": False,
            "available": False,
            "state": "not_installed",
            "slug": None,
            "config_url": None,
            "options": {
                key: value
                for key, value in UNIFI2MQTT_DEFAULT_OPTIONS.items()
                if key not in UNIFI2MQTT_SECRET_FIELDS
            },
            "api_key_configured": False,
            "mqtt_password_configured": False,
            "options_readable": False,
            "snapshot": snapshot,
        }
    slug = str(addon.get("slug") or "").strip()
    installed_value = addon.get("installed")
    installed = (
        addon.get("_source") == "addons"
        or installed_value not in (False, None, "", 0)
    )
    state = str(addon.get("state") or ("stopped" if installed else "not_installed"))
    options = dict(UNIFI2MQTT_DEFAULT_OPTIONS)
    options_readable = False
    if installed and slug:
        try:
            info = _supervisor_json(f"/addons/{quote(slug, safe='')}/info")
            info_data = info.get("data") if isinstance(info.get("data"), dict) else info
            if isinstance(info_data, dict):
                state = str(info_data.get("state") or state)
                stored = info_data.get("options")
                if isinstance(stored, dict) and "controller_url" in stored:
                    options.update(stored)
                    options_readable = True
        except RuntimeError:
            pass
    safe_options = {
        key: value for key, value in options.items() if key not in UNIFI2MQTT_SECRET_FIELDS
    }
    return {
        "installed": installed,
        "available": True,
        "state": state,
        "slug": slug or None,
        "config_url": (
            f"/config/app/{quote(slug, safe='')}/config" if installed and slug else None
        ),
        "options": safe_options,
        "api_key_configured": bool(str(options.get("api_key") or "").strip()),
        "mqtt_password_configured": bool(str(options.get("mqtt_password") or "").strip()),
        "options_readable": options_readable,
        "snapshot": snapshot,
    }


def _validate_unifi2mqtt_options(data: Any, current: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("UniFi2MQTT settings must be a JSON object.")
    result = dict(current)
    controller = _plain_text(
        data.get("controller_url", result.get("controller_url", "")),
        "controller_url",
        max_length=512,
        allow_empty=False,
    ).strip()
    parsed = urlparse(controller)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Controller URL must be a valid http:// or https:// URL.")
    result["controller_url"] = controller.rstrip("/")
    result["site_id"] = _plain_text(
        data.get("site_id", result.get("site_id", "")),
        "site_id",
        max_length=160,
        allow_empty=False,
    ).strip()
    result["verify_ssl"] = _bool_string(
        data.get("verify_ssl", result.get("verify_ssl", "false")),
        "verify_ssl",
    )
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
    for key in ("mqtt_topic_prefix", "mqtt_discovery_prefix"):
        value = _plain_text(
            str(data.get(key, result.get(key, ""))),
            key,
            max_length=256,
            allow_empty=False,
        ).strip().strip("/")
        if not value or "+" in value or "#" in value:
            raise ValueError(
                f"{key} must be a plain MQTT topic prefix without + or # wildcards."
            )
        result[key] = value
    # Blank secret inputs mean preserve the existing value. Secrets are never
    # sent back to the browser by the GET endpoint.
    for key in UNIFI2MQTT_SECRET_FIELDS:
        if key in data and str(data.get(key) or ""):
            result[key] = _plain_text(str(data[key]), key, max_length=2048)

    # UniFi Network Integration API requests are site-scoped and authenticated.
    # A blank API-key field is valid only when it preserves an already stored key.
    if not isinstance(result.get("api_key"), str) or not result["api_key"].strip():
        raise ValueError(
            "API Key is required. Enter the read-only UniFi Integration API key "
            "the first time you configure UniFi2MQTT."
        )
    return result


def _save_unifi2mqtt_settings(data: Any) -> dict[str, Any]:
    status = _unifi2mqtt_settings_status()
    if not status.get("installed") or not status.get("slug"):
        raise RuntimeError("Switch Vision UniFi2MQTT is not installed.")
    slug = str(status["slug"])
    info = _supervisor_json(f"/addons/{quote(slug, safe='')}/info")
    info_data = info.get("data") if isinstance(info.get("data"), dict) else info
    current = dict(UNIFI2MQTT_DEFAULT_OPTIONS)
    stored_options = info_data.get("options") if isinstance(info_data, dict) else None
    if not isinstance(stored_options, dict) or "controller_url" not in stored_options:
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
    result = _unifi2mqtt_settings_status()
    result["saved"] = True
    result["restarted"] = restarted
    result["started"] = started
    return result


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
        # generated file was consumed. Wait briefly, inspect state, then prove
        # the expected retained MQTT discovery set is live.
        time.sleep(2.0)
        resulting_state = "requested"
        try:
            info = _supervisor_json(f"/addons/{quote(slug, safe='')}/info")
            info_data = info.get("data") if isinstance(info.get("data"), dict) else info
            if isinstance(info_data, dict):
                resulting_state = str(info_data.get("state") or resulting_state)
        except Exception as exc:
            lines.append(f"SNMP2MQTT status refresh warning: {type(exc).__name__}.")

        activation = _verify_snmp2mqtt_activation(lines)
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

        if not activation.get("activation_verified"):
            expected = activation.get("mqtt_current_expected")
            retained = activation.get("mqtt_current_retained")
            missing = activation.get("mqtt_current_missing")
            if activation.get("verification_status") == "unavailable":
                detail = "the MQTT activation check was unavailable"
            else:
                detail = (
                    f"only {retained if retained is not None else 'unknown'}/"
                    f"{expected if expected is not None else 'unknown'} expected retained "
                    f"discovery entries were current; missing "
                    f"{missing if missing is not None else 'unknown'}"
                )
            message = (
                f"Switch Vision SNMP2MQTT {action} was requested, but the newly generated "
                f"configuration was not verified active because {detail}. "
                "Previous retained identities were preserved. Review the SNMP2MQTT app "
                "configuration/log, then run Discovery again."
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

        # The replacement identity set is proven live. Only now may older exact
        # generated identities be retired.
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

        message = (
            f"Switch Vision SNMP2MQTT {action} verified active; "
            f"{activation.get('mqtt_current_retained')}/"
            f"{activation.get('mqtt_current_expected')} expected MQTT discovery entries are current."
        )
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
        "note": "Review or copy this dashboard YAML. Discovery does not install it automatically.",
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


def _diagnostics_snapshot(version: str) -> dict[str, Any]:
    share = DEFAULT_SHARE_DIR
    registry_raw = _read_json(DEFAULT_REGISTRY_FILE)
    if isinstance(registry_raw, dict):
        registry_devices = registry_raw.get("devices") or []
    elif isinstance(registry_raw, list):
        registry_devices = registry_raw
    else:
        registry_devices = []

    capability_dir = share / "capabilities"
    capability_files = sorted(capability_dir.glob("*-capabilities.json")) if capability_dir.is_dir() else []
    devices: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    for cap_path in capability_files:
        data = _read_json(cap_path)
        if not isinstance(data, dict):
            warnings.append(f"Could not read capability file: {cap_path.name}")
            continue
        device = data.get("device") if isinstance(data.get("device"), dict) else {}
        interfaces = data.get("interfaces") if isinstance(data.get("interfaces"), list) else []
        model = str(device.get("detected_model_text") or device.get("model_text") or device.get("model") or "Unknown")
        registry = registry_lookup({"devices": registry_devices}, model) or {}
        validation = registry.get("validation") if isinstance(registry.get("validation"), dict) else {}
        physical = [i for i in interfaces if isinstance(i, dict) and i.get("physical")]
        rj45 = [i for i in physical if i.get("media") == "rj45"]
        uplinks = [i for i in physical if i.get("media") in {"sfp", "sfp_plus", "uplink"}]
        source_walk = Path(str(data.get("source_walk") or ""))
        walk_found = source_walk.is_file() if str(source_walk) else False
        status = str(registry.get("status") or device.get("support_status") or "detected")
        devices.append({
            "name": cap_path.name.removesuffix("-capabilities.json"),
            "model": model,
            "family": registry.get("family") or device.get("family") or "Unknown",
            "registry_match": bool(registry),
            "registry_status": status,
            "last_validated_version": registry.get("last_validated_version"),
            "mapping_profile": registry.get("mapping_profile") or registry.get("dashboard_profile"),
            "calibration_profile": registry.get("calibration_profile"),
            "validation": validation,
            "physical_interfaces": len(physical),
            "rj45_interfaces": len(rj45),
            "uplink_interfaces": len(uplinks),
            "walk_found": walk_found,
            "generated_at": data.get("generated_at"),
        })

    # Merge normalized UniFi2MQTT devices into the same Devices/Diagnostics
    # view without requiring duplicate SNMP target rows.
    unifi_snapshot = _read_json(DEFAULT_UNIFI_SNAPSHOT)
    if isinstance(unifi_snapshot, dict) and isinstance(unifi_snapshot.get("devices"), list):
        for raw in unifi_snapshot["devices"]:
            if not isinstance(raw, dict):
                continue
            model = str(raw.get("model") or "Unknown")
            registry = registry_lookup({"devices": registry_devices}, model) or {}
            validation = registry.get("validation") if isinstance(registry.get("validation"), dict) else {}
            ports = raw.get("ports") if isinstance(raw.get("ports"), list) else []
            physical = [p for p in ports if isinstance(p, dict)]
            rj45 = [p for p in physical if str(p.get("connector") or "").upper() == "RJ45"]
            uplinks = [p for p in physical if str(p.get("connector") or "").upper() in {"SFP", "SFPPLUS", "SFP+"}]
            devices.append({
                "name": str(raw.get("name") or model),
                "model": model,
                "family": registry.get("family") or "UniFi",
                "registry_match": bool(registry),
                "registry_status": str(registry.get("status") or "detected"),
                "last_validated_version": registry.get("last_validated_version"),
                "mapping_profile": registry.get("mapping_profile") or registry.get("dashboard_profile"),
                "calibration_profile": registry.get("calibration_profile"),
                "validation": validation,
                "physical_interfaces": len(physical),
                "rj45_interfaces": len(rj45),
                "uplink_interfaces": len(uplinks),
                "walk_found": False,
                "generated_at": unifi_snapshot.get("generated_at"),
                "data_source": "UniFi API",
                "online": str(raw.get("state") or "").upper() == "ONLINE",
                "firmware": raw.get("firmware"),
                "api_capabilities": raw.get("api_capabilities") if isinstance(raw.get("api_capabilities"), dict) else {},
            })

    unifi_diagnostics = _unifi2mqtt_diagnostics_status()

    if unifi_diagnostics.get("found"):
        if not unifi_diagnostics.get("valid"):
            warnings.append(
                "UniFi2MQTT diagnostics.json could not be read."
            )
        elif unifi_diagnostics.get("status") == "error":
            stage = unifi_diagnostics.get("stage") or "unknown"
            error_type = (
                unifi_diagnostics.get("error_type")
                or "UnknownError"
            )
            warnings.append(
                "UniFi2MQTT poll failed at "
                f"{stage}: {error_type}."
            )

    registry_loaded = isinstance(registry_raw, (dict, list))
    if not registry_loaded:
        errors.append("Supported-device registry could not be loaded.")
    report = _file_info(share / "discovery-report.txt")
    generated_yaml = _file_info(share / "generated-snmp2mqtt.yaml")
    generated_card = _file_info(share / "generated-dashboard-card.yaml")
    if not report["found"]:
        warnings.append("No discovery report has been generated yet.")
    snmp2mqtt_applicability = _snmp2mqtt_applicability()
    if not generated_yaml["found"] and snmp2mqtt_applicability["applicable"]:
        warnings.append("Generated SNMP2MQTT YAML was not found.")
    if not generated_card["found"]:
        warnings.append("Generated dashboard YAML was not found.")
    if report["found"]:
        report_path = share / "discovery-report.txt"
        report_mtime = report_path.stat().st_mtime
        # Files from one successful Discovery run are written sequentially and
        # can legitimately have slightly different mtimes. Only flag a file as
        # stale when it predates the report by more than two minutes, which
        # indicates it came from an earlier run rather than the same pipeline.
        stale_tolerance_seconds = 120
        stale_candidates = [("dashboard YAML", share / "generated-dashboard-card.yaml")]
        if snmp2mqtt_applicability["applicable"]:
            stale_candidates.insert(0, ("SNMP2MQTT YAML", share / "generated-snmp2mqtt.yaml"))
        for label, path in stale_candidates:
            if not path.is_file():
                continue
            generated_mtime = path.stat().st_mtime
            if generated_mtime + stale_tolerance_seconds < report_mtime:
                generated_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(generated_mtime))
                report_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(report_mtime))
                warnings.append(
                    f"Generated {label} appears stale: generated {generated_text}; latest discovery report {report_text}."
                )

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "version": version,
        "service": "Running",
        "discovery": _discovery_state_snapshot(),
        "registry": {"loaded": registry_loaded, "entries": len(registry_devices), "path": str(DEFAULT_REGISTRY_FILE)},
        "files": {"report": report, "generated_yaml": generated_yaml, "generated_card": generated_card},
        "snmp2mqtt_applicability": snmp2mqtt_applicability,
        "contribution_workflow": {"ready": DEFAULT_SUPPORT_SCRIPT.is_file(), "directory": str(DEFAULT_CONTRIBUTIONS_DIR)},
        "devices": devices,
        "unifi2mqtt_diagnostics": unifi_diagnostics,
        "warnings": warnings,
        "errors": errors,
    }


def _diagnostics_text(data: dict[str, Any]) -> str:
    snmp_applicability = data.get("snmp2mqtt_applicability") or {}
    if snmp_applicability.get("applicable", True):
        snmp_yaml_status = (
            "Found"
            if ((data.get("files") or {}).get("generated_yaml") or {}).get("found")
            else "Missing"
        )
    else:
        snmp_yaml_status = "Not applicable"
    lines = [
        "Switch Vision Diagnostics",
        "=========================",
        f"Generated: {data.get('generated_at')}",
        f"Switch Vision version: {data.get('version')}",
        f"Discovery app: {data.get('service')}",
        f"Discovery status: {(data.get('discovery') or {}).get('message', 'Unknown')}",
        f"Device registry: {'Loaded' if (data.get('registry') or {}).get('loaded') else 'Unavailable'}",
        f"Registry entries: {(data.get('registry') or {}).get('entries', 0)}",
        f"Generated SNMP2MQTT YAML: {snmp_yaml_status}",
        f"Generated dashboard YAML: {'Found' if ((data.get('files') or {}).get('generated_card') or {}).get('found') else 'Missing'}",
        f"Contribution workflow: {'Ready' if (data.get('contribution_workflow') or {}).get('ready') else 'Unavailable'}",
        (
            "UniFi2MQTT diagnostics: "
            + (
                (
                    f"{(data.get('unifi2mqtt_diagnostics') or {}).get('status') or 'unknown'}"
                    f" · stage {(data.get('unifi2mqtt_diagnostics') or {}).get('stage') or 'unknown'}"
                    f" · adopted {(data.get('unifi2mqtt_diagnostics') or {}).get('adopted_devices', 0)}"
                    f" · switches {(data.get('unifi2mqtt_diagnostics') or {}).get('switching_devices', 0)}"
                    f" · rejected {(data.get('unifi2mqtt_diagnostics') or {}).get('rejected_devices', 0)}"
                )
                if (data.get('unifi2mqtt_diagnostics') or {}).get('found')
                else "Unavailable"
            )
        ),
        "",
    ]

    unifi_diag = (
        data.get("unifi2mqtt_diagnostics")
        if isinstance(
            data.get("unifi2mqtt_diagnostics"),
            dict,
        )
        else {}
    )

    classifications = (
        unifi_diag.get("device_classification")
        if isinstance(
            unifi_diag.get("device_classification"),
            list,
        )
        else []
    )

    if classifications:
        lines.append(
            "UniFi2MQTT hardware classification"
        )
        lines.append(
            "---------------------------------"
        )

        for item in classifications:
            if not isinstance(item, dict):
                continue

            model = str(
                item.get("model")
                or "Unknown"
            )

            lines.append(
                f"Model: {model}"
            )
            lines.append(
                "Accepted as switch: "
                + (
                    "yes"
                    if item.get("accepted")
                    else "no"
                )
            )
            lines.append(
                "Classification: "
                + str(
                    item.get("reason")
                    or "unknown"
                )
            )

            features = item.get("features")

            if isinstance(features, list):
                lines.append(
                    "Features: "
                    + (
                        ", ".join(
                            str(value)
                            for value in features
                        )
                        or "none"
                    )
                )

            lines.append("")

    for device in data.get("devices") or []:
        source = str(device.get("data_source") or "SNMP")
        source_status = (
            f"UniFi API state: {'ONLINE' if device.get('online') else 'OFFLINE'}"
            if source == "UniFi API"
            else f"Last SNMP walk: {'PASS/file found' if device.get('walk_found') else 'Unavailable'}"
        )
        lines.extend([
            str(device.get("model") or "Unknown model"),
            "-" * len(str(device.get("model") or "Unknown model")),
            f"Target: {device.get('name')}",
            f"Data source: {source}",
            f"Registry match: {'yes' if device.get('registry_match') else 'no'}",
            f"Registry status: {device.get('registry_status')}",
            source_status,
            *( [f"Firmware: {device.get('firmware') or 'Unknown'}"] if source == "UniFi API" else [] ),
            f"Physical interfaces: {device.get('physical_interfaces', 0)}",
            f"RJ45 interfaces: {device.get('rj45_interfaces', 0)}",
            f"Uplink interfaces: {device.get('uplink_interfaces', 0)}",
            f"Mapping profile: {device.get('mapping_profile') or 'Not assigned'}",
            f"Calibration profile: {device.get('calibration_profile') or 'Not assigned'}",
        ])
        validation = device.get("validation") or {}
        for label, key in [("Exact model", "exact_model_detection"), ("RJ45 mapping", "rj45_mapping"), ("PoE", "poe"), ("System sensors", "system_sensors"), ("Uplinks", "uplinks"), ("Stack", "stack")]:
            lines.append(f"{label}: {validation.get(key, 'unknown')}")
        lines.append("")
    if data.get("warnings"):
        lines.append("Warnings")
        lines.append("--------")
        lines.extend(f"WARNING: {item}" for item in data["warnings"])
        lines.append("")
    if data.get("errors"):
        lines.append("Errors")
        lines.append("------")
        lines.extend(f"ERROR: {item}" for item in data["errors"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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


_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Switch Vision Hub</title>
<script>
(()=>{const key='switch-vision-management-theme-v1';const allowed=['switch-vision','cisco-classic','cisco-nexus','unifi'];let theme='switch-vision';try{const saved=localStorage.getItem(key);if(allowed.includes(saved))theme=saved}catch(_e){}document.documentElement.dataset.svTheme=theme})();
</script>
<style>
:root{color-scheme:dark;--accent:#2196f3;--accent-strong:#2f83bd;--accent-dark:#0f4f7d;--accent-dark-hover:#146698;--accent-soft:rgba(33,150,243,.12);--page:#071525;--card:#0b1d31;--card-strong:#0e233b;--surface-input:#08192b;--surface-button:#0a1a2c;--surface-inset:#091a2d;--surface-hover:#102a44;--muted:#9bb0c7;--line:#214766;--line-soft:#183750;--warn:#ffb74d;--warn-soft:rgba(255,183,77,.12);--ok:#45d483;--ok-soft:rgba(69,212,131,.15);--bad:#ff6b6b;--bad-soft:rgba(255,107,107,.13);--neutral-soft:rgba(119,128,138,.15);--text:#edf5fc;--on-accent:#fff;--on-primary:#fff;--shadow:rgba(0,0,0,.12);--status-bg:rgba(0,0,0,.12);--code-bg:rgba(0,0,0,.18);--chip-bg:rgba(255,255,255,.03);--chip-hover:rgba(255,255,255,.06);--heart:#ff6ea9;--sv-font-body:.9rem;--sv-font-page-title:1.65rem;--sv-font-section-title:1.12rem;--sv-font-small:.8rem;--sv-line-height:1.38}
html[data-sv-theme="cisco-classic"]{color-scheme:dark;--accent:#049fd9;--accent-strong:#049fd9;--accent-dark:#005073;--accent-dark-hover:#00658f;--accent-soft:rgba(4,159,217,.13);--page:#1b2126;--card:#252c32;--card-strong:#303940;--surface-input:#171c21;--surface-button:#20272d;--surface-inset:#20272d;--surface-hover:#303f49;--muted:#b1bec7;--line:#4a5963;--line-soft:#39464f;--warn:#f0b323;--warn-soft:rgba(240,179,35,.13);--ok:#6cc04a;--ok-soft:rgba(108,192,74,.13);--bad:#e05b63;--bad-soft:rgba(224,91,99,.13);--neutral-soft:rgba(177,190,199,.10);--text:#f2f5f7;--on-accent:#fff;--on-primary:#fff;--shadow:rgba(0,0,0,.20);--status-bg:rgba(0,0,0,.18);--code-bg:rgba(0,0,0,.24);--chip-bg:rgba(255,255,255,.04);--chip-hover:rgba(255,255,255,.08)}
html[data-sv-theme="cisco-nexus"]{color-scheme:dark;--accent:#42b4e6;--accent-strong:#42b4e6;--accent-dark:#176b8f;--accent-dark-hover:#1d83ae;--accent-soft:rgba(66,180,230,.12);--page:#0f1418;--card:#171e24;--card-strong:#202a32;--surface-input:#11171c;--surface-button:#182128;--surface-inset:#141b21;--surface-hover:#23313a;--muted:#a4b2bc;--line:#34434d;--line-soft:#28353d;--warn:#e7b23c;--warn-soft:rgba(231,178,60,.12);--ok:#63bf74;--ok-soft:rgba(99,191,116,.12);--bad:#df6970;--bad-soft:rgba(223,105,112,.12);--neutral-soft:rgba(164,178,188,.10);--text:#eef4f7;--on-accent:#071217;--on-primary:#fff;--shadow:rgba(0,0,0,.25);--status-bg:rgba(0,0,0,.22);--code-bg:rgba(0,0,0,.28);--chip-bg:rgba(255,255,255,.035);--chip-hover:rgba(255,255,255,.075)}
html[data-sv-theme="unifi"]{color-scheme:light;--accent:#006fff;--accent-strong:#57a0ff;--accent-dark:#003c9e;--accent-dark-hover:#0054cf;--accent-soft:rgba(0,111,255,.10);--page:#f5f6f7;--card:#fff;--card-strong:#fbfbfc;--surface-input:#fff;--surface-button:#f7f8f9;--surface-inset:#f8f9fa;--surface-hover:#eef5ff;--muted:#626675;--line:#d7dce4;--line-soft:#e7eaf0;--warn:#a66500;--warn-soft:rgba(166,101,0,.10);--ok:#23884e;--ok-soft:rgba(35,136,78,.10);--bad:#c8434e;--bad-soft:rgba(200,67,78,.09);--neutral-soft:rgba(98,102,117,.09);--text:#242635;--on-accent:#fff;--on-primary:#fff;--shadow:rgba(31,35,41,.07);--status-bg:#f0f2f5;--code-bg:#eef0f3;--chip-bg:rgba(36,38,53,.025);--chip-hover:rgba(36,38,53,.065)}
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,sans-serif;font-size:var(--sv-font-body);margin:0;padding:22px;line-height:var(--sv-line-height);background:var(--page);color:var(--text)}main{max-width:1180px;margin:auto}h1{font-size:var(--sv-font-page-title);line-height:1.2;margin:.1rem 0}h2{font-size:var(--sv-font-section-title);line-height:1.25}h3{font-size:1rem;line-height:1.3}.lead{color:var(--muted);margin-top:.25rem}.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin:18px 0;box-shadow:0 10px 28px var(--shadow)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px 22px}.option{display:flex;gap:10px;align-items:flex-start;padding:7px 0}.option input{margin-top:4px}.field{display:grid;gap:6px;margin:12px 0}select,input[type=text],input[type=file],input[type=number],input[type=password]{font:inherit;padding:10px;border-radius:8px;border:1px solid var(--line);background:var(--surface-input);color:inherit}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}button,a.button{font:inherit;border:1px solid var(--line);border-radius:9px;padding:11px 16px;background:var(--surface-button);color:inherit;text-decoration:none;cursor:pointer;transition:border-color .15s ease,background-color .15s ease,transform .15s ease}button:hover,a.button:hover,button:focus-visible,a.button:focus-visible{border-color:var(--accent);background:var(--accent-soft);outline:none}.primary{background:var(--accent-dark)!important;color:var(--on-primary)!important;border-color:var(--accent-strong)!important;font-weight:700}.primary:hover,.primary:focus-visible{background:var(--accent-dark-hover)!important}.danger{border-color:var(--bad)!important;color:var(--bad)!important;font-weight:700}.danger:hover,.danger:focus-visible{background:var(--bad-soft)!important}.hidden{display:none!important}.warning{border-left:4px solid var(--warn);padding:10px 12px;background:var(--warn-soft);margin:12px 0}.success{border-left:4px solid var(--ok);padding:10px 12px}.failure{border-left:4px solid var(--bad);padding:10px 12px}.status{white-space:pre-wrap;font-family:ui-monospace,monospace;font-size:.85rem;max-height:230px;overflow:auto;background:var(--status-bg);padding:12px;border-radius:8px}.device{padding:8px 0;border-bottom:1px solid var(--line)}.device:last-child{border:0}.meta{display:grid;grid-template-columns:max-content 1fr;gap:5px 12px}.meta dt{font-weight:700}.meta dd{margin:0;overflow-wrap:anywhere}small,.muted{font-size:var(--sv-font-small);color:var(--muted)}.topbar{display:flex;align-items:center;gap:12px;margin-bottom:10px}.topbar h1{flex:1}.back-button{padding:8px 12px!important}.device-card{border:1px solid var(--line-soft);border-radius:10px;padding:14px;margin:10px 0;background:var(--surface-inset)}.device-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap}.badge{display:inline-block;padding:4px 9px;border-radius:999px;font-size:.8rem;font-weight:700;text-transform:capitalize;border:1px solid var(--line)}.badge-confirmed{background:var(--ok-soft);border-color:var(--ok)}.badge-experimental{background:var(--warn-soft);border-color:var(--warn)}.badge-detected{background:var(--neutral-soft)}.validation-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:7px;margin-top:12px}.validation-item{display:flex;justify-content:space-between;gap:8px;border-top:1px solid var(--line);padding-top:7px}.state-confirmed{color:var(--ok);font-weight:700}.state-pending{color:var(--warn);font-weight:700}.state-not_applicable,.state-unknown{color:var(--muted)}.diag-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}.diag-tile{border:1px solid var(--line-soft);border-radius:9px;padding:11px;background:var(--surface-inset)}.diag-value{font-weight:700;font-size:1rem}.diag-list{margin:8px 0 0;padding-left:20px}.diag-good{color:var(--ok)}.diag-warn{color:var(--warn)}.diag-bad{color:var(--bad)}.nav-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-top:16px}.nav-card{display:flex;flex-direction:column;align-items:flex-start;min-height:150px;text-align:left;padding:16px!important;background:var(--surface-button);border-color:var(--line-soft);transition:border-color .15s ease,background-color .15s ease,transform .15s ease}.nav-card:hover,.nav-card:focus-visible{border-color:var(--accent-strong);background:var(--surface-hover);outline:none;transform:translateY(-1px)}.nav-card.unifi-unavailable{opacity:.48;filter:saturate(.25);cursor:not-allowed;background:var(--surface-inset);border-color:var(--line-soft);transform:none}.nav-card.unifi-unavailable:hover,.nav-card.unifi-unavailable:focus-visible{border-color:var(--line-soft);background:var(--surface-inset);transform:none}.nav-card.unifi-needs-setup{border-color:var(--warn);background:var(--warn-soft)}.nav-card.unifi-needs-setup:hover,.nav-card.unifi-needs-setup:focus-visible{border-color:var(--warn);background:var(--warn-soft)}.nav-card.unifi-warning{border-color:var(--warn);background:var(--warn-soft)}.unifi-card-state{display:inline-flex;margin-top:auto;padding-top:10px;font-size:var(--sv-font-small);font-weight:700;color:var(--muted)}.nav-card b{font-size:1rem;margin-bottom:7px}.nav-points{display:block;margin:0;padding-left:18px;color:var(--muted);font-size:var(--sv-font-small);line-height:1.35}.nav-points span{display:list-item}.nav-points span+span{margin-top:4px}.home-status{display:flex;align-items:center;gap:10px;font-size:1rem}.status-dot{width:11px;height:11px;border-radius:50%;background:var(--ok);display:inline-block}.status-dot.running{background:var(--accent)}.status-dot.failed{background:var(--bad)}.steps{display:grid;gap:8px;margin:16px 0}.step{display:flex;gap:10px;align-items:center;border:1px solid var(--line);border-radius:9px;padding:10px 12px}.step-mark{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;border:1px solid var(--line);font-size:.8rem;font-weight:700}.step.active{border-color:var(--accent)}.step.active .step-mark{background:var(--accent);color:var(--on-accent)}.step.done .step-mark{background:var(--ok);color:var(--on-accent);border-color:var(--ok)}details.advanced{margin-top:14px;border-top:1px solid var(--line);padding-top:12px}details.advanced summary{cursor:pointer;font-weight:600}.page-title{margin-bottom:0}.simple-result{display:flex;justify-content:space-between;gap:12px;align-items:center;border:1px solid var(--line-soft);border-radius:10px;padding:14px;margin:10px 0;background:var(--surface-inset)}.simple-result .result-main{min-width:0}.simple-result .result-actions{flex-shrink:0}.live-status{display:grid;grid-template-columns:max-content 1fr;gap:7px 14px;border:1px solid var(--line-soft);border-radius:10px;padding:14px;margin:14px 0;background:var(--surface-inset)}.live-status dt{font-weight:700}.live-status dd{margin:0;overflow-wrap:anywhere}.command-line{font-family:ui-monospace,monospace;font-size:.84rem;background:var(--status-bg);padding:8px;border-radius:7px}.debug-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:14px}.debug-panel{margin-top:10px;max-height:420px}.elapsed{font-variant-numeric:tabular-nums}.generated-card-manager summary{width:100%;box-sizing:border-box}
.yaml-manager{border:1px solid var(--line-soft);border-radius:10px;padding:14px;margin-top:18px;background:var(--surface-inset)}.yaml-manager summary{cursor:pointer;font-size:1rem;display:flex;align-items:center;gap:8px;list-style:none;width:100%;box-sizing:border-box}.yaml-manager summary::-webkit-details-marker{display:none}.yaml-manager summary::marker{content:""}.yaml-manager summary::after{content:"▸";margin-left:auto;flex:0 0 auto;transition:transform .12s ease}.yaml-manager[open] summary::after{transform:rotate(90deg)}.yaml-manager[open] summary{margin-bottom:10px}.generated-card-manager{border:1px solid var(--line-soft);border-radius:10px;padding:14px;margin-top:18px;background:var(--surface-inset)}.yaml-state{display:grid;grid-template-columns:max-content 1fr;gap:6px 12px;margin-top:12px}.yaml-state dt{font-weight:700}.yaml-state dd{margin:0;overflow-wrap:anywhere}.code-preview{max-height:360px;overflow:auto;white-space:pre;font-family:ui-monospace,monospace;font-size:.82rem;background:var(--code-bg);padding:12px;border-radius:8px}

/* User-selectable UI preferences supplied by the Switch Vision integration. */
body.text-normal{--sv-font-body:.98rem;--sv-font-page-title:1.8rem;--sv-font-section-title:1.22rem;--sv-font-small:.86rem;--sv-line-height:1.42}
body.text-small{--sv-font-body:.9rem;--sv-font-page-title:1.65rem;--sv-font-section-title:1.12rem;--sv-font-small:.8rem;--sv-line-height:1.38}
body.width-standard main{max-width:880px}
body.width-wide main{max-width:1100px}
body.width-full main{max-width:none}
body.density-comfortable{padding:22px}
body.density-comfortable .card{padding:18px;margin:18px 0}
body.density-comfortable .nav-grid{gap:12px;margin-top:16px}
body.density-comfortable .nav-card{min-height:150px;padding:16px!important}
body.density-compact{padding:12px}
body.density-compact .card{padding:14px;margin:12px 0}
body.density-compact .grid{gap:8px 14px}
body.density-compact .nav-grid{gap:8px;margin-top:12px}
body.density-compact .nav-card{min-height:132px;padding:12px!important}
body.density-compact .actions{gap:8px;margin-top:12px}
body.density-compact .device-card,body.density-compact .simple-result,body.density-compact .live-status{padding:12px;margin:8px 0}
body.density-compact .diag-summary{gap:8px}
body.density-compact .diag-tile{padding:10px}
body.density-dense{padding:8px}
body.density-dense .card{padding:10px;margin:8px 0}
body.density-dense .grid{gap:6px 10px}
body.density-dense .field{gap:4px;margin:7px 0}
body.density-dense .option{gap:7px;padding:3px 0}
body.density-dense .actions{gap:6px;margin-top:8px}
body.density-dense button,body.density-dense a.button{padding:8px 11px}
body.density-dense .nav-grid{gap:6px;margin-top:8px}
body.density-dense .nav-card{min-height:112px;padding:9px!important}
body.density-dense .device-card,body.density-dense .simple-result,body.density-dense .live-status{padding:9px;margin:6px 0}
body.density-dense .diag-summary{gap:6px}
body.density-dense .diag-tile{padding:8px}
body.density-dense .steps{gap:5px;margin:8px 0}
body.density-dense .step{padding:7px 9px}
.topbar-tools{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap}.theme-picker{display:flex;align-items:center;gap:7px;height:36px;padding:0 0 0 10px;border:1px solid var(--line-soft);border-radius:9px;background:var(--surface-button);color:var(--muted);font-size:var(--sv-font-small);font-weight:700;white-space:nowrap}.theme-picker select{height:34px;min-width:150px;margin:-1px -1px -1px 0;padding:7px 10px;border-radius:0 9px 9px 0;border-color:var(--line-soft);background:var(--surface-input);color:var(--text);font-weight:600}.theme-picker select:focus-visible{border-color:var(--accent);outline:none}.topbar-theme-label{pointer-events:none}@media(max-width:760px){.topbar{flex-wrap:wrap}.topbar h1{min-width:180px}.topbar-tools{width:100%;justify-content:flex-end}.theme-picker select{min-width:132px}}
.configured-device.disabled{opacity:.62}.configured-device .result-actions{display:flex;align-items:center;gap:10px}.device-state-toggle{display:inline-flex;align-items:center;gap:8px;min-width:118px;justify-content:center;padding:8px 11px!important;font-weight:700}.device-state-toggle .toggle-track{position:relative;display:inline-block;width:34px;height:18px;border-radius:999px;background:var(--line);transition:background-color .15s ease}.device-state-toggle .toggle-knob{position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;background:var(--surface-input);transition:transform .15s ease}.device-state-toggle.enabled{border-color:var(--ok);background:var(--ok-soft)}.device-state-toggle.enabled .toggle-track{background:var(--ok)}.device-state-toggle.enabled .toggle-knob{transform:translateX(16px)}.device-state-toggle.disabled{border-color:var(--line);background:var(--surface-button)}.device-state-toggle:disabled{cursor:not-allowed;opacity:.55}.configured-device-note{margin:4px 0 12px}.configured-device-status{min-height:1.25em}.devices-divider{border:0;border-top:1px solid var(--line);margin:20px 0 16px}.sponsor-chip{display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--line-soft);border-radius:999px;background:var(--chip-bg);color:var(--text);text-decoration:none;font-size:.92rem;font-weight:700;white-space:nowrap}.sponsor-chip:hover{background:var(--chip-hover)}.sponsor-chip .heart{font-size:1rem;line-height:1;color:var(--heart)}</style>
</head>
<body><main>
<div class="topbar"><button id="backButton" class="back-button" type="button">← Back to Home Assistant</button><h1 id="pageHeading" class="page-title">Switch Vision Hub</h1><div class="topbar-tools"><label class="theme-picker" title="Management UI theme. Switch dashboards are not affected."><span class="topbar-theme-label">Theme</span><select id="themeSelect" aria-label="Management UI theme"><option value="switch-vision">Switch Vision</option><option value="cisco-classic">Cisco Classic</option><option value="cisco-nexus">Cisco Nexus</option><option value="unifi">UniFi</option></select></label><a class="sponsor-chip" href="https://github.com/sponsors/zemerdon" target="_blank" rel="noopener noreferrer" title="Support Switch Vision on GitHub Sponsors"><span class="heart">♥</span><span>Sponsor</span></a></div></div>
<p id="pageLead" class="lead hidden"></p>

<section id="homeCard" class="card">
<div class="home-status"><span id="homeStatusDot" class="status-dot"></span><strong id="homeStatus">Ready</strong></div>
<p class="muted">The Web UI stays available while Discovery is idle, running, or complete.</p>
<div class="nav-grid">
<button id="openDiscoveryButton" class="nav-card" type="button"><b>Discovery</b><span class="nav-points"><span>SNMP Walk</span><span>Generate Native Dashboard YAML</span><span>Generate SNMP2MQTT YAML</span></span></button>
<button id="openDevicesButton" class="nav-card" type="button"><b>Devices</b><span class="nav-points"><span>Show detected devices &amp; status</span><span>Enable / Disable Devices</span></span></button>
<button id="openCalibrationProfilesButton" class="nav-card" type="button"><b>Calibration Profiles</b><span class="nav-points"><span>Manage faceplate calibrations</span><span>Copy / Import / Export profiles</span><span>Clean stale profiles</span></span></button>
<button id="openSupportButton" class="nav-card" type="button"><b>Support My Switch</b><span class="nav-points"><span>Create contribution package to add/increase support for your switch</span></span></button>
<button id="openDiagnosticsButton" class="nav-card" type="button"><b>Detected Device Information</b><span class="nav-points"><span>Detailed device(s) information</span></span></button>
<button id="openConfigurationButton" class="nav-card" type="button"><b>Import / Export Configuration</b><span class="nav-points"><span>Import / export Discovery configuration</span></span></button>
<button id="openMaintenanceButton" class="nav-card" type="button"><b>Maintenance</b><span class="nav-points"><span>Manage backups</span><span>Repair stale MQTT entities</span><span>Reset generated SNMP data</span></span></button>
</div>
<div class="nav-grid" style="margin-top:12px">
<button id="openIntegrationSettingsButton" class="nav-card" type="button"><b>Switch Vision Settings</b><span class="nav-points"><span>Sidebar toggles</span><span>Native card options</span><span>UI font &amp; display</span></span></button>
<button id="openDiscoverySettingsButton" class="nav-card" type="button"><b>Discovery Settings</b><span class="nav-points"><span>Add / remove devices</span><span>SNMP walk configuration</span><span>Path settings</span></span></button>
<button id="openSnmp2mqttSettingsButton" class="nav-card" type="button"><b>SNMP2MQTT Settings</b><span class="nav-points"><span>MQTT configuration</span><span>SNMP2MQTT paths</span><span>Logging level</span></span></button>
<button id="openUnifi2mqttSettingsButton" class="nav-card unifi-unavailable" type="button" aria-disabled="true" title="UniFi2MQTT status is being checked."><b>UniFi2MQTT Settings</b><span class="nav-points"><span>UniFi controller API</span><span>MQTT connection</span><span>App &amp; snapshot status</span></span><span id="unifiHomeCardState" class="unifi-card-state">Checking…</span></button>
</div>
</section>


<section id="calibrationProfilesCard" class="card hidden">
<h2>Calibration Profiles</h2>
<p class="lead">Manage saved Switch Vision faceplate calibration profiles.</p>
<div id="calibrationProfilesRoot"></div>
</section>

<section id="unifi2mqttCard" class="card hidden">
<h2>UniFi2MQTT Settings</h2>
<p class="lead">Configure the existing Switch Vision UniFi API support path. Home Assistant App configuration remains available as a fallback.</p>
<div id="unifiStatusGrid" class="diag-summary"></div>
<div id="unifiInstallWrap" class="warning hidden"><b>UniFi2MQTT is not installed.</b><div class="actions"><button id="installUnifi2mqttButton" class="primary" type="button">Install UniFi2MQTT</button></div><p id="unifiInstallStatus" class="muted"></p></div>
<div id="unifiSettingsForm">
<div class="grid">
<label class="field"><span><b>Controller URL</b></span><input id="unifi_controller_url" type="url" maxlength="512" required placeholder="https://192.168.1.1"></label>
<label class="field"><span><b>Site ID</b></span><input id="unifi_site_id" type="text" maxlength="160" required placeholder="Required UniFi Network site ID"><small>Required for site-scoped UniFi Integration API requests.</small></label>
<label class="field"><span><b>API Key</b></span><input id="unifi_api_key" type="password" maxlength="2048" autocomplete="new-password" placeholder="Leave blank to keep the current key"><small id="unifiApiKeyState">Required — not configured</small></label>
<label class="option"><input id="unifi_verify_ssl" type="checkbox"><span><b>Verify SSL</b><br><small>Enable when the controller uses a trusted certificate.</small></span></label>
<label class="field"><span><b>Poll interval (seconds)</b></span><input id="unifi_poll_interval" type="number" min="10" max="300" step="1"></label>
</div>
<h3>MQTT</h3>
<div class="grid">
<label class="field"><span><b>MQTT host</b></span><input id="unifi_mqtt_host" type="text" maxlength="255"></label>
<label class="field"><span><b>MQTT port</b></span><input id="unifi_mqtt_port" type="number" min="1" max="65535" step="1"></label>
<label class="field"><span><b>MQTT username</b></span><input id="unifi_mqtt_username" type="text" maxlength="256" autocomplete="username"></label>
<label class="field"><span><b>MQTT password</b></span><input id="unifi_mqtt_password" type="password" maxlength="2048" autocomplete="new-password" placeholder="Leave blank to keep the current password"><small id="unifiMqttPasswordState">Not configured</small></label>
<label class="field"><span><b>MQTT topic prefix</b></span><input id="unifi_mqtt_topic_prefix" type="text" maxlength="256"></label>
<label class="field"><span><b>MQTT discovery prefix</b></span><input id="unifi_mqtt_discovery_prefix" type="text" maxlength="256"></label>
</div>
<div class="actions"><button id="saveUnifi2mqttButton" class="primary" type="button">Save UniFi2MQTT Settings</button><button id="openUnifiAppConfigButton" type="button">Open Home Assistant App Configuration</button></div>
<p id="unifiSettingsStatus" class="muted">Secrets are never read back into this page. Blank secret fields preserve stored values. To clear an existing optional MQTT password, use the Home Assistant App configuration fallback.</p>
</div>
</section>

<section id="configurationCard" class="card hidden">
<h2>Import / Export Configuration</h2>
<p>Export your configured switches and Discovery settings before moving to a fresh Home Assistant installation.</p>
<div class="warning"><b>Keep the export private.</b> It can contain switch IP addresses and SNMP community strings.</div>
<div class="actions"><a id="exportConfigurationButton" class="button primary" href="#">Export Configuration</a></div>
<hr style="border:0;border-top:1px solid var(--line);margin:22px 0">
<h3>Import Configuration</h3>
<p>Select a Switch Vision Discovery configuration export. Import replaces the Discovery-related settings while preserving Support My Switch privacy preferences.</p>
<label class="field"><span><b>Configuration file</b></span><input id="configurationFile" type="file" accept="application/json,.json"></label>
<div class="actions"><button id="importConfigurationButton" type="button">Import Configuration</button></div>
<p id="configurationStatus" class="muted">No configuration imported.</p>
</section>


<section id="maintenanceCard" class="card hidden">
<h2>Maintenance</h2>
<p class="lead">Repair Switch Vision-managed runtime state without touching unrelated Home Assistant or MQTT data.</p>
<h3>Installer Recovery Backups</h3>
<p>Manage the full Switch Vision recovery backups created by Installer. These remain separate from the smaller Discovery configuration snapshots below.</p>
<div class="warning"><b>Private boundary preserved:</b> Recovery files stay inside Installer-owned <code>/data/switch-vision-backups</code>. Maintenance receives only sanitized metadata and sends narrow commands through Home Assistant Supervisor; backup files, saved option payloads and credentials are never exposed here.</div>
<div class="grid">
<label class="option"><input id="installerBackupAutomaticRetention" type="checkbox"><span><b>Automatic retention</b><br><small>When enabled, Installer prunes old recovery backups after creating a new backup.</small></span></label>
<label class="field"><span><b>Retained backups</b></span><input id="installerBackupRetentionCount" type="number" min="1" max="10" step="1" value="5"><small>Keep between 1 and 10 recovery backups.</small></label>
</div>
<div id="installerBackupSummary" class="diag-summary"></div>
<div class="actions"><button id="saveInstallerBackupPolicyButton" class="primary" type="button">Save Backup Policy</button><button id="createInstallerBackupButton" type="button">Create Backup</button><button id="applyInstallerBackupRetentionButton" type="button">Apply Retention Now</button><button id="refreshInstallerBackupsButton" type="button">Refresh Backups</button></div>
<p id="installerBackupStatus" class="muted">Loading Installer recovery backups…</p>
<div id="installerBackupList"></div>
<hr style="border:0;border-top:1px solid var(--line);margin:22px 0">
<h3>Discovery Configuration Backups</h3>
<p>Switch Vision can retain private snapshots before persistent configuration changes made through the Hub, including configuration import and saved-device enable/disable. Changes made independently through Home Assistant's add-on Configuration page are outside this interception path.</p>
<div class="warning"><b>Private data:</b> Backup files may contain saved configuration and secrets. Maintenance exposes only backup name, time, size and count; it never shows or downloads backup contents.</div>
<div id="discoveryBackupSummary" class="diag-summary"></div>
<div id="discoveryBackupList"></div>
<div class="actions"><button id="refreshDiscoveryBackupsButton" type="button">Refresh Backups</button></div>
<p id="discoveryBackupStatus" class="muted">Loading retained Discovery backups…</p>
<hr style="border:0;border-top:1px solid var(--line);margin:22px 0">
<h3>Repair MQTT Entities</h3>
<p>Scan retained Home Assistant MQTT Discovery entries and compare them with the current generated SNMP2MQTT YAML. Only retained entries that prove Switch Vision SNMP2MQTT ownership through their topic, origin, IDs and state-topic contract are eligible for repair.</p>
<div class="warning"><b>Safe scope:</b> Scan is read-only. Repair never performs a broker-wide wipe and never edits Home Assistant <code>.storage</code>. A current valid generated SNMP2MQTT YAML is required so Switch Vision can distinguish current entities from historical ghosts.</div>
<div id="mqttRepairSummary" class="diag-summary"></div>
<div id="mqttRepairEntities"></div>
<div class="actions"><button id="scanMqttEntitiesButton" class="primary" type="button">Scan MQTT Entities</button><button id="exportMqttResultsButton" type="button" disabled>Export Results</button><button id="repairMqttEntitiesButton" type="button" disabled>Repair Stale MQTT Entities</button></div>
<p id="mqttRepairStatus" class="muted">Run a scan to check for historical Switch Vision MQTT entities.</p>
<hr style="border:0;border-top:1px solid var(--line);margin:22px 0">
<h3>Reset SNMP Discovery Data</h3>
<p>Stronger cleanup for retiring SNMP switches or rebuilding the complete SNMP-generated state. It stops Switch Vision SNMP2MQTT, retires the exact retained discovery topics Switch Vision already knows about, deletes saved SNMP walk/capability/generated SNMP data, and clears the generated card. UniFi data and settings are preserved.</p>
<div class="warning"><b>This is more destructive than Repair MQTT Entities.</b> Use Repair first for stale Home Assistant entities. Reset is for a deliberate clean SNMP rebuild.</div>
<div class="actions"><button id="resetSnmpDiscoveryButton" class="danger" type="button">Reset SNMP Discovery Data</button></div>
<p id="resetSnmpDiscoveryStatus" class="muted"></p>
</section>

<section id="settingsCard" class="card hidden">
<div class="hub-settings-intro"><div><h2>Switch Vision Settings</h2><p class="muted">All normal Core, SNMP2MQTT and Discovery settings in one place. Each component remains the authoritative owner of its settings.</p></div></div>
<details id="hubComponent-core" class="hub-component" open><summary>Switch Vision Core</summary><div class="actions"><button id="hubCoreFallback" type="button">Native HA fallback</button><button id="hubCoreReset" class="danger" type="button">Reset Core defaults</button></div><div id="hubCoreSettings"></div></details>
<details id="hubComponent-snmp2mqtt" class="hub-component"><summary>SNMP2MQTT</summary><div class="actions"><button id="hubSnmpFallback" type="button">Native App fallback</button></div><div id="hubSnmpSettings"></div></details>
<details id="hubComponent-discovery" class="hub-component"><summary>Discovery</summary><div class="actions"><button id="hubDiscoveryFallback" type="button">Native App fallback</button></div><div id="hubDiscoverySettings"></div></details>
<div class="hub-settings-actions"><button id="hubSettingsSave" class="primary" type="button" disabled>Save changes</button><button id="hubSettingsReload" type="button">Reload</button><p id="hubSettingsStatus" class="muted hub-settings-status">Open a section to review settings.</p></div>
</section>

<section id="discoveryCard" class="card hidden">
<h2>Run Discovery</h2>
<p id="discoveryStatus" class="lead">Idle / Ready</p>
<div id="discoverySteps" class="steps">
<div class="step" data-step="0"><span class="step-mark">1</span><span>Validating configured switches</span></div>
<div class="step" data-step="1"><span class="step-mark">2</span><span>Running SNMP walks</span></div>
<div class="step" data-step="2"><span class="step-mark">3</span><span>Detecting exact models and interfaces</span></div>
<div class="step" data-step="3"><span class="step-mark">4</span><span>Generating SNMP2MQTT YAML</span></div>
<div class="step" data-step="4"><span class="step-mark">5</span><span>Generating dashboard card YAML</span></div>
<div class="step" data-step="5"><span class="step-mark">6</span><span>Complete</span></div>
</div>
<dl class="live-status">
<dt>Current stage</dt><dd id="liveStage">Ready</dd>
<dt>Switch</dt><dd id="liveSwitch">Not running</dd>
<dt>Target</dt><dd id="liveTarget">Not running</dd>
<dt>Action</dt><dd id="liveActivity">Waiting to start</dd>
<dt>Command</dt><dd id="liveCommand" class="command-line">No command running</dd>
<dt>Status</dt><dd id="liveRunStatus">Idle / Ready</dd>
<dt>SNMP2MQTT</dt><dd id="liveSnmp2mqtt">Waiting for Discovery</dd>
<dt>Elapsed</dt><dd id="liveElapsed" class="elapsed">00:00</dd>
</dl>
<div class="actions"><button class="primary" id="runDiscoveryButton" type="button">Run Discovery</button><button id="regenerateYamlButton" type="button">Regenerate SNMP2MQTT YAML</button><button id="stopDiscoveryButton" type="button" disabled>Stop Discovery</button><button id="viewResultsButton" type="button">View Results</button><button id="toggleDebugButton" type="button">Show Debug</button></div>
<p id="regenerateYamlHelp" class="muted">Regenerate SNMP2MQTT YAML uses the existing saved Discovery data and SNMP walks. No new SNMP walks are performed.</p>
<p id="regenerateYamlStatus" class="muted"></p>
<details class="yaml-manager generated-card-manager" open>
<summary><strong>Generated Card YAML</strong></summary>
<p>Exact dashboard YAML produced by Discovery. Review, copy, or download it before using it in a custom Home Assistant dashboard. Discovery does not install this file automatically.</p>
<dl class="yaml-state"><dt>Generated file</dt><dd id="generatedCardYamlState">Checking…</dd><dt>Validation</dt><dd id="generatedCardYamlValidation">Checking…</dd><dt>Last updated</dt><dd id="generatedCardYamlUpdated">Checking…</dd></dl>
<div class="actions"><button id="previewGeneratedCardYamlButton" type="button">Preview Card YAML</button><button id="copyGeneratedCardYamlButton" type="button">Copy Card YAML</button><a id="downloadGeneratedCardYamlButton" class="button" href="#">Download Card YAML</a></div>
<p id="generatedCardYamlActionStatus" class="muted"></p><pre id="generatedCardYamlPreview" class="code-preview hidden"></pre>
</details>
<details class="yaml-manager" open>
<summary><strong>Generated SNMP2MQTT YAML</strong></summary>
<p id="generatedYamlDescription">SNMP2MQTT YAML is only required for switches using the SNMP data path. UniFi API devices use UniFi2MQTT and do not require this file.</p>
<dl class="yaml-state"><dt>Generated file</dt><dd id="generatedYamlState">Checking…</dd><dt>Validation</dt><dd id="generatedYamlValidation">Checking…</dd><dt>Last updated</dt><dd id="generatedYamlUpdated">Checking…</dd></dl>
<div id="generatedYamlActions" class="actions"><button id="previewGeneratedYamlButton" type="button">Preview generated YAML</button><a id="downloadGeneratedYamlButton" class="button" href="#">Download YAML</a></div>
<p id="generatedYamlActionStatus" class="muted"></p><pre id="generatedYamlPreview" class="code-preview hidden"></pre>
</details>
<div id="debugWrap" class="hidden"><div class="debug-head"><strong>Discovery debug output</strong><small>Commands and detailed activity; credentials remain masked.</small></div><div id="discoveryLog" class="status debug-panel"></div><div class="actions"><button id="copyDebugButton" type="button">Copy Debug Info</button></div><p id="copyDebugStatus" class="muted"></p></div>
</section>

<section id="devicesCard" class="card hidden">
<h2>Devices</h2>
<h3>Enable / Disable Devices</h3>
<p class="muted configured-device-note">Choose which saved switches participate in Discovery. Disabled devices remain configured and can be re-enabled at any time.</p>
<div id="configuredDevices"></div>
<p id="configuredDevicesStatus" class="muted configured-device-status"></p>
<hr class="devices-divider">
<h3>Detected Devices</h3>
<p class="lead">Latest detected hardware and generated configuration status.</p>
<div id="devicesSummary"></div>
<div class="actions"><button class="primary" id="refreshDevicesButton" type="button">Refresh Devices</button><button id="devicesRunDiscoveryButton" type="button">Run Discovery</button></div>
<p id="devicesActionStatus" class="muted"></p>
</section>

<section id="diagnosticsCard" class="card hidden">
<h2>Detected Device Information</h2>
<p class="lead">Detailed device(s) information.</p>
<div id="diagnosticsSummary" class="diag-summary"></div>
<div id="diagnosticsMessages"></div>
<h3>Discovered devices</h3><div id="diagnosticsDevices"></div>
<div class="actions"><button class="primary" id="refreshDiagnosticsButton" type="button">Refresh Diagnostics</button><button id="copyDiagnosticsButton" type="button">Copy Diagnostics</button><a id="downloadDiagnosticsButton" class="button" href="#">Download Diagnostics Report</a><button id="diagnosticsRunDiscoveryButton" type="button">Run Discovery</button></div>
<p id="diagnosticsActionStatus" class="muted"></p>
</section>

<section id="createCard" class="card hidden">
<h2>Support My Switch</h2>
<p class="lead">Prepare a privacy-processed contribution bundle. Nothing is sent automatically.</p>
<h3>Create contribution</h3>
<div class="grid">
<label class="option"><input id="mask_management_ips" type="checkbox"><span><b>Mask management IPs</b><br><small>Recommended for anything shared outside your private network.</small></span></label>
<label class="option"><input id="mask_mac_addresses" type="checkbox"><span><b>Mask MAC addresses</b><br><small>Replaces hardware addresses while preserving useful structure.</small></span></label>
<label class="option"><input id="mask_hostnames" type="checkbox"><span><b>Mask hostnames</b><br><small>Removes detected hostnames and domain names.</small></span></label>
<label class="option"><input id="mask_vlan_names" type="checkbox"><span><b>Mask VLAN names</b><br><small>Enable when VLAN labels contain private information.</small></span></label>
<label class="option"><input id="mask_interface_descriptions" type="checkbox"><span><b>Mask interface descriptions</b><br><small>Enable when port descriptions contain names or locations.</small></span></label>
</div>
<div id="privacyWarning" class="warning hidden"><b>Privacy warning:</b> one or more common identity masks are disabled. The bundle is still credential-sanitized, but review it carefully before sending.</div>
<div class="grid">
<label class="field"><span><b>Recognition</b></span><select id="contributor_type"><option value="anonymous">Anonymous</option><option value="first_name">First name</option><option value="full_name">Full name</option><option value="github">GitHub username</option><option value="forum">Forum username</option></select></label>
<label class="field" id="recognitionValueWrap"><span><b>Name or username</b></span><input id="contributor_value" type="text" maxlength="120" placeholder="Optional recognition"></label>
</div>
<div class="actions"><button class="primary" id="createButton">Create contribution</button></div>
</section>

<section id="progressCard" class="card hidden"><h2>Preparing contribution</h2><p id="progressMessage">Starting…</p><div id="logTail" class="status"></div></section>

<section id="readyCard" class="card hidden">
<h2 id="readyHeading">Contribution ready</h2>
<div id="qualityBanner"></div>
<p id="qualityDetails" class="muted"></p>
<dl class="meta"><dt>Contribution ID</dt><dd id="contributionId"></dd><dt>Switch Vision version</dt><dd id="version"></dd><dt>Archive</dt><dd id="archiveName"></dd><dt>Archive size</dt><dd id="archiveSize"></dd></dl>
<h3>Detected hardware</h3><div id="devices"></div>
<div class="actions"><a id="prepareEmail" class="button primary">Prepare Email</a><a id="downloadArchive" class="button">Download Archive</a><a id="mailto" class="button">Open Email Without Attachment</a><button id="createAnother">Create Another Contribution</button></div>
<p><small><b>Prepare Email</b> downloads a standard .eml message with the ZIP attached. Open it in your email application, review it, then press Send.</small></p>
</section>

<section id="importantCard" class="card hidden"><h2>Important</h2><p>Credentials are always removed and device serial numbers are always masked in the temporary copy. Automated masking cannot identify every possible private value, so review the archive before sharing it.</p><p class="muted">Files are stored in <code>/share/switch_vision/contributions/</code>.</p></section>
</main>
<script>
const $=id=>document.getElementById(id); let defaultsLoaded=false; let polling=null; let elapsedTicker=null; let refreshInFlight=false; let currentView='home'; let lastRunning=false; let lastDiscoveryState={}; let generatedCardYamlModified=null;
const THEME_STORAGE_KEY='switch-vision-management-theme-v1';const MANAGEMENT_THEMES=new Set(['switch-vision','cisco-classic','cisco-nexus','unifi']);
function applyManagementTheme(value,{persist=true}={}){const theme=MANAGEMENT_THEMES.has(value)?value:'switch-vision';document.documentElement.dataset.svTheme=theme;if($('themeSelect'))$('themeSelect').value=theme;if(persist){try{localStorage.setItem(THEME_STORAGE_KEY,theme)}catch(_e){}}}
function initManagementTheme(){let theme=document.documentElement.dataset.svTheme||'switch-vision';try{const saved=localStorage.getItem(THEME_STORAGE_KEY);if(MANAGEMENT_THEMES.has(saved))theme=saved}catch(_e){}applyManagementTheme(theme,{persist:false})}
function syncDensityUi(value){const density=['comfortable','compact','dense'].includes(String(value))?String(value):'comfortable';for(const name of ['comfortable','compact','dense'])document.body.classList.toggle(`density-${name}`,name===density)}
function endpoint(path){const href=location.href.endsWith('/')?location.href:location.href+'/';return new URL(path,href).toString()}
function fmtBytes(n){if(!Number.isFinite(n))return 'Unknown';const u=['B','KB','MB','GB'];let i=0;while(n>=1024&&i<u.length-1){n/=1024;i++}return `${n.toFixed(i?1:0)} ${u[i]}`}
function updateRecognition(){const anon=$('contributor_type').value==='anonymous';$('recognitionValueWrap').classList.toggle('hidden',anon);if(anon)$('contributor_value').value=''}
function updateWarning(){const unsafe=!$('mask_management_ips').checked||!$('mask_mac_addresses').checked||!$('mask_hostnames').checked;$('privacyWarning').classList.toggle('hidden',!unsafe)}
function setForm(d){for(const k of ['mask_management_ips','mask_mac_addresses','mask_hostnames','mask_vlan_names','mask_interface_descriptions'])$(k).checked=!!d[k];$('contributor_type').value=d.contributor_type||'anonymous';$('contributor_value').value=d.contributor_value||'';updateRecognition();updateWarning();defaultsLoaded=true}
function payload(){return {mask_management_ips:$('mask_management_ips').checked,mask_mac_addresses:$('mask_mac_addresses').checked,mask_hostnames:$('mask_hostnames').checked,mask_vlan_names:$('mask_vlan_names').checked,mask_interface_descriptions:$('mask_interface_descriptions').checked,contributor_type:$('contributor_type').value,contributor_value:$('contributor_value').value}}
function mailto(latest){const subject=`Switch Vision Contribution - ${latest.contribution_id}`;const body=`Hello,\n\nPlease find attached my Switch Vision contribution bundle.\n\nContribution ID: ${latest.contribution_id}\nSwitch Vision version: ${latest.version}\n\nWhat works:\n\nWhat is missing or incorrect:\n\nAnything unusual about this switch:\n\nThank you.`;return `mailto:switch-vision@zemerdon.com?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`}
function statusLabel(value){return String(value||'unknown').replaceAll('_',' ')}
function validationItem(label,value){const item=document.createElement('div');item.className='validation-item';const name=document.createElement('span');name.textContent=label;const state=document.createElement('span');const normalized=String(value||'unknown').toLowerCase();state.className=`state-${normalized}`;state.textContent=statusLabel(normalized);item.append(name,state);return item}
function deviceCard(d){const card=document.createElement('div');card.className='device-card';const head=document.createElement('div');head.className='device-head';const title=document.createElement('div');const strong=document.createElement('strong');strong.textContent=d.model||'Unknown model';title.appendChild(strong);const detail=document.createElement('div');detail.className='muted';detail.textContent=`${d.vendor_name||d.vendor||'Unknown vendor'}${d.family&&d.family!=='unknown'?` · ${d.family}`:''}`;title.appendChild(detail);const status=String(d.registry_status||'detected').toLowerCase();const badge=document.createElement('span');badge.className=`badge badge-${status}`;badge.textContent=statusLabel(status);head.append(title,badge);card.appendChild(head);const meta=document.createElement('div');meta.className='meta';meta.style.marginTop='10px';const fields=[['Registry match',d.registry_match?'Yes':'No'],['Last validated',d.registry_last_validated_version?`v${d.registry_last_validated_version}`:'Not recorded'],['Physical interfaces',d.physical_count??0],['RJ45 interfaces',d.rj45_count??0]];for(const [label,value] of fields){const dt=document.createElement('dt');dt.textContent=label;const dd=document.createElement('dd');dd.textContent=String(value);meta.append(dt,dd)}card.appendChild(meta);const validation=d.registry_validation||{};const grid=document.createElement('div');grid.className='validation-grid';for(const [label,key] of [['Exact model','exact_model_detection'],['RJ45 mapping','rj45_mapping'],['PoE','poe'],['System sensors','system_sensors'],['Uplinks','uplinks'],['Stack','stack']])grid.appendChild(validationItem(label,validation[key]));card.appendChild(grid);return card}
function setView(view){currentView=view;const isHome=view==='home';$('backButton').textContent=isHome?'← Back to Home Assistant':'← Back';const titles={home:['Switch Vision Hub',''],discovery:['Discovery','Run a guided discovery job and review its progress.'],devices:['Devices','Latest detected hardware and generated configuration status.'],support:['Support My Switch','Prepare a privacy-processed contribution bundle. Nothing is sent automatically.'],diagnostics:['Detected Device Information','Detailed device(s) information.'],configuration:['Import / Export Configuration','Export or import the saved Discovery switch list and Discovery settings.'],maintenance:['Maintenance','Repair and reset Switch Vision-managed runtime state safely.'],profiles:['Calibration Profiles','Manage saved faceplate calibration profiles.'],settings:['Settings','Manage Switch Vision Core, SNMP2MQTT, and Discovery settings from one place.'],unifi2mqtt:['UniFi2MQTT Settings','Configure the UniFi controller API and MQTT support path.'],progress:['Support My Switch','Preparing your contribution bundle.'],ready:['Support My Switch','Your contribution bundle is ready to review.']};const title=titles[view]||titles.home;$('pageHeading').textContent=title[0];$('pageLead').textContent=title[1];$('pageLead').classList.toggle('hidden',!title[1]);$('homeCard').classList.toggle('hidden',view!=='home');$('discoveryCard').classList.toggle('hidden',view!=='discovery');$('devicesCard').classList.toggle('hidden',view!=='devices');$('createCard').classList.toggle('hidden',view!=='support');$('importantCard').classList.toggle('hidden',view!=='support');$('diagnosticsCard').classList.toggle('hidden',view!=='diagnostics');$('configurationCard').classList.toggle('hidden',view!=='configuration');$('maintenanceCard').classList.toggle('hidden',view!=='maintenance');$('calibrationProfilesCard').classList.toggle('hidden',view!=='profiles');$('settingsCard').classList.toggle('hidden',view!=='settings');$('unifi2mqttCard').classList.toggle('hidden',view!=='unifi2mqtt');$('progressCard').classList.toggle('hidden',view!=='progress');$('readyCard').classList.toggle('hidden',view!=='ready');window.scrollTo({top:0,behavior:'smooth'})}
function goBack(){if(!$('homeCard').classList.contains('hidden')){try{if(history.length>1){history.back();return}}catch(_e){}try{window.top.location.href='/';return}catch(_e){}location.href='/';return}setView('home')}
function openHomeAssistantPath(path){try{window.top.location.href=path;return}catch(_e){}window.location.href=path}
let appLinksCache=null;
async function loadAppLinks(){if(appLinksCache)return appLinksCache;const r=await fetch(endpoint('api/app-links'),{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not resolve installed apps');appLinksCache=d;return d}
async function openResolvedApp(kind){try{const links=await loadAppLinks();const item=links[kind]||{};const path=kind==='installer'?item.ingress_url:item.config_url;const labels={discovery:'Switch Vision Discovery',snmp2mqtt:'Switch Vision SNMP2MQTT',installer:'Switch Vision Installer'};if(!item.found||!path)throw new Error(`${labels[kind]||'Switch Vision app'} is not installed or could not be resolved.`);openHomeAssistantPath(path)}catch(e){alert(e.message||String(e))}}
function setUnifiHomeCardVisibility(show){const btn=$('openUnifi2mqttSettingsButton');if(!btn)return;btn.classList.toggle('hidden',show===false);if(show===false&&currentView==='unifi2mqtt')setView('home')}
function renderUnifiHomeCard(d){const btn=$('openUnifi2mqttSettingsButton');const label=$('unifiHomeCardState');if(!btn||!label)return;btn.classList.remove('unifi-unavailable','unifi-needs-setup','unifi-warning');const o=d?.options||{};const configured=!!(d?.installed&&String(o.controller_url||'').trim()&&String(o.site_id||'').trim()&&d?.api_key_configured&&String(o.mqtt_host||'').trim());const running=['started','running'].includes(String(d?.state||'').toLowerCase());if(!d?.installed){btn.classList.add('unifi-unavailable');btn.dataset.unifiAction='blocked';btn.setAttribute('aria-disabled','true');btn.title='UniFi2MQTT is not installed. Install it from Switch Vision Installer first.';label.textContent='Not installed';return}btn.dataset.unifiAction='open';btn.setAttribute('aria-disabled','false');if(!configured){btn.classList.add('unifi-needs-setup');btn.title='UniFi2MQTT is installed but not configured. Open settings to complete setup.';label.textContent='Needs setup';return}if(!running){btn.classList.add('unifi-warning');btn.title='UniFi2MQTT is configured but not running. Open settings to review status.';label.textContent='Configured — not running';return}btn.title='UniFi2MQTT is installed, configured, and running.';label.textContent='Ready'}
async function refreshUnifiHomeCard(){try{const d=await fetchUnifi2mqttSettings();renderUnifiHomeCard(d)}catch(e){const btn=$('openUnifi2mqttSettingsButton');const label=$('unifiHomeCardState');if(btn&&label){btn.classList.remove('unifi-needs-setup');btn.classList.add('unifi-warning');btn.dataset.unifiAction='open';btn.setAttribute('aria-disabled','false');btn.title=`UniFi2MQTT status could not be checked: ${e}`;label.textContent='Status unavailable'}}}
async function fetchUnifi2mqttSettings(){const r=await fetch(endpoint('api/unifi2mqtt/settings'),{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not load UniFi2MQTT settings');return d}
function renderUnifi2mqttSettings(d){const grid=$('unifiStatusGrid');grid.innerHTML='';const snapshot=d.snapshot||{};const state=String(d.state||'not installed');const o=d.options||{};const controllerReady=!!(String(o.controller_url||'').trim()&&String(o.site_id||'').trim()&&d.api_key_configured);grid.append(diagTile('UniFi2MQTT',d.installed?'Installed':'Not installed',d.installed?'diag-good':'diag-warn'),diagTile('App state',state,state==='started'||state==='running'?'diag-good':(d.installed?'diag-warn':'diag-warn')),diagTile('Controller',controllerReady?'Configured':'Needs setup',controllerReady?'diag-good':'diag-warn'),diagTile('Configuration access',d.options_readable?'Available':'Fallback required',d.options_readable?'diag-good':'diag-warn'),diagTile('Snapshot',snapshot.found?'Available':'Missing',snapshot.found?'diag-good':'diag-warn'),diagTile('Devices',String(snapshot.device_count||0),snapshot.device_count>0?'diag-good':'diag-warn'));$('unifiInstallWrap').classList.toggle('hidden',!!d.installed);$('unifiSettingsForm').classList.toggle('hidden',!d.installed);$('unifi_controller_url').value=o.controller_url||'';$('unifi_site_id').value=o.site_id||'';$('unifi_verify_ssl').checked=String(o.verify_ssl||'false').toLowerCase()==='true';$('unifi_poll_interval').value=o.poll_interval||30;$('unifi_mqtt_host').value=o.mqtt_host||'core-mosquitto';$('unifi_mqtt_port').value=o.mqtt_port||1883;$('unifi_mqtt_username').value=o.mqtt_username||'';$('unifi_mqtt_topic_prefix').value=o.mqtt_topic_prefix||'switch_vision/unifi';$('unifi_mqtt_discovery_prefix').value=o.mqtt_discovery_prefix||'homeassistant';$('unifi_api_key').value='';$('unifi_api_key').required=!d.api_key_configured;$('unifi_mqtt_password').value='';$('unifiApiKeyState').textContent=d.api_key_configured?'Configured — leave blank to keep':'Required — not configured';$('unifiMqttPasswordState').textContent=d.mqtt_password_configured?'Configured — leave blank to keep':'Not configured';$('openUnifiAppConfigButton').disabled=!d.config_url;window.unifi2mqttConfigUrl=d.config_url||null}
async function loadUnifi2mqttSettings(){setView('unifi2mqtt');$('unifiSettingsStatus').textContent='Loading UniFi2MQTT settings…';try{const d=await fetchUnifi2mqttSettings();renderUnifi2mqttSettings(d);$('unifiSettingsStatus').textContent='Secrets are never read back into this page. Blank secret fields preserve the stored values.'}catch(e){$('unifiSettingsStatus').textContent=`Could not load UniFi2MQTT settings: ${e}`}}
function unifiSettingsPayload(){return {controller_url:$('unifi_controller_url').value,site_id:$('unifi_site_id').value,api_key:$('unifi_api_key').value,verify_ssl:$('unifi_verify_ssl').checked,poll_interval:$('unifi_poll_interval').value,mqtt_host:$('unifi_mqtt_host').value,mqtt_port:$('unifi_mqtt_port').value,mqtt_username:$('unifi_mqtt_username').value,mqtt_password:$('unifi_mqtt_password').value,mqtt_topic_prefix:$('unifi_mqtt_topic_prefix').value,mqtt_discovery_prefix:$('unifi_mqtt_discovery_prefix').value}}
async function saveUnifi2mqttSettings(){const btn=$('saveUnifi2mqttButton');btn.disabled=true;$('unifiSettingsStatus').textContent='Saving UniFi2MQTT settings…';try{const r=await fetch(endpoint('api/unifi2mqtt/settings'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(unifiSettingsPayload())});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not save UniFi2MQTT settings');renderUnifi2mqttSettings(d);$('unifiSettingsStatus').textContent=d.restarted?'Saved. UniFi2MQTT restart requested.':(d.started?'Saved. UniFi2MQTT start requested.':'Saved.');appLinksCache=null}catch(e){$('unifiSettingsStatus').textContent=`Could not save: ${e}`}finally{btn.disabled=false}}
async function installUnifi2mqtt(){const btn=$('installUnifi2mqttButton');btn.disabled=true;$('unifiInstallStatus').textContent='Installing UniFi2MQTT…';try{const r=await fetch(endpoint('api/unifi2mqtt/install'),{method:'POST'});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not install UniFi2MQTT');appLinksCache=null;renderUnifi2mqttSettings(d);$('unifiInstallStatus').textContent='Installed. Configure the controller and MQTT settings below.'}catch(e){$('unifiInstallStatus').textContent=`Could not install: ${e}`}finally{btn.disabled=false}}
function openUnifiAppConfig(){if(window.unifi2mqttConfigUrl)openHomeAssistantPath(window.unifi2mqttConfigUrl)}
function showLatest(latest){if(!latest){$('readyCard').classList.add('hidden');return}const ready=!!latest.ready_to_send;const processing=latest.processing||{};$('readyHeading').textContent=ready?'Contribution ready':'Contribution requires review';$('contributionId').textContent=latest.contribution_id;$('version').textContent=latest.version;$('archiveName').textContent=latest.archive;$('archiveSize').textContent=fmtBytes(latest.archive_size);const q=$('qualityBanner');q.className=ready?'success':'failure';q.textContent=`Bundle quality: ${latest.quality}${ready?'':' — do not share until reviewed'}`;const issueCount=Number(processing.issue_count||0);$('qualityDetails').textContent=issueCount?`${issueCount} file(s) could not be fully inspected or sanitized. Download the archive and read SANITIZATION_REPORT.txt for privacy-safe issue identifiers.`:(ready?'All files were inspected by the privacy processor.':'Review SANITIZATION_REPORT.txt before sharing.');$('devices').innerHTML='';for(const d of latest.devices||[])$('devices').appendChild(deviceCard(d));if(!(latest.devices||[]).length)$('devices').textContent='No devices were detected.';const emailReady=ready&&!!latest.email;$('prepareEmail').classList.toggle('hidden',!emailReady);if(emailReady)$('prepareEmail').href=endpoint(`download/${encodeURIComponent(latest.email)}`);$('downloadArchive').href=endpoint(`download/${encodeURIComponent(latest.archive)}`);$('mailto').classList.toggle('hidden',!ready);if(ready)$('mailto').href=mailto(latest)}

function diagTile(label,value,state=''){const tile=document.createElement('div');tile.className='diag-tile';const l=document.createElement('div');l.className='muted';l.textContent=label;const v=document.createElement('div');v.className=`diag-value ${state}`;v.textContent=value;tile.append(l,v);return tile}
function renderDiagnostics(d){const summary=$('diagnosticsSummary');summary.innerHTML='';const discovery=d.discovery||{};const registry=d.registry||{};const files=d.files||{};summary.append(diagTile('Switch Vision version',`v${d.version||'Unknown'}`),diagTile('Discovery app',d.service||'Unknown',d.service==='Running'?'diag-good':'diag-bad'),diagTile('Discovery status',discovery.running?'Running':(discovery.message||'Idle / Ready'),discovery.success===false?'diag-bad':'diag-good'),diagTile('Device registry',registry.loaded?`Loaded · ${registry.entries||0} entries`:'Unavailable',registry.loaded?'diag-good':'diag-bad'),diagTile('SNMP2MQTT YAML',files.generated_yaml?.found?'Found':'Missing',files.generated_yaml?.found?'diag-good':'diag-warn'),diagTile('Dashboard YAML',files.generated_card?.found?'Found':'Missing',files.generated_card?.found?'diag-good':'diag-warn'),diagTile('Contribution workflow',d.contribution_workflow?.ready?'Ready':'Unavailable',d.contribution_workflow?.ready?'diag-good':'diag-bad'));
const messages=$('diagnosticsMessages');messages.innerHTML='';for(const [kind,items] of [['failure',d.errors||[]],['warning',d.warnings||[]]]){if(!items.length)continue;const box=document.createElement('div');box.className=kind;const ul=document.createElement('ul');ul.className='diag-list';for(const item of items){const li=document.createElement('li');li.textContent=`${kind==='failure'?'ERROR':'WARNING'}: ${item}`;ul.appendChild(li)}box.appendChild(ul);messages.appendChild(box)}
const devices=$('diagnosticsDevices');devices.innerHTML='';for(const item of d.devices||[]){const normalized={model:item.model,vendor_name:item.name,family:item.family,registry_status:item.registry_status,registry_match:item.registry_match,registry_last_validated_version:item.last_validated_version,physical_count:item.physical_interfaces,rj45_count:item.rj45_interfaces,registry_validation:item.validation};const card=deviceCard(normalized);const extra=document.createElement('div');extra.className='muted';extra.style.marginTop='10px';extra.textContent=`Source: ${item.data_source||'SNMP'} · ${item.data_source==='UniFi API'?`Firmware: ${item.firmware||'Unknown'}`:`SNMP walk: ${item.walk_found?'Available':'Unavailable'}`} · Uplinks detected: ${item.uplink_interfaces||0} · Mapping profile: ${item.mapping_profile||'Not assigned'} · Calibration profile: ${item.calibration_profile||'Not assigned'}`;card.appendChild(extra);devices.appendChild(card)}if(!(d.devices||[]).length)devices.textContent='No capability files were found. Run Discovery to populate device diagnostics.'}
let lastConfiguredDevices=null;
function configuredDeviceTitle(item){return item.display_name||item.switch_name||item.switch_host||'Configured switch'}
function syncConfiguredDeviceToggleAvailability(){const running=!!lastDiscoveryState?.running;document.querySelectorAll('.device-state-toggle').forEach(btn=>{const writable=btn.dataset.writable==='true';btn.disabled=running||!writable;btn.title=running?'Stop Discovery before changing device state.':(writable?'Toggle whether this saved device participates in the next Discovery run.':'Home Assistant app configuration is temporarily unavailable; use Discovery Settings as a fallback.')})}
function renderConfiguredDevices(d){lastConfiguredDevices=d;const root=$('configuredDevices');root.innerHTML='';const writable=!!d?.writable;for(const item of d?.devices||[]){const enabled=item.enabled!=='disabled';const row=document.createElement('div');row.className=`simple-result configured-device${enabled?'':' disabled'}`;const main=document.createElement('div');main.className='result-main';const title=document.createElement('strong');title.textContent=configuredDeviceTitle(item);const line=document.createElement('div');line.className='muted';const bits=[item.switch_name,item.switch_host,item.sensor_prefix,item.switch_model&&item.switch_model!=='auto'?item.switch_model:'Auto-detect'].filter(Boolean);line.textContent=bits.join(' · ');main.append(title,line);const actions=document.createElement('div');actions.className='result-actions';const toggle=document.createElement('button');toggle.type='button';toggle.className=`device-state-toggle ${enabled?'enabled':'disabled'}`;toggle.dataset.writable=String(writable);toggle.setAttribute('role','switch');toggle.setAttribute('aria-checked',String(enabled));toggle.setAttribute('aria-label',`${enabled?'Disable':'Enable'} ${configuredDeviceTitle(item)}`);const track=document.createElement('span');track.className='toggle-track';track.setAttribute('aria-hidden','true');const knob=document.createElement('span');knob.className='toggle-knob';track.appendChild(knob);const label=document.createElement('span');label.textContent=enabled?'Enabled':'Disabled';toggle.append(track,label);toggle.addEventListener('click',()=>setConfiguredDeviceState(item,enabled?'disabled':'enabled',toggle));actions.append(toggle);row.append(main,actions);root.appendChild(row)}if(!(d?.devices||[]).length)root.innerHTML='<p class="muted">No saved switches are configured. Add devices in Discovery Settings first.</p>';const status=$('configuredDevicesStatus');if(!d?.switch_list_enabled&&(d?.devices||[]).length)status.textContent='The saved switch list is globally disabled in Discovery Settings.';else if(!writable)status.textContent='Read-only fallback: Home Assistant app configuration is unavailable. Use Discovery Settings to change device state.';else status.textContent=`${d?.count||0} saved device(s). Changes apply to the next Discovery run.`;syncConfiguredDeviceToggleAvailability()}
async function refreshConfiguredDevices(showStatus=false){if(showStatus)$('configuredDevicesStatus').textContent='Refreshing saved devices…';try{const r=await fetch(endpoint('api/configured-devices'),{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not load saved devices');renderConfiguredDevices(d)}catch(e){$('configuredDevicesStatus').textContent=`Could not load saved devices: ${e.message||e}`}}
async function setConfiguredDeviceState(item,nextState,button){if(lastDiscoveryState?.running){$('configuredDevicesStatus').textContent='Stop Discovery before changing device state.';return}button.disabled=true;const title=configuredDeviceTitle(item);$('configuredDevicesStatus').textContent=`Saving ${title} as ${nextState}…`;try{const r=await fetch(endpoint('api/configured-devices/state'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({index:item.index,switch_name:item.switch_name,enabled:nextState})});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not save device state');renderConfiguredDevices(d);$('configuredDevicesStatus').textContent=`${title} is now ${nextState}. The change applies to the next Discovery run.`}catch(e){$('configuredDevicesStatus').textContent=`Could not change ${title}: ${e.message||e}`;await refreshConfiguredDevices(false)}finally{syncConfiguredDeviceToggleAvailability()}}
function renderDevices(d){const root=$('devicesSummary');root.innerHTML='';for(const item of d.devices||[]){const row=document.createElement('div');row.className='simple-result';const main=document.createElement('div');main.className='result-main';const title=document.createElement('strong');title.textContent=item.model||'Unknown model';const line=document.createElement('div');line.className='muted';const support=statusLabel(item.registry_status||'detected');line.textContent=`Source: ${item.data_source||'SNMP'} · ${item.data_source==='UniFi API'?(item.online?'Online':'Offline'):(item.walk_found?'Discovery passed':'Needs attention')} · Support: ${support} · Ports: ${item.rj45_interfaces||0} RJ45 + ${item.uplink_interfaces||0} uplinks`;if(item.compatibility_mode){const warning=document.createElement('div');warning.className='notice warning';warning.textContent=`Experimental model override: ${item.detected_model||item.model} → ${item.effective_model}`;main.append(title,line,warning)}else{main.append(title,line)}const generated=document.createElement('div');generated.className='muted';generated.textContent=`Sensor configuration: ${d.files?.generated_yaml?.found?'Ready':'Not available'} · Dashboard configuration: ${d.files?.generated_card?.found?'Ready':'Not available'}`;if(!item.compatibility_mode){}main.append(generated);const action=document.createElement('button');action.type='button';action.textContent='View Details';action.addEventListener('click',loadDiagnostics);row.append(main,action);root.appendChild(row)}if(!(d.devices||[]).length)root.innerHTML='<p class="muted">No discovered devices are available yet. Run Discovery first.</p>'}
async function fetchDiagnosticsData(){const r=await fetch(endpoint('api/diagnostics'),{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'Diagnostics request failed');return d}
async function refreshDevicesData(showStatus=true){if(showStatus)$('devicesActionStatus').textContent='Refreshing devices…';try{const d=await fetchDiagnosticsData();renderDevices(d);$('devicesActionStatus').textContent=`Updated ${d.generated_at||''}`}catch(e){$('devicesActionStatus').textContent=`Could not load devices: ${e}`}}
async function refreshDiagnosticsData(showStatus=true){if(showStatus)$('diagnosticsActionStatus').textContent='Refreshing diagnostics…';try{const d=await fetchDiagnosticsData();window.latestDiagnostics=d;renderDiagnostics(d);$('downloadDiagnosticsButton').href=endpoint('download/diagnostics.txt');$('diagnosticsActionStatus').textContent=`Updated ${d.generated_at||''}`}catch(e){$('diagnosticsActionStatus').textContent=`Could not load diagnostics: ${e}`}}
async function loadDevices(){setView('devices');await Promise.all([refreshConfiguredDevices(true),refreshDevicesData()])}
async function loadDiagnostics(){setView('diagnostics');await refreshDiagnosticsData()}
async function copyTextWithFallback(text){if(navigator.clipboard&&typeof navigator.clipboard.writeText==='function'){try{await navigator.clipboard.writeText(text);return true}catch(_e){}}const area=document.createElement('textarea');area.value=text;area.setAttribute('readonly','');area.style.position='fixed';area.style.left='-9999px';area.style.top='0';area.style.opacity='0';document.body.appendChild(area);area.focus();area.select();area.setSelectionRange(0,area.value.length);let copied=false;try{copied=document.execCommand('copy')}catch(_e){copied=false}document.body.removeChild(area);return copied}
async function copyDiagnostics(){const status=$('diagnosticsActionStatus');status.textContent='Copying diagnostics…';try{const r=await fetch(endpoint('download/diagnostics.txt'),{cache:'no-store'});if(!r.ok)throw new Error(`Diagnostics download failed (${r.status})`);const text=await r.text();const copied=await copyTextWithFallback(text);if(!copied)throw new Error('Clipboard access is unavailable in this browser context');status.textContent='Diagnostics copied to clipboard.'}catch(e){status.textContent=`Could not copy diagnostics: ${e}`}}

function sanitizeDebugText(text){
    let cleaned=String(text||'');

    cleaned=cleaned.replace(
        /((?:community|community_string|password|passwd|token|api[_-]?key|secret|authorization|credential|credentials)\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi,
        '$1[REDACTED]'
    );

    cleaned=cleaned.replace(
        /(\s(?:-c|--community|-A|--auth-password|-X|--priv-password|--token)\s+)(?:"[^"]*"|'[^']*'|\S+)/gi,
        '$1[REDACTED]'
    );

    cleaned=cleaned.replace(
        /(Authorization:\s*(?:Bearer|Basic)\s+)[^\s]+/gi,
        '$1[REDACTED]'
    );

    cleaned=cleaned.replace(
        /(https?:\/\/)([^\/\s:@]+):([^@\s\/]+)@/gi,
        '$1[REDACTED]:[REDACTED]@'
    );

    return cleaned;
}

async function copyDebugInfo(){
    const status=$('copyDebugStatus');
    const button=$('copyDebugButton');
    const raw=$('discoveryLog')?.textContent||'';

    if(!raw.trim()){
        status.textContent='No debug information is available to copy.';
        return;
    }

    const text=[
        'Switch Vision Discovery debug output',
        '',
        sanitizeDebugText(raw).trim()
    ].join('\n');

    button.disabled=true;
    status.textContent='Copying debug information…';

    try{
        const copied=await copyTextWithFallback(text);

        if(!copied){
            throw new Error(
                'Clipboard access is unavailable in this browser context'
            );
        }

        button.textContent='Copied ✓';
        status.textContent='Debug information copied to clipboard.';
    }catch(e){
        status.textContent=`Could not copy debug information: ${e}`;
    }finally{
        setTimeout(()=>{
            button.disabled=false;
            button.textContent='Copy Debug Info';
        },1200);
    }
}
function discoveryStage(state){if(!state.running)return state.success===true?5:-1;if((state.phase||'')==='preparing')return -1;const stage=String(state.stage||'').toLowerCase();if(stage.includes('generating snmp2mqtt yaml'))return 3;if(stage.includes('generating dashboard card yaml'))return 4;if(stage.includes('detecting exact models'))return 2;if(stage.includes('running snmp walks'))return 1;if(stage.includes('validating configured switches'))return 0;const text=((state.activity||'')+' '+(state.command||'')+' '+(state.message||'')+' '+(state.log_tail||[]).slice(-3).join(' ')).toLowerCase();if(text.includes('dashboard card')||text.includes('generated dashboard'))return 4;if(text.includes('generated yaml')||text.includes('snmp2mqtt')||text.includes('generator')||text.includes('write_generated_yaml'))return 3;if(text.includes('model/platform')||text.includes('interface mapping')||text.includes('parser summary')||text.includes('exact models'))return 2;if(text.includes('snmp walk')||text.includes('walking')||text.includes('oid trees'))return 1;if(text.includes('configured switches')||text.includes('validating'))return 0;return 0}
function updateSteps(state){const current=discoveryStage(state);for(const el of document.querySelectorAll('#discoverySteps .step')){const n=Number(el.dataset.step);el.classList.toggle('done',state.success===true||(current>=0&&n<current));el.classList.toggle('active',state.running&&(state.phase||'')!=='preparing'&&n===current)} }
let debugVisible=false;
function elapsedText(started,finished=null){if(!started)return '00:00';const start=Date.parse(started);const end=finished?Date.parse(finished):Date.now();if(!Number.isFinite(start)||!Number.isFinite(end))return '00:00';const total=Math.max(0,Math.floor((end-start)/1000));const h=Math.floor(total/3600);const m=Math.floor((total%3600)/60);const s=total%60;return h?`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`}
function updateElapsedClock(){const state=lastDiscoveryState||{};if(!$('liveElapsed'))return;$('liveElapsed').textContent=state.running?elapsedText(state.started_at):((state.started_at&&state.finished_at)?elapsedText(state.started_at,state.finished_at):'00:00')}
function startElapsedTicker(){if(elapsedTicker)return;elapsedTicker=setInterval(()=>{if(!document.hidden&&lastDiscoveryState?.running)updateElapsedClock()},250)}
function showDiscovery(d){const state=d||{};lastDiscoveryState=state;const running=!!state.running;const regen=state.mode==='regenerate_yaml';const phase=state.phase||(running?'running':(state.success===true?'complete':(state.success===false?'failed':'idle')));const preparing=running&&phase==='preparing';const stopping=running&&phase==='stopping';const active=running&&!preparing&&!stopping;const btn=$('runDiscoveryButton');const regenBtn=$('regenerateYamlButton');const stopBtn=$('stopDiscoveryButton');btn.disabled=running;regenBtn.disabled=running;btn.textContent=preparing&&!regen?'Preparing…':(stopping?'Stopping…':(active&&!regen?'Discovery Running…':'Run Discovery'));regenBtn.textContent=regen&&preparing?'Preparing…':(regen&&active?'Regenerating…':'Regenerate SNMP2MQTT YAML');stopBtn.disabled=!running||stopping;stopBtn.textContent=stopping?'Stopping…':'Stop Discovery';let label='Idle / Ready';if(preparing)label=regen?'Preparing SNMP2MQTT YAML regeneration':'Preparing Discovery';else if(stopping)label=regen?'Stopping YAML regeneration':'Stopping Discovery';else if(active)label=regen?'Regenerating SNMP2MQTT YAML':'Discovery running';else if(phase==='stopped')label=regen?'YAML regeneration stopped':'Discovery stopped';else if(state.success===true)label=regen?'SNMP2MQTT YAML regeneration complete':'Discovery complete';else if(state.success===false)label=`${regen?'YAML regeneration':'Discovery'} failed: ${state.message||'Unknown error'}`;$('discoveryStatus').textContent=label;$('homeStatus').textContent=preparing?'Preparing Discovery':(stopping?'Stopping Discovery':(active?'Discovery running':(phase==='stopped'?'Discovery stopped':(state.success===true?'Last discovery complete':(state.success===false?'Discovery needs attention':'Ready')))));$('homeStatusDot').className=`status-dot${running?' running':(state.success===false?' failed':'')}`;$('liveStage').textContent=preparing?'Preparing Discovery':(state.stage||label);$('liveSwitch').textContent=preparing?'Waiting':(state.switch||(!running&&state.success===true?'All configured switches':'Not running'));$('liveTarget').textContent=preparing?'Waiting':(state.target||'Not running');$('liveActivity').textContent=preparing?'Validating configured switches':(state.activity||label);$('liveCommand').textContent=preparing?'Not started':(state.command||'No command running');$('liveRunStatus').textContent=preparing?'Preparing':(stopping?'Stopping':(active?'Running':(phase==='stopped'?'Stopped':(state.success===true?'Complete':(state.success===false?'Failed':'Idle / Ready')))));const snmp=state.snmp2mqtt||{};$('liveSnmp2mqtt').textContent=snmp.message||snmp.status||'Waiting for Discovery';updateElapsedClock();const lines=state.log_tail||[];$('discoveryLog').textContent=lines.length?lines.join('\n'):'No debug details are available yet.';updateSteps(state);syncConfiguredDeviceToggleAvailability()}
async function loadGeneratedCardYamlStatus(){const status=$('generatedCardYamlActionStatus');const preview=$('generatedCardYamlPreview');try{const r=await fetch(endpoint('api/generated-card-yaml/status'),{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not read generated Card YAML status');const found=!!d.generated?.found;const valid=!!d.validation?.valid;const modified=d.generated?.modified||null;$('generatedCardYamlState').textContent=found?`${d.generated.path||'generated-dashboard-card.yaml'} · ${d.generated.size||0} bytes`:'Not generated';$('generatedCardYamlValidation').textContent=valid?`Valid · ${d.validation?.documents||1} YAML document${(d.validation?.documents||1)===1?'':'s'}`:`Invalid · ${d.validation?.error||'validation failed'}`;$('generatedCardYamlUpdated').textContent=modified||'Not available';$('downloadGeneratedCardYamlButton').href=endpoint('download/generated-dashboard-card.yaml');if(!found||!valid){preview.textContent='';preview.classList.add('hidden');status.textContent=!found?'Run Discovery to generate the Card YAML preview.':`Generated Card YAML is not available for preview: ${d.validation?.error||'validation failed'}`}else{if(generatedCardYamlModified&&modified!==generatedCardYamlModified&&!preview.classList.contains('hidden')){preview.textContent=await fetchGeneratedCardYaml();status.textContent='Generated Card YAML preview refreshed.'}else if(status.textContent.startsWith('Could not load')||status.textContent.startsWith('Generated Card YAML is not available'))status.textContent=''}generatedCardYamlModified=modified}catch(e){preview.textContent='';preview.classList.add('hidden');status.textContent=`Could not load generated Card YAML status: ${e}`}}
async function fetchGeneratedCardYaml(){const r=await fetch(endpoint('api/generated-card-yaml/preview'),{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'Card YAML preview failed');return d.text||''}
async function previewGeneratedCardYaml(){const status=$('generatedCardYamlActionStatus');try{const text=await fetchGeneratedCardYaml();$('generatedCardYamlPreview').textContent=text;$('generatedCardYamlPreview').classList.remove('hidden');status.textContent='Generated Card YAML preview loaded.'}catch(e){status.textContent=`Could not preview generated Card YAML: ${e}`}}
async function copyGeneratedCardYaml(){const status=$('generatedCardYamlActionStatus');status.textContent='Copying generated Card YAML…';try{const text=await fetchGeneratedCardYaml();const copied=await copyTextWithFallback(text);if(!copied)throw new Error('Clipboard access is unavailable in this browser context');$('generatedCardYamlPreview').textContent=text;$('generatedCardYamlPreview').classList.remove('hidden');status.textContent='Generated Card YAML copied to clipboard.'}catch(e){status.textContent=`Could not copy generated Card YAML: ${e}`}}
async function loadGeneratedYamlStatus(){try{const r=await fetch(endpoint('api/generated-yaml/status'),{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not read generated YAML status');const applicable=d.applicable!==false;const found=!!d.generated?.found;const description=$('generatedYamlDescription');const actions=$('generatedYamlActions');const regen=$('regenerateYamlButton');const regenHelp=$('regenerateYamlHelp');const preview=$('generatedYamlPreview');const actionStatus=$('generatedYamlActionStatus');if(!applicable){$('generatedYamlState').textContent='Not in use';$('generatedYamlValidation').textContent=`Not applicable · ${d.reason||'No enabled SNMP targets are configured.'}`;$('generatedYamlUpdated').textContent='Not applicable';if(description)description.textContent='SNMP2MQTT YAML is only required for switches using the SNMP data path. UniFi API devices use UniFi2MQTT and do not require this file.';if(actions)actions.hidden=true;if(regen)regen.hidden=true;if(regenHelp)regenHelp.hidden=true;preview.textContent='';preview.classList.add('hidden');actionStatus.textContent='No SNMP2MQTT YAML action is required for this installation.';$('liveSnmp2mqtt').textContent='Not in use · no enabled SNMP targets';return}if(description)description.textContent='Discovery writes the file used by the SNMP2MQTT generated-YAML import option. After a successful SNMP Discovery run, Switch Vision validates the YAML and automatically starts or restarts the SNMP2MQTT app.';if(actions)actions.hidden=false;if(regen)regen.hidden=false;if(regenHelp)regenHelp.hidden=false;actionStatus.textContent='';$('generatedYamlState').textContent=found?`${d.generated.path||'generated-snmp2mqtt.yaml'} · ${d.generated.size||0} bytes`:'Not generated';$('generatedYamlValidation').textContent=d.validation?.valid?'Valid':`Invalid · ${d.validation?.error||'validation failed'}`;$('generatedYamlUpdated').textContent=d.generated?.modified||'Not available';$('downloadGeneratedYamlButton').href=endpoint('download/generated-snmp2mqtt.yaml')}catch(e){$('generatedYamlActionStatus').textContent=`Could not load generated YAML status: ${e}`}}
async function previewGeneratedYaml(){const status=$('generatedYamlActionStatus');try{const r=await fetch(endpoint('api/generated-yaml/preview'),{cache:'no-store'});const d=await r.json();if(!r.ok)throw new Error(d.error||'Preview failed');$('generatedYamlPreview').textContent=d.text||'';$('generatedYamlPreview').classList.remove('hidden');status.textContent='Generated YAML preview loaded.'}catch(e){status.textContent=`Could not preview generated YAML: ${e}`}}
function toggleDebug(){debugVisible=!debugVisible;$('debugWrap').classList.toggle('hidden',!debugVisible);$('toggleDebugButton').textContent=debugVisible?'Hide Debug':'Show Debug'}
async function regenerateSnmp2mqttYaml(){const btn=$('regenerateYamlButton');const status=$('regenerateYamlStatus');btn.disabled=true;status.textContent='Preparing stored-walk YAML regeneration…';try{const r=await fetch(endpoint('api/discovery/regenerate-yaml'),{method:'POST'});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not start YAML regeneration');status.textContent='Regeneration started. Existing saved walks are being reprocessed; no SNMP walks will run.';await refresh()}catch(e){status.textContent=`Could not regenerate SNMP2MQTT YAML: ${e.message||e}`;btn.disabled=false}}
async function runDiscovery(){const btn=$('runDiscoveryButton');btn.disabled=true;$('discoveryStatus').textContent='Preparing Discovery';try{const r=await fetch(endpoint('api/discovery/start'),{method:'POST'});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not start Discovery');await refresh()}catch(e){$('discoveryStatus').textContent=`Could not start Discovery: ${e}`;btn.disabled=false}}
async function stopDiscovery(){const btn=$('stopDiscoveryButton');btn.disabled=true;$('discoveryStatus').textContent='Stopping Discovery';try{const r=await fetch(endpoint('api/discovery/stop'),{method:'POST'});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not stop Discovery');await refresh()}catch(e){$('discoveryStatus').textContent=`Could not stop Discovery: ${e}`;btn.disabled=false}}
async function resetSnmpDiscoveryData(){const btn=$('resetSnmpDiscoveryButton');const status=$('resetSnmpDiscoveryStatus');if(lastDiscoveryState?.running){status.textContent='Stop Discovery before resetting SNMP data.';return}if(!confirm('Reset SNMP Discovery data? This stops Switch Vision SNMP2MQTT, removes identifiable retained SNMP2MQTT Home Assistant discovery entities, deletes saved SNMP walk/capability/generated SNMP data, and clears the generated card for a clean rebuild. UniFi data and settings are preserved.'))return;btn.disabled=true;status.textContent='Resetting SNMP Discovery data…';try{const r=await fetch(endpoint('api/discovery/reset-snmp'),{method:'POST'});const d=await r.json();if(!r.ok)throw new Error(d.error||'SNMP reset failed');const warning=(d.warnings||[]).length?` Warnings: ${(d.warnings||[]).join(' | ')}`:'';status.textContent=`SNMP reset complete. MQTT entities retired: ${d.mqtt_topics_cleared||0}/${d.mqtt_topics_found||0}. Saved walk entries removed: ${d.walk_entries_removed||0}. Capability entries removed: ${d.capability_entries_removed||0}.${warning} Run Discovery to rebuild from the currently enabled sources.`;await Promise.all([loadGeneratedCardYamlStatus(),loadGeneratedYamlStatus(),refreshDevicesData(false)])}catch(e){status.textContent=`Could not reset SNMP Discovery data: ${e.message||e}`}finally{btn.disabled=false}}

async function importConfiguration(){const file=$('configurationFile').files[0];const status=$('configurationStatus');if(!file){status.textContent='Choose a configuration JSON file first.';return}if(file.size>1024*1024){status.textContent='Configuration file is too large.';return}if(!confirm('Import this Discovery configuration? The current switch list and Discovery settings will be replaced.'))return;const btn=$('importConfigurationButton');btn.disabled=true;status.textContent='Importing configuration…';try{const text=await file.text();const data=JSON.parse(text);const r=await fetch(endpoint('api/configuration/import'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const d=await r.json();if(!r.ok)throw new Error(d.error||'Import failed');status.textContent=`Imported ${d.switch_count||0} configured switch(es). The saved Supervisor configuration is active for the next Discovery run.`}catch(e){status.textContent=`Could not import configuration: ${e.message||e}`}finally{btn.disabled=false}}
function schedulePoll(running=lastRunning){if(polling){clearTimeout(polling);polling=null}if(document.hidden)return;polling=setTimeout(refresh,running?1000:5000)}
async function refresh(){if(refreshInFlight)return;refreshInFlight=true;try{const r=await fetch(endpoint('api/status'),{cache:'no-store'});const d=await r.json();if(d.ui_preferences?.density)syncDensityUi(d.ui_preferences.density);setUnifiHomeCardVisibility(d.ui_preferences?.show_unifi_integration!==false);if(d.ui_preferences?.show_unifi_integration!==false)await refreshUnifiHomeCard();if(!defaultsLoaded)setForm(d.defaults);showDiscovery(d.discovery);const contributionRunning=!!d.job.running;const discoveryRunning=!!d.discovery?.running;lastRunning=contributionRunning||discoveryRunning;$('createButton').disabled=contributionRunning;if(contributionRunning&&currentView!=='discovery')setView('progress');$('progressMessage').textContent=d.job.message||'Working…';$('logTail').textContent=(d.job.log_tail||[]).join('\n');if(!contributionRunning&&d.job.success===false&&currentView==='progress'){$('progressMessage').textContent=`Failed: ${d.job.message}`}if(!contributionRunning){showLatest(d.latest);if(d.job.success===true&&d.latest&&currentView==='progress')setView('ready')}if(currentView==='devices')await refreshDevicesData(false);else if(currentView==='diagnostics')await refreshDiagnosticsData(false);else if(currentView==='discovery')await Promise.all([loadGeneratedCardYamlStatus(),loadGeneratedYamlStatus()])}catch(e){if(currentView==='progress')$('progressMessage').textContent=`Could not contact Support My Switch: ${e}`;else $('homeStatus').textContent=`Connection problem: ${e}`}finally{refreshInFlight=false;schedulePoll(lastRunning)}}
document.addEventListener('visibilitychange',()=>{if(document.hidden){if(polling){clearTimeout(polling);polling=null}}else{updateElapsedClock();refresh()}});window.addEventListener('focus',()=>{if(!document.hidden){updateElapsedClock();refresh()}});
async function create(){const btn=$('createButton');btn.disabled=true;setView('progress');$('progressMessage').textContent='Starting…';try{const r=await fetch(endpoint('api/create'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not start contribution');await refresh()}catch(e){$('progressMessage').textContent=`Could not start: ${e}`;btn.disabled=false}}
$('themeSelect').addEventListener('change',e=>applyManagementTheme(e.target.value));initManagementTheme();syncDensityUi([...document.body.classList].find(v=>v.startsWith('density-'))?.slice(8)||'comfortable');for(const id of ['mask_management_ips','mask_mac_addresses','mask_hostnames'])$(id).addEventListener('change',updateWarning);$('contributor_type').addEventListener('change',updateRecognition);$('createButton').addEventListener('click',create);$('createAnother').addEventListener('click',()=>setView('support'));$('backButton').addEventListener('click',goBack);$('openDiscoveryButton').addEventListener('click',()=>{setView('discovery');Promise.all([loadGeneratedCardYamlStatus(),loadGeneratedYamlStatus()])});$('openDevicesButton').addEventListener('click',loadDevices);$('openCalibrationProfilesButton').addEventListener('click',()=>{setView('profiles');window.SwitchVisionCalibrationProfiles?.load()});$('openSupportButton').addEventListener('click',()=>setView('support'));$('runDiscoveryButton').addEventListener('click',runDiscovery);$('regenerateYamlButton').addEventListener('click',regenerateSnmp2mqttYaml);$('stopDiscoveryButton').addEventListener('click',stopDiscovery);$('resetSnmpDiscoveryButton').addEventListener('click',resetSnmpDiscoveryData);$('viewResultsButton').addEventListener('click',loadDevices);$('toggleDebugButton').addEventListener('click',toggleDebug);$('copyDebugButton').addEventListener('click',copyDebugInfo);$('previewGeneratedCardYamlButton').addEventListener('click',previewGeneratedCardYaml);$('copyGeneratedCardYamlButton').addEventListener('click',copyGeneratedCardYaml);$('previewGeneratedYamlButton').addEventListener('click',previewGeneratedYaml);$('devicesRunDiscoveryButton').addEventListener('click',()=>{setView('discovery');runDiscovery()});$('refreshDevicesButton').addEventListener('click',loadDevices);$('openDiagnosticsButton').addEventListener('click',loadDiagnostics);$('openConfigurationButton').addEventListener('click',()=>{setView('configuration');$('exportConfigurationButton').href=endpoint('download/discovery-configuration.json')});$('openIntegrationSettingsButton').addEventListener('click',()=>window.SwitchVisionHubSettings?.open('core'));$('openDiscoverySettingsButton').addEventListener('click',()=>window.SwitchVisionHubSettings?.open('discovery'));$('openSnmp2mqttSettingsButton').addEventListener('click',()=>window.SwitchVisionHubSettings?.open('snmp2mqtt'));$('openUnifi2mqttSettingsButton').addEventListener('click',()=>{const btn=$('openUnifi2mqttSettingsButton');if(btn?.dataset.unifiAction==='blocked')return;loadUnifi2mqttSettings()});$('saveUnifi2mqttButton').addEventListener('click',saveUnifi2mqttSettings);$('installUnifi2mqttButton').addEventListener('click',installUnifi2mqtt);$('openUnifiAppConfigButton').addEventListener('click',openUnifiAppConfig);$('importConfigurationButton').addEventListener('click',importConfiguration);$('refreshDiagnosticsButton').addEventListener('click',loadDiagnostics);$('copyDiagnosticsButton').addEventListener('click',copyDiagnostics);$('diagnosticsRunDiscoveryButton').addEventListener('click',()=>{setView('discovery');runDiscovery()});setView('home');startElapsedTicker();refresh();
</script>
<script>
(()=>{'use strict';const q=id=>document.getElementById(id),clone=v=>JSON.parse(JSON.stringify(v)),dirty=new Set(),state={core:null,snmp2mqtt:null,discovery:null,models:[],order:[]};const L={show_all_switch_vision_sidebar_items:'Show all Switch Vision sidebar items',show_panel_in_sidebar:'Show native Switch Vision in sidebar',show_lovelace_dashboard_in_sidebar:'Show Switch Vision dashboard in sidebar',show_hub_in_sidebar:'Show Switch Vision Hub in sidebar',show_installer_in_sidebar:'Show Switch Vision Installer in sidebar',show_dashboard_header:'Show dashboard header',native_header_show_summary:'Show summary',native_header_show_refresh:'Show refresh',native_header_show_version:'Show version',native_header_shortcut_switch_vision_settings:'Switch Vision Settings shortcut',native_header_shortcut_hub:'Hub shortcut',native_header_shortcut_maintenance:'Maintenance shortcut',native_header_shortcut_discovery_settings:'Discovery Settings shortcut',native_header_shortcut_installer:'Installer shortcut',native_header_shortcut_installer_settings:'Installer Settings shortcut',native_header_shortcut_snmp2mqtt_settings:'SNMP2MQTT Settings shortcut',native_header_shortcut_unifi2mqtt_settings:'UniFi2MQTT Settings shortcut',show_calibration_buttons:'Show calibration buttons on cards',show_card_headers:'Show card headers'};const OL={hub:'Hub',maintenance:'Maintenance',switch_vision_settings:'Switch Vision Settings',discovery_settings:'Discovery Settings',installer:'Installer',installer_settings:'Installer Settings',snmp2mqtt_settings:'SNMP2MQTT Settings',unifi2mqtt_settings:'UniFi2MQTT Settings'};function status(t,c=''){const n=q('hubSettingsStatus');if(n){n.className=`muted hub-settings-status ${c}`.trim();n.textContent=t}}function mark(o){dirty.add(o);q('hubSettingsSave').disabled=false;status('Unsaved changes')}function clear(o){dirty.delete(o);q('hubSettingsSave').disabled=!dirty.size}async function req(p,o={}){const r=await fetch(endpoint(p),{cache:'no-store',...o});let d={};try{d=await r.json()}catch(_e){}if(!r.ok)throw new Error(d.error||`Request failed (${r.status})`);return d}function sec(t,p=''){const x=document.createElement('section');x.className='hub-settings-section';x.innerHTML=`<h3>${t}</h3>${p?`<p class="muted">${p}</p>`:''}`;return x}function fld(t,c,h=''){const x=document.createElement('label');x.className='field hub-setting-field';const s=document.createElement('span');s.textContent=t;x.append(s,c);if(h){const m=document.createElement('small');m.textContent=h;x.append(m)}return x}function tog(t,v,fn,dis=false,h=''){const x=document.createElement('label');x.className='option hub-setting-toggle';const i=document.createElement('input');i.type='checkbox';i.checked=!!v;i.disabled=dis;i.onchange=()=>fn(i.checked);const s=document.createElement('span'),b=document.createElement('b');b.textContent=t;s.append(b);if(h){s.append(document.createElement('br'));const m=document.createElement('small');m.textContent=h;s.append(m)}x.append(i,s);return x}function sel(v,opts,fn){const s=document.createElement('select');for(const [a,b] of opts){const o=document.createElement('option');o.value=a;o.textContent=b;o.selected=String(v)===String(a);s.append(o)}s.onchange=()=>fn(s.value);return s}function inp(v,type,fn,a={}){const i=document.createElement('input');i.type=type;i.value=v??'';for(const[k,x]of Object.entries(a))if(x!==undefined&&x!==null)i.setAttribute(k,String(x));i.oninput=()=>fn(i.value);return i}function renderCore(){const r=q('hubCoreSettings');r.innerHTML='';if(!state.core?.settings){r.textContent='Core settings are unavailable.';return}const s=state.core.settings,side=sec('Sidebar & navigation');for(const[k,v]of Object.entries(s.sidebar||{}))side.append(tog(L[k]||k,v,x=>{s.sidebar[k]=x;mark('core')}));r.append(side);const h=sec('Native dashboard header','Choose which controls appear in the native Switch Vision header.');for(const[k,v]of Object.entries(s.native_header||{})){if(k!=='native_header_shortcut_order')h.append(tog(L[k]||k,v,x=>{s.native_header[k]=x;mark('core')}))}const box=document.createElement('div');box.className='hub-order-list';box.innerHTML='<b>Shortcut order</b>';state.order=[...(s.native_header.native_header_shortcut_order||[])];const draw=()=>{box.querySelectorAll('.hub-order-row').forEach(n=>n.remove());state.order.forEach((id,n)=>{const row=document.createElement('div');row.className='hub-order-row';const nm=document.createElement('span');nm.textContent=OL[id]||id;const u=document.createElement('button'),d=document.createElement('button');u.type=d.type='button';u.textContent='↑';d.textContent='↓';u.disabled=n===0;d.disabled=n===state.order.length-1;u.onclick=()=>{[state.order[n-1],state.order[n]]=[state.order[n],state.order[n-1]];s.native_header.native_header_shortcut_order=[...state.order];mark('core');draw()};d.onclick=()=>{[state.order[n+1],state.order[n]]=[state.order[n],state.order[n+1]];s.native_header.native_header_shortcut_order=[...state.order];mark('core');draw()};row.append(nm,u,d);box.append(row)})};draw();h.append(box);r.append(h);const dash=sec('Dashboard presentation');for(const[k,v]of Object.entries(s.dashboard||{}))dash.append(tog(L[k]||k,v,x=>{s.dashboard[k]=x;mark('core')}));r.append(dash);const a=sec('Activity LEDs'),g=document.createElement('div');g.className='grid';g.append(fld('Sensitivity preset',sel(s.activity_leds.activity_led_sensitivity_preset,[['low','Low'],['normal','Normal'],['high','High'],['custom','Custom']],x=>{s.activity_leds.activity_led_sensitivity_preset=x;mark('core')})));for(const[k,t,min,max,step]of [['activity_slow_max_utilization_pct','Slow activity maximum (%)',.001,100,.001],['activity_medium_max_utilization_pct','Medium activity maximum (%)',.001,100,.001],['activity_slow_period_ms','Slow blink period (ms)',120,2000,1],['activity_medium_period_ms','Medium blink period (ms)',120,2000,1],['activity_fast_period_ms','Fast blink period (ms)',120,2000,1],['activity_hold_seconds','Activity hold (seconds)',1,120,.1],['activity_hysteresis_pct','Hysteresis (%)',0,50,.1]])g.append(fld(t,inp(s.activity_leds[k],'number',x=>{s.activity_leds[k]=Number(x);mark('core')},{min,max,step})));a.append(g);r.append(a);const ap=document.createElement('div');ap.className='hub-settings-columns';for(const[grp,title]of[['discovery','Discovery appearance'],['installer','Installer appearance']]){const b=sec(title),v=s[grp];b.append(fld('UI density',sel(v[`${grp}_ui_density`],[['comfortable','Comfortable'],['compact','Compact'],['dense','Dense']],x=>{v[`${grp}_ui_density`]=x;mark('core')})),fld('Text size',sel(v[`${grp}_text_size`],[['normal','Normal (~15.7 px)'],['small','Small (14.4 px)']],x=>{v[`${grp}_text_size`]=x;mark('core')})),fld('Content width',sel(v[`${grp}_content_width`],[['standard','Standard'],['wide','Wide'],['full','Full']],x=>{v[`${grp}_content_width`]=x;mark('core')})));if(grp==='discovery')b.append(tog('Show UniFi integration',v.show_unifi_integration,x=>{v.show_unifi_integration=x;mark('core')}));ap.append(b)}r.append(ap)}function renderSnmp(){const r=q('hubSnmpSettings');r.innerHTML='';const d=state.snmp2mqtt;if(!d?.installed){r.innerHTML='<div class="warning">Switch Vision SNMP2MQTT is not installed.</div>';return}const s=d.settings,m=sec('MQTT connection'),g=document.createElement('div');g.className='grid';g.append(fld('MQTT host',inp(s.mqtt.host,'text',x=>{s.mqtt.host=x;mark('snmp2mqtt')})),fld('MQTT port',inp(s.mqtt.port,'number',x=>{s.mqtt.port=Number(x);mark('snmp2mqtt')},{min:1,max:65535,step:1})),fld('MQTT username',inp(s.mqtt.username,'text',x=>{s.mqtt.username=x;mark('snmp2mqtt')})),fld('MQTT password',inp('','password',x=>{s.mqtt.password=x;mark('snmp2mqtt')},{autocomplete:'new-password',placeholder:d.password_configured?'Saved — leave blank to keep':'Not configured'}),'The saved password is never returned to the Hub. Leave blank to preserve it.'));m.append(g,tog('Clear saved MQTT password',false,x=>{s.clear_password=x;mark('snmp2mqtt')},false,'Only enable this if the broker no longer requires the saved password.'));r.append(m);const p=sec('Target configuration'),pg=document.createElement('div');pg.className='grid';for(const[k,t]of[['targets_path','Targets path'],['switch_vision_generated_yaml_path','Generated YAML path'],['imported_targets_path','Imported targets path']])pg.append(fld(t,inp(s[k],'text',x=>{s[k]=x;mark('snmp2mqtt')})));p.append(pg,tog('Use Switch Vision generated YAML',s.use_switch_vision_generated_yaml,x=>{s.use_switch_vision_generated_yaml=x;mark('snmp2mqtt')}),tog('Back up existing config before import',s.backup_existing_config,x=>{s.backup_existing_config=x;mark('snmp2mqtt')}));r.append(p);const ha=sec('Home Assistant discovery');ha.append(tog('MQTT Discovery enabled',true,()=>{},true,'Required by Switch Vision and enforced by SNMP2MQTT.'),fld('Discovery prefix',inp('homeassistant','text',()=>{},{readonly:'readonly'}),'Required value: homeassistant.'));r.append(ha)}function bsel(v,fn){return sel(v===true||String(v).toLowerCase()==='true'?'true':'false',[['true','Enabled'],['false','Disabled']],fn)}function renderDiscovery(){const r=q('hubDiscoverySettings');r.innerHTML='';if(!state.discovery?.settings){r.textContent='Discovery settings are unavailable.';return}const s=state.discovery.settings,w=sec('Discovery workflow'),wg=document.createElement('div');wg.className='grid';for(const[k,t]of[['run_snmp_walks','Run SNMP walks'],['enable_switch_list','Use saved switch list'],['parse_all_walks','Parse all stored walks'],['generate_snmp2mqtt','Generate SNMP2MQTT YAML'],['clean_output_before_walk','Clean generated output before walk'],['generate_support_my_switch_bundle','Create Support My Switch bundle after Discovery']])wg.append(fld(t,bsel(s[k],x=>{s[k]=x;mark('discovery')})));w.append(wg);r.append(w);const sw=sec('Switches','SNMP communities are write-only. Blank preserves an existing saved community.');(s.switches||[]).forEach((row,n)=>{const c=document.createElement('div');c.className='device-card hub-setting-row';const hd=document.createElement('div');hd.className='device-head';hd.innerHTML=`<strong>Switch ${n+1}</strong>`;const rm=document.createElement('button');rm.type='button';rm.className='danger';rm.textContent='Remove';rm.onclick=()=>{s.switches.splice(n,1);mark('discovery');renderDiscovery()};hd.append(rm);c.append(hd);const g=document.createElement('div');g.className='grid';const f=(t,k,type='text',hint='')=>fld(t,inp(row[k]??'',type,x=>{row[k]=x;mark('discovery')},type==='password'?{autocomplete:'new-password',placeholder:row.snmp_community_configured?'Saved — leave blank to keep':'Required for new switch'}:{}),hint);g.append(f('Switch Name (Used internally only)','switch_name'),f('Display name','display_name'),f('Switch host','switch_host'),f('Sensor prefix','sensor_prefix'),f('SNMP community','snmp_community','password','Saved communities are never returned to the Hub.'),fld('State',sel(row.enabled||'enabled',[['enabled','Enabled'],['disabled','Disabled']],x=>{row.enabled=x;mark('discovery')})),fld('Walk mode',sel(row.walk_mode||'targeted',[['targeted','Targeted'],['full','Full']],x=>{row.walk_mode=x;mark('discovery')})),fld('Switch model',sel(row.switch_model||'auto',[['auto','Auto'],...state.models.filter(m=>m!=='auto').map(m=>[m,m])],x=>{row.switch_model=x;mark('discovery')})),f('Card header title','card_header_title'));c.append(g);sw.append(c)});const add=document.createElement('button');add.type='button';add.textContent='Add switch';add.onclick=()=>{s.switches.push({switch_name:'',display_name:'',switch_host:'',sensor_prefix:'',snmp_community:'',snmp_community_configured:false,original_switch_name:'',enabled:'enabled',walk_mode:'targeted',switch_model:'auto',card_header_title:''});mark('discovery');renderDiscovery()};sw.append(add);r.append(sw);const st=sec('Stack member display mapping');(s.stack_member_prefixes||[]).forEach((row,n)=>{const c=document.createElement('div');c.className='device-card hub-setting-row';const hd=document.createElement('div');hd.className='device-head';hd.innerHTML=`<strong>Stack member ${n+1}</strong>`;const rm=document.createElement('button');rm.type='button';rm.className='danger';rm.textContent='Remove';rm.onclick=()=>{s.stack_member_prefixes.splice(n,1);mark('discovery');renderDiscovery()};hd.append(rm);c.append(hd);const g=document.createElement('div');g.className='grid';for(const[k,t]of[['switch_name','Switch name'],['member','Member number'],['display_name','Display name'],['sensor_prefix','Sensor prefix'],['card_header_title','Card header title']])g.append(fld(t,inp(row[k]??'','text',x=>{row[k]=x;mark('discovery')})));c.append(g);st.append(c)});const as=document.createElement('button');as.type='button';as.textContent='Add stack member';as.onclick=()=>{s.stack_member_prefixes.push({switch_name:'',member:'1',display_name:'',sensor_prefix:'',card_header_title:''});mark('discovery');renderDiscovery()};st.append(as);r.append(st);const p=sec('Paths & SNMP timing'),pg=document.createElement('div');pg.className='grid';for(const[k,t]of[['input_path','Input walk path'],['snmpwalks_dir','SNMP walks directory'],['report_path','Discovery report path'],['targets_csv','Targets CSV path'],['last_run_summary_path','Last-run summary path'],['generated_yaml_path','Generated SNMP2MQTT path'],['generated_card_path','Generated dashboard path'],['snmp_log_path','SNMP log path']])pg.append(fld(t,inp(s[k]??'','text',x=>{s[k]=x;mark('discovery')})));for(const[k,t,min,max]of[['snmp_timeout','SNMP timeout',1,30],['snmp_retries','SNMP retries',0,10],['minimum_valid_walk_lines','Minimum valid walk lines',1,1000000]])pg.append(fld(t,inp(s[k]??'','number',x=>{s[k]=String(x);mark('discovery')},{min,max,step:1})));p.append(pg);r.append(p);const bk=sec('Discovery configuration backups'),bg=document.createElement('div');bg.className='grid';bg.append(fld('Automatic retention',bsel(s.backup_retention_enabled,x=>{s.backup_retention_enabled=x;mark('discovery')})),fld('Retained backups',inp(s.backup_retention_count,'number',x=>{s.backup_retention_count=Number(x);mark('discovery')},{min:1,max:10,step:1})));bk.append(bg);r.append(bk);const sp=sec('Support My Switch privacy & recognition'),sg=document.createElement('div');sg.className='grid';for(const[k,t]of[['support_mask_management_ips','Mask management IPs'],['support_mask_mac_addresses','Mask MAC addresses'],['support_mask_hostnames','Mask hostnames'],['support_mask_vlan_names','Mask VLAN names'],['support_mask_interface_descriptions','Mask interface descriptions']])sg.append(fld(t,bsel(s[k],x=>{s[k]=x;mark('discovery')})));sg.append(fld('Contributor recognition',sel(s.support_contributor_type||'anonymous',[['anonymous','Anonymous'],['first_name','First name'],['full_name','Full name'],['github','GitHub'],['forum','Forum']],x=>{s.support_contributor_type=x;mark('discovery')})),fld('Contributor value',inp('','text',x=>{s.support_contributor_value=x;mark('discovery')},{maxlength:120,placeholder:s.support_contributor_value_configured?'Saved — leave blank to keep':'Optional recognition'}),'Private and write-only in the Hub; nothing is published automatically.'));sp.append(sg);r.append(sp)}function cleanDiscovery(){const s=clone(state.discovery.settings);delete s.support_contributor_value_configured;s.switches=(s.switches||[]).map(row=>{const x={...row};delete x.snmp_community_configured;return x});return s}async function load(){status('Loading settings…');const a=await Promise.allSettled([req('api/settings/core'),req('api/settings/snmp2mqtt'),req('api/settings/discovery')]);state.core=a[0].status==='fulfilled'?clone(a[0].value):null;state.snmp2mqtt=a[1].status==='fulfilled'?clone(a[1].value):{installed:false};if(a[2].status==='fulfilled'){state.discovery=clone(a[2].value);state.models=[...(a[2].value.models||[])]}else state.discovery=null;renderCore();renderSnmp();renderDiscovery();dirty.clear();q('hubSettingsSave').disabled=true;const e=a.filter(x=>x.status==='rejected').map(x=>x.reason?.message||String(x.reason));status(e.length?`Loaded with ${e.length} unavailable section(s): ${e.join(' · ')}`:'All settings loaded from their authoritative components.',e.length?'failure':'success')}async function save(){if(!dirty.size)return;const b=q('hubSettingsSave'),done=[];b.disabled=true;try{for(const o of ['core','snmp2mqtt','discovery']){if(!dirty.has(o))continue;status(`Saving ${o==='core'?'Core':o==='snmp2mqtt'?'SNMP2MQTT':'Discovery'}…`);const body=o==='core'?{settings:state.core.settings}:o==='snmp2mqtt'?{settings:state.snmp2mqtt.settings}:{settings:cleanDiscovery()};const d=await req(`api/settings/${o}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(o==='core')state.core=clone(d);else if(o==='snmp2mqtt')state.snmp2mqtt=clone(d);else{state.discovery=clone(d);state.models=[...(d.models||state.models)]}done.push(o);clear(o)}renderCore();renderSnmp();renderDiscovery();status('Saved successfully.','success')}catch(e){status(`${done.length?`Saved ${done.join(', ')}. `:''}Save stopped: ${e.message||e}`,'failure');b.disabled=!dirty.size}}async function resetCore(){if(!confirm('Reset all Switch Vision Core settings to their factory defaults? SNMP2MQTT and Discovery settings are not changed.'))return;try{status('Resetting Core settings…');state.core=clone(await req('api/settings/core',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reset_to_defaults:true})}));clear('core');renderCore();status('Core settings reset to defaults.','success')}catch(e){status(`Core reset failed: ${e.message||e}`,'failure')}}function styles(){if(q('hubSettingsStyles'))return;const s=document.createElement('style');s.id='hubSettingsStyles';s.textContent='.hub-settings-intro{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;margin-bottom:14px}.hub-settings-section{border-top:1px solid var(--line-soft);padding-top:14px;margin-top:16px}.hub-settings-section:first-child{border-top:0;margin-top:0}.hub-settings-section h3{margin:.15rem 0 .35rem}.hub-settings-columns{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px}.hub-setting-toggle span{display:block}.hub-setting-field{margin:6px 0;gap:4px;align-self:start;align-content:start}.hub-setting-field>span{font-weight:600;line-height:1.2}.hub-setting-field>input,.hub-setting-field>select{width:100%;height:38px;min-height:38px;padding:6px 10px}.hub-setting-field>small{line-height:1.25;margin-top:1px}.hub-settings-section .grid{align-items:start;gap:8px 14px}.hub-order-list{border:1px solid var(--line-soft);border-radius:9px;padding:10px;margin-top:12px}.hub-order-row{display:grid;grid-template-columns:1fr auto auto;gap:7px;align-items:center;padding:5px 0}.hub-order-row button{padding:5px 9px}.hub-settings-actions{position:sticky;bottom:0;display:flex;gap:10px;align-items:center;flex-wrap:wrap;background:var(--card);border-top:1px solid var(--line);padding:12px 0 4px;margin-top:20px;z-index:3}.hub-settings-status{margin-left:auto}.hub-settings-status.success{color:var(--ok)}.hub-settings-status.failure{color:var(--bad)}.hub-component{border:1px solid var(--line-soft);border-radius:12px;padding:14px;margin:14px 0;background:var(--surface-inset)}.hub-component>summary{cursor:pointer;font-size:1rem;font-weight:700}.hub-component[open]>summary{margin-bottom:12px}.hub-setting-row{margin:12px 0}@media(max-width:700px){.hub-settings-status{width:100%;margin-left:0}.hub-settings-actions{padding-bottom:10px}}';document.head.append(s)}async function open(which='core'){styles();setView('settings');await load();const x=q(`hubComponent-${which}`);if(x){x.open=true;x.scrollIntoView({behavior:'smooth',block:'start'})}}function init(){styles();q('hubSettingsSave')?.addEventListener('click',save);q('hubSettingsReload')?.addEventListener('click',load);q('hubCoreReset')?.addEventListener('click',resetCore);q('hubCoreFallback')?.addEventListener('click',()=>openHomeAssistantPath('/config/integrations/integration/switch_vision'));q('hubSnmpFallback')?.addEventListener('click',()=>openResolvedApp('snmp2mqtt'));q('hubDiscoveryFallback')?.addEventListener('click',()=>openResolvedApp('discovery'))}window.SwitchVisionHubSettings={open,load,save};document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init,{once:true}):init()})();
</script>
<script src="maintenance.js"></script>
<script src="calibration_profiles.js"></script>
</body></html>"""


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
        body = _page_with_ui_preferences().encode("utf-8")
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
        if not path.is_file() or path.suffix.lower() not in {".zip", ".eml", ".html"}:
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

    def _diagnostics_download(self) -> None:
        data = _diagnostics_snapshot(self.app.version)
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
                "job": _state_snapshot(),
                "latest": _latest_contribution(self.app.contributions_dir),
                "defaults": _defaults(self.app.options_file),
                "discovery": _discovery_state_snapshot(),
                "ui_preferences": _discovery_ui_preferences(),
            })
        elif path == "/api/health":
            self._json({"status": "ok", "version": self.app.version})
        elif path == "/api/app-links":
            self._json(_installed_switch_vision_app_links())
        elif path == "/api/settings/core":
            try:
                self._json(_core_settings_status())
            except RuntimeError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
        elif path == "/api/settings/snmp2mqtt":
            try:
                self._json(_snmp2mqtt_settings_status())
            except RuntimeError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
        elif path == "/api/settings/discovery":
            try:
                self._json(_discovery_settings_status())
            except RuntimeError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
        elif path == "/api/maintenance/installer-backups":
            try:
                self._json(_installer_maintenance_request("status"))
            except (ValueError, RuntimeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
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
        elif path in {"/calibration_profiles.js", "/maintenance.js"}:
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
                    "application/javascript; charset=utf-8",
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
                    result
                    if isinstance(result, dict)
                    else {}
                )

            except (
                ValueError,
                RuntimeError,
            ) as exc:
                self._json(
                    {"error": str(exc)},
                    HTTPStatus.BAD_GATEWAY,
                )
        elif path == "/api/unifi2mqtt/settings":
            try:
                self._json(_unifi2mqtt_settings_status())
            except RuntimeError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
        elif path == "/api/configured-devices":
            self._json(_configured_devices_snapshot(self.app.options_file))
        elif path == "/api/diagnostics":
            self._json(_diagnostics_snapshot(self.app.version))
        elif path == "/api/generated-card-yaml/status":
            self._json(_generated_card_yaml_status())
        elif path == "/api/generated-card-yaml/preview":
            result = _validate_generated_card_yaml(DEFAULT_GENERATED_CARD)
            if not result.get("valid"):
                self._json({"error": result.get("error")}, HTTPStatus.BAD_REQUEST)
            else:
                self._json({"text": result.get("text"), "sha256": result.get("sha256")})
        elif path == "/api/generated-yaml/status":
            self._json(_generated_yaml_status())
        elif path == "/api/generated-yaml/preview":
            result = _validate_snmp2mqtt_yaml(DEFAULT_GENERATED_SNMP2MQTT)
            if not result.get("valid"):
                self._json({"error": result.get("error")}, HTTPStatus.BAD_REQUEST)
            else:
                self._json({"text": result.get("text"), "sha256": result.get("sha256")})
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
                    _home_assistant_service(
                        "switch_vision",
                        "delete_calibration",
                        {
                            "profile":
                            profile
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
        if path == "/api/configured-devices/state":
            try:
                with _exclusive_operation("Device configuration update"):
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 8192:
                        raise ValueError("Invalid device state request size.")
                    data = json.loads(self.rfile.read(length).decode("utf-8"))
                    self._json(_set_configured_device_state(self.app.options_file, data))
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except (ValueError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/configuration/import":
            try:
                with _exclusive_operation("Configuration import"):
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 1024 * 1024:
                        raise ValueError("Invalid configuration file size.")
                    data = json.loads(self.rfile.read(length).decode("utf-8"))
                    imported = _validate_discovery_import(data)
                    _import_discovery_options(imported)
                    self._json({
                        "imported": True,
                        "switch_count": _configured_switch_count(imported.get("switches")),
                        "restart_required": False,
                    })
            except OperationConflict as exc:
                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            except (ValueError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
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
