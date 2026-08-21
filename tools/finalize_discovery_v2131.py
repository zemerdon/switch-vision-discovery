#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
job_path = ROOT / "runtime_src/discovery_job.sh"
job = job_path.read_text(encoding="utf-8")
old = '      record_current_run_target         "$LIVE_OUTPUT_PATH"         "${SELECTED_SWITCH:-${LIVE_SWITCH_LABEL:-}}"         "$LIVE_SWITCH_IP"         "${DEFAULT_PREFIX:-${LIVE_SWITCH_LABEL:-SW}}"         "$LIVE_SNMP_COMMUNITY" ||         echo "WARNING: current-run target metadata could not be recorded for $LIVE_OUTPUT_PATH" >> "$LIVE_LOG_PATH"'
new = '''      record_current_run_target \\
        "$LIVE_OUTPUT_PATH" \\
        "${SELECTED_SWITCH:-${LIVE_SWITCH_LABEL:-}}" \\
        "$LIVE_SWITCH_IP" \\
        "${DEFAULT_PREFIX:-${LIVE_SWITCH_LABEL:-SW}}" \\
        "$LIVE_SNMP_COMMUNITY" || \\
        echo "WARNING: current-run target metadata could not be recorded for $LIVE_OUTPUT_PATH" >> "$LIVE_LOG_PATH"'''
if old not in job:
    raise SystemExit("ERROR: collapsed current-run metadata call not found")
job = job.replace(old, new, 1)
old_cap = 'CAPABILITIES_DIR="/share/switch_vision/capabilities"'
new_cap = 'CAPABILITIES_DIR="${SWITCH_VISION_CAPABILITIES_DIR:-/share/switch_vision/capabilities}"'
if old_cap not in job:
    raise SystemExit("ERROR: capabilities directory anchor not found")
job = job.replace(old_cap, new_cap, 1)
job_path.write_text(job, encoding="utf-8", newline="\n")

self_test_path = ROOT / "runtime_src/self-test.sh"
self_test = self_test_path.read_text(encoding="utf-8")
regression = r'''

# v2.1.31 end-to-end current-run handoff regression. Run the real Discovery
# engine against a deterministic fake Dell N2128PX-ON SNMP agent. This must
# exercise switch-list walking, current-run metadata capture, the real YAML
# generator, semantic validation, and atomic publication as one flow.
v2131_e2e="$tmp_dir/v2131-e2e"
mkdir -p "$v2131_e2e/bin" "$v2131_e2e/snmpwalks" "$v2131_e2e/capabilities"
cat > "$v2131_e2e/bin/snmpwalk" <<'FAKE_SNMPWALK_V2131'
#!/usr/bin/env sh
cat <<'WALK_V2131'
.1.3.6.1.2.1.1.1.0 = STRING: Dell EMC Networking N2128PX-ON, 6.7.1.27, Linux 4.14.174, v1.0.9
.1.3.6.1.2.1.1.3.0 = Timeticks: (123456) 0:20:34.56
.1.3.6.1.2.1.31.1.1.1.1.1 = STRING: Gi1/0/1
.1.3.6.1.2.1.31.1.1.1.1.28 = STRING: Gi1/0/28
.1.3.6.1.2.1.31.1.1.1.1.29 = STRING: Te1/0/1
.1.3.6.1.2.1.31.1.1.1.1.30 = STRING: Te1/0/2
.1.3.6.1.2.1.2.2.1.8.1 = INTEGER: 1
.1.3.6.1.2.1.2.2.1.8.28 = INTEGER: 2
.1.3.6.1.2.1.2.2.1.8.29 = INTEGER: 1
.1.3.6.1.2.1.2.2.1.8.30 = INTEGER: 2
.1.3.6.1.2.1.31.1.1.1.15.1 = Gauge32: 1000
.1.3.6.1.2.1.31.1.1.1.15.28 = Gauge32: 2500
.1.3.6.1.2.1.31.1.1.1.15.29 = Gauge32: 10000
.1.3.6.1.2.1.31.1.1.1.15.30 = Gauge32: 10000
WALK_V2131
FAKE_SNMPWALK_V2131
chmod +x "$v2131_e2e/bin/snmpwalk"

cat > "$v2131_e2e/options.json" <<JSON_V2131
{
  "input_path": "$v2131_e2e/legacy-unused.txt",
  "snmpwalks_dir": "$v2131_e2e/snmpwalks",
  "report_path": "$v2131_e2e/discovery-report.txt",
  "run_snmp_walks": "true",
  "enable_switch_list": "true",
  "switches": [
    {
      "switch_name": "DELL-REGRESSION",
      "display_name": "Dell Regression",
      "switch_host": "192.0.2.31",
      "sensor_prefix": "dellreg",
      "snmp_community": "public",
      "enabled": "enabled",
      "walk_mode": "targeted",
      "switch_model": "N2128PX-ON"
    }
  ],
  "stack_member_prefixes": [],
  "parse_all_walks": "false",
  "generate_snmp2mqtt": "true",
  "clean_output_before_walk": "false",
  "targets_csv": "$v2131_e2e/no-import.csv",
  "last_run_summary_path": "$v2131_e2e/last-run.txt",
  "generated_yaml_path": "$v2131_e2e/generated-snmp2mqtt.yaml",
  "generated_card_path": "$v2131_e2e/generated-dashboard-card.yaml",
  "snmp_timeout": "1",
  "snmp_retries": "0",
  "snmp_log_path": "$v2131_e2e/snmpwalk.log",
  "minimum_valid_walk_lines": "1"
}
JSON_V2131

rm -f /tmp/switch_vision_current_run_walks.txt /tmp/switch_vision_current_run_targets.txt
if ! PATH="$v2131_e2e/bin:$PATH" \
  SWITCH_VISION_OPTIONS_FILE="$v2131_e2e/options.json" \
  SWITCH_VISION_CAPABILITIES_DIR="$v2131_e2e/capabilities" \
  CV_MIB_DATABASE_DIR="$RUNTIME_DATA_DIR/mib_database" \
  CV_VENDOR_DIR="$RUNTIME_DATA_DIR/vendors" \
  sh "$BASE_DIR/discovery_job.sh" > "$v2131_e2e/run-output.txt" 2>&1; then
  echo "ERROR: v2.1.31 end-to-end Discovery process failed" >&2
  cat "$v2131_e2e/run-output.txt" >&2 || true
  cat "$v2131_e2e/snmpwalk.log" >&2 || true
  exit 1
fi

if ! python3 "$BASE_DIR/generated_yaml_guard.py" --validate "$v2131_e2e/generated-snmp2mqtt.yaml"; then
  echo "ERROR: v2.1.31 end-to-end generated YAML validation failed" >&2
  cat "$v2131_e2e/run-output.txt" >&2 || true
  cat "$v2131_e2e/snmpwalk.log" >&2 || true
  cat "$v2131_e2e/generated-snmp2mqtt.yaml" >&2 || true
  exit 1
fi
grep -Eq '^- host: 192\.0\.2\.31$' "$v2131_e2e/generated-snmp2mqtt.yaml"
grep -Fq 'DELL-REGRESSION/live-targeted-snmpwalk.txt' /tmp/switch_vision_current_run_targets.txt
grep -Fq '192.0.2.31' /tmp/switch_vision_current_run_targets.txt
grep -Fq 'dellreg' /tmp/switch_vision_current_run_targets.txt
grep -Fq 'Generated YAML published atomically:' "$v2131_e2e/snmpwalk.log"
! grep -Fq 'no target host entries' "$v2131_e2e/run-output.txt"
rm -f /tmp/switch_vision_current_run_walks.txt /tmp/switch_vision_current_run_targets.txt
printf '%s\n' "Switch Vision Discovery v2.1.31 end-to-end current-run handoff: PASS"
'''
if "v2.1.31 end-to-end current-run handoff" not in self_test:
    self_test += regression
self_test_path.write_text(self_test, encoding="utf-8", newline="\n")
print("Finalized Switch Vision Discovery v2.1.31 end-to-end regression")
