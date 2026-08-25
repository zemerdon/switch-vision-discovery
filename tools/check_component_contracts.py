#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CORE_REGISTRY_URL = (
    "https://raw.githubusercontent.com/zemerdon/"
    "switch-vision-releases/main/src/devices/supported_devices.json"
)
DEFAULT_CORE_SETTINGS_URL = (
    "https://raw.githubusercontent.com/zemerdon/"
    "switch-vision-releases/main/src/custom_components/switch_vision/__init__.py"
)
DEFAULT_SNMP_ADDON_CONFIG_URL = (
    "https://raw.githubusercontent.com/zemerdon/"
    "switch-vision-snmp2mqtt-addon/main/switch-vision-snmp2mqtt/config.yaml"
)

# Shared exact-model visual defaults are a hard Core/Discovery contract.
# Any intentional divergence must be listed here with a non-empty reason.
VISUAL_CONTRACT_EXCEPTIONS: dict[str, str] = {}


def classify_visual_contract_drift(model: str) -> tuple[str, str | None]:
    """Return strict/error by default; only documented exceptions may warn."""
    if model not in VISUAL_CONTRACT_EXCEPTIONS:
        return "error", None
    reason = str(VISUAL_CONTRACT_EXCEPTIONS.get(model) or "").strip()
    if not reason:
        return "invalid", None
    return "warning", reason


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Switch-Vision-Discovery-Contract-Check/1"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def by_model(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    devices = payload.get("devices")
    if not isinstance(devices, list):
        raise RuntimeError("registry devices field is not a list")
    result: dict[str, dict[str, Any]] = {}
    for item in devices:
        if not isinstance(item, dict):
            continue
        model = str(item.get("model") or "").strip()
        if model:
            result[model] = item
    return result


CORE_HUB_SETTINGS_GROUPS: dict[str, tuple[tuple[str, str], ...]] = {
    "sidebar": (
        ("CONF_SHOW_ALL_SWITCH_VISION_SIDEBAR_ITEMS", "show_all_switch_vision_sidebar_items"),
        ("CONF_SHOW_PANEL_IN_SIDEBAR", "show_panel_in_sidebar"),
        ("CONF_SHOW_LOVELACE_DASHBOARD_IN_SIDEBAR", "show_lovelace_dashboard_in_sidebar"),
        ("CONF_SHOW_HUB_IN_SIDEBAR", "show_hub_in_sidebar"),
        ("CONF_SHOW_INSTALLER_IN_SIDEBAR", "show_installer_in_sidebar"),
    ),
    "native_header": (
        ("CONF_SHOW_DASHBOARD_HEADER", "show_dashboard_header"),
        ("CONF_NATIVE_HEADER_SHOW_SUMMARY", "native_header_show_summary"),
        ("CONF_NATIVE_HEADER_SHOW_REFRESH", "native_header_show_refresh"),
        ("CONF_NATIVE_HEADER_SHOW_VERSION", "native_header_show_version"),
        ("CONF_NATIVE_HEADER_SHORTCUT_SWITCH_VISION_SETTINGS", "native_header_shortcut_switch_vision_settings"),
        ("CONF_NATIVE_HEADER_SHORTCUT_HUB", "native_header_shortcut_hub"),
        ("CONF_NATIVE_HEADER_SHORTCUT_MAINTENANCE", "native_header_shortcut_maintenance"),
        ("CONF_NATIVE_HEADER_SHORTCUT_DISCOVERY_SETTINGS", "native_header_shortcut_discovery_settings"),
        ("CONF_NATIVE_HEADER_SHORTCUT_INSTALLER", "native_header_shortcut_installer"),
        ("CONF_NATIVE_HEADER_SHORTCUT_INSTALLER_SETTINGS", "native_header_shortcut_installer_settings"),
        ("CONF_NATIVE_HEADER_SHORTCUT_SNMP2MQTT_SETTINGS", "native_header_shortcut_snmp2mqtt_settings"),
        ("CONF_NATIVE_HEADER_SHORTCUT_UNIFI2MQTT_SETTINGS", "native_header_shortcut_unifi2mqtt_settings"),
        ("CONF_NATIVE_HEADER_SHORTCUT_ORDER", "native_header_shortcut_order"),
    ),
    "dashboard": (
        ("CONF_SHOW_CALIBRATION_BUTTONS", "show_calibration_buttons"),
        ("CONF_SHOW_CARD_HEADERS", "show_card_headers"),
    ),
    "activity_leds": (
        ("CONF_ACTIVITY_LED_SENSITIVITY_PRESET", "activity_led_sensitivity_preset"),
        ("CONF_ACTIVITY_SLOW_MAX_UTILIZATION_PCT", "activity_slow_max_utilization_pct"),
        ("CONF_ACTIVITY_MEDIUM_MAX_UTILIZATION_PCT", "activity_medium_max_utilization_pct"),
        ("CONF_ACTIVITY_SLOW_PERIOD_MS", "activity_slow_period_ms"),
        ("CONF_ACTIVITY_MEDIUM_PERIOD_MS", "activity_medium_period_ms"),
        ("CONF_ACTIVITY_FAST_PERIOD_MS", "activity_fast_period_ms"),
        ("CONF_ACTIVITY_HOLD_SECONDS", "activity_hold_seconds"),
        ("CONF_ACTIVITY_HYSTERESIS_PCT", "activity_hysteresis_pct"),
    ),
    "discovery": (
        ("CONF_DISCOVERY_UI_DENSITY", "discovery_ui_density"),
        ("CONF_DISCOVERY_TEXT_SIZE", "discovery_text_size"),
        ("CONF_DISCOVERY_CONTENT_WIDTH", "discovery_content_width"),
        ("CONF_SHOW_UNIFI_INTEGRATION", "show_unifi_integration"),
    ),
    "installer": (
        ("CONF_INSTALLER_UI_DENSITY", "installer_ui_density"),
        ("CONF_INSTALLER_TEXT_SIZE", "installer_text_size"),
        ("CONF_INSTALLER_CONTENT_WIDTH", "installer_content_width"),
    ),
}


def check_core_hub_settings_contract(source: str) -> list[str]:
    """Fail closed when Core's public Hub settings API drifts from this Hub."""
    errors: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"Core Hub settings source could not be parsed: {exc}"]

    expected_constants = {
        name: literal
        for entries in CORE_HUB_SETTINGS_GROUPS.values()
        for name, literal in entries
    }
    assignments: dict[str, str] = {}
    group_node: ast.AST | None = None
    functions: dict[str, ast.AsyncFunctionDef | ast.FunctionDef] = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            functions[node.name] = node
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id == "CORE_SETTINGS_GROUP_KEYS":
            group_node = node.value
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            assignments[target.id] = node.value.value

    for name, literal in sorted(expected_constants.items()):
        actual = assignments.get(name)
        if actual != literal:
            errors.append(
                f"Core Hub settings constant drift: {name} expected {literal!r}, got {actual!r}"
            )

    actual_groups: dict[str, tuple[str, ...]] = {}
    if isinstance(group_node, ast.Dict):
        for key_node, value_node in zip(group_node.keys, group_node.values):
            if not (
                isinstance(key_node, ast.Constant)
                and isinstance(key_node.value, str)
                and isinstance(value_node, (ast.Tuple, ast.List))
            ):
                continue
            members: list[str] = []
            for item in value_node.elts:
                if isinstance(item, ast.Name):
                    members.append(item.id)
                else:
                    members.append("<non-name>")
            actual_groups[key_node.value] = tuple(members)
    else:
        errors.append("Core no longer exposes CORE_SETTINGS_GROUP_KEYS as a static mapping")

    expected_groups = {
        group: tuple(name for name, _literal in entries)
        for group, entries in CORE_HUB_SETTINGS_GROUPS.items()
    }
    if actual_groups != expected_groups:
        errors.append(
            "Core Hub settings group/key contract drift: "
            f"expected {expected_groups!r}, got {actual_groups!r}"
        )

    for function_name in ("websocket_get_core_settings", "websocket_set_core_settings"):
        function = functions.get(function_name)
        if function is None:
            errors.append(f"Core Hub settings function is missing: {function_name}")
            continue
        admin_guard = any(
            isinstance(decorator, ast.Attribute) and decorator.attr == "require_admin"
            for decorator in function.decorator_list
        )
        if not admin_guard:
            errors.append(f"Core Hub settings function lost admin guard: {function_name}")

    required_source_markers = (
        'vol.Required("type"): "switch_vision/get_settings"',
        'vol.Required("type"): "switch_vision/set_settings"',
        'websocket_api.async_register_command(hass, websocket_get_core_settings)',
        'websocket_api.async_register_command(hass, websocket_set_core_settings)',
        'hass.config_entries.async_update_entry(entry, options=options)',
        '_normalise_core_settings_update(',
        '_core_settings_payload(',
    )
    for marker in required_source_markers:
        if marker not in source:
            errors.append(f"Core Hub settings contract marker is missing: {marker}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Switch Vision Discovery cross-component contracts."
    )
    parser.add_argument("--core-registry-url", default=DEFAULT_CORE_REGISTRY_URL)
    parser.add_argument("--core-settings-url", default=DEFAULT_CORE_SETTINGS_URL)
    parser.add_argument("--snmp-addon-config-url", default=DEFAULT_SNMP_ADDON_CONFIG_URL)
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    discovery_config_path = Path("switch_vision_discovery/config.yaml")
    discovery_runtime_path = Path("runtime_src/discovery_job.sh")
    discovery_registry_path = Path(
        "runtime_src/opt/switch-vision/devices/supported_devices.json"
    )
    discovery_profiles_path = Path("runtime_src/profiles/switch-vision-profiles.yaml")

    discovery_config_text = discovery_config_path.read_text(encoding="utf-8")
    discovery_config = yaml.safe_load(discovery_config_text)
    runtime_text = discovery_runtime_path.read_text(encoding="utf-8")

    app_version = str((discovery_config or {}).get("version") or "").strip()
    match = re.search(
        r'(?m)^SWITCH_VISION_DISCOVERY_VERSION="([^"]+)"',
        runtime_text,
    )
    runtime_version = match.group(1).strip() if match else ""
    if not app_version or not runtime_version or app_version != runtime_version:
        errors.append(
            f"Discovery app/runtime version mismatch: app={app_version!r} "
            f"runtime={runtime_version!r}"
        )

    discovery_registry = json.loads(discovery_registry_path.read_text(encoding="utf-8"))
    profile_payload = yaml.safe_load(discovery_profiles_path.read_text(encoding="utf-8")) or {}
    discovery_profiles = profile_payload.get("profiles") or {}
    if not isinstance(discovery_profiles, dict):
        errors.append("Discovery profile file does not contain a profiles mapping")
        discovery_profiles = {}
    for item in discovery_registry.get("devices", []):
        if not isinstance(item, dict):
            continue
        model = str(item.get("model") or "").strip() or "<unknown>"
        mapping_profile = str(item.get("mapping_profile") or "").strip()
        if mapping_profile and mapping_profile not in discovery_profiles:
            errors.append(f"{model}: mapping_profile {mapping_profile!r} is not defined in shipped profiles")
    core_registry = json.loads(fetch_text(args.core_registry_url))
    try:
        core_settings_source = fetch_text(args.core_settings_url)
    except Exception as exc:
        errors.append(f"Could not fetch Core Hub settings contract: {exc}")
    else:
        errors.extend(check_core_hub_settings_contract(core_settings_source))
    discovery_models = by_model(discovery_registry)
    core_models = by_model(core_registry)

    missing_in_discovery = sorted(core_models.keys() - discovery_models.keys())
    if missing_in_discovery:
        errors.append(
            "Core exact models missing from Discovery: " + ", ".join(missing_in_discovery)
        )

    shared_models = core_models.keys() & discovery_models.keys()
    for model, raw_reason in sorted(VISUAL_CONTRACT_EXCEPTIONS.items()):
        reason = str(raw_reason or "").strip()
        if model not in shared_models:
            errors.append(
                f"Visual contract exception {model!r} is stale or not a shared exact model"
            )
        if not reason:
            errors.append(
                f"Visual contract exception {model!r} must include a non-empty reason"
            )

    hardware_fields = (
        "vendor",
        "mapping_profile",
        "ports",
        "stack_support",
        "discovery_support",
        "dashboard_support",
    )
    support_fields = ("status", "evidence", "validation")
    visual_fields = ("calibration_profile", "default_faceplate")

    for model in sorted(core_models.keys() & discovery_models.keys()):
        core = core_models[model]
        discovery = discovery_models[model]

        changed_hardware = [
            field
            for field in hardware_fields
            if core.get(field) != discovery.get(field)
        ]
        if changed_hardware:
            errors.append(
                f"{model}: hardware contract drift in " + ", ".join(changed_hardware)
            )

        changed_support = [
            field
            for field in support_fields
            if core.get(field) != discovery.get(field)
        ]
        if changed_support:
            errors.append(
                f"{model}: support-status contract drift in " + ", ".join(changed_support)
            )

        changed_visuals = [
            field
            for field in visual_fields
            if core.get(field) != discovery.get(field)
        ]
        core_visuals = core.get("visuals") if isinstance(core.get("visuals"), dict) else {}
        discovery_visuals = (
            discovery.get("visuals")
            if isinstance(discovery.get("visuals"), dict)
            else {}
        )
        if core_visuals.get("recommended_faceplate") != discovery_visuals.get(
            "recommended_faceplate"
        ):
            changed_visuals.append("visuals.recommended_faceplate")
        if core_visuals.get("calibration_profile") != discovery_visuals.get(
            "calibration_profile"
        ):
            changed_visuals.append("visuals.calibration_profile")

        if changed_visuals:
            policy, reason = classify_visual_contract_drift(model)
            if policy == "warning":
                warnings.append(
                    f"{model}: explicitly allowed shared visual contract drift in "
                    + ", ".join(changed_visuals)
                    + f"; reason: {reason}"
                )
            else:
                errors.append(
                    f"{model}: shared visual contract drift in "
                    + ", ".join(changed_visuals)
                )

    expected_huawei_profile = "stock_24rj45_4sfp"
    expected_huawei_faceplate = "faceplates/24rj45-4sfp.png"
    for model in ("S5720-12TP-LI-AC", "S5735-L8P4X-A1"):
        discovery = discovery_models.get(model) or {}
        visuals = discovery.get("visuals") if isinstance(discovery.get("visuals"), dict) else {}
        if discovery.get("calibration_profile") != expected_huawei_profile:
            errors.append(f"{model}: expected calibration_profile={expected_huawei_profile}")
        if discovery.get("default_faceplate") != expected_huawei_faceplate:
            errors.append(f"{model}: expected default_faceplate={expected_huawei_faceplate}")
        if visuals.get("calibration_profile") != expected_huawei_profile:
            errors.append(f"{model}: expected visuals.calibration_profile={expected_huawei_profile}")
        if visuals.get("recommended_faceplate") != expected_huawei_faceplate:
            errors.append(f"{model}: expected visuals.recommended_faceplate={expected_huawei_faceplate}")

    discovery_yaml_path = str(
        ((discovery_config or {}).get("options") or {}).get("generated_yaml_path") or ""
    ).strip()
    snmp_config = yaml.safe_load(fetch_text(args.snmp_addon_config_url)) or {}
    snmp_yaml_path = str(
        (snmp_config.get("options") or {}).get("switch_vision_generated_yaml_path")
        or ""
    ).strip()
    if not discovery_yaml_path or discovery_yaml_path != snmp_yaml_path:
        errors.append(
            "Discovery/SNMP2MQTT generated YAML path mismatch: "
            f"Discovery={discovery_yaml_path!r} SNMP2MQTT={snmp_yaml_path!r}"
        )

    print(
        f"Core exact models: {len(core_models)}; "
        f"Discovery exact models: {len(discovery_models)}"
    )
    extra = sorted(discovery_models.keys() - core_models.keys())
    if extra:
        print(
            "INFO: Discovery intentionally carries additional exact models: "
            + ", ".join(extra)
        )

    for warning in warnings:
        print(f"WARN: {warning}")

    if errors:
        print("Discovery cross-component contracts: FAIL")
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(
        "Discovery cross-component contracts: PASS "
        f"(version={app_version}; Core subset present; hardware mappings aligned; "
        "all shared exact-model visuals aligned or explicitly excepted; "
        "Core Hub settings schema aligned; SNMP2MQTT YAML path aligned)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
