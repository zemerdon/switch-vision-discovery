#!/usr/bin/env python3
"""Privacy-scoped Support My Switch diagnostics.

This module captures cross-layer evidence needed to diagnose Switch Vision
binding/entity failures without collecting credentials, Home Assistant
attributes, unrelated entities, or raw MQTT discovery payloads.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

from supervisor_runtime import read_supervisor_token
from walk_correlation import build_port_pipeline as build_correlated_port_pipeline

DIAG_DIR = Path("diagnostics")
ENTITY_SNAPSHOT = DIAG_DIR / "home-assistant-entity-resolution.json"
SAFE_MODEL_KEYS = (
    "vendor", "vendor_name", "family", "model", "model_text",
    "detected_model_text", "effective_model_text", "model_override",
    "compatibility_mode", "sys_object_id", "support_status",
)
CARD_KEYS = (
    "type", "title", "faceplate_label", "member", "selected_switch",
    "discovery_selected_switch", "stack_member_number", "sensor_prefix",
    "status_entity_prefix", "status_entity_suffix", "cpu_entity",
    "temperature_entity", "poe_used_entity", "calibration_profile",
)
STATUS_SUFFIX = "_status"
MAX_PORT_ROWS = 512
MAX_CARD_ROWS = 128
MAX_CAPABILITY_FILES = 128
MAX_PROVENANCE_FILES = 512
HA_STATES_URL = os.environ.get(
    "SWITCH_VISION_HA_STATES_URL", "http://supervisor/core/api/states"
)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _write(root: Path, relative: Path, payload: Any) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

def _yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None

def _slug(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace("~", "_")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    return text.strip("_")

def _safe_state(entity_id: str, raw: Any) -> str | None:
    text = str(raw if raw is not None else "").strip()
    if not text:
        return None
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return text
    lowered = text.casefold()
    if entity_id.endswith("_status") and lowered in {
        "up", "down", "on", "off", "true", "false",
        "online", "offline", "available", "unavailable", "unknown",
    }:
        return lowered
    return "<NON_NUMERIC>"

def _ha_states() -> tuple[list[dict[str, Any]], str | None]:
    token = read_supervisor_token()
    if not token:
        return [], "Home Assistant API token unavailable"
    request = Request(
        HA_STATES_URL,
        method="GET",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, list):
            return [], "Home Assistant states response was not a list"
        return [x for x in data if isinstance(x, dict)], None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, HTTPError, URLError) as exc:
        return [], f"Home Assistant state query failed: {type(exc).__name__}"

def _state_map(states: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for item in states:
        entity_id = str(item.get("entity_id") or "").strip()
        if entity_id:
            result[entity_id] = item
    return result

def _suffix_alternatives(entity_id: str, state_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    pattern = re.compile(rf"^{re.escape(entity_id)}_(\d+)$")
    out = []
    for candidate_id, item in state_map.items():
        if not pattern.fullmatch(candidate_id):
            continue
        out.append({
            "entity_id": candidate_id,
            "state": _safe_state(candidate_id, item.get("state")),
            "last_updated": str(item.get("last_updated") or ""),
        })
    return sorted(out, key=lambda row: row["entity_id"])

def _targets(generated: Any) -> list[dict[str, Any]]:
    rows = generated.get("targets") if isinstance(generated, dict) else None
    return [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []

def _sensor_rows(generated: Any) -> list[dict[str, Any]]:
    out = []
    for target_index, target in enumerate(_targets(generated), start=1):
        target_name = str(
            target.get("name") or target.get("target") or target.get("id") or f"target-{target_index}"
        )
        sensors = target.get("sensors")
        if not isinstance(sensors, list):
            continue
        for sensor in sensors:
            if not isinstance(sensor, dict):
                continue
            object_id = _slug(sensor.get("object_id") or sensor.get("name"))
            if not object_id:
                continue
            component = "binary_sensor" if sensor.get("binary_sensor") is True else "sensor"
            out.append({
                "target": target_name,
                "component": component,
                "object_id": object_id,
                "entity_id": f"{component}.{object_id}",
                "oid": str(sensor.get("oid") or sensor.get("object_id_oid") or "").strip(),
                "name": str(sensor.get("name") or "").strip(),
            })
    return out

def _parse_walk_statuses(root: Path) -> dict[str, str]:
    """Return latest observed ifOperStatus by exact numeric OID."""
    statuses: dict[str, str] = {}
    candidates = []
    for path in root.rglob("*.txt"):
        name = path.name.lower()
        if "walk" in name and path.is_file():
            candidates.append(path)
    candidates.sort(key=lambda p: (p.stat().st_mtime if p.exists() else 0, str(p)))
    pattern = re.compile(
        r"^\s*\.?(1\.3\.6\.1\.2\.1\.2\.2\.1\.8\.\d+)\s*=\s*(?:INTEGER:\s*)?([A-Za-z]+(?:\(\d+\))?|\d+)",
        re.I,
    )
    for path in candidates[-64:]:
        try:
            for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
                match = pattern.match(raw)
                if match:
                    statuses[match.group(1)] = match.group(2).strip()
        except OSError:
            continue
    return statuses

def build_port_pipeline(
    generated: Any,
    states: list[dict[str, Any]],
    walk_status: dict[str, str],
    *,
    ha_available: bool = True,
) -> dict[str, Any]:
    state_map = _state_map(states) if ha_available else {}
    rows = []
    for sensor in _sensor_rows(generated):
        if not sensor["object_id"].endswith(STATUS_SUFFIX):
            continue
        exact = state_map.get(sensor["entity_id"]) if ha_available else None
        oid = sensor["oid"].lstrip(".")
        rows.append({
            "target": sensor["target"],
            "object_id": sensor["object_id"],
            "expected_entity_id": sensor["entity_id"],
            "status_oid": oid or None,
            "walk_if_oper_status": walk_status.get(oid) if oid else None,
            "exact_present": (exact is not None) if ha_available else None,
            "ha_state": _safe_state(sensor["entity_id"], exact.get("state")) if exact else None,
            "last_updated": str(exact.get("last_updated") or "") if exact else "",
            "suffix_alternatives": (
                _suffix_alternatives(sensor["entity_id"], state_map)
                if ha_available
                else []
            ),
        })
    rows = rows[:MAX_PORT_ROWS]
    walk_up_rows = [
        row for row in rows
        if row["walk_if_oper_status"]
        and str(row["walk_if_oper_status"]).casefold().startswith("up")
    ]
    anomalies = [
        row for row in walk_up_rows
        if ha_available
        and (
            not row["exact_present"]
            or row["ha_state"] not in {"up", "on", "true", "1"}
        )
    ]
    return {
        "schema_version": 1,
        "generated_at": _now(),
        "scope": "generated Switch Vision port status entities correlated with captured walk ifOperStatus and HA state; no attributes",
        "summary": {
            "status_rows": len(rows),
            "ha_state_status": "available" if ha_available else "unavailable",
            "walk_up_count": len(walk_up_rows),
            "walk_up_but_exact_not_up": len(anomalies) if ha_available else None,
            "suffix_alternative_count": (
                sum(len(x["suffix_alternatives"]) for x in rows)
                if ha_available
                else None
            ),
        },
        "ports": rows,
        "anomalies": anomalies[:128],
    }

def _capability_model(path: Path) -> dict[str, Any] | None:
    data = _json(path)
    if not isinstance(data, dict):
        return None
    device = data.get("device") if isinstance(data.get("device"), dict) else {}
    registry = data.get("registry") if isinstance(data.get("registry"), dict) else {}
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    row = {"source": path.name}
    for key in SAFE_MODEL_KEYS:
        if key in device and device.get(key) not in (None, ""):
            row[key] = device.get(key)
    row["registry_match"] = bool(registry.get("match")) if registry else False
    if registry:
        row["registry_status"] = registry.get("status")
    for key in ("interface_count", "physical_count", "rj45_count", "sfp_count", "sfp_plus_count", "sfp28_count", "uplink_count", "stack_count"):
        if key in summary:
            row[key] = summary.get(key)
    evidence = {}
    for container_name in ("identity", "model_detection", "detection", "classification"):
        container = data.get(container_name)
        if isinstance(container, dict):
            for key in (
                "source", "method", "product_match", "model_source", "sys_object_id",
                "detected_model_text", "effective_model_text", "model_override",
            ):
                if key in container and container.get(key) not in (None, ""):
                    evidence[f"{container_name}.{key}"] = container.get(key)
    if evidence:
        row["evidence"] = evidence
    return row

def build_model_provenance(root: Path) -> dict[str, Any]:
    files = sorted(root.rglob("*-capabilities.json"))[:MAX_CAPABILITY_FILES]
    rows = []
    for path in files:
        row = _capability_model(path)
        if row:
            rows.append(row)
    return {
        "schema_version": 1,
        "generated_at": _now(),
        "scope": "safe model/classification fields from sanitized capability outputs; names, addresses and credentials excluded",
        "device_count": len(rows),
        "devices": rows,
    }

def _walk_mappings(node: Any, path: str = "$") -> list[dict[str, Any]]:
    out = []
    if isinstance(node, dict):
        selected = {key: node.get(key) for key in CARD_KEYS if key in node and node.get(key) not in (None, "")}
        if selected and ("type" in selected or "selected_switch" in selected or "discovery_selected_switch" in selected):
            selected["_path"] = path
            out.append(selected)
        for key, value in node.items():
            out.extend(_walk_mappings(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out.extend(_walk_mappings(value, f"{path}[{index}]"))
    return out

def build_card_bindings(root: Path, generated: Any) -> dict[str, Any]:
    card = _yaml(root / "generated-dashboard-card.yaml")
    cards = _walk_mappings(card)[:MAX_CARD_ROWS] if card is not None else []
    targets = []
    for index, target in enumerate(_targets(generated), start=1):
        sensors = target.get("sensors") if isinstance(target.get("sensors"), list) else []
        status_ids = []
        for sensor in sensors:
            if not isinstance(sensor, dict):
                continue
            object_id = _slug(sensor.get("object_id") or sensor.get("name"))
            if object_id.endswith(STATUS_SUFFIX):
                status_ids.append(object_id)
        targets.append({
            "index": index,
            "target": str(target.get("name") or target.get("target") or target.get("id") or f"target-{index}"),
            "status_entity_count": len(status_ids),
            "status_entity_first": status_ids[:8],
        })
    return {
        "schema_version": 1,
        "generated_at": _now(),
        "scope": "generated card identity/binding keys and generated target/entity contract; credentials and management addresses excluded",
        "cards": cards,
        "targets": targets,
    }

def build_file_provenance(root: Path) -> dict[str, Any]:
    selected = []
    fixed = [
        root / "generated-snmp2mqtt.yaml",
        root / "generated-dashboard-card.yaml",
        root / "discovery-report.txt",
        root / "last-discovery-run.txt",
    ]
    candidates = fixed + sorted(root.rglob("*-capabilities.json")) + [
        p for p in sorted(root.rglob("*.txt")) if "walk" in p.name.lower()
    ]
    seen = set()
    for path in candidates:
        if len(selected) >= MAX_PROVENANCE_FILES or not path.is_file():
            continue
        try:
            relative = str(path.relative_to(root))
        except ValueError:
            continue
        if relative in seen:
            continue
        seen.add(relative)
        try:
            raw = path.read_bytes()
            stat = path.stat()
        except OSError:
            continue
        selected.append({
            "path": relative,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "mtime_ns": stat.st_mtime_ns,
        })
    return {
        "schema_version": 1,
        "generated_at": _now(),
        "scope": "file names, sizes, hashes and mtimes only; no file contents",
        "files": selected,
    }

def capture_mqtt_maintenance(root: Path) -> dict[str, Any]:
    try:
        from mqtt_maintenance_runtime import scan_mqtt_entities
        result = scan_mqtt_entities()
        if not isinstance(result, dict):
            raise RuntimeError("maintenance scan returned invalid data")
        result = {
            key: value for key, value in result.items()
            if key != "plan_token" and not str(key).startswith("_")
        }
        payload = {
            "schema_version": 1,
            "generated_at": _now(),
            "status": "ok",
            "scope": "safe Switch Vision-owned retained MQTT discovery counts/entity IDs only; raw payloads excluded",
            **result,
        }
    except Exception as exc:
        payload = {
            "schema_version": 1,
            "generated_at": _now(),
            "status": "unavailable",
            "reason": f"MQTT maintenance scan failed safely: {type(exc).__name__}",
        }
    _write(root, DIAG_DIR / "mqtt-maintenance-scan.json", payload)
    return payload

DEFAULT_DISCOVERY_PATHS = {
    "input_path": "/share/switch_vision/snmpwalk.txt",
    "snmpwalks_dir": "/share/switch_vision/snmpwalks",
    "report_path": "/share/switch_vision/discovery-report.txt",
    "targets_csv": "/share/switch_vision/discovery-targets.csv",
    "last_run_summary_path": "/share/switch_vision/last-discovery-run.txt",
    "generated_yaml_path": "/share/switch_vision/generated-snmp2mqtt.yaml",
    "generated_card_path": "/share/switch_vision/generated-dashboard-card.yaml",
    "snmp_log_path": "/share/switch_vision/snmpwalk.log",
}
DEFAULT_SNMP_PATHS = {
    "targets_path": "/config/app_configs/switch_vision_snmp2mqtt/targets.yaml",
    "switch_vision_generated_yaml_path": "/share/switch_vision/generated-snmp2mqtt.yaml",
    "imported_targets_path": "/config/app_configs/switch_vision_snmp2mqtt/imported/generated-snmp2mqtt.yaml",
}
DEFAULT_INSTALLER_RELEASE_API = (
    "https://api.github.com/repos/zemerdon/switch-vision-releases/releases/latest"
)

def _configured(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and value.strip().casefold() != "null"
    return True

def _boolish(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        text = value.strip().casefold()
        if text in {"true", "1", "yes", "on", "enabled"}:
            return True
        if text in {"false", "0", "no", "off", "disabled"}:
            return False
    return None

def _intish(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None

def _mode(value: Any, expected: str) -> str:
    if not _configured(value):
        return "missing"
    return "default" if str(value).strip() == expected else "custom"

def _mqtt_host_mode(value: Any) -> str:
    if not _configured(value):
        return "supervisor_default"
    text = str(value).strip().casefold()
    if text in {"localhost", "127.0.0.1", "core-mosquitto"}:
        return "supervisor_default"
    return "custom"

def _enabled_state(value: Any) -> str:
    state = _boolish(value)
    if state is not None:
        return "enabled" if state else "disabled"
    text = str(value or "").strip().casefold()
    if text in {"", "enabled"}:
        return "enabled"
    return "custom"

def _safe_discovery_options(options: Any) -> dict[str, Any]:
    data = options if isinstance(options, dict) else {}
    known = {
        *DEFAULT_DISCOVERY_PATHS,
        "run_snmp_walks", "enable_switch_list", "switches",
        "stack_member_prefixes", "parse_all_walks", "generate_snmp2mqtt",
        "clean_output_before_walk", "snmp_timeout", "snmp_retries",
        "minimum_valid_walk_lines", "backup_retention_enabled",
        "backup_retention_count", "generate_support_my_switch_bundle",
        "support_mask_management_ips", "support_mask_mac_addresses",
        "support_mask_hostnames", "support_mask_vlan_names",
        "support_mask_interface_descriptions", "support_contributor_type",
        "support_contributor_value",
    }
    switches = data.get("switches")
    safe_switches = []
    for index, row in enumerate(switches if isinstance(switches, list) else [], start=1):
        if not isinstance(row, dict):
            safe_switches.append({"index": index, "valid_row": False})
            continue
        safe_switches.append({
            "index": index,
            "valid_row": True,
            "configured": _configured(row.get("switch_name")) or _configured(row.get("switch_host")),
            "switch_name_configured": _configured(row.get("switch_name")),
            "switch_host_configured": _configured(row.get("switch_host")),
            "sensor_prefix_configured": _configured(row.get("sensor_prefix")),
            "snmp_community_configured": _configured(row.get("snmp_community")),
            "enabled": _enabled_state(row.get("enabled", "enabled")),
            "walk_mode": (
                str(row.get("walk_mode")).strip().casefold()
                if str(row.get("walk_mode") or "").strip().casefold() in {"targeted", "full"}
                else "custom"
            ),
            "switch_model": str(row.get("switch_model") or "auto").strip() or "auto",
            "display_name_configured": _configured(row.get("display_name")),
            "card_header_title_configured": _configured(row.get("card_header_title")),
        })
    stack = data.get("stack_member_prefixes")
    safe_stack = []
    for index, row in enumerate(stack if isinstance(stack, list) else [], start=1):
        if not isinstance(row, dict):
            safe_stack.append({"index": index, "valid_row": False})
            continue
        safe_stack.append({
            "index": index,
            "valid_row": True,
            "switch_name_configured": _configured(row.get("switch_name")),
            "member": _intish(row.get("member")),
            "display_name_configured": _configured(row.get("display_name")),
            "sensor_prefix_configured": _configured(row.get("sensor_prefix")),
            "card_header_title_configured": _configured(row.get("card_header_title")),
        })
    return {
        "paths": {key: _mode(data.get(key), expected) for key, expected in DEFAULT_DISCOVERY_PATHS.items()},
        "run_snmp_walks": _boolish(data.get("run_snmp_walks")),
        "enable_switch_list": _boolish(data.get("enable_switch_list")),
        "parse_all_walks": _boolish(data.get("parse_all_walks")),
        "generate_snmp2mqtt": _boolish(data.get("generate_snmp2mqtt")),
        "clean_output_before_walk": _boolish(data.get("clean_output_before_walk")),
        "snmp_timeout": _intish(data.get("snmp_timeout")),
        "snmp_retries": _intish(data.get("snmp_retries")),
        "minimum_valid_walk_lines": _intish(data.get("minimum_valid_walk_lines")),
        "backup_retention_enabled": _boolish(data.get("backup_retention_enabled")),
        "backup_retention_count": _intish(data.get("backup_retention_count")),
        "generate_support_my_switch_bundle": _boolish(data.get("generate_support_my_switch_bundle")),
        "privacy": {
            "mask_management_ips": _boolish(data.get("support_mask_management_ips")),
            "mask_mac_addresses": _boolish(data.get("support_mask_mac_addresses")),
            "mask_hostnames": _boolish(data.get("support_mask_hostnames")),
            "mask_vlan_names": _boolish(data.get("support_mask_vlan_names")),
            "mask_interface_descriptions": _boolish(data.get("support_mask_interface_descriptions")),
        },
        "recognition": {
            "type": str(data.get("support_contributor_type") or "anonymous").strip(),
            "value_configured": _configured(data.get("support_contributor_value")),
        },
        "switches": safe_switches,
        "stack_members": safe_stack,
        "unknown_option_keys": sorted(str(key) for key in data if key not in known),
    }

def _safe_snmp2mqtt_options(options: Any) -> dict[str, Any]:
    data = options if isinstance(options, dict) else {}
    mqtt = data.get("mqtt") if isinstance(data.get("mqtt"), dict) else {}
    homeassistant = data.get("homeassistant") if isinstance(data.get("homeassistant"), dict) else {}
    known = {
        "mqtt", "targets_path", "use_switch_vision_generated_yaml",
        "switch_vision_generated_yaml_path", "imported_targets_path",
        "backup_existing_config", "homeassistant", "log",
    }
    known_mqtt = {
        "host", "port", "username", "password", "client_id", "keepalive",
        "clean", "retain", "qos", "base_topic", "host_name_as_target",
        "ca", "cert", "key", "reject_unauthorized",
    }
    log_value = str(data.get("log") or "").strip().casefold()
    return {
        "mqtt": {
            "host_mode": _mqtt_host_mode(mqtt.get("host")),
            "port": _intish(mqtt.get("port")),
            "username_configured": _configured(mqtt.get("username")),
            "password_configured": _configured(mqtt.get("password")),
            "client_id_mode": _mode(mqtt.get("client_id"), "snmp2mqtt"),
            "keepalive": _intish(mqtt.get("keepalive")),
            "clean": _boolish(mqtt.get("clean")),
            "retain": _boolish(mqtt.get("retain")),
            "qos": _intish(mqtt.get("qos")),
            "base_topic_mode": _mode(mqtt.get("base_topic"), "snmp2mqtt"),
            "host_name_as_target": _boolish(mqtt.get("host_name_as_target")),
            "ca_configured": _configured(mqtt.get("ca")),
            "cert_configured": _configured(mqtt.get("cert")),
            "key_configured": _configured(mqtt.get("key")),
            "reject_unauthorized": _boolish(mqtt.get("reject_unauthorized")),
            "unknown_option_keys": sorted(str(key) for key in mqtt if key not in known_mqtt),
        },
        "targets_path_mode": _mode(data.get("targets_path"), DEFAULT_SNMP_PATHS["targets_path"]),
        "generated_yaml_import": _boolish(data.get("use_switch_vision_generated_yaml")),
        "generated_yaml_path_mode": _mode(
            data.get("switch_vision_generated_yaml_path"),
            DEFAULT_SNMP_PATHS["switch_vision_generated_yaml_path"],
        ),
        "imported_targets_path_mode": _mode(
            data.get("imported_targets_path"),
            DEFAULT_SNMP_PATHS["imported_targets_path"],
        ),
        "backup_existing_config": _boolish(data.get("backup_existing_config")),
        "homeassistant": {
            "discovery_requested": _boolish(homeassistant.get("discovery")),
            "prefix_mode": _mode(homeassistant.get("prefix"), "homeassistant"),
        },
        "log": log_value if log_value in {"debug", "info", "warning", "error"} else None,
        "unknown_option_keys": sorted(str(key) for key in data if key not in known),
    }

def _safe_unifi2mqtt_options(options: Any) -> dict[str, Any]:
    data = options if isinstance(options, dict) else {}
    known = {
        "controller_url", "site_id", "api_key", "verify_ssl",
        "allow_insecure_http", "poll_interval", "mqtt_host", "mqtt_port",
        "mqtt_username", "mqtt_password", "mqtt_tls", "mqtt_verify_ssl",
        "mqtt_ca", "mqtt_topic_prefix", "mqtt_discovery_prefix",
    }
    controller = str(data.get("controller_url") or "").strip().casefold()
    controller_mode = (
        "missing" if not controller
        else "https" if controller.startswith("https://")
        else "http" if controller.startswith("http://")
        else "custom"
    )
    site = str(data.get("site_id") or "").strip().casefold()
    site_mode = "auto" if site in {"", "auto", "default"} else "custom"
    return {
        "controller": {
            "configured": _configured(data.get("controller_url")),
            "transport": controller_mode,
            "api_key_configured": _configured(data.get("api_key")),
            "site_mode": site_mode,
            "verify_ssl": _boolish(data.get("verify_ssl")),
            "allow_insecure_http": _boolish(data.get("allow_insecure_http")),
            "poll_interval": _intish(data.get("poll_interval")),
        },
        "mqtt": {
            "host_mode": _mqtt_host_mode(data.get("mqtt_host")),
            "port": _intish(data.get("mqtt_port")),
            "username_configured": _configured(data.get("mqtt_username")),
            "password_configured": _configured(data.get("mqtt_password")),
            "tls": _boolish(data.get("mqtt_tls")),
            "verify_ssl": _boolish(data.get("mqtt_verify_ssl")),
            "ca_configured": _configured(data.get("mqtt_ca")),
            "topic_prefix_mode": _mode(data.get("mqtt_topic_prefix"), "switch_vision/unifi"),
            "discovery_prefix_mode": _mode(data.get("mqtt_discovery_prefix"), "homeassistant"),
        },
        "unknown_option_keys": sorted(str(key) for key in data if key not in known),
    }

def _safe_installer_options(options: Any) -> dict[str, Any]:
    data = options if isinstance(options, dict) else {}
    known = {
        "release_api_url", "allow_custom_release_source", "release_asset_pattern",
        "preserve_custom_assets", "create_backup", "allow_prerelease",
        "backup_retention",
    }
    return {
        "release_source_mode": _mode(data.get("release_api_url"), DEFAULT_INSTALLER_RELEASE_API),
        "allow_custom_release_source": _boolish(data.get("allow_custom_release_source")),
        "release_asset_pattern_mode": _mode(data.get("release_asset_pattern"), "switch-vision-*.zip"),
        "preserve_custom_assets": _boolish(data.get("preserve_custom_assets")),
        "create_backup": _boolish(data.get("create_backup")),
        "allow_prerelease": _boolish(data.get("allow_prerelease")),
        "backup_retention": _intish(data.get("backup_retention")),
        "unknown_option_keys": sorted(str(key) for key in data if key not in known),
    }

def _safe_snmp2mqtt_runtime(root: Path) -> dict[str, Any]:
    raw = _json(root / DIAG_DIR / "snmp2mqtt-runtime.json")
    if not isinstance(raw, dict):
        return {"status": "unavailable"}
    result: dict[str, Any] = {"status": "ok"}
    source = str(raw.get("configuration_source") or "").strip()
    if source in {"manual_targets", "switch_vision_generated_yaml"}:
        result["configuration_source"] = source
    version = str(raw.get("app_version") or "").strip()
    if re.fullmatch(r"\d+\.\d+\.\d+", version):
        result["app_version"] = version
    result["generated_yaml_import_requested"] = _boolish(raw.get("generated_yaml_import_requested"))
    result["generated_yaml_import_effective"] = _boolish(raw.get("generated_yaml_import_effective"))
    result["generated_target_count"] = _intish(raw.get("generated_target_count"))
    result["generated_sensor_count"] = _intish(raw.get("generated_sensor_count"))
    digest = str(raw.get("generated_yaml_sha256") or "").strip().casefold()
    result["generated_yaml_sha256"] = digest if re.fullmatch(r"[0-9a-f]{64}", digest) else None
    result["homeassistant_discovery_requested"] = _boolish(raw.get("homeassistant_discovery_requested"))
    result["homeassistant_discovery_effective"] = _boolish(raw.get("homeassistant_discovery_effective"))
    requested_mode = str(raw.get("homeassistant_prefix_requested_mode") or "").strip()
    if requested_mode in {"homeassistant", "custom"}:
        result["homeassistant_prefix_requested_mode"] = requested_mode
    result["homeassistant_prefix_effective"] = (
        "homeassistant"
        if str(raw.get("homeassistant_prefix_effective") or "").strip() == "homeassistant"
        else "custom"
    )
    return result

def _addon_kind(slug: Any, name: Any) -> str | None:
    text = f"{slug or ''} {name or ''}".casefold().replace("-", "_")
    if "switch_vision_snmp2mqtt" in text or "switch vision snmp2mqtt" in text:
        return "snmp2mqtt"
    if "switch_vision_unifi2mqtt" in text or "switch vision unifi2mqtt" in text:
        return "unifi2mqtt"
    if "switch_vision_discovery" in text or "switch vision discovery" in text:
        return "discovery"
    if "switch_vision_installer" in text or "switch vision installer" in text:
        return "installer"
    return None

def _configuration_from_documents(root: Path, documents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    safe = {
        "discovery": _safe_discovery_options(documents.get("discovery", {}).get("options")) if "discovery" in documents else None,
        "snmp2mqtt": _safe_snmp2mqtt_options(documents.get("snmp2mqtt", {}).get("options")) if "snmp2mqtt" in documents else None,
        "unifi2mqtt": _safe_unifi2mqtt_options(documents.get("unifi2mqtt", {}).get("options")) if "unifi2mqtt" in documents else None,
        "installer": _safe_installer_options(documents.get("installer", {}).get("options")) if "installer" in documents else None,
    }
    for kind, document in documents.items():
        if kind not in safe or safe[kind] is None:
            continue
        safe[kind] = {
            "version": str(document.get("version") or "").strip() or None,
            "state": str(document.get("state") or "").strip() or None,
            "options": safe[kind],
        }
    return {
        "schema_version": 1,
        "generated_at": _now(),
        "scope": (
            "privacy-safe Switch Vision operational configuration; credentials, "
            "management addresses, community strings, API keys, private names and "
            "raw custom paths/topics are excluded"
        ),
        "status": "ok",
        "components": safe,
        "effective_snmp2mqtt": _safe_snmp2mqtt_runtime(root),
        "privacy": {
            "credential_values_included": False,
            "management_addresses_included": False,
            "snmp_communities_included": False,
            "api_keys_included": False,
            "private_switch_names_included": False,
            "raw_custom_paths_or_topics_included": False,
        },
    }

def build_configuration_snapshot(root: Path) -> dict[str, Any]:
    token = read_supervisor_token()
    if not token:
        payload = _configuration_from_documents(root, {})
        payload["status"] = "partial"
        payload["reason"] = "Supervisor token unavailable"
        return payload

    def get(path: str) -> Any:
        req = Request(
            f"http://supervisor{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        with urlopen(req, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))

    documents: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    try:
        addons_doc = get("/addons")
        data = addons_doc.get("data") if isinstance(addons_doc, dict) and isinstance(addons_doc.get("data"), dict) else addons_doc
        addons = data.get("addons") if isinstance(data, dict) else []
        for addon in addons if isinstance(addons, list) else []:
            if not isinstance(addon, dict):
                continue
            kind = _addon_kind(addon.get("slug"), addon.get("name"))
            if not kind or kind in documents:
                continue
            slug = str(addon.get("slug") or "").strip()
            if not slug:
                continue
            try:
                info_doc = get(f"/addons/{slug}/info")
                info = info_doc.get("data") if isinstance(info_doc, dict) and isinstance(info_doc.get("data"), dict) else info_doc
                if not isinstance(info, dict):
                    raise ValueError("add-on info was not an object")
                documents[kind] = {
                    "version": info.get("version") or addon.get("version"),
                    "state": info.get("state") or addon.get("state"),
                    "options": info.get("options") if isinstance(info.get("options"), dict) else {},
                }
            except Exception as exc:
                warnings.append(f"{kind} option query failed: {type(exc).__name__}")
    except Exception as exc:
        payload = _configuration_from_documents(root, {})
        payload["status"] = "partial"
        payload["reason"] = f"Supervisor add-on query failed: {type(exc).__name__}"
        return payload

    payload = _configuration_from_documents(root, documents)
    if warnings:
        payload["status"] = "partial"
        payload["warnings"] = warnings
    return payload

def build_runtime_versions() -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "generated_at": _now(),
        "discovery_version": os.environ.get("SWITCH_VISION_DISCOVERY_VERSION", "unknown"),
        "home_assistant": {},
        "switch_vision_addons": [],
    }
    token = read_supervisor_token()
    if not token:
        payload["status"] = "partial"
        payload["reason"] = "Supervisor token unavailable"
        return payload
    def get(path: str) -> Any:
        req = Request(
            f"http://supervisor{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        with urlopen(req, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    try:
        core = get("/core/info")
        data = core.get("data") if isinstance(core, dict) and isinstance(core.get("data"), dict) else core
        if isinstance(data, dict):
            for key in ("version", "version_latest", "arch", "machine"):
                if key in data:
                    payload["home_assistant"][key] = data.get(key)
        addons_doc = get("/addons")
        data = addons_doc.get("data") if isinstance(addons_doc, dict) and isinstance(addons_doc.get("data"), dict) else addons_doc
        addons = data.get("addons") if isinstance(data, dict) else []
        for addon in addons if isinstance(addons, list) else []:
            if not isinstance(addon, dict):
                continue
            haystack = f"{addon.get('slug','')} {addon.get('name','')}".casefold()
            if "switch vision" not in haystack and "switch_vision" not in haystack and "snmp2mqtt" not in haystack and "unifi2mqtt" not in haystack:
                continue
            payload["switch_vision_addons"].append({
                key: addon.get(key) for key in ("slug", "name", "version", "version_latest", "state")
                if addon.get(key) not in (None, "")
            })
        payload["status"] = "ok"
    except Exception as exc:
        payload["status"] = "partial"
        payload["reason"] = f"Supervisor version query failed: {type(exc).__name__}"
    return payload

def build_summary(
    entity_snapshot: Any,
    port_pipeline: dict[str, Any],
    model_provenance: dict[str, Any],
    card_bindings: dict[str, Any],
    mqtt_scan: dict[str, Any],
) -> dict[str, Any]:
    entity_summary = entity_snapshot.get("summary", {}) if isinstance(entity_snapshot, dict) else {}
    return {
        "schema_version": 1,
        "generated_at": _now(),
        "purpose": "Cross-layer Support My Switch diagnostic summary",
        "signals": {
            "expected_entity_count": entity_summary.get("expected_count"),
            "missing_exact_entity_count": entity_summary.get("missing_exact_count"),
            "suffix_alternative_count": entity_summary.get("suffix_alternative_count"),
            "port_status_rows": port_pipeline.get("summary", {}).get("status_rows"),
            "ha_state_status": port_pipeline.get("summary", {}).get("ha_state_status"),
            "walk_state_status": port_pipeline.get("summary", {}).get("walk_state_status"),
            "walk_up_count": port_pipeline.get("summary", {}).get("walk_up_count"),
            "fresh_walk_up_count": port_pipeline.get("summary", {}).get("fresh_walk_up_count"),
            "stale_walk_up_count": port_pipeline.get("summary", {}).get("stale_walk_up_count"),
            "walk_up_but_exact_not_up": port_pipeline.get("summary", {}).get("walk_up_but_exact_not_up"),
            "mqtt_current_missing_retained_count": (
                mqtt_scan.get("current_missing_retained_count")
                if mqtt_scan.get("status") == "ok"
                else None
            ),
            "mqtt_stale_count": mqtt_scan.get("stale_count") if mqtt_scan.get("status") == "ok" else None,
            "model_device_count": model_provenance.get("device_count"),
            "generated_card_binding_count": len(card_bindings.get("cards", [])),
            "generated_target_count": len(card_bindings.get("targets", [])),
        },
        "privacy": {
            "home_assistant_attributes_included": False,
            "unrelated_home_assistant_entities_included": False,
            "raw_mqtt_discovery_payloads_included": False,
            "credentials_included": False,
        },
    }

def capture_support_diagnostics(root: Path) -> None:
    generated = _yaml(root / "generated-snmp2mqtt.yaml") or {}
    states, ha_error = _ha_states()
    entity_snapshot = _json(root / ENTITY_SNAPSHOT) or {}
    card_bindings = build_card_bindings(root, generated)
    port_pipeline = build_correlated_port_pipeline(
        root,
        generated,
        states,
        card_bindings,
        ha_available=ha_error is None,
    )
    model_provenance = build_model_provenance(root)
    file_provenance = build_file_provenance(root)
    mqtt_scan = capture_mqtt_maintenance(root)
    runtime_versions = build_runtime_versions()
    configuration_snapshot = build_configuration_snapshot(root)
    if ha_error:
        runtime_versions.setdefault("warnings", []).append(ha_error)

    _write(root, DIAG_DIR / "port-pipeline.json", port_pipeline)
    _write(root, DIAG_DIR / "model-provenance.json", model_provenance)
    _write(root, DIAG_DIR / "card-entity-bindings.json", card_bindings)
    _write(root, DIAG_DIR / "generated-file-provenance.json", file_provenance)
    _write(root, DIAG_DIR / "runtime-versions.json", runtime_versions)
    _write(root, DIAG_DIR / "configuration-snapshot.json", configuration_snapshot)
    _write(
        root,
        DIAG_DIR / "diagnostic-summary.json",
        build_summary(entity_snapshot, port_pipeline, model_provenance, card_bindings, mqtt_scan),
    )
