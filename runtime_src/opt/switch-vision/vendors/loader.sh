#!/usr/bin/env sh
CV_VENDOR_LAYER_VERSION="4"
CV_KNOWN_VENDOR_IDS="juniper hp_aruba dell extreme ruckus_brocade mikrotik ubiquiti netgear huawei zyxel"

# interface.sh historically defined model extraction by scanning the complete
# walk. Load the local-identity implementation after interface.sh so neighbour
# identity from LLDP/CDP can never override the local switch model.
if [ -f "$CV_VENDOR_DIR/model_identity.sh" ]; then
  . "$CV_VENDOR_DIR/model_identity.sh"
fi

cv_vendor_database_self_test() {
  required_files="
$CV_MIB_DATABASE_DIR/schema.json
$CV_MIB_DATABASE_DIR/standard/identity.json
$CV_MIB_DATABASE_DIR/standard/interfaces.json
$CV_MIB_DATABASE_DIR/vendors/cisco/vendor.json
$CV_MIB_DATABASE_DIR/vendors/cisco/identity.json
$CV_MIB_DATABASE_DIR/vendors/cisco/products.json
"
  for vendor_id in $CV_KNOWN_VENDOR_IDS; do
    required_files="$required_files
$CV_MIB_DATABASE_DIR/vendors/$vendor_id/vendor.json
$CV_MIB_DATABASE_DIR/vendors/$vendor_id/identity.json
$CV_MIB_DATABASE_DIR/vendors/$vendor_id/sensors.json"
  done
  for f in $required_files; do
    [ -f "$f" ] || return 1
    jq -e . "$f" >/dev/null 2>&1 || return 1
  done
  jq -e '.schema_version == 1' "$CV_MIB_DATABASE_DIR/schema.json" >/dev/null 2>&1 || return 1
  return 0
}

cv_detect_vendor_identity() {
  walk_file="$1"
  CV_ID_DATABASE_STATUS="ready"
  CV_ID_MODEL_HINT=""
  CV_ID_PRODUCT_MATCH="none"
  if ! cv_vendor_database_self_test; then
    CV_ID_DATABASE_STATUS="invalid; existing parser fallback remains active"
    CV_ID_VENDOR="fallback"
    CV_ID_VENDOR_NAME="Existing parser fallback"
    CV_ID_ADAPTER="none"
    CV_ID_FAMILY="Unknown"
    CV_ID_SUPPORT_STATUS="fallback"
    CV_ID_SYS_OBJECT_ID=""
    CV_ID_SYS_DESCR=""
    CV_ID_SYS_NAME=""
    return 0
  fi
  cv_generic_identity "$walk_file"
  if cv_cisco_matches; then
    cv_cisco_identity
    return 0
  fi
  for vendor_id in $CV_KNOWN_VENDOR_IDS; do
    if cv_known_vendor_matches "$vendor_id"; then
      cv_known_vendor_identity "$vendor_id"
      return 0
    fi
  done
}

cv_write_vendor_identity_report() {
  walk_file="$1"
  cv_detect_vendor_identity "$walk_file"
  echo "Vendor knowledge:"
  echo "- Database schema: v1 (identity + interface + sensor candidate knowledge)"
  echo "- Vendor layer: v$CV_VENDOR_LAYER_VERSION"
  echo "- Database status: $CV_ID_DATABASE_STATUS"
  echo "- Adapter: $CV_ID_ADAPTER"
  echo "- Vendor: $CV_ID_VENDOR_NAME ($CV_ID_VENDOR)"
  echo "- sysObjectID: ${CV_ID_SYS_OBJECT_ID:-not found}"
  echo "- sysName: ${CV_ID_SYS_NAME:-not found}"
  echo "- Product family: $CV_ID_FAMILY"
  echo "- Product match: $CV_ID_PRODUCT_MATCH"
  echo "- Support status: $CV_ID_SUPPORT_STATUS"
  if [ -n "${CV_ID_MODEL_HINT:-}" ]; then echo "- Model hint: $CV_ID_MODEL_HINT"; fi
  echo "- Behaviour authority: current Switch Vision parser/generator (knowledge layers are observational only)"
  echo ""
}
