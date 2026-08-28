#!/usr/bin/env python3
"""Switch Vision Discovery functional consistency audit.

Read-only checks for Hub UI wiring, API route parity, registry/profile/schema
consistency, vendor identity data, and critical action bindings.
"""
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


def load_page() -> str:
    source = SUPPORT_WEB.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(SUPPORT_WEB))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "_PAGE" for t in targets):
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    return value.value
    raise RuntimeError("Could not locate literal _PAGE in support_web.py")


def audit_registry_and_profiles() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    profile_doc = yaml.safe_load(PROFILES.read_text(encoding="utf-8")) or {}
    profiles = profile_doc.get("profiles") or {}
    devices = registry.get("devices") or []
    if not isinstance(devices, list):
        fail("supported_devices.json devices must be a list")
        return
    if not isinstance(profiles, dict):
        fail("switch-vision-profiles.yaml profiles must be a mapping")
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

    profile_errors = []
    model_pattern_errors = []
    for device in devices:
        if not isinstance(device, dict):
            fail("Registry contains a non-object device entry")
            continue
        model = str(device.get("model") or "").strip()
        mapping = str(device.get("mapping_profile") or "").strip()
        if mapping:
            if mapping not in profiles:
                profile_errors.append(f"{model} -> {mapping} (missing)")
                continue
            patterns = profiles[mapping].get("model_patterns") or []
            if model and patterns and canon(model) not in {canon(p) for p in patterns}:
                model_pattern_errors.append(f"{model} -> {mapping}; patterns={patterns}")
    if profile_errors:
        fail("Registry references missing mapping profiles: " + "; ".join(profile_errors))
    else:
        ok("Every registry mapping_profile exists in the shipped profile database")
    if model_pattern_errors:
        fail("Registry model not represented by its mapping profile patterns: " + "; ".join(model_pattern_errors))
    else:
        ok("Registry model/profile model_patterns agree")

    # Hub settings derives manual SNMP override choices from exactly this rule.
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
        fail(
            "Hub manual-model registry choices are missing from Supervisor config schema: "
            + ", ".join(missing_from_schema)
        )
    else:
        ok("Every Hub-selectable manual SNMP model is accepted by Supervisor schema")
    if stale_in_schema:
        fail(
            "Supervisor config schema exposes manual models not present in the authoritative Hub registry/profile set: "
            + ", ".join(stale_in_schema)
        )
    else:
        ok("Supervisor manual-model enum has no stale registry entries")

    # UniFi API maps: exact map positions should match advertised connector counts.
    unifi_errors = []
    for device in devices:
        if not isinstance(device, dict):
            continue
        port_map = device.get("unifi_api_port_map")
        if not isinstance(port_map, dict):
            continue
        model = str(device.get("model") or "unknown")
        rj = port_map.get("rj45") or []
        sfp = port_map.get("sfp") or []
        if len(rj) != len(set(rj)) or len(sfp) != len(set(sfp)) or set(rj) & set(sfp):
            unifi_errors.append(f"{model}: overlapping/duplicate API port positions")
        ports = device.get("ports") or {}
        if isinstance(ports, dict):
            advertised_rj = int(ports.get("rj45") or 0)
            advertised_optical = int(ports.get("gigabit_sfp") or 0) + int(ports.get("ten_gigabit_sfp_plus") or 0)
            if advertised_rj != len(rj):
                unifi_errors.append(f"{model}: rj45 registry={advertised_rj} map={len(rj)}")
            if advertised_optical != len(sfp):
                unifi_errors.append(f"{model}: optical registry={advertised_optical} map={len(sfp)}")
    if unifi_errors:
        fail("UniFi API topology map inconsistencies: " + "; ".join(unifi_errors))
    else:
        ok("UniFi API topology maps match registry connector counts")

    # Vendor identity database must be syntactically valid and registry vendors
    # should be represented by an identity directory or known parser layer.
    bad_json = []
    vendor_dirs = set()
    for path in MIB_VENDOR_ROOT.rglob("*.json"):
        vendor_dirs.add(path.parent.name.casefold())
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - audit should report every malformed file
            bad_json.append(f"{path.relative_to(ROOT)}: {exc}")
    if bad_json:
        fail("Malformed vendor identity JSON: " + "; ".join(bad_json))
    else:
        ok(f"All vendor identity JSON files parse ({len(list(MIB_VENDOR_ROOT.rglob('*.json')))} files)")

    registry_vendors = {str(d.get("vendor") or "").strip().casefold() for d in devices if isinstance(d, dict)}
    known_vendor_source = (RUNTIME / "opt" / "switch-vision" / "vendors" / "known_vendor.sh").read_text(encoding="utf-8").casefold()
    missing_vendor_representation = []
    for vendor in sorted(v for v in registry_vendors if v):
        if vendor not in vendor_dirs and vendor not in known_vendor_source:
            missing_vendor_representation.append(vendor)
    if missing_vendor_representation:
        warn("Registry vendors without an obvious MIB identity directory/known_vendor hint: " + ", ".join(missing_vendor_representation))
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

    # Explicit functional controls requested for this audit. Each control must
    # exist and must have a corresponding binding/handler in the shipped JS.
    critical_bindings = {
        "hubSettingsSave": ["hubSettingsSave')?.addEventListener('click',save", 'hubSettingsSave\")?.addEventListener(\"click\", save'],
        "hubSettingsReload": ["hubSettingsReload')?.addEventListener('click',load"],
        "hubCoreReset": ["hubCoreReset')?.addEventListener('click',resetCore"],
        "runDiscoveryButton": ["runDiscoveryButton').addEventListener('click',runDiscovery"],
        "stopDiscoveryButton": ["stopDiscoveryButton').addEventListener('click',stopDiscovery"],
        "regenerateYamlButton": ["regenerateYamlButton').addEventListener('click',regenerateSnmp2mqttYaml"],
        "resetSnmpDiscoveryButton": ["resetSnmpDiscoveryButton').addEventListener('click',resetSnmpDiscoveryData"],
        "saveUnifi2mqttButton": ["saveUnifi2mqttButton').addEventListener('click',saveUnifi2mqttSettings"],
        "importConfigurationButton": ["importConfigurationButton').addEventListener('click',importConfiguration"],
        "scanMqttEntitiesButton": ['el("scanMqttEntitiesButton")?.addEventListener("click", scan)'],
        "repairMqttEntitiesButton": ['el("repairMqttEntitiesButton")?.addEventListener("click", repair)'],
        "exportMqttResultsButton": ['el("exportMqttResultsButton")?.addEventListener("click", exportResults)'],
        "refreshInstallerBackupsButton": ['el("refreshInstallerBackupsButton")?.addEventListener("click"'],
        "installerBackupAutomaticRetention": ['el("installerBackupAutomaticRetention")?.addEventListener("click", toggleInstallerBackupRetention)'],
        "createInstallerBackupButton": ['el("createInstallerBackupButton")?.addEventListener("click"'],
    }
    binding_errors = []
    for control, needles in critical_bindings.items():
        if f'id="{control}"' not in page:
            binding_errors.append(f"{control}: HTML control missing")
        elif not any(needle in all_js for needle in needles):
            binding_errors.append(f"{control}: click binding not found")
    if binding_errors:
        fail("Critical Hub action binding failures: " + "; ".join(binding_errors))
    else:
        ok(f"All {len(critical_bindings)} critical Hub save/reset/run/maintenance controls are wired")

    # Calibration profile base controls are dynamically rendered but must still
    # be present in both creation and event binding code.
    calibration_source = js_sources["calibration_profiles.js"]
    calibration_controls = {
        "svProfilesRefresh": "load(true)",
        "svProfilesSelectStale": "state.selected = new Set",
        "svProfilesCleanStale": "await deleteSelected()",
        "svProfilesClearSelection": "state.selected.clear()",
        "svProfilesDeleteSelected": "deleteSelected",
    }
    cal_errors = []
    for control, handler in calibration_controls.items():
        if f'id="{control}"' not in calibration_source:
            cal_errors.append(f"{control}: creation missing")
        if control not in calibration_source or handler not in calibration_source:
            cal_errors.append(f"{control}: handler missing")
    if cal_errors:
        fail("Calibration profile control wiring failures: " + "; ".join(cal_errors))
    else:
        ok("Calibration profile refresh/select/clean/clear/delete controls are wired")

    # Backend persistence/reset functions must be routed by the HTTP handler.
    backend_contracts = {
        "/api/settings/core": "_save_core_settings(data)",
        "/api/settings/snmp2mqtt": "_save_snmp2mqtt_settings(data)",
        "/api/settings/discovery": "_save_discovery_settings(data)",
        "/api/discovery/reset-snmp": "_reset_snmp_discovery_data()",
        "/api/discovery/start": "_start_discovery_job",
        "/api/discovery/stop": "_stop_discovery_job",
        "/api/discovery/regenerate-yaml": "_start_discovery_regeneration",
    }
    backend_errors = []
    for route, handler in backend_contracts.items():
        if route not in support_source:
            backend_errors.append(f"{route}: route missing")
        if handler not in support_source:
            backend_errors.append(f"{route}: handler {handler} missing")
    if backend_errors:
        fail("Critical backend route/handler failures: " + "; ".join(backend_errors))
    else:
        ok("Critical Hub settings, Discovery run/stop/regenerate/reset routes have backend handlers")

    # Secret-preservation contract for Hub saves.
    secret_needles = [
        'row["snmp_community"] = ""',
        'row["original_switch_name"] = original_name',
        'previous = current_by_name.get(original_name',
        'support_contributor_value_configured',
    ]
    if all(needle in support_source for needle in secret_needles):
        ok("Discovery Hub save path retains write-only secret preservation logic")
    else:
        fail("Discovery Hub write-only secret preservation contract is incomplete")

    # Every literal client API endpoint should at least appear in server source.
    endpoint_literals = set()
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
