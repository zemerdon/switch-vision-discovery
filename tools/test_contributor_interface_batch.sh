#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BASE_DIR="$ROOT/runtime_src"
CV_MIB_DATABASE_DIR="$BASE_DIR/opt/switch-vision/mib_database"
CV_VENDOR_DIR="$BASE_DIR/opt/switch-vision/vendors"
REGISTRY="$BASE_DIR/opt/switch-vision/devices/supported_devices.json"
DISCOVERY_JOB="$BASE_DIR/discovery_job.sh"
export CV_MIB_DATABASE_DIR CV_VENDOR_DIR

. "$CV_VENDOR_DIR/base.sh"
. "$CV_VENDOR_DIR/generic.sh"
. "$CV_VENDOR_DIR/cisco.sh"
. "$CV_VENDOR_DIR/known_vendor.sh"
. "$CV_VENDOR_DIR/interface.sh"
. "$CV_VENDOR_DIR/loader.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

make_ifname_walk() {
  walk=$1
  sysdescr=$2
  sysoid=$3
  shift 3
  {
    printf '.1.3.6.1.2.1.1.1.0 = STRING: "%s"\n' "$sysdescr"
    printf '.1.3.6.1.2.1.1.2.0 = OID: .%s\n' "$sysoid"
    idx=1
    for ifname in "$@"; do
      printf '.1.3.6.1.2.1.31.1.1.1.1.%s = STRING: "%s"\n' "$idx" "$ifname"
      idx=$((idx + 1))
    done
  } > "$walk"
}

# Dell PowerConnect 5548P: 48 lowercase Gi access ports + 2 lowercase Te uplinks.
set --
i=1
while [ "$i" -le 48 ]; do set -- "$@" "gi1/0/$i"; i=$((i + 1)); done
set -- "$@" "te1/0/1" "te1/0/2"
make_ifname_walk "$TMP/dell.txt" "Dell Networking PowerConnect 5548P" "1.3.6.1.4.1.674.10895.3057" "$@"
cv_detect_vendor_identity "$TMP/dell.txt"
[ "$CV_ID_VENDOR" = "dell" ]
[ "$CV_ID_MODEL_HINT" = "PowerConnect 5548P" ]
cv_write_capabilities_json "$TMP/dell.txt" "$TMP/dell.json" ""
jq -e '(.device.model_text == "PowerConnect 5548P") and (.summary.physical_count == 50) and (.summary.rj45_count == 48) and (.summary.sfp_plus_count == 2)' "$TMP/dell.json" >/dev/null

# Catalyst 3750X-48P two-member stack. Gi module aliases 1/1/1-2 and 2/1/1-2
# are suppressed when corresponding Te names exist; Gi */1/3-4 remain 1G SFP.
set --
member=1
while [ "$member" -le 2 ]; do
  port=1
  while [ "$port" -le 48 ]; do set -- "$@" "Gi${member}/0/${port}"; port=$((port + 1)); done
  port=1
  while [ "$port" -le 4 ]; do set -- "$@" "Gi${member}/1/${port}"; port=$((port + 1)); done
  set -- "$@" "Te${member}/1/1" "Te${member}/1/2"
  member=$((member + 1))
done
make_ifname_walk "$TMP/c3750x.txt" "Cisco IOS Software, C3750E Software, WS-C3750X-48P" "1.3.6.1.4.1.9.1.1226" "$@"
cv_detect_vendor_identity "$TMP/c3750x.txt"
[ "$CV_ID_VENDOR" = "cisco" ]
[ "$CV_ID_MODEL_HINT" = "WS-C3750X-48P" ]
cv_write_capabilities_json "$TMP/c3750x.txt" "$TMP/c3750x.json" ""
jq -e '(.device.model_text == "WS-C3750X-48P") and (.summary.physical_count == 104) and (.summary.rj45_count == 96) and (.summary.sfp_count == 4) and (.summary.sfp_plus_count == 4)' "$TMP/c3750x.json" >/dev/null

# Cisco SG350-20: 16 fixed copper + 2 dual-personality positions + 2 SFP.
set --
i=1
while [ "$i" -le 20 ]; do set -- "$@" "gi$i"; i=$((i + 1)); done
make_ifname_walk "$TMP/sg350.txt" "Cisco SG350-20 20-Port Gigabit Managed Switch" "1.3.6.1.4.1.9.6.1.95.20.1" "$@"
cv_detect_vendor_identity "$TMP/sg350.txt"
[ "$CV_ID_VENDOR" = "cisco" ]
[ "$CV_ID_MODEL_HINT" = "SG350-20" ]
cv_write_capabilities_json "$TMP/sg350.txt" "$TMP/sg350.json" ""
jq -e '(.device.model_text == "SG350-20") and (.summary.physical_count == 20) and (.summary.rj45_count == 16) and (.summary.sfp_count == 2) and (.summary.uplink_count == 4) and ([.interfaces[] | select(.media == "uplink")] | length == 2)' "$TMP/sg350.json" >/dev/null

# Zyxel GS1900-24E identity is now exact; its existing generic interface parser
# remains authoritative because the contributed walk already classified 24 RJ45.
make_ifname_walk "$TMP/gs1900.txt" "Zyxel GS1900-24E" "1.3.6.1.4.1.890.1.5.8.16" "GigabitEthernet1" "GigabitEthernet24"
cv_detect_vendor_identity "$TMP/gs1900.txt"
[ "$CV_ID_VENDOR" = "zyxel" ]
[ "$CV_ID_MODEL_HINT" = "GS1900-24E" ]
model=$(cv_cap_extract_model_text "$TMP/gs1900.txt")
[ "$model" = "GS1900-24E" ]

# Anonymous UniFi SNMP evidence: compact model strings and 0/N front-panel names.
set --
i=1
while [ "$i" -le 28 ]; do set -- "$@" "0/$i"; i=$((i + 1)); done
make_ifname_walk "$TMP/usw-hd24.txt" "USWProHD24PoE" "1.3.6.1.4.1.8072.3.2.10" "$@"
cv_detect_vendor_identity "$TMP/usw-hd24.txt"
[ "$CV_ID_VENDOR" = "ubiquiti" ]
[ "$CV_ID_MODEL_HINT" = "USW Pro HD 24 PoE" ]
cv_write_capabilities_json "$TMP/usw-hd24.txt" "$TMP/usw-hd24.json" ""
jq -e '(.device.model_text == "USW Pro HD 24 PoE") and (.summary.physical_count == 28) and (.summary.rj45_count == 24) and (.summary.sfp_plus_count == 4)' "$TMP/usw-hd24.json" >/dev/null

set --
i=1
while [ "$i" -le 10 ]; do set -- "$@" "0/$i"; i=$((i + 1)); done
make_ifname_walk "$TMP/usw-xg8.txt" "USWProXG8PoE" "1.3.6.1.4.1.8072.3.2.10" "$@"
cv_detect_vendor_identity "$TMP/usw-xg8.txt"
[ "$CV_ID_VENDOR" = "ubiquiti" ]
[ "$CV_ID_MODEL_HINT" = "USW Pro XG 8 PoE" ]
cv_write_capabilities_json "$TMP/usw-xg8.txt" "$TMP/usw-xg8.json" ""
jq -e '(.device.model_text == "USW Pro XG 8 PoE") and (.summary.physical_count == 10) and (.summary.rj45_count == 8) and (.summary.sfp_plus_count == 2)' "$TMP/usw-xg8.json" >/dev/null

# Negative guardrails: the unusual names above are not generic physical rules.
CV_CAP_MODEL_TEXT="Generic Linux"
CV_CAP_PLATFORM="generic"
CV_CAP_FRONT_PANEL_AWARE="false"
[ "$(cv_interface_class_for_name '0/1')" = "other" ]
[ "$(cv_interface_class_for_name 'gi1/0/1')" = "other" ]
[ "$(cv_interface_class_for_name '17')" = "other" ]

# Anonymous HP evidence: both generated-card branches must bind the J8693A four
# dual-personality positions to the `uplink_N_status` entities actually emitted
# by Discovery, rather than the generic sfp_10g template.
hp_binding='*J8693A*|*3500yl-48G*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_uplink_{port}_status" ;;'
[ "$(grep -Fc "$hp_binding" "$DISCOVERY_JOB")" -eq 2 ]

# Registry contracts distilled from anonymous contributor evidence. Match model
# identity canonically because older exact entries legitimately use SKU dashes
# while newer display names may use spaces. Raw evidence never enters Git.
jq -e '
  def canon: ascii_downcase | gsub("[^a-z0-9]"; "");
  def dev($m): ($m | canon) as $target | [.devices[] | select((.model | canon) == $target)][0];
  (dev("PowerConnect 5548P") | .status == "experimental" and .ports.rj45 == 48 and .ports.ten_gigabit_sfp_plus == 2) and
  (dev("GS1900-24E") | .status == "experimental" and .ports.rj45 == 24) and
  (dev("WS-C3750X-48P") | .status == "experimental" and .ports.rj45 == 48 and .stack_support == true) and
  (dev("SG350-20") | .status == "experimental" and .ports.rj45 == 16 and .ports.uplinks == 4) and
  (dev("HP J8693A Switch 3500yl-48G") | .status == "experimental" and .ports.rj45 == 44 and .ports.uplinks == 4) and
  (dev("USW Pro HD 24 PoE") | .status == "experimental" and .ports.rj45 == 24 and .ports.ten_gigabit_sfp_plus == 4) and
  (dev("USW Pro XG 8 PoE") | .status == "experimental" and (.contributions | map(.id) | index("evidence-unifi-pro-xg8-snmp-a")) != null) and
  (dev("USW Aggregation") | .status == "experimental" and .unifi_api_port_map.rj45 == [] and .unifi_api_port_map.sfp == [1,2,3,4,5,6,7,8]) and
  (dev("USW Enterprise 24 PoE") | .status == "experimental" and .unifi_api_port_map.rj45 == [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24] and .unifi_api_port_map.sfp == [25,26]) and
  (dev("USW Flex 2.5G 5") | .status == "experimental" and .unifi_api_port_map.rj45 == [1,2,3,4,5]) and
  (dev("USW WAN") | .status == "experimental" and .ports.rj45 == 1 and .ports.ten_gigabit_sfp_plus == 3 and .unifi_api_port_map.rj45 == [4] and .unifi_api_port_map.sfp == [1,2,3]) and
  (dev("USW Enterprise 8 PoE") | (.contributions | map(.id) | index("evidence-unifi-enterprise8-refresh-a")) != null) and
  (dev("USW Flex Mini") | (.contributions | map(.id) | index("evidence-unifi-flex-mini-refresh-a")) != null)
' "$REGISTRY" >/dev/null

echo 'Switch Vision contributor interface batch regression: PASS'
