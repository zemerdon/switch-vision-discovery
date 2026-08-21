#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "switch_vision_discovery"
RUNTIME = ROOT / "runtime_src"
VERSION = "2.1.34"
CORE_REGISTRY_URL = (
    "https://raw.githubusercontent.com/zemerdon/"
    "switch-vision-releases/main/src/devices/supported_devices.json"
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8", newline="\n")


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Switch-Vision-Discovery-Prepare/1"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("Core registry payload is not an object")
    return payload


def devices_by_model(payload: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    devices = payload.get("devices")
    if not isinstance(devices, list):
        raise SystemExit(f"{label} registry devices field is not a list")
    result: dict[str, dict[str, Any]] = {}
    for item in devices:
        if not isinstance(item, dict):
            continue
        model = str(item.get("model") or "").strip()
        if model:
            result[model] = item
    return result


def sync_shared_visual_contracts() -> None:
    """Copy Core's enforced visual defaults onto shared exact-model entries."""
    registry_path = RUNTIME / "opt" / "switch-vision" / "devices" / "supported_devices.json"
    discovery_registry = json.loads(read(registry_path))
    if not isinstance(discovery_registry, dict):
        raise SystemExit("Discovery registry payload is not an object")

    core_registry = fetch_json(CORE_REGISTRY_URL)
    discovery_models = devices_by_model(discovery_registry, "Discovery")
    core_models = devices_by_model(core_registry, "Core")

    changed_models = 0
    changed_fields = 0
    top_level_fields = ("calibration_profile", "default_faceplate")
    nested_fields = ("recommended_faceplate", "calibration_profile")

    for model in sorted(core_models.keys() & discovery_models.keys()):
        core = core_models[model]
        discovery = discovery_models[model]
        model_changed = False

        for field in top_level_fields:
            if core.get(field) == discovery.get(field):
                continue
            if field in core:
                discovery[field] = core[field]
            else:
                discovery.pop(field, None)
            changed_fields += 1
            model_changed = True

        core_visuals = core.get("visuals") if isinstance(core.get("visuals"), dict) else {}
        discovery_visuals = (
            discovery.get("visuals")
            if isinstance(discovery.get("visuals"), dict)
            else {}
        )
        for field in nested_fields:
            if core_visuals.get(field) == discovery_visuals.get(field):
                continue
            if not isinstance(discovery.get("visuals"), dict):
                discovery["visuals"] = discovery_visuals
            if field in core_visuals:
                discovery_visuals[field] = core_visuals[field]
            else:
                discovery_visuals.pop(field, None)
            changed_fields += 1
            model_changed = True

        if model_changed:
            changed_models += 1

    write(
        registry_path,
        json.dumps(discovery_registry, indent=2, ensure_ascii=False) + "\n",
    )
    print(
        "Synchronized Core visual contracts into Discovery: "
        f"{changed_models} model(s), {changed_fields} field(s)"
    )


# Version metadata and runtime/self-test expectations.
config_path = APP / "config.yaml"
config = read(config_path)
if 'version: "2.1.33"' not in config:
    raise SystemExit("Discovery config version marker missing")
write(config_path, config.replace('version: "2.1.33"', f'version: "{VERSION}"', 1))

runtime_version_old = 'SWITCH_VISION_DISCOVERY_VERSION="2.1.33"'
runtime_version_new = f'SWITCH_VISION_DISCOVERY_VERSION="{VERSION}"'

job_path = RUNTIME / "discovery_job.sh"
job = read(job_path)
if runtime_version_old not in job:
    raise SystemExit("Discovery job runtime version marker missing")
write(job_path, job.replace(runtime_version_old, runtime_version_new, 1))

run_path = RUNTIME / "run.sh"
run = read(run_path)
if runtime_version_old not in run:
    raise SystemExit("Discovery run runtime version marker missing")
write(run_path, run.replace(runtime_version_old, runtime_version_new, 1))

self_test_path = RUNTIME / "self-test.sh"
self_test = read(self_test_path)
if self_test.count(runtime_version_old) < 2:
    raise SystemExit("Discovery self-test version expectations missing")
write(self_test_path, self_test.replace(runtime_version_old, runtime_version_new))

# Align the product source with Core before making shared visual drift fatal.
# Discovery-only exact models remain untouched, and no hardware contract fields
# are copied here.
sync_shared_visual_contracts()

# Harden cross-component visual contracts. Shared exact-model visuals are strict
# by default. Intentional divergence requires an explicit model -> reason entry.
contract_path = ROOT / "tools" / "check_component_contracts.py"
contract = read(contract_path)
url_marker = '''DEFAULT_SNMP_ADDON_CONFIG_URL = (
    "https://raw.githubusercontent.com/zemerdon/"
    "switch-vision-snmp2mqtt-addon/main/switch-vision-snmp2mqtt/config.yaml"
)
'''
policy_block = '''DEFAULT_SNMP_ADDON_CONFIG_URL = (
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
'''
if url_marker not in contract:
    raise SystemExit("component-contract URL marker missing")
contract = contract.replace(url_marker, policy_block, 1)

old_visual = '''        if changed_visuals:
            strict_visual_models = {"S5720-12TP-LI-AC", "S5735-L8P4X-A1"}
            if str(core.get("vendor") or "").strip() == "Ubiquiti" or model in strict_visual_models:
                errors.append(
                    f"{model}: shared visual contract drift in "
                    + ", ".join(changed_visuals)
                )
            else:
                warnings.append(
                    f"{model}: visual recommendation differs between Core and Discovery "
                    f"({', '.join(changed_visuals)})"
                )
'''
new_visual = '''        if changed_visuals:
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
'''
if old_visual not in contract:
    raise SystemExit("old selective visual-contract block missing")
contract = contract.replace(old_visual, new_visual, 1)

shared_marker = '''    missing_in_discovery = sorted(core_models.keys() - discovery_models.keys())
    if missing_in_discovery:
        errors.append(
            "Core exact models missing from Discovery: " + ", ".join(missing_in_discovery)
        )

    hardware_fields = (
'''
shared_replacement = '''    missing_in_discovery = sorted(core_models.keys() - discovery_models.keys())
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
'''
if shared_marker not in contract:
    raise SystemExit("shared-model contract marker missing")
contract = contract.replace(shared_marker, shared_replacement, 1)

old_pass = '''        "Discovery cross-component contracts: PASS "
        f"(version={app_version}; Core subset present; hardware mappings aligned; "
        "shared Ubiquiti visuals aligned; SNMP2MQTT YAML path aligned)"
'''
new_pass = '''        "Discovery cross-component contracts: PASS "
        f"(version={app_version}; Core subset present; hardware mappings aligned; "
        "all shared exact-model visuals aligned or explicitly excepted; "
        "SNMP2MQTT YAML path aligned)"
'''
if old_pass not in contract:
    raise SystemExit("component-contract PASS marker missing")
contract = contract.replace(old_pass, new_pass, 1)
write(contract_path, contract)

# Permanent synthetic policy regression: every vendor is strict by default and
# only a documented exception can downgrade drift to a warning.
test_path = ROOT / "tools" / "test_visual_contract_policy.py"
write(test_path, '''#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "check_component_contracts.py"
spec = importlib.util.spec_from_file_location("sv_discovery_contracts", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

# No vendor gets implicit warning-only treatment anymore.
for model in (
    "WS-C3650-48PD",
    "EX3300-48P",
    "N2128PX-ON",
    "S5720-12TP-LI-AC",
    "S5735-L8P4X-A1",
    "USW-Pro-24-PoE",
):
    policy, reason = module.classify_visual_contract_drift(model)
    assert policy == "error", (model, policy, reason)
    assert reason is None

assert module.VISUAL_CONTRACT_EXCEPTIONS == {}, module.VISUAL_CONTRACT_EXCEPTIONS

module.VISUAL_CONTRACT_EXCEPTIONS["INTENTIONAL-MODEL"] = "documented test divergence"
policy, reason = module.classify_visual_contract_drift("INTENTIONAL-MODEL")
assert policy == "warning"
assert reason == "documented test divergence"

module.VISUAL_CONTRACT_EXCEPTIONS["EMPTY-REASON"] = "   "
policy, reason = module.classify_visual_contract_drift("EMPTY-REASON")
assert policy == "invalid"
assert reason is None

source = MODULE_PATH.read_text(encoding="utf-8")
assert "strict_visual_models" not in source
assert "all shared exact-model visuals aligned or explicitly excepted" in source
print("Discovery strict visual-contract policy: PASS")
''')

# Changelog.
changelog_path = APP / "CHANGELOG.md"
changelog = read(changelog_path)
entry = '''# Changelog\n\n## 2.1.34\n\n- Make Core/Discovery visual defaults a hard contract for every shared exact model, regardless of vendor.\n- Remove the previous warning-only path for non-Ubiquiti/non-Huawei shared visual drift.\n- Add an explicit model-to-reason exception table for rare intentional visual divergence; empty, unknown, or stale exceptions are rejected.\n- Add a permanent synthetic regression proving Cisco, Juniper, Dell, Huawei and Ubiquiti models are all strict by default.\n- Preserve hardware contracts, Huawei exact-model safeguards, SNMP2MQTT path checks, saved-walk YAML regeneration, and runtime behavior unchanged.\n\n'''
if not changelog.startswith("# Changelog\n\n"):
    raise SystemExit("Discovery changelog header missing")
if "## 2.1.34" not in changelog:
    changelog = entry + changelog[len("# Changelog\n\n"):]
write(changelog_path, changelog)

print("Prepared Switch Vision Discovery v2.1.34 strict visual contracts")
