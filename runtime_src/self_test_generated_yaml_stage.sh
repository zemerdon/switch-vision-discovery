# Switch Vision Discovery self-test generated-YAML regression module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# v2.1.28 generated SNMP2MQTT YAML publication regression. An invalid/empty
# target candidate must never replace an already-valid live handoff file.
yaml_guard="$BASE_DIR/generated_yaml_guard.py"
[ -f "$yaml_guard" ]
valid_yaml="$tmp_dir/generated-valid.yaml"
invalid_yaml="$tmp_dir/generated-invalid.yaml"
live_yaml="$tmp_dir/generated-live.yaml"
cat > "$valid_yaml" <<'YAML_VALID_V2128'
# Switch Vision generated SNMP2MQTT YAML
# Source: Switch Vision Discovery v2.1.28
targets:
  - host: 192.0.2.128
    name: Switch Vision Regression
    version: 2c
    community: public
    sensors:
      - oid: 1.3.6.1.2.1.1.3.0
        name: Regression Uptime
YAML_VALID_V2128
cat > "$invalid_yaml" <<'YAML_INVALID_V2128'
# Switch Vision generated SNMP2MQTT YAML
# Source: Switch Vision Discovery v2.1.28
targets:
YAML_INVALID_V2128
cp "$valid_yaml" "$live_yaml"
valid_sha_before=$(sha256sum "$live_yaml" | awk '{print $1}')
if python3 "$yaml_guard" --publish "$invalid_yaml" "$live_yaml"; then
  echo "ERROR: target-less generated YAML candidate was accepted" >&2
  exit 1
fi
valid_sha_after=$(sha256sum "$live_yaml" | awk '{print $1}')
[ "$valid_sha_before" = "$valid_sha_after" ] || {
  echo "ERROR: invalid generated YAML replaced the live handoff" >&2
  exit 1
}
cp "$valid_yaml" "$tmp_dir/generated-valid-candidate.yaml"
python3 "$yaml_guard" --publish "$tmp_dir/generated-valid-candidate.yaml" "$live_yaml"
grep -Eq '^[[:space:]]*-[[:space:]]+host:[[:space:]]+192\.0\.2\.128$' "$live_yaml"
[ ! -e "$tmp_dir/generated-valid-candidate.yaml" ]
grep -Fq 'candidate_path="${GENERATED_YAML_PATH}.candidate.$$"' "$YAML_STAGE_SOURCE"
grep -Fq 'python3 "$guard" --publish "$candidate_path" "$GENERATED_YAML_PATH"' "$YAML_STAGE_SOURCE"
! grep -Fq '} > "$GENERATED_YAML_PATH"' "$YAML_STAGE_SOURCE"
printf '%s\n' "Switch Vision Discovery v2.1.28 atomic generated-YAML publication: PASS"

# S5720 generator contract: its fallback ifDescr names must still create target
# output and its four physical 1G SFP cages retain the v2.1.27 speed cap.
grep -Fq 'model == "S5720-12TP-LI-AC" && label ~ /(^| )SFP 1G /' "$YAML_STAGE_SOURCE"
grep -Fq 'if (!(idx in ifname)) { ifname[idx]=val; ifname_source[idx]="ifDescr" }' "$YAML_STAGE_SOURCE"
printf '%s\n' "Switch Vision Discovery v2.1.28 S5720 generated-target prerequisites: PASS"

# v2.1.30 Discovery progress-stage regression. Structured current stage must
# beat stale/historical log-tail text so the blue highlight stays on the task
# that is actually running.
python3 - "$SV_HUB_SOURCE" <<'PYTEST_V2130_PROGRESS'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
start = text.index("function discoveryStage(state)")
end = text.index("function updateSteps(state)", start)
fn = text[start:end]
assert "const stage=String(state.stage||'').toLowerCase()" in fn
assert "if(stage.includes('snmp2mqtt handoff')||stage.includes('support my switch')||stage.includes('finaliz'))return 5" in fn
assert "if(stage.includes('generating snmp2mqtt yaml'))return 3" in fn
assert "if(stage.includes('generating dashboard card yaml'))return 4" in fn
assert fn.index("const stage=") < fn.index("const text=")
assert fn.index("snmp2mqtt handoff") < fn.index("generating snmp2mqtt yaml")
assert fn.index("generating snmp2mqtt yaml") < fn.index("dashboard card')||text.includes")
assert ".slice(-3).join(' ')" in fn
print("Switch Vision Discovery v2.1.30 structured progress-stage regression: PASS")
PYTEST_V2130_PROGRESS


# v2.1.31 generated-YAML handoff regression. Current-run metadata captured at
# collection time must be authoritative, failed walks must not enter generation,
# parser/formatter failures must not be hidden by a shell pipeline, and an
# already-invalid live handoff must not survive another failed generation.
python3 - "$BASE_DIR/discovery_job.sh" "$YAML_STAGE_SOURCE" <<'PYTEST_V2131_HANDOFF'
from pathlib import Path
import sys

text = (
    Path(sys.argv[1]).read_text(encoding="utf-8")
    + "\n"
    + Path(sys.argv[2]).read_text(encoding="utf-8")
)
assert 'CURRENT_RUN_TARGETS="${SWITCH_VISION_CURRENT_RUN_TARGETS:-/tmp/switch_vision_current_run_targets_$$.txt}"' in text
assert 'CURRENT_RUN_WALKS="${SWITCH_VISION_CURRENT_RUN_WALKS:-/tmp/switch_vision_current_run_walks_$$.txt}"' in text
assert 'record_current_run_target' in text
assert 'current_run_target_field_for_walk "$walk_file" host' in text
assert 'current_run_target_field_for_walk "$walk_file" prefix' in text
assert 'current_run_target_field_for_walk "$walk_file" community' in text
target_start = text.index("target_for_walk() {")
target_end = text.index("\nmapping_key() {", target_start)
target_host = text.index('current_run_target_field_for_walk "$walk_file" host', target_start, target_end)
target_csv = text.index('if [ -f "$TARGETS_CSV" ]; then', target_start, target_end)
assert target_host < target_csv
assert 'if [ "$result" = "PASS" ] || [ "$result" = "WARN" ]; then' in text
assert 'Current-run parse skipped for failed walk' in text
assert 'generator_raw_tmp="/tmp/switch_vision_generator_raw_$$.yaml"' in text
assert '"$walk_file" | awk' not in text
assert 'Generated YAML source parser failed for:' in text
assert 'Generated YAML formatter failed for:' in text
assert 'quarantine_invalid_generated_live_yaml()' in text
assert 'python3 "$guard" --validate "$GENERATED_YAML_PATH"' in text
assert 'mv "$GENERATED_YAML_PATH" "$quarantine_path"' in text
assert 'Previous invalid generated YAML was quarantined; no broken live handoff remains.' in text
print("Switch Vision Discovery v2.1.31 generated-YAML handoff regression: PASS")
PYTEST_V2131_HANDOFF


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

v2131_current_walks="$v2131_e2e/current-run-walks.txt"
v2131_current_targets="$v2131_e2e/current-run-targets.txt"
rm -f "$v2131_current_walks" "$v2131_current_targets"
if ! PATH="$v2131_e2e/bin:$PATH" \
  SWITCH_VISION_OPTIONS_FILE="$v2131_e2e/options.json" \
  SWITCH_VISION_SHARE_DIR="$v2131_e2e/share" \
  SWITCH_VISION_CAPABILITIES_DIR="$v2131_e2e/capabilities" \
  SWITCH_VISION_CURRENT_RUN_WALKS="$v2131_current_walks" \
  SWITCH_VISION_CURRENT_RUN_TARGETS="$v2131_current_targets" \
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
grep -Fq 'DELL-REGRESSION/live-targeted-snmpwalk.txt' "$v2131_current_targets"
grep -Fq 'S5720-REGRESSION/live-targeted-snmpwalk.txt' "$v2131_current_targets"
grep -Fq '192.0.2.31' "$v2131_current_targets"
grep -Fq '192.0.2.32' "$v2131_current_targets"
grep -Fq 'dellreg' "$v2131_current_targets"
grep -Fq 'huaweireg' "$v2131_current_targets"
grep -Fq 'Generated YAML published atomically:' "$v2131_e2e/snmpwalk.log"
! grep -Fq 'Generated YAML source parser failed' "$v2131_e2e/snmpwalk.log"
! grep -Fq 'no target host entries' "$v2131_e2e/run-output.txt"
rm -f "$v2131_current_walks" "$v2131_current_targets"
printf '%s\n' "Switch Vision Discovery v2.1.31 end-to-end Dell + S5720 current-run handoff: PASS"
