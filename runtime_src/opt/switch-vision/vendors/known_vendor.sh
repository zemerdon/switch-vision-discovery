#!/usr/bin/env sh
cv_known_vendor_matches() {
  vendor_id="$1"
  identity_db="$CV_MIB_DATABASE_DIR/vendors/$vendor_id/identity.json"
  [ -f "$identity_db" ] || return 1
  for prefix in $(jq -r '.detection.sys_object_id_prefixes[]? // empty' "$identity_db" 2>/dev/null); do
    case "${CV_ID_SYS_OBJECT_ID:-}" in "$prefix"*) return 0 ;; esac
  done
  patterns=$(jq -r '.detection.sys_descr_patterns[]? // empty' "$identity_db" 2>/dev/null | paste -sd'|' -)
  [ -n "$patterns" ] && printf '%s' "${CV_ID_SYS_DESCR:-}" | grep -Eqi "$patterns"
}

cv_known_vendor_identity() {
  vendor_id="$1"
  vendor_db="$CV_MIB_DATABASE_DIR/vendors/$vendor_id/vendor.json"
  CV_ID_VENDOR=$(jq -r '.id // "unknown"' "$vendor_db" 2>/dev/null)
  CV_ID_VENDOR_NAME=$(jq -r '.name // "Known vendor"' "$vendor_db" 2>/dev/null)
  CV_ID_ADAPTER=$(jq -r '.adapter // "known_vendor"' "$vendor_db" 2>/dev/null)
  CV_ID_FAMILY="Unknown ${CV_ID_VENDOR_NAME}"
  CV_ID_SUPPORT_STATUS=$(jq -r '.support_status // "vendor-pack"' "$vendor_db" 2>/dev/null)
  CV_ID_MODEL_HINT=""
  CV_ID_PRODUCT_MATCH="enterprise-only"

  if [ "$vendor_id" = "juniper" ]; then
    case "${CV_ID_SYS_DESCR:-}" in
      *[Ee][Xx]3300-48[Pp]*)
        CV_ID_FAMILY="EX3300"
        CV_ID_MODEL_HINT="Juniper EX3300-48P"
        CV_ID_PRODUCT_MATCH="ex3300-48p"
        CV_ID_SUPPORT_STATUS="supported"
        ;;
    esac
  fi

  if [ "$vendor_id" = "hp_aruba" ]; then
    case "${CV_ID_SYS_DESCR:-}" in
      *J8693A*|*j8693a*|*3500yl-48G*|*3500YL-48G*)
        CV_ID_FAMILY="3500yl"
        CV_ID_MODEL_HINT="HP J8693A Switch 3500yl-48G"
        CV_ID_PRODUCT_MATCH="j8693a-local-sysdescr"
        CV_ID_SUPPORT_STATUS="detected"
        ;;
      *1810-24G*|*1810-24g*)
        CV_ID_FAMILY="1810"
        CV_ID_MODEL_HINT="HP 1810-24G"
        CV_ID_PRODUCT_MATCH="1810-24g-local-sysdescr"
        CV_ID_SUPPORT_STATUS="experimental"
        ;;
    esac
  fi

  if [ "$vendor_id" = "dell" ]; then
    case "${CV_ID_SYS_DESCR:-}" in
      *PowerConnect*5548P*|*POWERCONNECT*5548P*)
        CV_ID_FAMILY="PowerConnect 5500"
        CV_ID_MODEL_HINT="PowerConnect 5548P"
        CV_ID_PRODUCT_MATCH="powerconnect-5548p-local-sysdescr"
        CV_ID_SUPPORT_STATUS="experimental"
        ;;
    esac
  fi

  if [ "$vendor_id" = "mikrotik" ]; then
    case "${CV_ID_SYS_OBJECT_ID:-}|${CV_ID_SYS_DESCR:-}" in
      1.3.6.1.4.1.14988.*'|'*CRS328-24P-4S+*|*'|'*CRS328-24P-4S+*)
        CV_ID_FAMILY="CRS328"
        CV_ID_MODEL_HINT="CRS328-24P-4S+"
        CV_ID_PRODUCT_MATCH="crs328-24p-4splus"
        CV_ID_SUPPORT_STATUS="experimental"
        ;;
    esac
  fi

  if [ "$vendor_id" = "ubiquiti" ]; then
    case "${CV_ID_SYS_DESCR:-}" in
      *USWProHD24PoE*)
        CV_ID_FAMILY="UniFi Switch Pro HD"
        CV_ID_MODEL_HINT="USW Pro HD 24 PoE"
        CV_ID_PRODUCT_MATCH="usw-pro-hd-24-poe-local-sysdescr"
        CV_ID_SUPPORT_STATUS="experimental"
        ;;
      *USWProXG8PoE*)
        CV_ID_FAMILY="UniFi Switch Pro XG"
        CV_ID_MODEL_HINT="USW Pro XG 8 PoE"
        CV_ID_PRODUCT_MATCH="usw-pro-xg-8-poe-local-sysdescr"
        CV_ID_SUPPORT_STATUS="experimental"
        ;;
    esac
  fi

  if [ "$vendor_id" = "zyxel" ]; then
    case "${CV_ID_SYS_DESCR:-}" in
      *XS1930-10*)
        CV_ID_FAMILY="XS1930"
        CV_ID_MODEL_HINT="XS1930-10"
        CV_ID_PRODUCT_MATCH="xs1930-10-local-sysdescr"
        CV_ID_SUPPORT_STATUS="experimental"
        ;;
      *GS1900-24E*)
        CV_ID_FAMILY="GS1900"
        CV_ID_MODEL_HINT="GS1900-24E"
        CV_ID_PRODUCT_MATCH="gs1900-24e-local-sysdescr"
        CV_ID_SUPPORT_STATUS="experimental"
        ;;
      *GS1900-8*)
        CV_ID_FAMILY="GS1900"
        CV_ID_MODEL_HINT="GS1900-8"
        CV_ID_PRODUCT_MATCH="gs1900-8-local-sysdescr"
        CV_ID_SUPPORT_STATUS="experimental"
        ;;
    esac
  fi

  if [ "$vendor_id" = "realtek_oem" ]; then
    case "${CV_ID_SYS_DESCR:-}" in
      *SR-S25G3420F*)
        CV_ID_VENDOR_NAME="Sirivision"
        CV_ID_FAMILY="SR-S25G"
        CV_ID_MODEL_HINT="SR-S25G3420F"
        CV_ID_PRODUCT_MATCH="sr-s25g3420f-local-sysdescr"
        CV_ID_SUPPORT_STATUS="experimental"
        ;;
    esac
  fi
}
