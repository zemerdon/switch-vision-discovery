# Switch Vision Discovery self-test hardware/status/speed contract module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# v2.1.27 hardware-validation and speed-contract regressions.
python3 - "$RUNTIME_REGISTRY" "$BASE_DIR/profiles/switch-vision-profiles.yaml" "$BASE_DIR/discovery_job.sh" "$YAML_STAGE_SOURCE" <<'PYTEST_V2127_HARDWARE'
import json
import sys
from pathlib import Path
import yaml

registry = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
profiles_doc = yaml.safe_load(Path(sys.argv[2]).read_text(encoding="utf-8")) or {}
profiles = profiles_doc.get("profiles", profiles_doc)
job = Path(sys.argv[3]).read_text(encoding="utf-8")
yaml_stage = Path(sys.argv[4]).read_text(encoding="utf-8")
models = {d["model"]: d for d in registry["devices"] if isinstance(d, dict)}
community_validated = {
    "SG500X-24",
    "S5735-L8P4X-A1",
    "S5720-12TP-LI-AC",
}
for model in community_validated:
    assert models[model]["status"] == "community_validated", model

pending_experimental = {
    "WS-C2960X-24TS-L",
    "WS-C3560CG-8PC-S",
}
for model in pending_experimental:
    assert models[model]["status"] == "experimental", model

c2960x24ps = models["WS-C2960X-24PS-L"]
assert c2960x24ps["status"] == "community_validated"
assert c2960x24ps["last_validated_version"] == "3.0.0"
assert c2960x24ps["validation"]["uplinks"] == "confirmed"
assert c2960x24ps["visuals"]["status"] == "community_validated"
assert c2960x24ps["ports"]["gigabit_sfp"] == 4
assert c2960x24ps["ports"]["ten_gigabit_sfp_plus"] == 0
assert models["WS-C2960X-24TS-L"]["validation"]["uplinks"] == "pending"

c2960xr = models["WS-C2960XR-48LPS-I"]
assert c2960xr["status"] == "experimental"
assert c2960xr["ports"]["rj45"] == 48
assert c2960xr["ports"]["uplinks"] == 4
assert c2960xr["ports"]["gigabit_sfp"] == 4
assert c2960xr["ports"]["ten_gigabit_sfp_plus"] == 0
assert c2960xr["mapping_profile"] == "cisco-2960xr-48lps-48p-4sfp"
assert c2960xr["validation"]["uplinks"] == "contribution_confirmed_gi1_0_49_52_1g_sfp"
assert profiles["cisco-2960xr-48lps-48p-4sfp"]["layout"]["sfp_1g_ports"] == 4

p3560 = next(p for p in profiles.values() if "WS-C3560CG-8PC-S" in (p.get("model_patterns") or []))
assert p3560["layout"]["rj45_ports"] == 8
assert p3560["layout"]["sfp_1g_ports"] == 2
assert p3560["interface_patterns"]["sfp_1g"] == ["Gi0/9", "Gi0/10", "GigabitEthernet0/9", "GigabitEthernet0/10"]

s5720 = next(p for p in profiles.values() if "S5720-12TP-LI-AC" in (p.get("model_patterns") or []))
assert s5720["layout"]["rj45_ports"] == 8
assert s5720["layout"]["sfp_1g_ports"] == 4
assert s5720["layout"]["sfp_10g_ports"] == 0
assert s5720["physical_speed_caps_mbps"]["sfp_1g"] == 1000
assert 'physical_speed_cap_mbps(model, label)' in yaml_stage
assert 'model == "S5720-12TP-LI-AC" && label ~ /(^| )SFP 1G /' in yaml_stage
# Source ordering is the contract: ifHighSpeed must win whenever available.
helper = yaml_stage[yaml_stage.index('function yaml_speed_sensor'):yaml_stage.index('function yaml_interface_sensor')]
assert helper.index('if (has_highspeed)') < helper.index('else if (has_ifspeed)')
assert '1.3.6.1.2.1.31.1.1.1.15.' in helper
assert '1.3.6.1.2.1.2.2.1.5.' in helper

# UniFi models that claim dashboard support must carry an explicit visual/profile
# assignment. Detected hardware may intentionally remain visual-pending, but
# profile/faceplate state must stay paired and must never fall through to Cisco
# artwork/profile names.
for model, device in models.items():
    if device.get("vendor") != "Ubiquiti":
        continue
    faceplate = str(device.get("default_faceplate") or "")
    profile = str(device.get("calibration_profile") or "")
    visuals = device.get("visuals") if isinstance(device.get("visuals"), dict) else {}
    if device.get("dashboard_support") is True:
        assert faceplate and profile, model
    assert bool(faceplate) == bool(profile), model
    assert str(visuals.get("recommended_faceplate") or "") == faceplate, model
    assert str(visuals.get("calibration_profile") or "") == profile, model
    if faceplate:
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
