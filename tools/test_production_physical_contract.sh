#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUNTIME="$ROOT/runtime_src"
CV_MIB_DATABASE_DIR="$RUNTIME/opt/switch-vision/mib_database"
CV_VENDOR_DIR="$RUNTIME/opt/switch-vision/vendors"
export CV_MIB_DATABASE_DIR CV_VENDOR_DIR

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
failures=0

note_failure() {
  printf 'FAIL: %s\n' "$1" >&2
  failures=$((failures + 1))
}

make_walk() {
  walk=$1
  sysdescr=$2
  sysoid=$3
  {
    printf '.1.3.6.1.2.1.1.1.0 = STRING: "%s"\n' "$sysdescr"
    printf '.1.3.6.1.2.1.1.2.0 = OID: .%s\n' "$sysoid"
  } > "$walk"
}

append_iface() {
  walk=$1
  idx=$2
  name=$3
  {
    printf '.1.3.6.1.2.1.31.1.1.1.1.%s = STRING: "%s"\n' "$idx" "$name"
    printf '.1.3.6.1.2.1.2.2.1.7.%s = INTEGER: up(1)\n' "$idx"
    printf '.1.3.6.1.2.1.2.2.1.8.%s = INTEGER: up(1)\n' "$idx"
    printf '.1.3.6.1.2.1.31.1.1.1.15.%s = Gauge32: 1000\n' "$idx"
  } >> "$walk"
}

run_case() {
  case_name=$1
  walk=$2
  prefix=$3
  expected_model=$4
  expected_physical=$5

  case_dir="$TMP/$case_name"
  mkdir -p "$case_dir/capabilities" "$case_dir/snmpwalks" "$case_dir/live" "$case_dir/share"
  report="$case_dir/report.txt"
  yaml="$case_dir/generated.yaml"
  card="$case_dir/card.yaml"
  summary="$case_dir/summary.txt"
  log="$case_dir/discovery.log"
  targets="$case_dir/targets.csv"
  options="$case_dir/options.json"
  live_output="$case_dir/live/live-targeted-snmpwalk.txt"

  printf '%s,192.0.2.10,%s,readonly,,%s\n' "$(basename "$walk")" "$prefix" "$case_name" > "$targets"
  cat > "$options" <<EOF
{
  "input_path": "$walk",
  "snmpwalks_dir": "$case_dir/snmpwalks",
  "report_path": "$report",
  "run_snmp_walks": "false",
  "enable_switch_list": "false",
  "parse_all_walks": "true",
  "generate_snmp2mqtt": "true",
  "targets_csv": "$targets",
  "last_run_summary_path": "$summary",
  "generated_yaml_path": "$yaml",
  "generated_card_path": "$card",
  "snmp_log_path": "$log",
  "live_output_dir": "$case_dir/live",
  "live_output_path": "$live_output",
  "generate_support_my_switch_bundle": "false"
}
EOF

  if ! SWITCH_VISION_OPTIONS_FILE="$options" \
       SWITCH_VISION_CAPABILITIES_DIR="$case_dir/capabilities" \
       SWITCH_VISION_SHARE_DIR="$case_dir/share" \
       sh "$RUNTIME/discovery_job.sh" > "$case_dir/stdout.txt" 2> "$case_dir/stderr.txt"; then
    note_failure "$case_name: discovery_job.sh exited non-zero"
    sed -n '1,120p' "$case_dir/stderr.txt" >&2 || true
    return 0
  fi

  actual_model=$(awk -F': ' '/^Model\/platform:/ {print $2; exit}' "$report" 2>/dev/null || true)
  actual_physical=$(awk -F': ' '/^- Physical switch interfaces detected:/ {print $2; exit}' "$report" 2>/dev/null || true)
  actual_mapped=$(awk -F': ' '/^- Mapped physical interfaces:/ {print $2; exit}' "$report" 2>/dev/null || true)
  yaml_model=$(awk -F': ' '/^# Detected model:/ {print $2; exit}' "$yaml" 2>/dev/null || true)
  yaml_status=$(grep -Ec '^  - oid: 1\.3\.6\.1\.2\.1\.2\.2\.1\.8\.[0-9]+$' "$yaml" 2>/dev/null || true)

  printf '%-12s report_model=%-28s physical=%-4s mapped=%-4s yaml_model=%-28s yaml_status=%s\n' \
    "$case_name" "${actual_model:-missing}" "${actual_physical:-missing}" "${actual_mapped:-missing}" "${yaml_model:-missing}" "${yaml_status:-0}"

  [ "$actual_model" = "$expected_model" ] || note_failure "$case_name: report model '$actual_model' != '$expected_model'"
  [ "$actual_physical" = "$expected_physical" ] || note_failure "$case_name: report physical '$actual_physical' != '$expected_physical'"
  [ "$actual_mapped" = "$expected_physical" ] || note_failure "$case_name: mapped physical '$actual_mapped' != '$expected_physical'"
  [ "$yaml_model" = "$expected_model" ] || note_failure "$case_name: YAML model '$yaml_model' != '$expected_model'"
  [ "$yaml_status" = "$expected_physical" ] || note_failure "$case_name: YAML status sensors '$yaml_status' != '$expected_physical'"
}

# Known-good control: this legacy production path already handles the HP numeric
# interface convention. If this fails, the harness/environment is invalid.
hp="$TMP/hp-j8693a.txt"
make_walk "$hp" 'HP J8693A Switch 3500yl-48G' '1.3.6.1.4.1.11.2.3.7.11.69'
i=1
while [ "$i" -le 48 ]; do append_iface "$hp" "$i" "$i"; i=$((i + 1)); done
run_case hp-control "$hp" HP 'HP J8693A Switch 3500yl-48G' 48

# Bernard: exact capability/registry identity is known, but production currently
# fails lowercase gi/te names and therefore emits no physical port telemetry.
dell="$TMP/dell-5548p.txt"
make_walk "$dell" 'Dell Networking PowerConnect 5548P' '1.3.6.1.4.1.674.10895.3057'
idx=1
i=1
while [ "$i" -le 48 ]; do append_iface "$dell" "$idx" "gi1/0/$i"; idx=$((idx + 1)); i=$((i + 1)); done
i=1
while [ "$i" -le 2 ]; do append_iface "$dell" "$idx" "te1/0/$i"; idx=$((idx + 1)); i=$((i + 1)); done
run_case dell-5548p "$dell" DELL 'PowerConnect 5548P' 50

# Bernard: GS1900 uses GigabitEthernet1..24 without slash-separated members.
zyxel="$TMP/zyxel-gs1900.txt"
make_walk "$zyxel" 'Zyxel GS1900-24E' '1.3.6.1.4.1.890.1.5.8.16'
i=1
while [ "$i" -le 24 ]; do append_iface "$zyxel" "$i" "GigabitEthernet$i"; i=$((i + 1)); done
run_case zyxel-gs1900 "$zyxel" ZYXEL 'GS1900-24E' 24

# escapeedv: SG350-20 exposes gi1..gi20. The physical contract is 20 logical
# front-panel positions (16 fixed copper + 2 combo + 2 SFP-only positions).
sg350="$TMP/cisco-sg350.txt"
make_walk "$sg350" 'Cisco SG350-20 20-Port Gigabit Managed Switch' '1.3.6.1.4.1.9.6.1.95.20.1'
i=1
while [ "$i" -le 20 ]; do append_iface "$sg350" "$i" "gi$i"; i=$((i + 1)); done
run_case cisco-sg350 "$sg350" SG350 'SG350-20' 20

# Zayed: each 3750X member has 48 access ports and four network-module cages.
# Gi aliases for cages 1-2 must collapse onto the corresponding Te interfaces,
# giving 52 physical positions per member rather than 54 interface aliases.
c3750x="$TMP/cisco-3750x.txt"
make_walk "$c3750x" 'Cisco IOS Software, C3750E Software, WS-C3750X-48P' '1.3.6.1.4.1.9.1.1226'
idx=1
member=1
while [ "$member" -le 2 ]; do
  port=1
  while [ "$port" -le 48 ]; do append_iface "$c3750x" "$idx" "Gi${member}/0/${port}"; idx=$((idx + 1)); port=$((port + 1)); done
  port=1
  while [ "$port" -le 4 ]; do append_iface "$c3750x" "$idx" "Gi${member}/1/${port}"; idx=$((idx + 1)); port=$((port + 1)); done
  port=1
  while [ "$port" -le 2 ]; do append_iface "$c3750x" "$idx" "Te${member}/1/${port}"; idx=$((idx + 1)); port=$((port + 1)); done
  member=$((member + 1))
done
run_case cisco-3750x "$c3750x" C3750X 'WS-C3750X-48P' 104

if [ "$failures" -ne 0 ]; then
  printf '\nSwitch Vision production physical-contract regression: %s failure(s)\n' "$failures" >&2
  exit 1
fi

echo 'Switch Vision production physical-contract regression: PASS'
