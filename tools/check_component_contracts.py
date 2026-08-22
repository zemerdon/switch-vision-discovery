#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Switch Vision Discovery cross-component contracts."
    )
    parser.add_argument("--core-registry-url", default=DEFAULT_CORE_REGISTRY_URL)
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
        "SNMP2MQTT YAML path aligned)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
