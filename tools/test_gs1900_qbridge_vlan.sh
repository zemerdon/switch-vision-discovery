#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/runtime_src/discovery_yaml_stage.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

make_walk() {
  path="$1"
  include_untagged="$2"
  mkdir -p "$(dirname "$path")"
  {
    echo '.1.3.6.1.2.1.1.1.0 = STRING: GS1900-8'
    echo '.1.3.6.1.4.1.890.1.15.3.1.11.0 = STRING: "GS1900-8"'
    i=1
    while [ "$i" -le 8 ]; do
      echo ".1.3.6.1.2.1.31.1.1.1.1.$i = STRING: GigabitEthernet$i"
      echo ".1.3.6.1.2.1.17.1.4.1.2.$i = INTEGER: $i"
      echo ".1.3.6.1.2.1.17.7.1.4.5.1.1.$i = Gauge32: 1"
      i=$((i + 1))
    done
    echo '.1.3.6.1.2.1.17.7.1.4.2.1.4.0.1 = Hex-STRING: FF'
    echo '.1.3.6.1.2.1.17.7.1.4.2.1.4.0.10 = Hex-STRING: 45'
    echo '.1.3.6.1.2.1.17.7.1.4.2.1.4.0.20 = Hex-STRING: 40'
    echo '.1.3.6.1.2.1.17.7.1.4.3.1.2.1 = Hex-STRING: FF'
    echo '.1.3.6.1.2.1.17.7.1.4.3.1.2.10 = Hex-STRING: 45'
    echo '.1.3.6.1.2.1.17.7.1.4.3.1.2.20 = Hex-STRING: 40'
    if [ "$include_untagged" = "yes" ]; then
      echo '.1.3.6.1.2.1.17.7.1.4.3.1.4.1 = Hex-STRING: FF'
      echo '.1.3.6.1.2.1.17.7.1.4.3.1.4.10 = Hex-STRING: 01'
      echo '.1.3.6.1.2.1.17.7.1.4.3.1.4.20 = Hex-STRING: 00'
    fi
  } > "$path"
}

LIVE_LOG_PATH="$TMP/live.log"
walk="$TMP/GS1900-8/live-full-snmpwalk.txt"
out="$TMP/generated.yaml"
make_walk "$walk" yes
write_generated_yaml_for_walk "$walk" "192.0.2.85" "swz1" "public" > "$out"

grep -F '# Detected model: GS1900-8' "$out" >/dev/null
grep -F 'device_manufacturer: Zyxel' "$out" >/dev/null
grep -F '# Stack-safe polling: 1 member(s), 8 physical interfaces' "$out" >/dev/null
grep -F 'name: Switch Vision swz1 Q-BRIDGE VLAN State' "$out" >/dev/null
[ "$(grep -c 'source: qbridge_vlan' "$out")" -eq 40 ]
[ "$(grep -c 'interface: GigabitEthernet' "$out")" -eq 40 ]
! grep -F 'interface: Gi1/0/' "$out" >/dev/null
grep -F 'name: swz1 Port 2 Native VLAN' "$out" >/dev/null
grep -F 'name: swz1 Port 2 VLANs' "$out" >/dev/null
grep -F 'name: swz1 Port 2 Tagged VLANs' "$out" >/dev/null
grep -F 'name: swz1 Port 6 VLANs' "$out" >/dev/null
grep -F 'name: swz1 Port 8 Untagged VLANs' "$out" >/dev/null
grep -F '# Q-BRIDGE derived VLAN sensors emitted: 40' "$out" >/dev/null
PYTHONPATH="$ROOT/runtime_src" python3 - "$out" <<'PY'
import sys
from pathlib import Path
import support_web
result = support_web._validate_snmp2mqtt_yaml(Path(sys.argv[1]))
assert result["valid"] is True, result
PY

incomplete="$TMP/GS1900-8-incomplete/live-full-snmpwalk.txt"
incomplete_out="$TMP/incomplete.yaml"
make_walk "$incomplete" no
write_generated_yaml_for_walk "$incomplete" "192.0.2.86" "swz2" "public" > "$incomplete_out"

! grep -F 'source: qbridge_vlan' "$incomplete_out" >/dev/null
grep -F '# Q-BRIDGE derived VLAN sensors skipped:' "$incomplete_out" >/dev/null
grep -F 'static untagged rows=0' "$incomplete_out" >/dev/null

echo "GS1900-8 Q-BRIDGE VLAN generation regression: PASS"
