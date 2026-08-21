#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
job_path = ROOT / "runtime_src/discovery_job.sh"
job = job_path.read_text(encoding="utf-8")

# Keep the final source readable after the initial builder patched this call.
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

# Testability only: production defaults remain the normal HAOS /share paths.
old_cap = 'CAPABILITIES_DIR="/share/switch_vision/capabilities"'
new_cap = 'CAPABILITIES_DIR="${SWITCH_VISION_CAPABILITIES_DIR:-/share/switch_vision/capabilities}"'
if old_cap not in job:
    raise SystemExit("ERROR: capabilities directory anchor not found")
job = job.replace(old_cap, new_cap, 1)
old_mkdir = 'mkdir -p "$REPORT_DIR" /share/switch_vision "$CAPABILITIES_DIR" "$SNMPWALKS_DIR" "$(dirname "$GENERATED_YAML_PATH")" "$(dirname "$GENERATED_CARD_PATH")" "$(dirname "$LIVE_LOG_PATH")"'
new_mkdir = 'mkdir -p "$REPORT_DIR" "${SWITCH_VISION_SHARE_DIR:-/share/switch_vision}" "$CAPABILITIES_DIR" "$SNMPWALKS_DIR" "$(dirname "$GENERATED_YAML_PATH")" "$(dirname "$GENERATED_CARD_PATH")" "$(dirname "$LIVE_LOG_PATH")"'
if old_mkdir not in job:
    raise SystemExit("ERROR: Switch Vision share mkdir anchor not found")
job = job.replace(old_mkdir, new_mkdir, 1)

# Root cause of the target-less YAML regression: these literal single quotes
# live inside a shell single-quoted AWK program. They terminated the AWK program
# at shell parse time, making `int`/`min` look like shell pipeline commands.
old_tmpl_mbps = '        if (cap_mbps > 0) print "    template: \'{{ [value | int, " cap_mbps "] | min }}\'"'
new_tmpl_mbps = '        if (cap_mbps > 0) print "    template: \\"{{ [value | int, " cap_mbps "] | min }}\\""'
old_tmpl_bps = '        if (cap_mbps > 0) print "    template: \'{{ [value | int, " (cap_mbps * 1000000) "] | min }}\'"'
new_tmpl_bps = '        if (cap_mbps > 0) print "    template: \\"{{ [value | int, " (cap_mbps * 1000000) "] | min }}\\""'
for old_line, new_line, label in (
    (old_tmpl_mbps, new_tmpl_mbps, "S5720 Mbps template"),
    (old_tmpl_bps, new_tmpl_bps, "S5720 Bps template"),
):
    if old_line not in job:
        raise SystemExit(f"ERROR: {label} anchor not found")
    job = job.replace(old_line, new_line, 1)

# Generated physical labels are prefixed (for example `SW1 SFP 1G 1`), so
# the old /^SFP 1G / expression could never activate the cap.
old_cap_match = '      if (model == "S5720-12TP-LI-AC" && label ~ /^SFP 1G /) return 1000'
new_cap_match = '      if (model == "S5720-12TP-LI-AC" && label ~ /(^| )SFP 1G /) return 1000'
if old_cap_match not in job:
    raise SystemExit("ERROR: S5720 physical speed-cap matcher anchor not found")
job = job.replace(old_cap_match, new_cap_match, 1)
job_path.write_text(job, encoding="utf-8", newline="\n")

self_test_path = ROOT / "runtime_src/self-test.sh"
self_test = self_test_path.read_text(encoding="utf-8")
# Update both historical regressions that intentionally pin this source-level
# contract so they now assert the corrected prefixed-label matcher.
old_assert = 'assert \'model == "S5720-12TP-LI-AC" && label ~ /^SFP 1G /\' in job'
new_assert = 'assert \'model == "S5720-12TP-LI-AC" && label ~ /(^| )SFP 1G /\' in job'
if old_assert not in self_test:
    raise SystemExit("ERROR: v2.1.27 S5720 matcher assertion not found")
self_test = self_test.replace(old_assert, new_assert, 1)
old_grep = 'grep -Fq \'model == "S5720-12TP-LI-AC" && label ~ /^SFP 1G /\' "$BASE_DIR/discovery_job.sh"'
new_grep = 'grep -Fq \'model == "S5720-12TP-LI-AC" && label ~ /(^| )SFP 1G /\' "$BASE_DIR/discovery_job.sh"'
if old_grep not in self_test:
    raise SystemExit("ERROR: v2.1.28 S5720 matcher grep not found")
self_test = self_test.replace(old_grep, new_grep, 1)

regression = r'''

# v2.1.31 end-to-end current-run handoff regression. Run the real Discovery
# engine against deterministic fake Dell N2128PX-ON and Huawei S5720 agents.
# This exercises switch-list walking, current-run metadata capture, the actual
# AWK generator, S5720 ifDescr fallback + 1G speed cap, semantic validation,
# and atomic publication as one flow.
v2131_e2e="$tmp_dir/v2131-e2e"
mkdir -p "$v2131_e2e/bin" "$v2131_e2e/snmpwalks" "$v2131_e2e/capabilities" "$v2131_e2e/share"
cat > "$v2131_e2e/bin/snmpwalk" <<'FAKE_SNMPWALK_V2131'
#!/usr/bin/env sh
case " $* " in
  *" 192.0.2.32 "*)
    cat <<'HUAWEI_WALK_V2131'
.1.3.6.1.2.1.1.1.0 = STRING: Huawei S5720-12TP-LI-AC V200R022C00SPC500
.1.3.6.1.2.1.1.3.0 = Timeticks: (654321) 1:49:03.21
.1.3.6.1.2.1.2.2.1.2.5 = STRING: GigabitEthernet0/0/1
.1.3.6.1.2.1.2.2.1.2.13 = STRING: GigabitEthernet0/0/9
.1.3.6.1.2.1.2.2.1.2.14 = STRING: GigabitEthernet0/0/10
.1.3.6.1.2.1.2.2.1.2.15 = STRING: GigabitEthernet0/0/11
.1.3.6.1.2.1.2.2.1.2.16 = STRING: GigabitEthernet0/0/12
.1.3.6.1.2.1.2.2.1.8.5 = INTEGER: 1
.1.3.6.1.2.1.2.2.1.8.13 = INTEGER: 1
.1.3.6.1.2.1.2.2.1.8.14 = INTEGER: 2
.1.3.6.1.2.1.2.2.1.8.15 = INTEGER: 1
.1.3.6.1.2.1.2.2.1.8.16 = INTEGER: 2
.1.3.6.1.2.1.31.1.1.1.15.5 = Gauge32: 1000
.1.3.6.1.2.1.31.1.1.1.15.13 = Gauge32: 10000
.1.3.6.1.2.1.31.1.1.1.15.14 = Gauge32: 10000
.1.3.6.1.2.1.31.1.1.1.15.15 = Gauge32: 10000
.1.3.6.1.2.1.31.1.1.1.15.16 = Gauge32: 10000
HUAWEI_WALK_V2131
    ;;
  *)
    cat <<'DELL_WALK_V2131'
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
DELL_WALK_V2131
    ;;
esac
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
    },
    {
      "switch_name": "S5720-REGRESSION",
      "display_name": "S5720 Regression",
      "switch_host": "192.0.2.32",
      "sensor_prefix": "huaweireg",
      "snmp_community": "public",
      "enabled": "enabled",
      "walk_mode": "targeted",
      "switch_model": "S5720-12TP-LI-AC"
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
  SWITCH_VISION_SHARE_DIR="$v2131_e2e/share" \
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
grep -Eq '^- host: 192\.0\.2\.32$' "$v2131_e2e/generated-snmp2mqtt.yaml"
grep -Fq 'template: "{{ [value | int, 1000] | min }}"' "$v2131_e2e/generated-snmp2mqtt.yaml"
grep -Fq 'DELL-REGRESSION/live-targeted-snmpwalk.txt' /tmp/switch_vision_current_run_targets.txt
grep -Fq 'S5720-REGRESSION/live-targeted-snmpwalk.txt' /tmp/switch_vision_current_run_targets.txt
grep -Fq '192.0.2.31' /tmp/switch_vision_current_run_targets.txt
grep -Fq '192.0.2.32' /tmp/switch_vision_current_run_targets.txt
grep -Fq 'dellreg' /tmp/switch_vision_current_run_targets.txt
grep -Fq 'huaweireg' /tmp/switch_vision_current_run_targets.txt
grep -Fq 'Generated YAML published atomically:' "$v2131_e2e/snmpwalk.log"
! grep -Fq 'Generated YAML source parser failed' "$v2131_e2e/snmpwalk.log"
! grep -Fq 'no target host entries' "$v2131_e2e/run-output.txt"
rm -f /tmp/switch_vision_current_run_walks.txt /tmp/switch_vision_current_run_targets.txt
printf '%s\n' "Switch Vision Discovery v2.1.31 end-to-end Dell + S5720 current-run handoff: PASS"
'''
if "v2.1.31 end-to-end Dell + S5720 current-run handoff" not in self_test:
    self_test += regression
self_test_path.write_text(self_test, encoding="utf-8", newline="\n")

changelog_path = ROOT / "switch_vision_discovery/CHANGELOG.md"
changelog = changelog_path.read_text(encoding="utf-8")
anchor = "## 2.1.31\n\n"
extra = (
    "- Fix the v2.1.27 S5720 speed-template shell/AWK quoting regression that could abort every SNMP2MQTT generator run, leaving a target-less YAML file; the generator now emits shell-safe quoted templates and surfaces parser-stage failures explicitly.\n"
    "- Correct the S5720 physical 1G SFP speed-cap matcher for prefixed labels (for example `SW1 SFP 1G 1`), so implausible IF-MIB speeds are actually capped at 1000 Mbps.\n"
)
if anchor not in changelog:
    raise SystemExit("ERROR: v2.1.31 changelog anchor not found")
if "v2.1.27 S5720 speed-template shell/AWK quoting regression" not in changelog:
    changelog = changelog.replace(anchor, anchor + extra, 1)
changelog_path.write_text(changelog, encoding="utf-8", newline="\n")

print("Finalized Switch Vision Discovery v2.1.31 root-cause fix and end-to-end regressions")
