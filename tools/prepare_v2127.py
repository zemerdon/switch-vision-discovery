#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.1.27"
TARGET_MODELS = {
    "WS-C2960X-24TS-L",
    "WS-C3560CG-8PC-S",
    "SG500X-24",
    "S5735-L8P4X-A1",
    "S5720-12TP-LI-AC",
}


def write(path: Path, text: str) -> None:
    path.write_text(text.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8", newline="\n")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"ERROR: {label}: expected one occurrence, found {count}")
    return text.replace(old, new, 1)


# Home Assistant app version.
config_path = ROOT / "switch_vision_discovery" / "config.yaml"
config = config_path.read_text(encoding="utf-8")
config = replace_once(config, 'version: "2.1.26"', f'version: "{VERSION}"', "config version")
write(config_path, config)

# Runtime version contract.
for rel in ("runtime_src/run.sh", "runtime_src/discovery_job.sh"):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'SWITCH_VISION_DISCOVERY_VERSION="2.1.26"',
        f'SWITCH_VISION_DISCOVERY_VERSION="{VERSION}"',
        f"{rel} version",
    )
    write(path, text)

# Promote only the models explicitly approved by the hardware-validation pass.
registry_path = ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"
registry = json.loads(registry_path.read_text(encoding="utf-8"))
seen: set[str] = set()
for device in registry.get("devices", []):
    if not isinstance(device, dict):
        continue
    model = str(device.get("model") or "")
    if model not in TARGET_MODELS:
        continue
    seen.add(model)
    device["status"] = "community_validated"
    notes = device.setdefault("notes", [])
    if not isinstance(notes, list):
        raise SystemExit(f"ERROR: {model}: notes is not a list")
    note = "Promoted to Community Validated after real-hardware validation; model-specific physical layout remains authoritative."
    if note not in notes:
        notes.append(note)
    if model == "WS-C3560CG-8PC-S":
        combo = "Gi0/9 and Gi0/10 remain dual-purpose combo uplink positions; promotion does not change their physical semantics."
        if combo not in notes:
            notes.append(combo)
    if model == "S5720-12TP-LI-AC":
        speed_note = "Ports 9-12 are physical 1G SFP cages; Discovery caps generated speed telemetry for these positions at 1000 Mbps when IF-MIB reports an implausible higher value."
        if speed_note not in notes:
            notes.append(speed_note)
if seen != TARGET_MODELS:
    raise SystemExit(f"ERROR: registry target mismatch: missing {sorted(TARGET_MODELS-seen)}")
write(registry_path, json.dumps(registry, indent=2) + "\n")

# Keep profile maturity aligned and encode the S5720 physical speed capability.
profiles_path = ROOT / "runtime_src/profiles/switch-vision-profiles.yaml"
profiles_doc = yaml.safe_load(profiles_path.read_text(encoding="utf-8")) or {}
profiles = profiles_doc.get("profiles", profiles_doc)
if not isinstance(profiles, dict):
    raise SystemExit("ERROR: profiles root is not a mapping")
profile_by_model: dict[str, tuple[str, dict]] = {}
for name, profile in profiles.items():
    if not isinstance(profile, dict):
        continue
    for model in profile.get("model_patterns") or []:
        if model in TARGET_MODELS:
            profile_by_model[model] = (name, profile)
for model in TARGET_MODELS:
    if model not in profile_by_model:
        raise SystemExit(f"ERROR: no profile found for {model}")
    profile_by_model[model][1]["status"] = "community_validated"

s5720_profile = profile_by_model["S5720-12TP-LI-AC"][1]
s5720_profile["physical_speed_caps_mbps"] = {"sfp_1g": 1000}
notes = s5720_profile.setdefault("notes", [])
cap_note = "Physical 1G SFP cages 9-12 are capped at 1000 Mbps for generated speed telemetry even if IF-MIB reports a higher capability value."
if cap_note not in notes:
    notes.append(cap_note)
write(profiles_path, yaml.safe_dump(profiles_doc, sort_keys=False, allow_unicode=True))

# Discovery parser/generator status labels and speed normalization.
job_path = ROOT / "runtime_src/discovery_job.sh"
job = job_path.read_text(encoding="utf-8")
for model in TARGET_MODELS:
    old = f'if (model == "{model}") return "experimental"'
    new = f'if (model == "{model}") return "community_validated"'
    job = replace_once(job, old, new, f"{model} model status")

sfp_anchor = 'if (status == "supported") return "validated"'
job = replace_once(
    job,
    sfp_anchor,
    sfp_anchor + '\n      if (status == "community_validated") return "real-hardware validated"',
    "community validated SFP note",
)

confidence_anchor = 'if (profile_status == "supported") print "- Generator confidence: supported profile; review generated YAML before installing"'
job = replace_once(
    job,
    confidence_anchor,
    confidence_anchor + '\n      else if (profile_status == "community_validated") print "- Generator confidence: community-validated profile; physical layout verified on real hardware"',
    "community validated confidence",
)

# Replace the generic speed emission with a model-capability aware helper.  The
# physical mapping remains untouched: only the reported speed value is capped.
helper_anchor = '''    function yaml_sensor(oid, name) {\n      print "  - oid: " oid\n      print "    name: " name\n    }'''
helper_replacement = helper_anchor + '''\n    function physical_speed_cap_mbps(model, label) {\n      if (model == "S5720-12TP-LI-AC" && label ~ /^SFP 1G /) return 1000\n      return 0\n    }\n    function yaml_speed_sensor(model, idx, label, has_highspeed, has_ifspeed, cap_mbps) {\n      cap_mbps = physical_speed_cap_mbps(model, label)\n      if (has_highspeed) {\n        yaml_sensor("1.3.6.1.2.1.31.1.1.1.15." idx, label " Speed Mbps")\n        if (cap_mbps > 0) print "    template: '{{ [value | int, " cap_mbps "] | min }}'"\n      } else if (has_ifspeed) {\n        yaml_sensor("1.3.6.1.2.1.2.2.1.5." idx, label " Speed Bps")\n        if (cap_mbps > 0) print "    template: '{{ [value | int, " (cap_mbps * 1000000) "] | min }}'"\n      }\n    }'''
job = replace_once(job, helper_anchor, helper_replacement, "speed helper anchor")

speed_old = '''          if (idx in highspeed_idx) yaml_sensor("1.3.6.1.2.1.31.1.1.1.15." idx, label " Speed Mbps")\n          else if (idx in ifspeed_idx) yaml_sensor("1.3.6.1.2.1.2.2.1.5." idx, label " Speed Bps")'''
speed_new = '''          yaml_speed_sensor(model, idx, label, (idx in highspeed_idx), (idx in ifspeed_idx))'''
job = replace_once(job, speed_old, speed_new, "speed generation block")
write(job_path, job)

# Version assertions + permanent regression coverage.
self_test_path = ROOT / "runtime_src/self-test.sh"
test = self_test_path.read_text(encoding="utf-8")
old_version_assert = 'SWITCH_VISION_DISCOVERY_VERSION="2.1.26"'
if test.count(old_version_assert) != 2:
    raise SystemExit(f"ERROR: expected two self-test version assertions, found {test.count(old_version_assert)}")
test = test.replace(old_version_assert, f'SWITCH_VISION_DISCOVERY_VERSION="{VERSION}"')

regression = r'''

# v2.1.27 hardware-validation and speed-contract regressions.
python3 - "$RUNTIME_REGISTRY" "$BASE_DIR/profiles/switch-vision-profiles.yaml" "$BASE_DIR/discovery_job.sh" <<'PYTEST_V2127_HARDWARE'
import json
import sys
from pathlib import Path
import yaml

registry = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
profiles_doc = yaml.safe_load(Path(sys.argv[2]).read_text(encoding="utf-8")) or {}
profiles = profiles_doc.get("profiles", profiles_doc)
job = Path(sys.argv[3]).read_text(encoding="utf-8")
models = {d["model"]: d for d in registry["devices"] if isinstance(d, dict)}
expected = {
    "WS-C2960X-24TS-L",
    "WS-C3560CG-8PC-S",
    "SG500X-24",
    "S5735-L8P4X-A1",
    "S5720-12TP-LI-AC",
}
for model in expected:
    assert models[model]["status"] == "community_validated", model

p3560 = next(p for p in profiles.values() if "WS-C3560CG-8PC-S" in (p.get("model_patterns") or []))
assert p3560["layout"]["rj45_ports"] == 8
assert p3560["layout"]["sfp_1g_ports"] == 2
assert p3560["interface_patterns"]["sfp_1g"] == ["Gi0/9", "Gi0/10", "GigabitEthernet0/9", "GigabitEthernet0/10"]

s5720 = next(p for p in profiles.values() if "S5720-12TP-LI-AC" in (p.get("model_patterns") or []))
assert s5720["layout"]["rj45_ports"] == 8
assert s5720["layout"]["sfp_1g_ports"] == 4
assert s5720["layout"]["sfp_10g_ports"] == 0
assert s5720["physical_speed_caps_mbps"]["sfp_1g"] == 1000
assert 'physical_speed_cap_mbps(model, label)' in job
assert 'model == "S5720-12TP-LI-AC" && label ~ /^SFP 1G /' in job
# Source ordering is the contract: ifHighSpeed must win whenever available.
helper = job[job.index('function yaml_speed_sensor'):job.index('function yaml_interface_sensor')]
assert helper.index('if (has_highspeed)') < helper.index('else if (has_ifspeed)')
assert '1.3.6.1.2.1.31.1.1.1.15.' in helper
assert '1.3.6.1.2.1.2.2.1.5.' in helper

# Every known UniFi model must carry an explicit visual/profile assignment and
# must never fall through to Cisco-specific artwork/profile names.
for model, device in models.items():
    if device.get("vendor") != "Ubiquiti":
        continue
    faceplate = str(device.get("default_faceplate") or "")
    profile = str(device.get("calibration_profile") or "")
    visuals = device.get("visuals") if isinstance(device.get("visuals"), dict) else {}
    assert faceplate and profile, model
    assert visuals.get("recommended_faceplate") == faceplate, model
    assert visuals.get("calibration_profile") == profile, model
    assert "cisco" not in faceplate.lower(), (model, faceplate)
    assert not profile.lower().startswith("cisco_"), (model, profile)
print("Switch Vision Discovery v2.1.27 hardware/status/UniFi contract regression: PASS")
PYTEST_V2127_HARDWARE

# Dell N2128PX-ON physical-front-panel safeguards. Interfaces 29/30 are the
# two physical 10G SFP+ cages. 31/32 can exist in IF-MIB but are not present
# front-panel ports and must stay excluded.
dell_v2127="$tmp_dir/dell-v2127.txt"
cat > "$dell_v2127" <<'EOF_DELL_V2127'
.1.3.6.1.2.1.1.1.0 = STRING: Dell EMC Networking N2128PX-ON, 6.7.1.27
.1.3.6.1.2.1.31.1.1.1.1.25 = STRING: Gi1/0/25
.1.3.6.1.2.1.31.1.1.1.1.26 = STRING: Gi1/0/26
.1.3.6.1.2.1.31.1.1.1.1.29 = STRING: Te1/0/1
.1.3.6.1.2.1.31.1.1.1.1.30 = STRING: Te1/0/2
.1.3.6.1.2.1.31.1.1.1.1.31 = STRING: Te1/0/3
.1.3.6.1.2.1.31.1.1.1.1.32 = STRING: Te1/0/4
.1.3.6.1.2.1.2.2.1.8.31 = INTEGER: notPresent(6)
.1.3.6.1.2.1.2.2.1.8.32 = INTEGER: notPresent(6)
.1.3.6.1.2.1.2.2.1.5.25 = Gauge32: 4294967295
.1.3.6.1.2.1.2.2.1.5.26 = Gauge32: 4294967295
.1.3.6.1.2.1.2.2.1.5.29 = Gauge32: 4294967295
.1.3.6.1.2.1.2.2.1.5.30 = Gauge32: 4294967295
.1.3.6.1.2.1.31.1.1.1.15.25 = Gauge32: 2500
.1.3.6.1.2.1.31.1.1.1.15.26 = Gauge32: 2500
.1.3.6.1.2.1.31.1.1.1.15.29 = Gauge32: 10000
.1.3.6.1.2.1.31.1.1.1.15.30 = Gauge32: 10000
.1.3.6.1.2.1.31.1.1.1.15.31 = Gauge32: 20000
.1.3.6.1.2.1.31.1.1.1.15.32 = Gauge32: 20000
EOF_DELL_V2127
cv_write_capabilities_json "$dell_v2127" "$tmp_dir/dell-v2127-capabilities.json" ""
jq -e '
  ([.interfaces[] | select(.if_index == 29 or .if_index == 30) | select(.media == "sfp_plus" and .physical == true)] | length == 2)
  and ([.interfaces[] | select(.if_index == 31 or .if_index == 32) | select(.physical == true)] | length == 0)
' "$tmp_dir/dell-v2127-capabilities.json" >/dev/null

echo "Switch Vision Discovery v2.1.27 Dell physical/speed safeguard regression: PASS"
'''
if "v2.1.27 hardware-validation and speed-contract regressions" not in test:
    test += regression
write(self_test_path, test)

# Changelog.
changelog_path = ROOT / "switch_vision_discovery" / "CHANGELOG.md"
changelog = changelog_path.read_text(encoding="utf-8")
entry = f'''# Changelog\n\n## v{VERSION} — Hardware validation safeguards\n\n- Promote WS-C2960X-24TS-L, WS-C3560CG-8PC-S, SG500X-24, Huawei S5735-L8P4X-A1, and Huawei S5720-12TP-LI-AC to Community Validated from existing real-hardware evidence.\n- Preserve WS-C3560CG-8PC-S Gi0/9 and Gi0/10 dual-purpose combo-uplink semantics.\n- Keep Huawei S5720-12TP-LI-AC at 8 RJ45 + 4 physical 1G SFP positions and cap generated speed telemetry for those cages at 1000 Mbps when IF-MIB reports an implausible higher value.\n- Strengthen Dell N2128PX-ON regressions for physical 10G uplinks 29/30, exclusion of non-present 31/32, and ifHighSpeed preference over legacy ifSpeed.\n- Add a permanent UniFi registry regression requiring explicit model faceplate/profile assignments and rejecting Cisco-specific visual fallbacks.\n- Preserve existing MQTT topics, saved calibrations, Support My Switch privacy behavior, and unrelated device mappings.\n\n'''
if changelog.startswith("# Changelog\n\n"):
    changelog = entry + changelog[len("# Changelog\n\n"):]
else:
    raise SystemExit("ERROR: unexpected Discovery changelog header")
write(changelog_path, changelog)

print("Prepared Discovery 2.1.27 hardware validation safeguards")
