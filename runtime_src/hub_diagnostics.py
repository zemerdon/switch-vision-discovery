#!/usr/bin/env python3
"""Hub Devices diagnostics assembly and identity reconciliation.

This module owns the browser-safe diagnostics projection while keeping all
platform state, paths and surrounding Hub services explicitly injected. It
never imports support_web.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from pathlib import Path
import re
import time
from typing import Any, Callable


@dataclass(frozen=True)
class HubDiagnosticsRuntime:
    read_json: Callable[[Path], Any]
    registry_lookup: Callable[[dict[str, Any], str], dict[str, Any] | None]
    switch_name_identity: Callable[[str], str]
    self_addon_options: Callable[[], dict[str, Any]]
    load_options: Callable[[Path], dict[str, Any]]
    unifi2mqtt_diagnostics_status: Callable[[], dict[str, Any]]
    file_info: Callable[[Path], dict[str, Any]]
    snmp2mqtt_applicability: Callable[[], dict[str, Any]]
    discovery_state_snapshot: Callable[[], dict[str, Any]]
    default_share_dir: Path
    default_registry_file: Path
    default_unifi_snapshot: Path
    default_support_script: Path
    default_contributions_dir: Path


def normalized_device_mac(value: Any) -> str:
    compact = re.sub(r"[^0-9a-f]", "", str(value or "").strip().casefold())
    if len(compact) != 12 or not re.fullmatch(r"[0-9a-f]{12}", compact):
        return ""
    return ":".join(compact[index:index + 2] for index in range(0, 12, 2))


def normalized_device_ip(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return ipaddress.ip_address(text).compressed
    except ValueError:
        return ""


def unique_detected_snmp_identity_match(
    devices: list[dict[str, Any]], *, mac_address: Any = "", ip_address: Any = ""
) -> tuple[dict[str, Any] | None, str]:
    mac = normalized_device_mac(mac_address)
    if mac:
        matches = [
            item for item in devices
            if item.get("data_source", "SNMP") != "UniFi API"
            and normalized_device_mac(item.get("_identity_mac")) == mac
        ]
        if len(matches) == 1:
            return matches[0], "hardware_mac"
        if len(matches) > 1:
            return None, ""

    ip = normalized_device_ip(ip_address)
    if ip:
        matches = [
            item for item in devices
            if item.get("data_source", "SNMP") != "UniFi API"
            and normalized_device_ip(item.get("_identity_ip")) == ip
        ]
        if len(matches) == 1:
            return matches[0], "management_ip"

    return None, ""


def walk_management_target(path: Path) -> str:
    """Read the management target recorded in a Switch Vision walk header."""
    if not path.is_file():
        return ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for _ in range(32):
                line = handle.readline()
                if not line:
                    break
                if line.startswith("# Switch IP: "):
                    value = line.split(": ", 1)[1].strip()
                    if value not in {"", "not set", "unknown"}:
                        return value[:255]
    except OSError:
        return ""
    return ""


def configured_snmp_diagnostics_inventory(
    options: dict[str, Any], *, runtime: HubDiagnosticsRuntime
) -> list[dict[str, str]]:
    """Return authoritative saved SNMP identities used to reconcile cache rows."""
    rows = options.get("switches") if isinstance(options.get("switches"), list) else []
    inventory: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        switch_name = str(raw.get("switch_name") or "").strip()
        if not switch_name:
            continue
        identity = runtime.switch_name_identity(switch_name)
        if not identity or identity in seen:
            continue
        seen.add(identity)
        management_target = ""
        for key in ("switch_host", "host", "manual_switch_host"):
            value = str(raw.get(key) or "").strip()
            if value:
                management_target = value.casefold()
                break
        inventory.append({
            "identity": identity,
            "switch_name": switch_name,
            "management_target": management_target,
        })
    return inventory


def reconcile_snmp_diagnostics_devices(
    devices: list[dict[str, Any]],
    options: dict[str, Any],
    *,
    runtime: HubDiagnosticsRuntime,
) -> list[dict[str, Any]]:
    """Collapse stale capability aliases onto the current saved switch inventory."""
    inventory = configured_snmp_diagnostics_inventory(options, runtime=runtime)
    if not inventory:
        return devices

    by_identity = {item["identity"]: item for item in inventory}
    targets: dict[str, list[str]] = {}
    for item in inventory:
        target = item["management_target"]
        if target:
            targets.setdefault(target, []).append(item["identity"])

    selected: dict[str, tuple[tuple[int, str, str], dict[str, Any]]] = {}
    for item in devices:
        source_identity = runtime.switch_name_identity(
            str(item.get("source_switch_name") or item.get("name") or "")
        )
        owner = ""
        strength = 0
        if source_identity and source_identity in by_identity:
            owner = source_identity
            strength = 2
        else:
            target = str(item.get("management_target") or "").strip().casefold()
            matches = targets.get(target, []) if target else []
            if len(matches) == 1:
                owner = matches[0]
                strength = 1

        if not owner:
            continue

        score = (
            strength,
            str(item.get("generated_at") or ""),
            str(item.get("name") or ""),
        )
        current = selected.get(owner)
        if current is None or score > current[0]:
            selected[owner] = (score, item)

    return [
        selected[item["identity"]][1]
        for item in inventory
        if item["identity"] in selected
    ]


def diagnostics_options(
    options_file: Path | None, *, runtime: HubDiagnosticsRuntime
) -> dict[str, Any]:
    if options_file is None:
        return {}
    try:
        return runtime.self_addon_options()
    except RuntimeError:
        return runtime.load_options(options_file)


def diagnostics_snapshot(
    version: str,
    options_file: Path | None = None,
    *,
    runtime: HubDiagnosticsRuntime,
) -> dict[str, Any]:
    share = runtime.default_share_dir
    registry_raw = runtime.read_json(runtime.default_registry_file)
    if isinstance(registry_raw, dict):
        registry_devices = registry_raw.get("devices") or []
    elif isinstance(registry_raw, list):
        registry_devices = registry_raw
    else:
        registry_devices = []

    capability_dir = share / "capabilities"
    capability_files = (
        sorted(capability_dir.glob("*-capabilities.json"))
        if capability_dir.is_dir()
        else []
    )
    devices: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    for cap_path in capability_files:
        data = runtime.read_json(cap_path)
        if not isinstance(data, dict):
            warnings.append(f"Could not read capability file: {cap_path.name}")
            continue
        device = data.get("device") if isinstance(data.get("device"), dict) else {}
        interfaces = (
            data.get("interfaces") if isinstance(data.get("interfaces"), list) else []
        )
        model = str(
            device.get("detected_model_text")
            or device.get("model_text")
            or device.get("model")
            or "Unknown"
        )
        registry = runtime.registry_lookup({"devices": registry_devices}, model) or {}
        validation = (
            registry.get("validation")
            if isinstance(registry.get("validation"), dict)
            else {}
        )
        physical = [
            item for item in interfaces
            if isinstance(item, dict) and item.get("physical")
        ]
        rj45 = [item for item in physical if item.get("media") == "rj45"]
        uplinks = [
            item for item in physical
            if item.get("media") in {"sfp", "sfp_plus", "uplink"}
        ]
        source_walk_value = str(data.get("source_walk") or "").strip()
        source_walk = Path(source_walk_value) if source_walk_value else Path()
        walk_found = source_walk.is_file() if source_walk_value else False
        source_switch_name = source_walk.parent.name if source_walk_value else ""
        if source_walk_value and not walk_found:
            continue
        management_target = str(device.get("management_target") or "").strip()[:255]
        if not management_target:
            management_target = walk_management_target(source_walk)
        status = str(
            registry.get("status") or device.get("support_status") or "detected"
        )
        devices.append({
            "name": cap_path.name.removesuffix("-capabilities.json"),
            "source_switch_name": source_switch_name,
            "management_target": management_target,
            "model": model,
            "family": registry.get("family") or device.get("family") or "Unknown",
            "registry_match": bool(registry),
            "registry_status": status,
            "last_validated_version": registry.get("last_validated_version"),
            "mapping_profile": (
                registry.get("mapping_profile") or registry.get("dashboard_profile")
            ),
            "calibration_profile": registry.get("calibration_profile"),
            "validation": validation,
            "physical_interfaces": len(physical),
            "rj45_interfaces": len(rj45),
            "uplink_interfaces": len(uplinks),
            "walk_found": walk_found,
            "generated_at": data.get("generated_at"),
            "_identity_mac": (
                device.get("mac_address")
                or device.get("base_mac")
                or device.get("chassis_mac")
                or device.get("mac")
                or ""
            ),
            "_identity_ip": management_target,
        })

    current_options = diagnostics_options(options_file, runtime=runtime)
    if current_options:
        devices = reconcile_snmp_diagnostics_devices(
            devices, current_options, runtime=runtime
        )

    unifi_snapshot = runtime.read_json(runtime.default_unifi_snapshot)
    if (
        isinstance(unifi_snapshot, dict)
        and isinstance(unifi_snapshot.get("devices"), list)
    ):
        for raw in unifi_snapshot["devices"]:
            if not isinstance(raw, dict):
                continue
            model = str(raw.get("model") or "Unknown")
            registry = runtime.registry_lookup({"devices": registry_devices}, model) or {}
            validation = (
                registry.get("validation")
                if isinstance(registry.get("validation"), dict)
                else {}
            )
            ports = raw.get("ports") if isinstance(raw.get("ports"), list) else []
            physical = [item for item in ports if isinstance(item, dict)]
            rj45 = [
                item for item in physical
                if str(item.get("connector") or "").upper() == "RJ45"
            ]
            uplinks = [
                item for item in physical
                if str(item.get("connector") or "").upper()
                in {"SFP", "SFPPLUS", "SFP+"}
            ]
            matched_snmp, match_basis = unique_detected_snmp_identity_match(
                devices,
                mac_address=raw.get("mac_address"),
                ip_address=raw.get("ip_address"),
            )
            if matched_snmp is not None:
                matched_snmp["unifi_device_id"] = str(raw.get("id") or "").strip()
                matched_snmp["data_source"] = "SNMP + UniFi API"
                matched_snmp["unifi_match_basis"] = match_basis
                matched_snmp["online"] = (
                    str(raw.get("state") or "").upper() == "ONLINE"
                )
                matched_snmp["firmware"] = raw.get("firmware")
                matched_snmp["api_capabilities"] = (
                    raw.get("api_capabilities")
                    if isinstance(raw.get("api_capabilities"), dict)
                    else {}
                )
                continue

            devices.append({
                "unifi_device_id": str(raw.get("id") or "").strip(),
                "name": str(raw.get("name") or model),
                "model": model,
                "family": registry.get("family") or "UniFi",
                "registry_match": bool(registry),
                "registry_status": str(registry.get("status") or "detected"),
                "last_validated_version": registry.get("last_validated_version"),
                "mapping_profile": (
                    registry.get("mapping_profile")
                    or registry.get("dashboard_profile")
                ),
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
                "api_capabilities": (
                    raw.get("api_capabilities")
                    if isinstance(raw.get("api_capabilities"), dict)
                    else {}
                ),
            })

    unifi_diagnostics = runtime.unifi2mqtt_diagnostics_status()
    if unifi_diagnostics.get("found"):
        if not unifi_diagnostics.get("valid"):
            warnings.append("UniFi2MQTT diagnostics.json could not be read.")
        elif unifi_diagnostics.get("status") == "error":
            stage = unifi_diagnostics.get("stage") or "unknown"
            error_type = unifi_diagnostics.get("error_type") or "UnknownError"
            warnings.append(f"UniFi2MQTT poll failed at {stage}: {error_type}.")

    for item in devices:
        item.pop("_identity_mac", None)
        item.pop("_identity_ip", None)

    registry_loaded = isinstance(registry_raw, (dict, list))
    if not registry_loaded:
        errors.append("Supported-device registry could not be loaded.")
    report = runtime.file_info(share / "discovery-report.txt")
    generated_yaml = runtime.file_info(share / "generated-snmp2mqtt.yaml")
    generated_card = runtime.file_info(share / "generated-dashboard-card.yaml")
    if not report["found"]:
        warnings.append("No discovery report has been generated yet.")
    snmp2mqtt_applicability = runtime.snmp2mqtt_applicability()
    if not generated_yaml["found"] and snmp2mqtt_applicability["applicable"]:
        warnings.append("Generated SNMP2MQTT YAML was not found.")
    if not generated_card["found"]:
        warnings.append("Generated dashboard YAML was not found.")
    if report["found"]:
        report_path = share / "discovery-report.txt"
        report_mtime = report_path.stat().st_mtime
        stale_tolerance_seconds = 120
        stale_candidates = [
            ("dashboard YAML", share / "generated-dashboard-card.yaml")
        ]
        if snmp2mqtt_applicability["applicable"]:
            stale_candidates.insert(
                0, ("SNMP2MQTT YAML", share / "generated-snmp2mqtt.yaml")
            )
        for label, path in stale_candidates:
            if not path.is_file():
                continue
            generated_mtime = path.stat().st_mtime
            if generated_mtime + stale_tolerance_seconds < report_mtime:
                generated_text = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(generated_mtime)
                )
                report_text = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(report_mtime)
                )
                warnings.append(
                    f"Generated {label} appears stale: generated {generated_text}; "
                    f"latest discovery report {report_text}."
                )

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "version": version,
        "service": "Running",
        "discovery": runtime.discovery_state_snapshot(),
        "registry": {
            "loaded": registry_loaded,
            "entries": len(registry_devices),
            "path": str(runtime.default_registry_file),
        },
        "files": {
            "report": report,
            "generated_yaml": generated_yaml,
            "generated_card": generated_card,
        },
        "snmp2mqtt_applicability": snmp2mqtt_applicability,
        "contribution_workflow": {
            "ready": runtime.default_support_script.is_file(),
            "directory": str(runtime.default_contributions_dir),
        },
        "devices": devices,
        "unifi2mqtt_diagnostics": unifi_diagnostics,
        "warnings": warnings,
        "errors": errors,
    }


def diagnostics_text(data: dict[str, Any]) -> str:
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
        (
            "Device registry: "
            + (
                "Loaded"
                if (data.get("registry") or {}).get("loaded")
                else "Unavailable"
            )
        ),
        f"Registry entries: {(data.get('registry') or {}).get('entries', 0)}",
        f"Generated SNMP2MQTT YAML: {snmp_yaml_status}",
        (
            "Generated dashboard YAML: "
            + (
                "Found"
                if ((data.get("files") or {}).get("generated_card") or {}).get("found")
                else "Missing"
            )
        ),
        (
            "Contribution workflow: "
            + (
                "Ready"
                if (data.get("contribution_workflow") or {}).get("ready")
                else "Unavailable"
            )
        ),
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
                if (data.get("unifi2mqtt_diagnostics") or {}).get("found")
                else "Unavailable"
            )
        ),
        "",
    ]

    unifi_diag = (
        data.get("unifi2mqtt_diagnostics")
        if isinstance(data.get("unifi2mqtt_diagnostics"), dict)
        else {}
    )
    classifications = (
        unifi_diag.get("device_classification")
        if isinstance(unifi_diag.get("device_classification"), list)
        else []
    )
    if classifications:
        lines.append("UniFi2MQTT hardware classification")
        lines.append("---------------------------------")
        for item in classifications:
            if not isinstance(item, dict):
                continue
            model = str(item.get("model") or "Unknown")
            lines.append(f"Model: {model}")
            lines.append(
                "Accepted as switch: " + ("yes" if item.get("accepted") else "no")
            )
            lines.append(
                "Classification: " + str(item.get("reason") or "unknown")
            )
            features = item.get("features")
            if isinstance(features, list):
                lines.append(
                    "Features: "
                    + (
                        ", ".join(str(value) for value in features)
                        or "none"
                    )
                )
            lines.append("")

    for device in data.get("devices") or []:
        source = str(device.get("data_source") or "SNMP")
        source_status = (
            f"UniFi API state: {'ONLINE' if device.get('online') else 'OFFLINE'}"
            if source == "UniFi API"
            else (
                "Last SNMP walk: "
                + ("PASS/file found" if device.get("walk_found") else "Unavailable")
            )
        )
        model = str(device.get("model") or "Unknown model")
        lines.extend([
            model,
            "-" * len(model),
            f"Target: {device.get('name')}",
            f"Data source: {source}",
            f"Registry match: {'yes' if device.get('registry_match') else 'no'}",
            f"Registry status: {device.get('registry_status')}",
            source_status,
            *(
                [f"Firmware: {device.get('firmware') or 'Unknown'}"]
                if source == "UniFi API"
                else []
            ),
            f"Physical interfaces: {device.get('physical_interfaces', 0)}",
            f"RJ45 interfaces: {device.get('rj45_interfaces', 0)}",
            f"Uplink interfaces: {device.get('uplink_interfaces', 0)}",
            f"Mapping profile: {device.get('mapping_profile') or 'Not assigned'}",
            (
                "Calibration profile: "
                + str(device.get("calibration_profile") or "Not assigned")
            ),
        ])
        validation = device.get("validation") or {}
        for label, key in [
            ("Exact model", "exact_model_detection"),
            ("RJ45 mapping", "rj45_mapping"),
            ("PoE", "poe"),
            ("System sensors", "system_sensors"),
            ("Uplinks", "uplinks"),
            ("Stack", "stack"),
        ]:
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
