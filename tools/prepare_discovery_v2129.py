#!/usr/bin/env python3
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {"S5720-12TP-LI-AC", "S5735-L8P4X-A1"}
PROFILE = "stock_24rj45_4sfp"
FACEPLATE = "faceplates/24rj45-4sfp.png"

registry_path = ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"
doc = json.loads(registry_path.read_text(encoding="utf-8"))
found = set()
for device in doc.get("devices", []):
    if not isinstance(device, dict) or device.get("model") not in TARGETS:
        continue
    found.add(device["model"])
    device["calibration_profile"] = PROFILE
    device["default_faceplate"] = FACEPLATE
    visuals = device.setdefault("visuals", {})
    visuals["recommended_faceplate"] = FACEPLATE
    visuals["calibration_profile"] = PROFILE
if found != TARGETS:
    raise SystemExit(f"ERROR: Huawei models missing from Discovery registry: {sorted(TARGETS-found)}")
registry_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")

for rel in ("runtime_src/run.sh", "runtime_src/discovery_job.sh"):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    old = 'SWITCH_VISION_DISCOVERY_VERSION="2.1.28"'
    new = 'SWITCH_VISION_DISCOVERY_VERSION="2.1.29"'
    if old not in text:
        raise SystemExit(f"ERROR: {rel}: expected 2.1.28 runtime version not found")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

# Keep the runtime self-test's current-version assertions aligned with the app
# version. Historical v2.1.28 atomic-YAML fixtures later in this file remain
# unchanged so their regression semantics are preserved.
self_test_path = ROOT / "runtime_src/self-test.sh"
self_test = self_test_path.read_text(encoding="utf-8")
for rel in ("discovery_job.sh", "run.sh"):
    old = f'grep -q \'SWITCH_VISION_DISCOVERY_VERSION="2.1.28"\' "$BASE_DIR/{rel}"'
    new = f'grep -q \'SWITCH_VISION_DISCOVERY_VERSION="2.1.29"\' "$BASE_DIR/{rel}"'
    if self_test.count(old) != 1:
        raise SystemExit(f"ERROR: expected one 2.1.28 current-version assertion for {rel}")
    self_test = self_test.replace(old, new, 1)
self_test_path.write_text(self_test, encoding="utf-8", newline="\n")

config_path = ROOT / "switch_vision_discovery/config.yaml"
config = config_path.read_text(encoding="utf-8")
config, count = re.subn(r'(?m)^version:\s*"2\.1\.28"\s*$', 'version: "2.1.29"', config, count=1)
if count != 1:
    raise SystemExit("ERROR: Discovery config version 2.1.28 not found exactly once")
config_path.write_text(config, encoding="utf-8", newline="\n")

changelog_path = ROOT / "switch_vision_discovery/CHANGELOG.md"
changelog = changelog_path.read_text(encoding="utf-8")
entry = """## 2.1.29

- Restore `S5720-12TP-LI-AC` and `S5735-L8P4X-A1` to the neutral `stock_24rj45_4sfp` calibration profile and `faceplates/24rj45-4sfp.png` visual recommendation.
- Keep Discovery-generated cards aligned with Core factory/reset defaults for both Huawei 8 RJ45 + 4 SFP models.
- Upgrade Huawei visual drift from a warning to a permanent cross-component contract failure.
- Preserve S5720 physical 1G SFP speed capping, interface-name fallback, generated-YAML atomic publication, device mappings, and telemetry behavior unchanged.

"""
if changelog.startswith("# Changelog\n\n"):
    changelog = "# Changelog\n\n" + entry + changelog[len("# Changelog\n\n"):]
else:
    raise SystemExit("ERROR: unexpected Discovery changelog header")
changelog_path.write_text(changelog, encoding="utf-8", newline="\n")

contracts_path = ROOT / "tools/check_component_contracts.py"
contracts = contracts_path.read_text(encoding="utf-8")
old = '''        if changed_visuals:\n            if str(core.get("vendor") or "").strip() == "Ubiquiti":\n                errors.append(\n                    f"{model}: shared Ubiquiti visual contract drift in "\n                    + ", ".join(changed_visuals)\n                )\n            else:\n                warnings.append(\n                    f"{model}: visual recommendation differs between Core and Discovery "\n                    f"({', '.join(changed_visuals)})"\n                )\n'''
new = '''        if changed_visuals:\n            strict_visual_models = {"S5720-12TP-LI-AC", "S5735-L8P4X-A1"}\n            if str(core.get("vendor") or "").strip() == "Ubiquiti" or model in strict_visual_models:\n                errors.append(\n                    f"{model}: shared visual contract drift in "\n                    + ", ".join(changed_visuals)\n                )\n            else:\n                warnings.append(\n                    f"{model}: visual recommendation differs between Core and Discovery "\n                    f"({', '.join(changed_visuals)})"\n                )\n'''
if old not in contracts:
    raise SystemExit("ERROR: expected visual drift block not found")
contracts = contracts.replace(old, new, 1)
marker = "    discovery_yaml_path = str(\n"
explicit = '''    expected_huawei_profile = "stock_24rj45_4sfp"\n    expected_huawei_faceplate = "faceplates/24rj45-4sfp.png"\n    for model in ("S5720-12TP-LI-AC", "S5735-L8P4X-A1"):\n        discovery = discovery_models.get(model) or {}\n        visuals = discovery.get("visuals") if isinstance(discovery.get("visuals"), dict) else {}\n        if discovery.get("calibration_profile") != expected_huawei_profile:\n            errors.append(f"{model}: expected calibration_profile={expected_huawei_profile}")\n        if discovery.get("default_faceplate") != expected_huawei_faceplate:\n            errors.append(f"{model}: expected default_faceplate={expected_huawei_faceplate}")\n        if visuals.get("calibration_profile") != expected_huawei_profile:\n            errors.append(f"{model}: expected visuals.calibration_profile={expected_huawei_profile}")\n        if visuals.get("recommended_faceplate") != expected_huawei_faceplate:\n            errors.append(f"{model}: expected visuals.recommended_faceplate={expected_huawei_faceplate}")\n\n'''
if marker not in contracts:
    raise SystemExit("ERROR: component contract insertion marker not found")
contracts_path.write_text(contracts.replace(marker, explicit + marker, 1), encoding="utf-8", newline="\n")
print("Prepared Discovery v2.1.29 Huawei visual hotfix")
