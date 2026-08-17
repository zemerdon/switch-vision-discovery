#!/usr/bin/env sh
# Vendor adapter contract helpers. Keep this POSIX-sh compatible for HA app images.
cv_normalize_oid() {
  printf '%s' "${1:-}" | sed -E 's/^iso\./1./; s/^\.//; s/[[:space:]]+$//'
}

cv_walk_value_for_oid() {
  walk_file="$1"
  wanted_oid="$2"
  awk -v wanted="$wanted_oid" '
    function norm(s) {
      sub(/^\./, "", s)
      sub(/^iso\./, "1.", s)
      return s
    }
    {
      oid=$1
      if (norm(oid) == wanted) {
        line=$0
        sub(/^[^=]*=[[:space:]]*/, "", line)
        sub(/^[A-Za-z0-9-]+:[[:space:]]*/, "", line)
        gsub(/^"|"$/, "", line)
        gsub(/\r/, "", line)
        sub(/[[:space:]]+$/, "", line)
        print line
        exit
      }
    }
  ' "$walk_file" 2>/dev/null
}

cv_walk_oid_value_for_oid() {
  cv_walk_value_for_oid "$1" "$2" | sed -E 's/^OID:[[:space:]]*//; s/^iso\./1./; s/^\.//; s/[[:space:]].*$//'
}
