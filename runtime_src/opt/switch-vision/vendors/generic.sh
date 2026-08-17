#!/usr/bin/env sh
cv_generic_identity() {
  walk_file="$1"
  standard_db="$CV_MIB_DATABASE_DIR/standard/identity.json"
  sys_descr_oid=$(jq -r '.oids.sys_descr // empty' "$standard_db" 2>/dev/null)
  sys_object_oid=$(jq -r '.oids.sys_object_id // empty' "$standard_db" 2>/dev/null)
  sys_name_oid=$(jq -r '.oids.sys_name // empty' "$standard_db" 2>/dev/null)
  CV_ID_SYS_DESCR=$(cv_walk_value_for_oid "$walk_file" "$sys_descr_oid")
  CV_ID_SYS_OBJECT_ID=$(cv_walk_oid_value_for_oid "$walk_file" "$sys_object_oid")
  CV_ID_SYS_NAME=$(cv_walk_value_for_oid "$walk_file" "$sys_name_oid")
  CV_ID_VENDOR="generic"
  CV_ID_VENDOR_NAME="Unknown / standard MIB only"
  CV_ID_ADAPTER="generic"
  CV_ID_FAMILY="Unknown"
  CV_ID_SUPPORT_STATUS="generic"
}
