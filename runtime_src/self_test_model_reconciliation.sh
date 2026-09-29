# Switch Vision Discovery self-test model-reconciliation module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# Zyxel XS1930-10 contribution / registry / generator reconciliation regression.
grep -q 'if (model == "XS1930-10") return "experimental"' "$REPORT_STAGE_SOURCE"
grep -q 'profile = "zyxel-xs1930-10"' "$REPORT_STAGE_SOURCE"
grep -q 'model == "XS1930-10" && if_total > 0 && rj45 == 8 && ten == 2' "$REPORT_STAGE_SOURCE"
grep -q 'RJ45 swp00-swp07 ports' "$REPORT_STAGE_SOURCE"
grep -q '10G SFP+ swp08-swp09 uplinks' "$REPORT_STAGE_SOURCE"
grep -q '1.3.6.1.4.1.890.1.15.3.2.4.0' "$YAML_STAGE_SOURCE"
grep -q '1.3.6.1.4.1.890.1.15.3.2.4.3' "$YAML_STAGE_SOURCE"
grep -q 'Q-BRIDGE-MIB PVID' "$REPORT_STAGE_SOURCE"

awk '
  /^  zyxel-xs1930-10:/ { in_zyxel=1; next }
  in_zyxel && /^  [A-Za-z0-9_-]+:/ { exit }
  in_zyxel && /^    status: experimental$/ { found=1 }
  END { exit(found ? 0 : 1) }
' "$BASE_DIR/profiles/switch-vision-profiles.yaml"

printf '%s\n' "Switch Vision Zyxel XS1930-10 contribution regression self-test: PASS"

# Full-walk correctness / authoritative-status regression.
grep -q 'Running split Juniper full SNMP walk' "$BASE_DIR/discovery_job.sh"
grep -q '1.3.6.1.4.1.2636' "$BASE_DIR/discovery_job.sh"
grep -q '# Switch Vision SNMP walk result: warning' "$BASE_DIR/discovery_job.sh"
grep -q 'registry_status == "confirmed"' "$REPORT_STAGE_SOURCE"
grep -q '.device.support_status=(.registry.status' "$REPORT_STAGE_SOURCE"
printf '%s\n' "Switch Vision full-walk/status reconciliation regression: PASS"

# Juniper EX3300 legacy-parser / registry reconciliation regression.
grep -q 'if (model == "Juniper EX3300-48P") return "supported"' "$REPORT_STAGE_SOURCE"
grep -q 'profile = "juniper-ex3300-48p"' "$REPORT_STAGE_SOURCE"
grep -q 'model == "Juniper EX3300-48P" && if_total > 0 && rj45 == 48' "$REPORT_STAGE_SOURCE"
grep -q 'RJ45 ge-0/0/0-47 ports' "$REPORT_STAGE_SOURCE"
grep -q 'SFP/SFP+ uplink cage' "$REPORT_STAGE_SOURCE"
grep -q 'Virtual Chassis support: not validated' "$REPORT_STAGE_SOURCE"

awk '
  /^  juniper-ex3300-48p:/ { in_ex=1; next }
  in_ex && /^  [A-Za-z0-9_-]+:/ { exit }
  in_ex && /^    status: supported$/ { found=1 }
  END { exit(found ? 0 : 1) }
' "$BASE_DIR/profiles/switch-vision-profiles.yaml"

awk '
  /CV_ID_FAMILY="EX3300"/ { in_ex=1 }
  in_ex && /CV_ID_SUPPORT_STATUS="supported"/ { found=1 }
  in_ex && /^[[:space:]]*;;[[:space:]]*$/ { exit }
  END { exit(found ? 0 : 1) }
' "$CV_VENDOR_DIR/known_vendor.sh"

printf '%s\n' "Switch Vision Juniper legacy-parser/registry reconciliation self-test: PASS"

# EX3300 live SFP/SFP+ generation regression.
grep -q 'function yaml_interface_sensor' "$YAML_STAGE_SOURCE"
grep -q 'function yaml_juniper_vlan_candidates_sensor' "$YAML_STAGE_SOURCE"
grep -q 'primary="xe-0/1/" cage' "$YAML_STAGE_SOURCE"
grep -q 'secondary="ge-0/1/" cage' "$YAML_STAGE_SOURCE"
grep -q 'label " Status", "oper_status"' "$YAML_STAGE_SOURCE"
grep -q 'yaml_target_header("Switch Vision " prefix " SFP Status", 5)' "$YAML_STAGE_SOURCE"
grep -q 'label " RX Bytes", "rx_bytes"' "$YAML_STAGE_SOURCE"
grep -q 'label " TX Bytes", "tx_bytes"' "$YAML_STAGE_SOURCE"
grep -q 'label " Admin Status", "admin_status"' "$YAML_STAGE_SOURCE"
grep -q 'label " Speed Mbps", "speed_mbps"' "$YAML_STAGE_SOURCE"
grep -q 'label " Alias", "alias"' "$YAML_STAGE_SOURCE"
grep -q 'sensor_source in {"juniper_ex_vlan", "interface"}' "$SV_HUB_SOURCE"
printf '%s\n' "Switch Vision EX3300 live-interface generation regression: PASS"
