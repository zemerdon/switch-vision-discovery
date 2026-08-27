#!/usr/bin/env sh

# Local model identity extraction. Only inspect OIDs that describe this device;
# never scan arbitrary walk text because LLDP/CDP neighbour identity can contain
# exact model strings belonging to a different switch.
CV_CAP_MODEL_PATTERN='WS-C[0-9A-Za-z][0-9A-Za-z._-]*|SG500X-24|S5735-L8P4X-A1|S5720-12TP-LI-AC|CRS328-24P-4S\+|XS1930-10|N2128PX-ON|ex3300-48p|J8693A'

cv_cap_model_from_local_scope() {
  walk_file="$1"
  scope="$2"
  awk -v scope="$scope" '
    function norm(s) {
      sub(/^\./, "", s)
      sub(/^iso\./, "1.", s)
      return s
    }
    {
      oid=norm($1)
      if (scope == "entity_model" && index(oid, "1.3.6.1.2.1.47.1.1.1.1.13.") == 1) print
      else if (scope == "entity_descr" && index(oid, "1.3.6.1.2.1.47.1.1.1.1.2.") == 1) print
      else if (scope == "sys_descr" && oid == "1.3.6.1.2.1.1.1.0") print
    }
  ' "$walk_file" 2>/dev/null |
    grep -Eio "$CV_CAP_MODEL_PATTERN" 2>/dev/null |
    head -n 1 || true
}

cv_cap_extract_model_text() {
  walk_file="$1"
  model=""

  # ENTITY-MIB modelName is the strongest local SKU source, followed by local
  # chassis description and finally sysDescr. Remote LLDP/CDP tables are never
  # considered here.
  for scope in entity_model entity_descr sys_descr; do
    model=$(cv_cap_model_from_local_scope "$walk_file" "$scope")
    [ -n "$model" ] && break
  done

  if [ -n "$model" ]; then
    case "$model" in
      [Ee][Xx]3300-48[Pp]) printf 'Juniper EX3300-48P' ;;
      [Jj]8693[Aa]) printf 'HP J8693A Switch 3500yl-48G' ;;
      *) printf '%s' "$model" ;;
    esac
    return 0
  fi

  if [ -n "${CV_ID_MODEL_HINT:-}" ]; then
    printf '%s' "$CV_ID_MODEL_HINT"
  else
    printf '%s %s' "${CV_ID_FAMILY:-}" "${CV_ID_SYS_DESCR:-}"
  fi
}
