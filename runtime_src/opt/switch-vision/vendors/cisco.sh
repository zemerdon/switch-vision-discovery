#!/usr/bin/env sh
cv_cisco_matches() {
  prefix=$(jq -r '.detection.sys_object_id_prefix // empty' "$CV_MIB_DATABASE_DIR/vendors/cisco/identity.json" 2>/dev/null)
  case "${CV_ID_SYS_OBJECT_ID:-}" in
    "$prefix"*) return 0 ;;
  esac
  printf '%s' "${CV_ID_SYS_DESCR:-}" | grep -Eqi 'Cisco|Catalyst'
}

cv_cisco_identity() {
  vendor_db="$CV_MIB_DATABASE_DIR/vendors/cisco/vendor.json"
  products_db="$CV_MIB_DATABASE_DIR/vendors/cisco/products.json"
  CV_ID_VENDOR=$(jq -r '.id // "cisco"' "$vendor_db" 2>/dev/null)
  CV_ID_VENDOR_NAME=$(jq -r '.name // "Cisco Systems"' "$vendor_db" 2>/dev/null)
  CV_ID_ADAPTER=$(jq -r '.adapter // "cisco"' "$vendor_db" 2>/dev/null)
  product=$(jq -c --arg oid "${CV_ID_SYS_OBJECT_ID:-}" '.products[]? | select(.sys_object_id == $oid)' "$products_db" 2>/dev/null | head -n 1)
  if [ -n "$product" ]; then
    CV_ID_FAMILY=$(printf '%s' "$product" | jq -r '.family // "Unknown Cisco"')
    CV_ID_SUPPORT_STATUS=$(printf '%s' "$product" | jq -r '.support_status // "experimental"')
    CV_ID_MODEL_HINT=$(printf '%s' "$product" | jq -r '.model_hint // empty')
    CV_ID_PRODUCT_MATCH="exact"
  else
    CV_ID_FAMILY="Unknown Cisco"
    CV_ID_SUPPORT_STATUS="unclassified"
    CV_ID_MODEL_HINT=""
    CV_ID_PRODUCT_MATCH="enterprise-only"
  fi

  # sysObjectID values can be shared across related Catalyst families. Prefer
  # the explicit model found in sysDescr when it is more specific.
  case "${CV_ID_SYS_DESCR:-}" in
    *WS-C2960S-*|*C2960S*)
      CV_ID_FAMILY="Catalyst 2960S"
      CV_ID_MODEL_HINT="WS-C2960S"
      CV_ID_SUPPORT_STATUS="experimental"
      CV_ID_PRODUCT_MATCH="model-description"
      ;;
    *WS-C2960X-*|*C2960X*)
      CV_ID_FAMILY="Catalyst 2960X"
      CV_ID_MODEL_HINT="WS-C2960X"
      CV_ID_SUPPORT_STATUS="experimental"
      CV_ID_PRODUCT_MATCH="model-description"
      ;;
  esac
}
