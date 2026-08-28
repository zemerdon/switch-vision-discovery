#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUNTIME="$ROOT/runtime_src"
REGISTRY="$RUNTIME/opt/switch-vision/devices/supported_devices.json"
ENTRYPOINT="$RUNTIME/discovery_contract_entrypoint.py"
PREPARE="$RUNTIME/physical_contract_prepare.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

make_dell_walk() {
  path=$1
  ports=$2
  {
    echo '.1.3.6.1.2.1.1.1.0 = STRING: "Dell Networking PowerConnect 5548P"'
    echo '.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.674.10895.3057'
    idx=1
    port=1
    while [ "$port" -le "$ports" ]; do
      printf '.1.3.6.1.2.1.31.1.1.1.1.%s = STRING: "gi1/0/%s"\n' "$idx" "$port"
      printf '.1.3.6.1.2.1.2.2.1.8.%s = INTEGER: up(1)\n' "$idx"
      idx=$((idx + 1)); port=$((port + 1))
    done
    if [ "$ports" -eq 48 ]; then
      port=1
      while [ "$port" -le 2 ]; do
        printf '.1.3.6.1.2.1.31.1.1.1.1.%s = STRING: "te1/0/%s"\n' "$idx" "$port"
        printf '.1.3.6.1.2.1.2.2.1.8.%s = INTEGER: up(1)\n' "$idx"
        idx=$((idx + 1)); port=$((port + 1))
      done
    fi
  } > "$path"
}

run_entrypoint() {
  case_dir=$1
  options=$2
  SWITCH_VISION_OPTIONS_FILE="$options" \
  SWITCH_VISION_LEGACY_DISCOVERY_SCRIPT="$RUNTIME/discovery_job.sh" \
  SWITCH_VISION_PHYSICAL_PREPARE="$PREPARE" \
  SWITCH_VISION_DEVICE_REGISTRY="$REGISTRY" \
  SWITCH_VISION_CAPABILITIES_DIR="$case_dir/published-capabilities" \
  SWITCH_VISION_RUNTIME_DIR="$RUNTIME" \
  python3 "$ENTRYPOINT"
}

# Positive path: the exact Web-UI entrypoint must repair the production parser
# boundary and preserve the public report/YAML contract.
ok="$TMP/ok"
mkdir -p "$ok/walks" "$ok/live" "$ok/share"
walk="$ok/dell.txt"
make_dell_walk "$walk" 48
printf '%s,192.0.2.10,DELL,readonly,,Dell\n' "$(basename "$walk")" > "$ok/targets.csv"
cat > "$ok/options.json" <<EOF
{
  "input_path": "$walk",
  "snmpwalks_dir": "$ok/walks",
  "report_path": "$ok/report.txt",
  "run_snmp_walks": "false",
  "enable_switch_list": "false",
  "parse_all_walks": "true",
  "generate_snmp2mqtt": "true",
  "targets_csv": "$ok/targets.csv",
  "last_run_summary_path": "$ok/summary.txt",
  "generated_yaml_path": "$ok/generated.yaml",
  "generated_card_path": "$ok/card.yaml",
  "snmp_log_path": "$ok/discovery.log",
  "live_output_dir": "$ok/live",
  "live_output_path": "$ok/live/live-targeted-snmpwalk.txt",
  "generate_support_my_switch_bundle": "false"
}
EOF
run_entrypoint "$ok" "$ok/options.json" > "$ok/stdout.txt" 2> "$ok/stderr.txt"
grep -Fq 'Model/platform: PowerConnect 5548P' "$ok/report.txt"
grep -Fq -- '- Physical switch interfaces detected: 50' "$ok/report.txt"
grep -Fq -- '- Mapped physical interfaces: 50' "$ok/report.txt"
[ "$(grep -Ec '^  - oid: 1\.3\.6\.1\.2\.1\.2\.2\.1\.8\.[0-9]+$' "$ok/generated.yaml")" -eq 50 ]
grep -Fq '# Detected model: PowerConnect 5548P' "$ok/generated.yaml"
find "$ok/published-capabilities" -name '*-physical-contract.json' -type f | grep -q .

echo 'entrypoint positive path: PASS'

# Negative path: an exact registered model with incomplete physical evidence
# must fail closed rather than silently drawing a smaller switch.
conflict="$TMP/conflict"
mkdir -p "$conflict/walks" "$conflict/live" "$conflict/share"
conflict_walk="$conflict/dell-incomplete.txt"
make_dell_walk "$conflict_walk" 47
printf '%s,192.0.2.11,DELLBAD,readonly,,DellBad\n' "$(basename "$conflict_walk")" > "$conflict/targets.csv"
cat > "$conflict/options.json" <<EOF
{
  "input_path": "$conflict_walk",
  "snmpwalks_dir": "$conflict/walks",
  "report_path": "$conflict/report.txt",
  "run_snmp_walks": "false",
  "enable_switch_list": "false",
  "parse_all_walks": "true",
  "generate_snmp2mqtt": "true",
  "targets_csv": "$conflict/targets.csv",
  "last_run_summary_path": "$conflict/summary.txt",
  "generated_yaml_path": "$conflict/generated.yaml",
  "generated_card_path": "$conflict/card.yaml",
  "snmp_log_path": "$conflict/discovery.log",
  "live_output_dir": "$conflict/live",
  "live_output_path": "$conflict/live/live-targeted-snmpwalk.txt",
  "generate_support_my_switch_bundle": "false"
}
EOF
if run_entrypoint "$conflict" "$conflict/options.json" > "$conflict/stdout.txt" 2> "$conflict/stderr.txt"; then
  echo 'FAIL: topology conflict unexpectedly succeeded' >&2
  exit 1
fi
grep -Fq 'Topology conflict' "$conflict/stdout.txt"
[ ! -s "$conflict/generated.yaml" ] || {
  echo 'FAIL: topology conflict produced final YAML' >&2
  exit 1
}

echo 'entrypoint topology-conflict guard: PASS'
echo 'Switch Vision Discovery physical-contract entrypoint: PASS'
