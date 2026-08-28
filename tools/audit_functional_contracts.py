#!/usr/bin/env python3
"""Read-only functional consistency audit for Switch Vision Discovery/Hub."""
from __future__ import annotations

import ast
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
SUPPORT_WEB = RUNTIME / "support_web.py"
CONFIG = ROOT / "switch_vision_discovery" / "config.yaml"
REGISTRY = RUNTIME / "opt" / "switch-vision" / "devices" / "supported_devices.json"
PROFILES = RUNTIME / "profiles" / "switch-vision-profiles.yaml"
MIB_VENDOR_ROOT = RUNTIME / "opt" / "switch-vision" / "mib_database" / "vendors"
EXTERNAL_JS = [
    RUNTIME / "maintenance.js",
    RUNTIME / "calibration_profiles.js",
    RUNTIME / "calibration_profiles_manager.js",
]

errors: list[str] = []
warnings: list[str] = []
passes: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def warn(message: str) -> None:
    warnings.append(message)


def ok(message: str) -> None:
    passes.append(message)


def canon(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def optical_count(mapping: dict) -> int:
    """Count physical optical connectors across SFP/SFP+/SFP28/QSFP fields."""
    total = 0
    for key, value in mapping.items():
        normalized = str(key).casefold()
        if ("sfp" in normalized or "qsfp" in normalized) and isinstance(value, int) and not isinstance(value, bool):
            total += value
    return total


def load_page() -> str:
    source = SUPPORT_WEB.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(SUPPORT_WEB))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "_PAGE" for t in targets):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value
    raise RuntimeError("Could not locate literal _PAGE in support_web.py")


def audit_registry_and_profiles() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    profile_doc = yaml.safe_load(PROFILES.read_text(encoding="utf-8")) or {}
    profiles = profile_doc.get("profiles") or {}
    devices = registry.get("devices") or []
    if not isinstance(devices, list) or not isinstance(profiles, dict):
        fail("Registry/profile documents have invalid top-level structure")
        return

    models = [str(d.get("model") or "").strip() for d in devices if isinstance(d, dict)]
    exact_dupes = [m for m, count in Counter(models).items() if m and count > 1]
    if exact_dupes:
        fail(f"Duplicate exact registry model entries: {exact_dupes}")
    else:
        ok(f"Registry exact model keys are unique ({len([m for m in models if m])} models)")

    canonical = defaultdict(list)
    for model in models:
        if model:
            canonical[canon(model)].append(model)
    collisions = {k: v for k, v in canonical.items() if len(set(v)) > 1}
    if collisions:
        fail(f"Canonical registry model collisions: {collisions}")
    else:
        ok("Registry has no punctuation/case canonical model collisions")

    pattern_owners: dict[str, set[str]] = defaultdict(set)
    for profile_name, profile in profiles.items():
        if not isinstance(profile, dict):
            fail(f"Mapping profile {profile_name} is not an object")
            continue
        for pattern in profile.get("model_patterns") or []:
            key = canon(pattern)
            if key:
                pattern_owners[key].add(str(profile_name))
    ambiguous_patterns = {k: sorted(v) for k, v in pattern_owners.items() if len(v) > 1}
    if ambiguous_patterns:
        fail(f"Canonical model patterns are owned by multiple mapping profiles: {ambiguous_patterns}")
    else:
        ok("Mapping profile exact model patterns have no cross-profile collisions")

    missing_profiles: list[str] = []
    pattern_errors: list[str] = []
    layout_errors: list[str] = []
    for device in devices:
        if not isinstance(device, dict):
            fail("Registry contains a non-object device entry")
            continue
        model = str(device.get("model") or "").strip()
        mapping = str(device.get("mapping_profile") or "").strip()
        if not mapping:
            continue
        profile = profiles.get(mapping)
        if not isinstance(profile, dict):
            missing_profiles.append(f"{model} -> {mapping}")
            continue
        patterns = profile.get("model_patterns") or []
        if model and patterns and canon(model) not in {canon(p) for p in patterns}:
            pattern_errors.append(f"{model} -> {mapping}; patterns={patterns}")

        ports = device.get("ports") if isinstance(device.get("ports"), dict) else {}
        layout = profile.get("layout") if isinstance(profile.get("layout"), dict) else {}
        if isinstance(layout.get("rj45_ports"), int) and int(ports.get("rj45") or 0) != int(layout["rj45_ports"]):
            layout_errors.append(
                f"{model}: registry RJ45={int(ports.get('rj45') or 0)} profile={layout['rj45_ports']}"
            )
        layout_optical = optical_count(layout)
        registry_optical = optical_count(ports)
        if layout_optical != registry_optical:
            layout_errors.append(f"{model}: registry optical={registry_optical} profile={layout_optical}")

    if missing_profiles:
        fail("Registry references missing mapping profiles: " + "; ".join(missing_profiles))
    else:
        ok("Every registry mapping_profile exists in the shipped profile database")
    if pattern_errors:
        fail("Registry model not represented by its mapping profile patterns: " + "; ".join(pattern_errors))
    else:
        ok("Registry model/profile model_patterns agree")
    if layout_errors:
        fail("Registry/profile physical layout mismatches: " + "; ".join(layout_errors))
    else:
        ok("Registry physical connector counts agree with mapping-profile layouts")

    manual_models = {
        str(d.get("model") or "").strip()
        for d in devices
        if isinstance(d, dict)
        and str(d.get("vendor") or "").strip().casefold() != "ubiquiti"
        and bool(d.get("discovery_support"))
        and str(d.get("mapping_profile") or "").strip()
        and str(d.get("model") or "").strip()
    }
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    switch_schema = (((config.get("schema") or {}).get("switches") or [{}])[0])
    schema_value = str(switch_schema.get("switch_model") or "")
    match = re.fullmatch(r"list\((.*)\)\??", schema_value.strip())
    if not match:
        fail(f"Could not parse config.yaml switch_model schema: {schema_value!r}")
        schema_models: set[str] = set()
    else:
        schema_models = {item for item in match.group(1).split("|") if item and item != "auto"}

    missing_from_schema = sorted(manual_models - schema_models)
    stale_in_schema = sorted(schema_models - manual_models)
    if missing_from_schema:
        fail("Hub manual-model choices missing from Supervisor schema: " + ", ".join(missing_from_schema))
    else:
        ok("Every Hub-selectable manual SNMP model is accepted by Supervisor schema")
    if stale_in_schema:
        fail("Supervisor manual-model enum has stale registry entries: " + ", ".join(stale_in_schema))
    else:
        ok("Supervisor manual-model enum has no stale registry entries")

    unifi_errors: list[str] = []
    mapped_unifi = 0
    for device in devices:
        if not isinstance(device, dict) or not isinstance(device.get("unifi_api_port_map"), dict):
            continue
        mapped_unifi += 1
        model = str(device.get("model") or "unknown")
        port_map = device["unifi_api_port_map"]
        rj = port_map.get("rj45") or []
        sfp = port_map.get("sfp") or []
        if not isinstance(rj, list) or not isinstance(sfp, list):
            unifi_errors.append(f"{model}: API map values must be lists")
            continue
        if len(rj) != len(set(rj)) or len(sfp) != len(set(sfp)) or set(rj) & set(sfp):
            unifi_errors.append(f"{model}: overlapping/duplicate API port positions")
        ports = device.get("ports") if isinstance(device.get("ports"), dict) else {}
        if int(ports.get("rj45") or 0) != len(rj):
            unifi_errors.append(f"{model}: RJ45 registry={int(ports.get('rj45') or 0)} API map={len(rj)}")
        if optical_count(ports) != len(sfp):
            unifi_errors.append(f"{model}: optical registry={optical_count(ports)} API map={len(sfp)}")
        if int(ports.get("uplinks") or 0) != len(sfp):
            unifi_errors.append(f"{model}: uplinks registry={int(ports.get('uplinks') or 0)} API optical map={len(sfp)}")
    if unifi_errors:
        fail("UniFi API topology map inconsistencies: " + "; ".join(unifi_errors))
    else:
        ok(f"All explicit UniFi API topology maps match registry connector counts ({mapped_unifi} models)")

    bad_json: list[str] = []
    vendor_dirs: set[str] = set()
    vendor_json_files = list(MIB_VENDOR_ROOT.rglob("*.json"))
    for path in vendor_json_files:
        vendor_dirs.add(path.parent.name.casefold())
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            bad_json.append(f"{path.relative_to(ROOT)}: {exc}")
    if bad_json:
        fail("Malformed vendor identity JSON: " + "; ".join(bad_json))
    else:
        ok(f"All vendor identity JSON files parse ({len(vendor_json_files)} files)")

    registry_vendors = {
        str(d.get("vendor") or "").strip().casefold()
        for d in devices if isinstance(d, dict)
    }
    known_vendor_source = (RUNTIME / "opt" / "switch-vision" / "vendors" / "known_vendor.sh").read_text(encoding="utf-8").casefold()
    missing_vendor = [v for v in sorted(registry_vendors) if v and v not in vendor_dirs and v not in known_vendor_source]
    if missing_vendor:
        warn("Registry vendors without an obvious MIB identity directory/known_vendor hint: " + ", ".join(missing_vendor))
    else:
        ok("Every registry vendor has an identity-database or known-vendor representation")


def audit_hub_ui_and_routes() -> None:
    page = load_page()
    support_source = SUPPORT_WEB.read_text(encoding="utf-8")
    js_sources = {p.name: p.read_text(encoding="utf-8") for p in EXTERNAL_JS}
    all_js = page + "\n" + "\n".join(js_sources.values())

    ids = re.findall(r'\bid="([A-Za-z0-9_.:-]+)"', page)
    duplicate_ids = sorted(k for k, v in Counter(ids).items() if v > 1)
    if duplicate_ids:
        fail("Duplicate static HTML ids in Hub page: " + ", ".join(duplicate_ids))
    else:
        ok(f"Static Hub HTML ids are unique ({len(ids)} ids)")

    critical_bindings = {
        "hubSettingsSave": "addEventListener('click',save",
        "hubSettingsReload": "addEventListener('click',load",
        "hubCoreReset": "addEventListener('click',resetCore",
        "runDiscoveryButton": "addEventListener('click',runDiscovery",
        "stopDiscoveryButton": "addEventListener('click',stopDiscovery",
        "regenerateYamlButton": "addEventListener('click',regenerateSnmp2mqttYaml",
        "resetSnmpDiscoveryButton": "addEventListener('click',resetSnmpDiscoveryData",
        "saveUnifi2mqttButton": "addEventListener('click',saveUnifi2mqttSettings",
        "importConfigurationButton": "addEventListener('click',importConfiguration",
        "scanMqttEntitiesButton": 'addEventListener("click", scan)',
        "repairMqttEntitiesButton": 'addEventListener("click", repair)',
        "exportMqttResultsButton": 'addEventListener("click", exportResults)',
        "refreshInstallerBackupsButton": 'addEventListener("click"',
        "installerBackupAutomaticRetention": 'addEventListener("click", toggleInstallerBackupRetention)',
        "createInstallerBackupButton": 'addEventListener("click"',
    }
    binding_errors: list[str] = []
    for control, handler in critical_bindings.items():
        if f'id="{control}"' not in page:
            binding_errors.append(f"{control}: HTML control missing")
        elif control not in all_js or handler not in all_js:
            binding_errors.append(f"{control}: handler binding missing")
    if binding_errors:
        fail("Critical Hub action binding failures: " + "; ".join(binding_errors))
    else:
        ok(f"All {len(critical_bindings)} critical Hub save/reset/run/maintenance controls are wired")

    calibration_source = js_sources["calibration_profiles.js"]
    calibration_controls = {
        "svProfilesRefresh": "load(true)",
        "svProfilesSelectStale": "state.selected = new Set",
        "svProfilesCleanStale": "await deleteSelected()",
        "svProfilesClearSelection": "state.selected.clear()",
        "svProfilesDeleteSelected": "deleteSelected",
    }
    cal_errors = [
        f"{control}: creation/handler missing"
        for control, handler in calibration_controls.items()
        if f'id="{control}"' not in calibration_source or handler not in calibration_source
    ]
    if cal_errors:
        fail("Calibration profile control wiring failures: " + "; ".join(cal_errors))
    else:
        ok("Calibration profile refresh/select/clean/clear/delete controls are wired")

    backend_contracts = {
        "/api/settings/core": "_save_core_settings(data)",
        "/api/settings/snmp2mqtt": "_save_snmp2mqtt_settings(data)",
        "/api/settings/discovery": "_save_discovery_settings(data)",
        "/api/discovery/reset-snmp": "_reset_snmp_discovery_data()",
        "/api/discovery/start": "threading.Thread(target=_run_discovery, args=(self.app.discovery_script,), daemon=True)",
        "/api/discovery/stop": "_request_discovery_stop()",
        "/api/discovery/regenerate-yaml": 'args=(self.app.discovery_script, "regenerate_yaml")',
    }
    backend_errors = [
        f"{route}: route/action contract missing"
        for route, action in backend_contracts.items()
        if route not in support_source or action not in support_source
    ]
    if backend_errors:
        fail("Critical backend route/action failures: " + "; ".join(backend_errors))
    else:
        ok("Critical settings and Discovery run/stop/regenerate/reset routes have real backend actions")

    secret_needles = [
        'row["snmp_community"] = ""',
        'row["original_switch_name"] = original_name',
        'previous = current_by_name.get(original_name',
        'support_contributor_value_configured',
        'merged_mqtt["password"] = "" if clear_password else (password if password else current_mqtt.get("password", ""))',
    ]
    if all(needle in support_source for needle in secret_needles):
        ok("Hub save paths retain write-only Discovery and MQTT secret-preservation logic")
    else:
        fail("Hub write-only secret preservation contract is incomplete")

    endpoint_literals: set[str] = set()
    for source in [page, *js_sources.values()]:
        for match in re.finditer(r"endpoint\(\s*['\"]([^'\"]+)['\"]\s*\)", source):
            value = match.group(1)
            if value.startswith("api/"):
                endpoint_literals.add("/" + value)
    missing_routes = sorted(route for route in endpoint_literals if route not in support_source)
    if missing_routes:
        fail("Client calls API routes not represented in support_web.py: " + ", ".join(missing_routes))
    else:
        ok(f"All {len(endpoint_literals)} literal client API endpoints are represented in the Hub backend")


def main() -> int:
    try:
        audit_registry_and_profiles()
        audit_hub_ui_and_routes()
    except Exception as exc:  # noqa: BLE001
        fail(f"Audit crashed: {type(exc).__name__}: {exc}")

    print("\n=== Switch Vision Discovery functional audit ===")
    for message in passes:
        print(f"PASS: {message}")
    for message in warnings:
        print(f"WARN: {message}")
    for message in errors:
        print(f"FAIL: {message}")
    print(f"\nSummary: {len(passes)} pass, {len(warnings)} warning, {len(errors)} fail")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
