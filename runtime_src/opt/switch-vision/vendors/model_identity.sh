#!/usr/bin/env sh

# Local model identity extraction. Only inspect OIDs that describe this device;
# never scan arbitrary walk text because LLDP/CDP neighbour identity can contain
# exact model strings belonging to a different switch.
CV_CAP_MODEL_PATTERN='WS-C[0-9A-Za-z][0-9A-Za-z._-]*|SG500X-24|SG350-20|S5735-L8P4X-A1|S5720-12TP-LI-AC|CRS328-24P-4S\+|XS1930-10|GS1900-24E|N2128PX-ON|PowerConnect[[:space:]]+5548P|ex3300-48p|J8693A|USWProHD24PoE|USWProXG8PoE|UDM-Pro|US-8-60W|US-8-150W|US-16-XG|US-24-250W|US-48-G1'

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
      [Uu][Ss][Ww][Pp][Rr][Oo][Hh][Dd]24[Pp][Oo][Ee]) printf 'USW Pro HD 24 PoE' ;;
      [Uu][Ss][Ww][Pp][Rr][Oo][Xx][Gg]8[Pp][Oo][Ee]) printf 'USW Pro XG 8 PoE' ;;
      [Uu][Dd][Mm]-[Pp][Rr][Oo]) printf 'UDM Pro' ;;
      [Uu][Ss]-8-60[Ww]) printf 'US 8 60W' ;;
      [Uu][Ss]-8-150[Ww]) printf 'US-8-150W' ;;
      [Uu][Ss]-16-[Xx][Gg]) printf 'US XG 16' ;;
      [Uu][Ss]-24-250[Ww]) printf 'US-24-250W' ;;
      [Uu][Ss]-48-[Gg]1) printf 'US 48' ;;
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
