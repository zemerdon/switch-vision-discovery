# Switch Vision Discovery self-test Dell N2128PX-ON contribution module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# v2.1.20 Dell EMC Networking N2128PX-ON contribution regression.
dell_walk="$tmp_dir/dell-n2128px-on.txt"
cat > "$dell_walk" <<'EOF_DELL_N2128PX'
.1.3.6.1.2.1.1.1.0 = STRING: Dell EMC Networking N2128PX-ON, 6.7.1.27, Linux 4.14.174, v1.0.9
.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.674.10895.3077
.1.3.6.1.2.1.31.1.1.1.1.1 = STRING: Gi1/0/1
.1.3.6.1.2.1.31.1.1.1.1.28 = STRING: Gi1/0/28
.1.3.6.1.2.1.31.1.1.1.1.29 = STRING: Te1/0/1
.1.3.6.1.2.1.31.1.1.1.1.30 = STRING: Te1/0/2
.1.3.6.1.2.1.31.1.1.1.1.54 = STRING: Gi2/0/1
.1.3.6.1.2.1.31.1.1.1.1.81 = STRING: Gi2/0/28
.1.3.6.1.2.1.31.1.1.1.1.82 = STRING: Te2/0/1
.1.3.6.1.2.1.31.1.1.1.1.83 = STRING: Te2/0/2
EOF_DELL_N2128PX

(
  . "$BASE_DIR/opt/switch-vision/vendors/interface.sh"
  cv_cap_set_front_panel_profile "$dell_walk"
  [ "$CV_CAP_MODEL_TEXT" = "N2128PX-ON" ]
  [ "$CV_CAP_PLATFORM" = "dell_n2128px_on" ]
  [ "$CV_CAP_RJ45_LIMIT" = "28" ]
  [ "$(cv_interface_class_for_name Gi1/0/1)" = "rj45" ]
  [ "$(cv_interface_class_for_name Gi2/0/28)" = "rj45" ]
  [ "$(cv_interface_class_for_name Te1/0/1)" = "sfp_plus" ]
  [ "$(cv_interface_class_for_name Te2/0/2)" = "sfp_plus" ]
  [ "$(cv_interface_class_for_name Gi1/0/29)" = "other" ]
  [ "$(cv_interface_class_for_name Te1/0/3)" = "other" ]
)

python3 "$BASE_DIR/registry_lookup.py" --registry "$RUNTIME_REGISTRY" --model "N2128PX-ON" --report > "$tmp_dir/dell-registry-report.txt"
grep -q -- '- Registry match: yes' "$tmp_dir/dell-registry-report.txt"
grep -q -- '- Registry status: experimental' "$tmp_dir/dell-registry-report.txt"

python3 - "$RUNTIME_REGISTRY" "$BASE_DIR/profiles/switch-vision-profiles.yaml" <<'PYTEST_V2120_DELL'
import json, sys
from pathlib import Path
import yaml
reg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
prof = yaml.safe_load(Path(sys.argv[2]).read_text(encoding="utf-8"))
profiles = prof.get("profiles", prof)
devices = {d["model"]: d for d in reg["devices"]}
d = devices["N2128PX-ON"]
assert d["status"] == "experimental"
assert d["ports"]["rj45"] == 28
assert d["ports"]["uplinks"] == 2
assert d["ports"]["ten_gigabit_sfp_plus"] == 2
assert d["stack_support"] is True
assert d["tested_firmware"] == ["6.7.1.27", "6.6.0.7"]
assert d["mapping_profile"] == "dell-n2128px-on"
p = profiles["dell-n2128px-on"]
assert p["sys_object_ids"] == ["1.3.6.1.4.1.674.10895.3077"]
assert p["layout"]["rj45_ports"] == 28
assert p["layout"]["sfp_10g_ports"] == 2
assert "Gi{member}/0/{port}" in p["interface_patterns"]["rj45"]
assert "Te{member}/0/1" in p["interface_patterns"]["sfp_10g"]
job = (Path(sys.argv[2]).parents[1] / "discovery_report_stage.sh").read_text(encoding="utf-8")
for required in ('model == "N2128PX-ON"', 'profile = "dell-n2128px-on"', '10G SFP+ uplink', 'manufacturer = "Dell"'):
    assert required in job, required
print("Switch Vision Discovery v2.1.20 Dell N2128PX-ON regression: PASS")
PYTEST_V2120_DELL
