#!/usr/bin/env sh
set -eu

# Strangler adapter: promote the contribution-tested interface classifier to
# production authority without rewriting the legacy parser/generator in one go.
# Original walks are never modified.

SOURCE_WALK=${1:?source walk required}
NORMALIZED_WALK=${2:?normalized walk required}
CAPABILITIES_JSON=${3:?capabilities json required}
CONTRACT_JSON=${4:?contract json required}

BASE_DIR=${SWITCH_VISION_RUNTIME_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)}
CV_MIB_DATABASE_DIR=${CV_MIB_DATABASE_DIR:-$BASE_DIR/opt/switch-vision/mib_database}
CV_VENDOR_DIR=${CV_VENDOR_DIR:-$BASE_DIR/opt/switch-vision/vendors}
REGISTRY=${SWITCH_VISION_DEVICE_REGISTRY:-$BASE_DIR/opt/switch-vision/devices/supported_devices.json}
RESOLVER=${SWITCH_VISION_PHYSICAL_RESOLVER:-$BASE_DIR/physical_contract.py}
export CV_MIB_DATABASE_DIR CV_VENDOR_DIR

. "$CV_VENDOR_DIR/base.sh"
. "$CV_VENDOR_DIR/generic.sh"
. "$CV_VENDOR_DIR/cisco.sh"
. "$CV_VENDOR_DIR/known_vendor.sh"
. "$CV_VENDOR_DIR/interface.sh"
. "$CV_VENDOR_DIR/loader.sh"

mkdir -p "$(dirname "$NORMALIZED_WALK")" "$(dirname "$CAPABILITIES_JSON")" "$(dirname "$CONTRACT_JSON")"

cv_detect_vendor_identity "$SOURCE_WALK"
cv_write_capabilities_json "$SOURCE_WALK" "$CAPABILITIES_JSON" ""

python3 "$RESOLVER" \
  --capabilities "$CAPABILITIES_JSON" \
  --registry "$REGISTRY" \
  --contract "$CONTRACT_JSON" \
  --walk "$SOURCE_WALK" \
  --normalized-walk "$NORMALIZED_WALK"

# The capability classifier intentionally suppresses alternate logical aliases
# such as Catalyst 3750X Gi/Te names that refer to the same physical cage.  The
# legacy parser would rediscover those names if left visible. Mask only
# physical-looking rows classified as non-physical/other; virtual/logical rows
# keep their original names for VLAN and diagnostics behaviour.
mask_file=$(mktemp)
tmp_walk=$(mktemp)
trap 'rm -f "$mask_file" "$tmp_walk"' EXIT HUP INT TERM
jq -r '
  .interfaces[]?
  | select(.physical == false and .media == "other")
  | select((.name // "") | test("^(gi|gigabitethernet|te|tengigabitethernet|fa|fastethernet)[0-9]"; "i"))
  | (.if_index | tostring)
' "$CAPABILITIES_JSON" > "$mask_file"

awk -v mask_file="$mask_file" '
  BEGIN {
    while ((getline line < mask_file) > 0) if (line ~ /^[0-9]+$/) mask[line+0]=1
    close(mask_file)
  }
  function oid_index(line, left, idx) {
    left=line
    sub(/[[:space:]]*=.*/, "", left)
    sub(/^\./, "", left)
    sub(/^iso\./, "1.", left)
    if (left ~ /^1\.3\.6\.1\.2\.1\.31\.1\.1\.1\.1\.[0-9]+$/ || left ~ /^1\.3\.6\.1\.2\.1\.2\.2\.1\.2\.[0-9]+$/) {
      sub(/^.*\./, "", left)
      return left+0
    }
    return -1
  }
  {
    idx=oid_index($0)
    if (idx >= 0 && (idx in mask)) {
      left=$0
      sub(/[[:space:]]*=.*/, "", left)
      print left " = STRING: \"SwitchVisionNonPhysical" idx "\""
    } else print
  }
' "$NORMALIZED_WALK" > "$tmp_walk"
mv "$tmp_walk" "$NORMALIZED_WALK"
trap 'rm -f "$mask_file" "$tmp_walk"' EXIT HUP INT TERM
