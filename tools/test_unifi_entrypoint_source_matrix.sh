#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUNTIME="$ROOT/runtime_src"
ENTRYPOINT="$RUNTIME/discovery_contract_entrypoint.py"
PREPARE="$RUNTIME/physical_contract_prepare.sh"
REGISTRY="$RUNTIME/opt/switch-vision/devices/supported_devices.json"
HELPER="$RUNTIME/unifi_dashboard_cards.py"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

make_snapshot() {
  path=$1
  mode=${2:-good}
  python3 - "$path" "$mode" <<'PY'
import json, sys
from pathlib import Path
path=Path(sys.argv[1]); mode=sys.argv[2]
def ports(n, connector='RJ45', start=1):
    return [{'idx':i,'connector':connector,'state':'UP'} for i in range(start,start+n)]
good={'id':'ucg-good','model':'UCG Ultra','name':'UCG Good','ports':ports(5)}
devices=[good]
if mode=='conflict':
    devices.append({'id':'ucg-bad','model':'USW Pro Max 24','name':'Conflict Switch','ports':ports(23)+ports(2,'SFPPLUS',24)})
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({'devices':devices}), encoding='utf-8')
PY
}

make_dell_walk() {
  path=$1
  {
    echo '.1.3.6.1.2.1.1.1.0 = STRING: "Dell Networking PowerConnect 5548P"'
    echo '.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.674.10895.3057'
    i=1
    while [ "$i" -le 48 ]; do
      printf '.1.3.6.1.2.1.31.1.1.1.1.%s = STRING: "gi1/0/%s"\n' "$i" "$i"
      printf '.1.3.6.1.2.1.2.2.1.8.%s = INTEGER: up(1)\n' "$i"
      i=$((i+1))
    done
    printf '.1.3.6.1.2.1.31.1.1.1.1.49 = STRING: "te1/0/1"\n'
    printf '.1.3.6.1.2.1.2.2.1.8.49 = INTEGER: up(1)\n'
    printf '.1.3.6.1.2.1.31.1.1.1.1.50 = STRING: "te1/0/2"\n'
    printf '.1.3.6.1.2.1.2.2.1.8.50 = INTEGER: up(1)\n'
  } > "$path"
}

run_entrypoint() {
  case_dir=$1
  options=$2
  legacy=${3:-$RUNTIME/discovery_job.sh}
  SWITCH_VISION_OPTIONS_FILE="$options" \
  SWITCH_VISION_LEGACY_DISCOVERY_SCRIPT="$legacy" \
  SWITCH_VISION_PHYSICAL_PREPARE="$PREPARE" \
  SWITCH_VISION_DEVICE_REGISTRY="$REGISTRY" \
  SWITCH_VISION_UNIFI_DASHBOARD_HELPER="$HELPER" \
  SWITCH_VISION_UNIFI_SNAPSHOT="$case_dir/share/unifi/devices.json" \
  SWITCH_VISION_SHARE_DIR="$case_dir/share" \
  SWITCH_VISION_CAPABILITIES_DIR="$case_dir/capabilities" \
  SWITCH_VISION_RUNTIME_DIR="$RUNTIME" \
  "$ENTRYPOINT"
}

write_options() {
  path=$1; root=$2; input=${3:-$root/missing.txt}; parse=${4:-false}; live=${5:-false}
  cat > "$path" <<EOF
{
  "input_path": "$input",
  "snmpwalks_dir": "$root/walks",
  "report_path": "$root/report.txt",
  "run_snmp_walks": "$live",
  "enable_switch_list": "false",
  "parse_all_walks": "$parse",
  "generate_snmp2mqtt": "true",
  "targets_csv": "$root/targets.csv",
  "last_run_summary_path": "$root/summary.txt",
  "generated_yaml_path": "$root/generated.yaml",
  "generated_card_path": "$root/card.yaml",
  "snmp_log_path": "$root/discovery.log",
  "live_output_dir": "$root/live",
  "live_output_path": "$root/live/live-targeted-snmpwalk.txt",
  "minimum_valid_walk_lines": "1",
  "generate_support_my_switch_bundle": "false"
}
EOF
}

# 1. UniFi-only: zero accepted SNMP walks must still emit the current UniFi card,
# and the zero-SNMP branch must not touch an existing SNMP2MQTT YAML handoff.
one="$TMP/unifi-only"; mkdir -p "$one/share/unifi" "$one/walks" "$one/live"
make_snapshot "$one/share/unifi/devices.json" good
write_options "$one/options.json" "$one"
printf 'sentinel-preserve-me\n' > "$one/generated.yaml"
run_entrypoint "$one" "$one/options.json" > "$one/stdout.txt" 2> "$one/stderr.txt"
grep -Fq 'title: UCG Good' "$one/card.yaml" || { echo 'FAIL: UniFi-only card was erased' >&2; cat "$one/card.yaml" >&2; exit 1; }
grep -Fq 'data_source: unifi_api' "$one/card.yaml" || { echo 'FAIL: UniFi-only data source marker missing' >&2; exit 1; }
[ "$(cat "$one/generated.yaml")" = 'sentinel-preserve-me' ] || { echo 'FAIL: zero-SNMP UniFi branch modified existing SNMP2MQTT YAML' >&2; exit 1; }
echo 'entrypoint source matrix: UniFi-only PASS'

# 2. Mixed current SNMP + UniFi: the real legacy generator must preserve both
# independent sources in one dashboard file.
two="$TMP/mixed"; mkdir -p "$two/share/unifi" "$two/walks" "$two/live"
make_snapshot "$two/share/unifi/devices.json" good
make_dell_walk "$two/dell.txt"
printf 'dell.txt,192.0.2.10,DELL,readonly,,Dell\n' > "$two/targets.csv"
write_options "$two/options.json" "$two" "$two/dell.txt" true false
run_entrypoint "$two" "$two/options.json" > "$two/stdout.txt" 2> "$two/stderr.txt"
python3 - "$two/card.yaml" <<'PY'
from pathlib import Path
import sys
text=Path(sys.argv[1]).read_text(encoding='utf-8')
snmp=text.split('# UniFi API devices',1)[0].count('- type: custom:switch-vision-3650')
if snmp != 1:
    raise SystemExit(f'FAIL: mixed run expected one SNMP card before UniFi section, found {snmp}')
PY
grep -Fq 'title: UCG Good' "$two/card.yaml" || { echo 'FAIL: mixed run lost UniFi card' >&2; cat "$two/card.yaml" >&2; exit 1; }
echo 'entrypoint source matrix: mixed SNMP + UniFi PASS'

# 3. All SNMP collection fails but UniFi remains valid. Simulate a completed
# collector with zero successful current-run records; the wrapper must still
# preserve the independent UniFi card.
three="$TMP/all-snmp-failed"; mkdir -p "$three/share/unifi" "$three/walks" "$three/live"
make_snapshot "$three/share/unifi/devices.json" good
write_options "$three/options.json" "$three" "$three/missing.txt" false true
cat > "$three/fake-live.sh" <<'EOF'
#!/usr/bin/env sh
set -eu
# Intentionally emit no current-run walk/target records: every SNMP attempt failed.
exit 0
EOF
chmod +x "$three/fake-live.sh"
run_entrypoint "$three" "$three/options.json" "$three/fake-live.sh" > "$three/stdout.txt" 2> "$three/stderr.txt"
grep -Fq 'title: UCG Good' "$three/card.yaml" || { echo 'FAIL: all-SNMP-failed path erased valid UniFi card' >&2; cat "$three/card.yaml" >&2; exit 1; }
echo 'entrypoint source matrix: all SNMP failed + UniFi PASS'

# 4. Genuinely empty current sources still produce a safe empty review wrapper,
# not stale cards copied from an earlier run.
four="$TMP/empty"; mkdir -p "$four/share/unifi" "$four/walks" "$four/live"
write_options "$four/options.json" "$four"
printf '%s\n' 'STALE CARD MUST GO' > "$four/card.yaml"
run_entrypoint "$four" "$four/options.json" > "$four/stdout.txt" 2> "$four/stderr.txt"
! grep -Fq 'STALE CARD MUST GO' "$four/card.yaml" || { echo 'FAIL: empty run retained stale dashboard content' >&2; exit 1; }
grep -Fq 'views:' "$four/card.yaml" || { echo 'FAIL: empty run did not emit safe dashboard wrapper' >&2; cat "$four/card.yaml" >&2; exit 1; }
echo 'entrypoint source matrix: genuinely empty PASS'

# 5. One conflicting UniFi device must fail closed without deleting an unrelated
# valid UniFi card from the same snapshot.
five="$TMP/unifi-conflict"; mkdir -p "$five/share/unifi" "$five/walks" "$five/live"
make_snapshot "$five/share/unifi/devices.json" conflict
write_options "$five/options.json" "$five"
run_entrypoint "$five" "$five/options.json" > "$five/stdout.txt" 2> "$five/stderr.txt"
grep -Fq 'title: UCG Good' "$five/card.yaml" || { echo 'FAIL: conflicting UniFi device deleted unrelated valid card' >&2; cat "$five/card.yaml" >&2; exit 1; }
grep -Fq 'TOPOLOGY_CONFLICT' "$five/card.yaml" || { echo 'FAIL: conflicting UniFi topology did not fail closed visibly' >&2; cat "$five/card.yaml" >&2; exit 1; }
if grep -Fq 'title: Conflict Switch' "$five/card.yaml"; then echo 'FAIL: conflicting UniFi topology emitted a card' >&2; cat "$five/card.yaml" >&2; exit 1; fi
echo 'entrypoint source matrix: valid + conflicting UniFi PASS'

echo 'Switch Vision UniFi/physical-contract full-entrypoint source matrix: PASS'
