#!/usr/bin/env sh
set -eu

SWITCH_VISION_DISCOVERY_VERSION="2.3.4"
export SWITCH_VISION_DISCOVERY_VERSION

CONFIG_FILE="${SWITCH_VISION_OPTIONS_FILE:-/data/options.json}"
INPUT_PATH="/share/switch_vision/snmpwalk.txt"
SNMPWALKS_DIR="/share/switch_vision/snmpwalks"
REPORT_PATH="/share/switch_vision/discovery-report.txt"
DEFAULT_HOST=""
DEFAULT_PREFIX=""
DEFAULT_COMMUNITY="readonly"
GENERATE_SNMP2MQTT="false"
TARGETS_CSV="/share/switch_vision/discovery-targets.csv"
SELECTED_SWITCH=""
PARSE_ALL_WALKS="false"
LAST_RUN_SUMMARY_PATH="/share/switch_vision/last-discovery-run.txt"
GENERATED_YAML_PATH="/share/switch_vision/generated-snmp2mqtt.yaml"
GENERATED_CARD_PATH="/share/switch_vision/generated-dashboard-card.yaml"
RUN_LIVE_SNMPWALK="false"
LIVE_SNMPWALK_MODE="targeted"
LIVE_SWITCH_IP=""
LIVE_SWITCH_LABEL="live"
LIVE_SNMP_COMMUNITY="readonly"
LIVE_SNMP_TIMEOUT="3"
LIVE_SNMP_RETRIES="1"
LIVE_CLEAN_OUTPUT_BEFORE_WALK="false"
LIVE_OUTPUT_DIR="/share/switch_vision/snmpwalks/live"
LIVE_OUTPUT_PATH=""
LIVE_LOG_PATH="/share/switch_vision/live-snmpwalk.log"
LIVE_MIN_VALID_LINES="100"
MULTI_SWITCH_WALKS_ENABLED="false"
DISCOVERY_STARTED_ISO=$(date -Iseconds)
DISCOVERY_STARTED_EPOCH=$(date +%s)
CURRENT_RUN_WALKS="/tmp/switch_vision_current_run_walks.txt"
CURRENT_RUN_TARGETS="/tmp/switch_vision_current_run_targets.txt"
CAPABILITIES_DIR="${SWITCH_VISION_CAPABILITIES_DIR:-/share/switch_vision/capabilities}"
POST_WALK_ALREADY_DONE="false"
GENERATED_CARD_SNMP_ENABLED="false"

sv_status() {
  # Structured, credential-safe status consumed by the persistent Web UI.
  # Keep values free of the pipe character.
  printf 'SV_STATUS|stage=%s|switch=%s|target=%s|command=%s|activity=%s\n' \
    "${1:-Discovery}" "${2:-${SELECTED_SWITCH:-not set}}" "${3:-${LIVE_SWITCH_IP:-not set}}" "${4:-}" "${5:-}"
}

sv_debug() {
  printf 'SV_DEBUG|%s\n' "${1:-}"
}

# Curated OID/vendor knowledge layer. This first slice is observational only:
# the proven v0.7.17 parser and generator remain authoritative.
CV_MIB_DATABASE_DIR="${CV_MIB_DATABASE_DIR:-/opt/switch-vision/mib_database}"
CV_VENDOR_DIR="${CV_VENDOR_DIR:-/opt/switch-vision/vendors}"
if [ -f "$CV_VENDOR_DIR/base.sh" ] && [ -f "$CV_VENDOR_DIR/loader.sh" ]; then
  . "$CV_VENDOR_DIR/base.sh"
  . "$CV_VENDOR_DIR/generic.sh"
  . "$CV_VENDOR_DIR/cisco.sh"
. "$CV_VENDOR_DIR/known_vendor.sh"
  . "$CV_VENDOR_DIR/interface.sh"
  . "$CV_VENDOR_DIR/loader.sh"
fi

json_get() {
  key="$1"
  fallback="$2"
  if [ -f "$CONFIG_FILE" ]; then
    # Prefer jq when available so nested switch-row fields named like top-level
    # fallbacks, such as sensor_prefix, do not accidentally override globals.
    if command -v jq >/dev/null 2>&1; then
      value=$(jq -r --arg k "$key" 'if has($k) and .[$k] != null and ((.[$k]|type) == "string" or (.[$k]|type) == "number" or (.[$k]|type) == "boolean") then .[$k]|tostring else empty end' "$CONFIG_FILE" 2>/dev/null | head -n 1)
      if [ -n "${value:-}" ]; then
        printf '%s' "$value"
        return 0
      fi
    fi
    # Fallback parser for minimal images without jq. This is only reliable for
    # flat top-level string options.
    value=$(grep -o "\"$key\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" "$CONFIG_FILE" 2>/dev/null | head -n 1 | sed 's/^.*:[[:space:]]*"//;s/"$//')
    if [ -n "${value:-}" ]; then
      printf '%s' "$value"
      return 0
    fi
  fi
  printf '%s' "$fallback"
}

json_has_configured_switch_rows() {
  # True when the persistent switch inventory contains at least one real row,
  # regardless of whether that row is currently enabled. This is deliberately
  # separate from json_has_enabled_switch_rows so disabled inventory entries
  # can gate legacy/offline fallbacks without being selected for generation.
  [ -f "$CONFIG_FILE" ] || return 1
  command -v jq >/dev/null 2>&1 || return 1
  jq -e '
    (.switches // .multi_switch_walks // []) as $rows |
    ($rows | type == "array") and
    any($rows[]?;
      (((.switch_name // .switch // .selected_switch // .name // "")
       | tostring | length) > 0)
    )
  ' "$CONFIG_FILE" >/dev/null 2>&1
}

json_has_enabled_switch_rows() {
  [ -f "$CONFIG_FILE" ] || return 1
  command -v jq >/dev/null 2>&1 || return 1
  jq -e '
    def enabled($sw):
      (($sw.enabled // "enabled") as $value |
        if ($value | type) == "boolean" then $value
        elif ($value | type) == "string" then
          (($value | ascii_downcase) as $state |
            ($state != "false" and $state != "disabled" and $state != "disable" and
             $state != "off" and $state != "no" and $state != "0"))
        else true end);
    (.switches // .multi_switch_walks // []) as $rows |
    ($rows | type == "array") and
    any($rows[]?;
      enabled(.) and
      (((.switch_name // .switch // .selected_switch // .name // "")
       | tostring | length) > 0)
    )
  ' "$CONFIG_FILE" >/dev/null 2>&1
}

legacy_single_walk_allowed() {
  # Once a real switch inventory exists, it is authoritative. In particular,
  # an all-disabled inventory must not fall through to the legacy single-walk
  # input and accidentally regenerate a disabled device. With no configured
  # inventory rows, the historical single-walk workflow remains available.
  if truthy "$MULTI_SWITCH_WALKS_ENABLED" && json_has_configured_switch_rows; then
    return 1
  fi
  truthy "$PARSE_ALL_WALKS" && [ -f "$INPUT_PATH" ]
}

multi_switch_walk_rows() {
  # Output TSV:
  # switch_name<TAB>switch_host<TAB>folder_label<TAB>sensor_prefix<TAB>snmp_community<TAB>mode<TAB>output_dir<TAB>display_name<TAB>switch_model
  # v0.7.6 switch-list rows can carry the full switch definition so most users do not need a CSV.
  # Older rows with only switch/mode remain supported and will resolve through discovery-targets.csv.
  [ -f "$CONFIG_FILE" ] || return 0
  command -v jq >/dev/null 2>&1 || return 0
  jq -r '
    def enabled($sw):
      (($sw.enabled // "enabled") as $value |
        if ($value | type) == "boolean" then $value
        elif ($value | type) == "string" then
          (($value | ascii_downcase) as $state |
            ($state != "false" and $state != "disabled" and $state != "disable" and
             $state != "off" and $state != "no" and $state != "0"))
        else true end);
    (.switches // .multi_switch_walks // [])[]?
    | select(enabled(.))
    | [
      (.switch_name // .switch // .selected_switch // .name // ""),
      (.switch_host // .host // .manual_switch_host // ""),
      (.switch_name // .switch // .selected_switch // .name // ""),
      (.sensor_prefix // .entity_prefix // .prefix // ""),
      (.snmp_community // .community // ""),
      (.walk_mode // .mode // "targeted"),
      (.output_dir // ""),
      (.display_name // .card_title // ""),
      (.switch_model // .model_override // "auto")
    ] | map(tostring) | join("\u001c")' "$CONFIG_FILE" 2>/dev/null || true
}


multi_switch_stack_member_rows() {
  # Output TSV:
  # switch_name<TAB>folder_label<TAB>output_dir<TAB>member<TAB>member_name<TAB>sensor_prefix
  # v0.7.12 exposes stack members as a separate flat list so standalone switch rows
  # do not show a stack-member submenu. Legacy nested rows are still accepted if
  # they exist in an older options.json.
  [ -f "$CONFIG_FILE" ] || return 0
  command -v jq >/dev/null 2>&1 || return 0
  jq -r --arg root "$SNMPWALKS_ROOT_DIR" '
    def swname($sw): ($sw.switch_name // $sw.switch // $sw.selected_switch // $sw.name // "");
    def enabled($sw):
      (($sw.enabled // "enabled") as $value |
        if ($value | type) == "boolean" then $value
        elif ($value | type) == "string" then
          (($value | ascii_downcase) as $state |
            ($state != "false" and $state != "disabled" and $state != "disable" and
             $state != "off" and $state != "no" and $state != "0"))
        else true end);
    def swlabel($sw): (swname($sw) // "live");
    def swout($sw): (($sw.output_dir // "") as $od | if $od != "" then $od else ($root + "/" + swname($sw)) end);
    . as $cfg |
    (
      (($cfg.stack_member_prefixes // [])[]? as $m |
        ($m.switch_name // $m.switch // $m.selected_switch // $m.name // "") as $target |
        ((($cfg.switches // $cfg.multi_switch_walks // []) | map(select(swname(.) == $target)) | .[0]) // {}) as $sw |
        select(($sw | length) == 0 or enabled($sw)) |
        select(($m.member // $m.member_number // "") != "" and ($m.member // $m.member_number // "") != "[]") |
        [
          $target,
          (if ($sw | length) > 0 then swlabel($sw) else ($m.folder_label // $m.label // "") end),
          (if ($sw | length) > 0 then swout($sw) else ($m.output_dir // "") end),
          ($m.member // $m.member_number // ""),
          ($m.display_name // $m.member_name // $m.name // ""),
          ($m.sensor_prefix // $m.entity_prefix // $m.prefix // "")
        ] | map(tostring) | join("\u001c")
      ),
      (($cfg.switches // $cfg.multi_switch_walks // [])[]? as $sw |
        select(enabled($sw)) |
        ($sw.stack_members // [])[]? as $m |
        select(($m.member // $m.member_number // "") != "" and ($m.member // $m.member_number // "") != "[]") |
        [
          swname($sw),
          swlabel($sw),
          swout($sw),
          ($m.member // $m.member_number // ""),
          ($m.display_name // $m.member_name // $m.name // ""),
          ($m.sensor_prefix // $m.entity_prefix // $m.prefix // "")
        ] | map(tostring) | join("\u001c")
      )
    )' "$CONFIG_FILE" 2>/dev/null || true
}

format_duration() {
  seconds="${1:-0}"
  case "$seconds" in ''|*[!0-9]*) seconds=0 ;; esac
  mins=$((seconds / 60))
  secs=$((seconds % 60))
  if [ "$mins" -gt 0 ]; then
    printf '%dm %02ds' "$mins" "$secs"
  else
    printf '%ds' "$secs"
  fi
}

now_epoch() { date +%s; }

safe_clean_walk_outputs() {
  cleanup_dir="$1"
  cleanup_root="/share/switch_vision/snmpwalks"
  mkdir -p "$cleanup_root" "$cleanup_dir"
  root_real=$(readlink -f "$cleanup_root" 2>/dev/null || true)
  dir_real=$(readlink -f "$cleanup_dir" 2>/dev/null || true)
  if [ -z "$root_real" ] || [ -z "$dir_real" ]; then
    echo "Clean before walk: skipped because cleanup path could not be resolved" >> "$LIVE_LOG_PATH"
    return 1
  fi
  case "$dir_real" in
    "$root_real"|"$root_real"/*) : ;;
    *)
      echo "Clean before walk: refused unsafe directory $cleanup_dir (resolved $dir_real)" >> "$LIVE_LOG_PATH"
      return 1
      ;;
  esac
  rm -f "$dir_real"/*.txt "$dir_real"/*.walk "$dir_real"/*.snmpwalk 2>/dev/null || true
  return 0
}

INPUT_PATH=$(json_get input_path "$INPUT_PATH")
SNMPWALKS_DIR=$(json_get snmpwalks_dir "$SNMPWALKS_DIR")
REPORT_PATH=$(json_get report_path "$REPORT_PATH")
# Legacy single-file/CSV fallback values are internal only. The opening app
# configuration now uses self-contained switch-list rows.
DEFAULT_HOST=""
DEFAULT_PREFIX=""
DEFAULT_COMMUNITY="readonly"
GENERATE_SNMP2MQTT=$(json_get generate_snmp2mqtt "$GENERATE_SNMP2MQTT")
TARGETS_CSV=$(json_get targets_csv "$TARGETS_CSV")
SELECTED_SWITCH=""
PARSE_ALL_WALKS=$(json_get parse_all_walks "$PARSE_ALL_WALKS")
LAST_RUN_SUMMARY_PATH=$(json_get last_run_summary_path "$LAST_RUN_SUMMARY_PATH")
GENERATED_YAML_PATH=$(json_get generated_yaml_path "$GENERATED_YAML_PATH")
GENERATED_CARD_PATH=$(json_get generated_card_path "$GENERATED_CARD_PATH")
RUN_LIVE_SNMPWALK=$(json_get run_snmp_walks "$(json_get run_live_snmpwalk "$RUN_LIVE_SNMPWALK")")
LIVE_SNMPWALK_MODE=$(json_get live_snmpwalk_mode "$LIVE_SNMPWALK_MODE") # legacy single-switch fallback only
LIVE_SWITCH_IP=$(json_get manual_switch_host "$(json_get live_switch_ip "$LIVE_SWITCH_IP")")
LIVE_SWITCH_LABEL=$(json_get live_switch_label "$LIVE_SWITCH_LABEL")
LIVE_SNMP_COMMUNITY=$(json_get live_snmp_community "$LIVE_SNMP_COMMUNITY")
LIVE_SNMP_TIMEOUT=$(json_get snmp_timeout "$(json_get live_snmp_timeout "$LIVE_SNMP_TIMEOUT")")
LIVE_SNMP_RETRIES=$(json_get snmp_retries "$(json_get live_snmp_retries "$LIVE_SNMP_RETRIES")")
LIVE_CLEAN_OUTPUT_BEFORE_WALK=$(json_get clean_output_before_walk "$(json_get live_clean_output_before_walk "$LIVE_CLEAN_OUTPUT_BEFORE_WALK")")
LIVE_OUTPUT_DIR=$(json_get live_output_dir "$LIVE_OUTPUT_DIR")
LIVE_OUTPUT_PATH=$(json_get live_output_path "$LIVE_OUTPUT_PATH")
LIVE_OUTPUT_PATH_CONFIGURED="$LIVE_OUTPUT_PATH"
LIVE_LOG_PATH=$(json_get snmp_log_path "$(json_get live_log_path "$LIVE_LOG_PATH")")
LIVE_MIN_VALID_LINES=$(json_get minimum_valid_walk_lines "$(json_get live_min_valid_lines "$LIVE_MIN_VALID_LINES")")
MULTI_SWITCH_WALKS_ENABLED=$(json_get enable_switch_list "$(json_get multi_switch_walks_enabled "$MULTI_SWITCH_WALKS_ENABLED")")

# Normalize folder-style paths so reports do not show accidental double slashes
# and so per-switch live output folders resolve consistently.
SNMPWALKS_DIR=${SNMPWALKS_DIR%/}
SNMPWALKS_ROOT_DIR="$SNMPWALKS_DIR"
LIVE_OUTPUT_DIR=${LIVE_OUTPUT_DIR%/}
REPORT_PATH=$(printf '%s' "$REPORT_PATH" | sed 's#//*#/#g')
TARGETS_CSV=$(printf '%s' "$TARGETS_CSV" | sed 's#//*#/#g')
GENERATED_YAML_PATH=$(printf '%s' "$GENERATED_YAML_PATH" | sed 's#//*#/#g')
GENERATED_CARD_PATH=$(printf '%s' "$GENERATED_CARD_PATH" | sed 's#//*#/#g')
LIVE_LOG_PATH=$(printf '%s' "$LIVE_LOG_PATH" | sed 's#//*#/#g')
LAST_RUN_SUMMARY_PATH=$(printf '%s' "$LAST_RUN_SUMMARY_PATH" | sed 's#//*#/#g')

LIVE_SNMPWALK_MODE=$(printf '%s' "$LIVE_SNMPWALK_MODE" | tr '[:upper:]' '[:lower:]')
case "$LIVE_SNMPWALK_MODE" in
  targeted|full) : ;;
  *) LIVE_SNMPWALK_MODE="targeted" ;;
esac
case "$LIVE_SWITCH_LABEL" in
  ""|*/*|*..*) LIVE_SWITCH_LABEL="live" ;;
esac
if [ -z "${LIVE_OUTPUT_PATH:-}" ]; then
  if [ "$LIVE_SNMPWALK_MODE" = "full" ]; then
    LIVE_OUTPUT_PATH="$LIVE_OUTPUT_DIR/live-full-snmpwalk.txt"
  else
    LIVE_OUTPUT_PATH="$LIVE_OUTPUT_DIR/live-targeted-snmpwalk.txt"
  fi
fi
LIVE_OUTPUT_PATH=$(printf '%s' "$LIVE_OUTPUT_PATH" | sed 's#//*#/#g')
REPORT_DIR=$(dirname "$REPORT_PATH")
mkdir -p "$REPORT_DIR" "${SWITCH_VISION_SHARE_DIR:-/share/switch_vision}" "$CAPABILITIES_DIR" "$SNMPWALKS_DIR" "$(dirname "$GENERATED_YAML_PATH")" "$(dirname "$GENERATED_CARD_PATH")" "$(dirname "$LIVE_LOG_PATH")"
if ! json_has_configured_switch_rows; then
  mkdir -p "$LIVE_OUTPUT_DIR" "$(dirname "$LIVE_OUTPUT_PATH")"
fi


clean_csv_field() {
  # Trim common CSV whitespace/quotes/CR characters without requiring jq.
  printf '%s' "$1" \
    | tr -d '\r' \
    | sed "s/^[[:space:]]*//; s/[[:space:]]*$//; s/^\"//; s/\"$//; s/^'//; s/'$//"
}

csv_field() {
  # Extract one CSV field by 1-based index, then let clean_csv_field handle spaces/quotes/CR.
  # This deliberately accepts both compact and spaced CSV:
  #   sw5-fullwalk.txt,192.168.1.102
  #   sw5-fullwalk.txt , 192.168.1.102
  line="$1"
  idx="$2"
  raw=$(printf '%s\n' "$line" | awk -F',' -v idx="$idx" '{ print $idx }')
  clean_csv_field "$raw"
}


lower_value() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

normalized_header_key() {
  # Normalize CSV header text so both old compact headers and new friendly
  # headers are accepted. Examples: "switch name", "switch_name", "switch-name".
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[[:space:]_-]//g'
}

is_targets_csv_header() {
  key=$(normalized_header_key "$1")
  case "$key" in
    switch|switchname|selectedswitch|filename|file|walk|walkfile|snmpwalk) return 0 ;;
    *) return 1 ;;
  esac
}

target_csv_prefix_field() {
  # Current map: switch name,switch host,sensor prefix,switch snmp community,output_dir,display name
  line="$1"
  csv_field "$line" 3
}

target_csv_community_field() {
  line="$1"
  csv_field "$line" 4
}

entity_prefix_example() {
  prefix="${1:-sw}"
  safe_prefix=$(printf '%s' "$prefix" | tr '[:upper:]' '[:lower:]')
  printf 'sensor.%s_port_1_status, sensor.%s_port_1_rx_bytes, sensor.%s_port_1_tx_bytes, sensor.%s_uptime' "$safe_prefix" "$safe_prefix" "$safe_prefix" "$safe_prefix"
}

safe_label_value() {
  v=$(clean_csv_field "$1")
  # Stable filesystem-safe folder names derived from switch_name.
  # Spaces and unsafe characters become underscores.
  v=$(printf '%s' "$v" | sed 's/[[:space:]]\+/_/g; s/[^A-Za-z0-9._-]/_/g; s/_\+/_/g; s/^[_ .-]*//; s/[_ .-]*$//')
  case "$v" in
    ""|"."|"..") printf 'live' ;;
    *) printf '%s' "$v" ;;
  esac
}

SELECTED_SWITCH_MATCHED="no"
SELECTED_SWITCH_AVAILABLE=""
SELECTED_SWITCH_ROW_KEY="none"
SELECTED_SWITCH_RESOLVED_HOST=""
SELECTED_SWITCH_RESOLVED_LABEL=""
SELECTED_SWITCH_RESOLVED_PREFIX=""
SELECTED_SWITCH_RESOLVED_COMMUNITY=""
SELECTED_SWITCH_RESOLVED_OUTPUT_DIR=""

reset_selected_switch_resolution() {
  SELECTED_SWITCH_MATCHED="no"
  SELECTED_SWITCH_AVAILABLE=""
  SELECTED_SWITCH_ROW_KEY="none"
  SELECTED_SWITCH_RESOLVED_HOST=""
  SELECTED_SWITCH_RESOLVED_LABEL=""
  SELECTED_SWITCH_RESOLVED_PREFIX=""
  SELECTED_SWITCH_RESOLVED_COMMUNITY=""
  SELECTED_SWITCH_RESOLVED_OUTPUT_DIR=""
}

append_available_switch() {
  sw="$1"
  [ -n "$sw" ] || return 0
  if [ -z "$SELECTED_SWITCH_AVAILABLE" ]; then
    SELECTED_SWITCH_AVAILABLE="$sw"
  else
    SELECTED_SWITCH_AVAILABLE="$SELECTED_SWITCH_AVAILABLE, $sw"
  fi
}

resolve_selected_switch() {
  reset_selected_switch_resolution
  [ -n "${SELECTED_SWITCH:-}" ] || return 0

  selected_lc=$(lower_value "$SELECTED_SWITCH")
  if [ ! -f "$TARGETS_CSV" ]; then
    SELECTED_SWITCH_MATCHED="no_csv"
    return 0
  fi

  while IFS= read -r line || [ -n "$line" ]; do
    sw=$(csv_field "$line" 1)
    host=$(csv_field "$line" 2)
    prefix=$(csv_field "$line" 3)
    community=$(csv_field "$line" 4)
    output_dir=$(csv_field "$line" 5)

    [ -n "$sw" ] || continue
    case "$sw" in \#*) continue ;; esac
    sw_lc=$(lower_value "$sw")
    if is_targets_csv_header "$sw"; then
      continue
    fi

    append_available_switch "$sw"

    if [ "$sw_lc" = "$selected_lc" ]; then
      SELECTED_SWITCH_MATCHED="yes"
      SELECTED_SWITCH_ROW_KEY="$sw"
      SELECTED_SWITCH_RESOLVED_HOST="$host"
      SELECTED_SWITCH_RESOLVED_LABEL=$(safe_label_value "$sw")
      SELECTED_SWITCH_RESOLVED_PREFIX="${prefix:-$SELECTED_SWITCH_RESOLVED_LABEL}"
      SELECTED_SWITCH_RESOLVED_COMMUNITY="${community:-$DEFAULT_COMMUNITY}"
      if [ -n "$output_dir" ]; then
        SELECTED_SWITCH_RESOLVED_OUTPUT_DIR="$output_dir"
      else
        SELECTED_SWITCH_RESOLVED_OUTPUT_DIR="/share/switch_vision/snmpwalks/$(safe_label_value "$sw")"
      fi
      break
    fi
  done < "$TARGETS_CSV"

  if [ "$SELECTED_SWITCH_MATCHED" = "yes" ]; then
    # selected_switch is authoritative. It intentionally overrides stale manual/default values.
    if [ -n "$SELECTED_SWITCH_RESOLVED_HOST" ]; then
      LIVE_SWITCH_IP="$SELECTED_SWITCH_RESOLVED_HOST"
      DEFAULT_HOST="$SELECTED_SWITCH_RESOLVED_HOST"
    fi
    LIVE_SWITCH_LABEL="$SELECTED_SWITCH_RESOLVED_LABEL"
    DEFAULT_PREFIX="$SELECTED_SWITCH_RESOLVED_PREFIX"
    LIVE_SNMP_COMMUNITY="$SELECTED_SWITCH_RESOLVED_COMMUNITY"
    DEFAULT_COMMUNITY="$SELECTED_SWITCH_RESOLVED_COMMUNITY"
    LIVE_OUTPUT_DIR="$SELECTED_SWITCH_RESOLVED_OUTPUT_DIR"
    case "$(lower_value "$PARSE_ALL_WALKS")" in
      true|yes|on|1) : ;;
      *) SNMPWALKS_DIR="$SELECTED_SWITCH_RESOLVED_OUTPUT_DIR" ;;
    esac
  else
    # A requested selected_switch that does not resolve must not fall through to stale options.
    safe_selected=$(safe_label_value "$SELECTED_SWITCH")
    LIVE_SWITCH_IP=""
    DEFAULT_HOST=""
    LIVE_SWITCH_LABEL="$safe_selected"
    DEFAULT_PREFIX="$safe_selected"
    LIVE_OUTPUT_DIR="/share/switch_vision/snmpwalks/$safe_selected"
    case "$(lower_value "$PARSE_ALL_WALKS")" in
      true|yes|on|1) : ;;
      *) SNMPWALKS_DIR="$LIVE_OUTPUT_DIR" ;;
    esac
  fi
}

resolve_selected_switch

# Re-normalize paths after selected_switch may have resolved host/label/output_dir.
SNMPWALKS_DIR=${SNMPWALKS_DIR%/}
LIVE_OUTPUT_DIR=${LIVE_OUTPUT_DIR%/}
SNMPWALKS_DIR=$(printf '%s' "$SNMPWALKS_DIR" | sed 's#//*#/#g')
LIVE_OUTPUT_DIR=$(printf '%s' "$LIVE_OUTPUT_DIR" | sed 's#//*#/#g')
if [ -z "${LIVE_OUTPUT_PATH_CONFIGURED:-}" ]; then
  if [ "$LIVE_SNMPWALK_MODE" = "full" ]; then
    LIVE_OUTPUT_PATH="$LIVE_OUTPUT_DIR/live-full-snmpwalk.txt"
  else
    LIVE_OUTPUT_PATH="$LIVE_OUTPUT_DIR/live-targeted-snmpwalk.txt"
  fi
fi
LIVE_OUTPUT_PATH=$(printf '%s' "$LIVE_OUTPUT_PATH" | sed 's#//*#/#g')
if json_has_configured_switch_rows; then
  # Switch-list mode creates each persistent switch_name folder immediately
  # before its own walk. Remove an obsolete empty live directory left by older
  # releases, but never delete it when it contains user data.
  mkdir -p "$SNMPWALKS_ROOT_DIR" "$(dirname "$LAST_RUN_SUMMARY_PATH")"
  rmdir "$SNMPWALKS_ROOT_DIR/live" 2>/dev/null || true
else
  mkdir -p "$SNMPWALKS_DIR" "$LIVE_OUTPUT_DIR" "$(dirname "$LIVE_OUTPUT_PATH")" "$(dirname "$LAST_RUN_SUMMARY_PATH")"
fi

strip_walk_ext() {
  name="$1"
  name=${name##*/}
  case "$name" in
    *.snmpwalk) name=${name%'.snmpwalk'} ;;
    *.walk) name=${name%'.walk'} ;;
    *.txt) name=${name%'.txt'} ;;
  esac
  printf '%s' "$name"
}

current_run_target_field_for_walk() {
  manifest_walk="$1"
  manifest_field="$2"
  [ -f "${CURRENT_RUN_TARGETS:-}" ] || return 1
  manifest_sep="$(printf '\034')"
  while IFS="$manifest_sep" read -r mf_walk mf_switch mf_host mf_prefix mf_community || [ -n "$mf_walk$mf_switch$mf_host$mf_prefix$mf_community" ]; do
    [ "$mf_walk" = "$manifest_walk" ] || continue
    case "$manifest_field" in
      switch) printf '%s' "$mf_switch" ;;
      host) printf '%s' "$mf_host" ;;
      prefix) printf '%s' "$mf_prefix" ;;
      community) printf '%s' "$mf_community" ;;
      *) return 1 ;;
    esac
    return 0
  done < "$CURRENT_RUN_TARGETS"
  return 1
}

record_current_run_target() {
  manifest_walk="$1"
  manifest_switch="$2"
  manifest_host="$3"
  manifest_prefix="$4"
  manifest_community="$5"
  [ -n "$manifest_walk" ] || return 1
  [ -n "$manifest_host" ] || return 1
  manifest_sep="$(printf '\034')"
  printf '%s%s%s%s%s%s%s%s%s\n' \
    "$manifest_walk" "$manifest_sep" \
    "$manifest_switch" "$manifest_sep" \
    "$manifest_host" "$manifest_sep" \
    "$manifest_prefix" "$manifest_sep" \
    "$manifest_community" >> "$CURRENT_RUN_TARGETS"
}

walk_header_target_for_walk() {
  walk_file="$1"
  [ -f "$walk_file" ] || return 1
  header_target=$(awk -F': ' '/^# Switch IP: / { print $2; exit }' "$walk_file" 2>/dev/null || true)
  case "$header_target" in
    ''|'not set'|'unknown') return 1 ;;
  esac
  printf '%s' "$header_target"
}

target_for_walk() {
  walk_file="$1"

  # Current-run metadata is authoritative. The walk and its connection
  # details are recorded together at collection time, so generation never
  # has to rediscover a host from a filename or directory.
  if current_host=$(current_run_target_field_for_walk "$walk_file" host 2>/dev/null) && [ -n "$current_host" ]; then
    printf '%s' "$current_host"
    return 0
  fi

  # Prefer explicit per-file mappings over default_host. This allows multi-walk
  # reports to map each file to a different switch IP.
  # The loop intentionally handles files without a final newline.
  if [ -f "$TARGETS_CSV" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      name=$(csv_field "$line" 1)
      host=$(csv_field "$line" 2)
      [ -n "$name" ] || continue
      case "$name" in \#*) continue ;; esac
      if is_targets_csv_header "$name"; then
        continue
      fi
      [ -n "$host" ] || continue
      if csv_row_matches_walk "$line" "$walk_file"; then
        printf '%s' "$host"
        return 0
      fi
    done < "$TARGETS_CSV"
  fi

  # A Switch Vision live walk also records its target in the walk header.
  # This is a diagnostic recovery fallback only; current-run metadata and
  # explicit mappings remain preferred.
  if header_host=$(walk_header_target_for_walk "$walk_file" 2>/dev/null) && [ -n "$header_host" ]; then
    printf '%s' "$header_host"
    return 0
  fi

  if [ -n "${DEFAULT_HOST:-}" ]; then
    printf '%s' "$DEFAULT_HOST"
    return 0
  fi

  printf 'unknown'
}


mapping_key() {
  # Normalize configured names and persistent folder names to the same key.
  # This allows "3650 DESKTOP STACK" to match 3650_DESKTOP_STACK while
  # preserving switch_name as the stable source of identity.
  printf '%s' "$1" \
    | tr '[:lower:]' '[:upper:]' \
    | sed 's#[^A-Z0-9._-]#_#g; s/_\{2,\}/_/g; s/^_//; s/_$//'
}

csv_mapping_matches() {
  csv_name="$1"
  walk_file="$2"
  base=$(basename "$walk_file")
  base_no_ext=$(strip_walk_ext "$base")
  name_base=$(basename "$csv_name")
  name_no_ext=$(strip_walk_ext "$name_base")
  parent_dir=$(basename "$(dirname "$walk_file")")
  parent_no_ext=$(strip_walk_ext "$parent_dir")

  csv_key=$(mapping_key "$csv_name")
  name_key=$(mapping_key "$name_base")
  name_no_ext_key=$(mapping_key "$name_no_ext")
  walk_key=$(mapping_key "$walk_file")
  base_key=$(mapping_key "$base")
  base_no_ext_key=$(mapping_key "$base_no_ext")
  parent_key=$(mapping_key "$parent_dir")
  parent_no_ext_key=$(mapping_key "$parent_no_ext")

  [ "$csv_key" = "$walk_key" ] \
    || [ "$name_key" = "$base_key" ] \
    || [ "$name_no_ext_key" = "$base_no_ext_key" ] \
    || [ "$name_key" = "$parent_key" ] \
    || [ "$name_no_ext_key" = "$parent_no_ext_key" ]
}

csv_row_matches_walk() {
  line="$1"
  walk_file="$2"
  name=$(csv_field "$line" 1)
  output_dir=$(csv_field "$line" 5)

  csv_mapping_matches "$name" "$walk_file" && return 0
  [ -n "$output_dir" ] && csv_mapping_matches "$output_dir" "$walk_file" && return 0

  return 1
}
derive_prefix_from_walk() {
  walk_file="$1"
  base_no_ext=$(strip_walk_ext "$(basename "$walk_file")")
  guessed=$(printf '%s' "$base_no_ext" | sed -n 's/.*\([sS][wW][0-9][0-9]*\).*/\1/p' | head -n 1 | tr '[:lower:]' '[:upper:]')
  if [ -n "$guessed" ]; then
    printf '%s' "$guessed"
  elif [ -n "${DEFAULT_PREFIX:-}" ]; then
    printf '%s' "$DEFAULT_PREFIX"
  else
    printf 'SW'
  fi
}

target_prefix_for_walk() {
  walk_file="$1"
  if current_prefix=$(current_run_target_field_for_walk "$walk_file" prefix 2>/dev/null) && [ -n "$current_prefix" ]; then
    printf '%s' "$current_prefix"
    return 0
  fi
  if [ -f "$TARGETS_CSV" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      name=$(csv_field "$line" 1)
      prefix=$(target_csv_prefix_field "$line")
      [ -n "$name" ] || continue
      case "$name" in \#*) continue ;; esac
      if is_targets_csv_header "$name"; then
        continue
      fi
      if csv_row_matches_walk "$line" "$walk_file" && [ -n "$prefix" ]; then
        printf '%s' "$prefix"
        return 0
      fi
    done < "$TARGETS_CSV"
  fi
  if [ -n "${DEFAULT_PREFIX:-}" ]; then
    printf '%s' "$DEFAULT_PREFIX"
  else
    derive_prefix_from_walk "$walk_file"
  fi
}


target_community_for_walk() {
  walk_file="$1"
  if current_community=$(current_run_target_field_for_walk "$walk_file" community 2>/dev/null) && [ -n "$current_community" ]; then
    printf '%s' "$current_community"
    return 0
  fi
  if [ -f "$TARGETS_CSV" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      name=$(csv_field "$line" 1)
      community=$(target_csv_community_field "$line")
      [ -n "$name" ] || continue
      case "$name" in \#*) continue ;; esac
      if is_targets_csv_header "$name"; then
        continue
      fi
      if csv_row_matches_walk "$line" "$walk_file" && [ -n "$community" ]; then
        printf '%s' "$community"
        return 0
      fi
    done < "$TARGETS_CSV"
  fi
  printf '%s' "$DEFAULT_COMMUNITY"
}

csv_rows_parsed() {
  count=0
  if [ -f "$TARGETS_CSV" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      name=$(csv_field "$line" 1)
      host=$(csv_field "$line" 2)
      [ -n "$name" ] || continue
      case "$name" in \#*) continue ;; esac
      if is_targets_csv_header "$name"; then
        continue
      fi
      [ -n "$host" ] || continue
      count=$((count + 1))
    done < "$TARGETS_CSV"
  fi
  printf '%s' "$count"
}

csv_matched_key_for_walk() {
  walk_file="$1"
  if [ -f "$TARGETS_CSV" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      name=$(csv_field "$line" 1)
      host=$(csv_field "$line" 2)
      [ -n "$name" ] || continue
      case "$name" in \#*) continue ;; esac
      if is_targets_csv_header "$name"; then
        continue
      fi
      [ -n "$host" ] || continue
      if csv_row_matches_walk "$line" "$walk_file"; then
        printf '%s' "$name"
        return 0
      fi
    done < "$TARGETS_CSV"
  fi
  printf 'none'
}

write_csv_diagnostics_for_walk() {
  walk_file="$1"
  if [ -f "$TARGETS_CSV" ]; then
    rows=$(csv_rows_parsed)
    key=$(csv_matched_key_for_walk "$walk_file")
    echo "Targets CSV diagnostics:"
    echo "- found: yes"
    echo "- rows parsed: $rows"
    if [ "$key" != "none" ]; then
      echo "- matched row: yes"
      echo "- matched key: $key"
    else
      echo "- matched row: no"
      echo "- matched key: none"
    fi
  else
    echo "Targets CSV diagnostics:"
    echo "- found: no"
    echo "- rows parsed: 0"
    echo "- matched row: no"
    echo "- matched key: none"
  fi
}

parser_report() {
  walk_file="$1"
  target_ip="$2"
  registry_status=""
  if command -v cv_cap_extract_model_text >/dev/null 2>&1 && [ -f /registry_lookup.py ]; then
    registry_model=$(cv_cap_extract_model_text "$walk_file")
    registry_status=$(python3 /registry_lookup.py --model "$registry_model" --report 2>/dev/null | awk -F': ' '/^- Registry status:/ {print $2; exit}')
  fi
  awk -v target_ip="$target_ip" -v generator_enabled="$GENERATE_SNMP2MQTT" -v source_walk="$walk_file" -v registry_status="$registry_status" '
    function value_of(line, v) {
      v = line
      sub(/^[^=]*= /, "", v)
      sub(/^[A-Za-z0-9-]+: /, "", v)
      gsub(/\r/, "", v)
      gsub(/^"/, "", v)
      gsub(/"$/, "", v)
      return v
    }
    function oid_index(line, s) {
      s = line
      sub(/^.*\./, "", s)
      sub(/ =.*$/, "", s)
      return s
    }
    function add_unique(list, item, sep) {
      sep = (list == "" ? "" : ", ")
      if (item == "") return list
      if (index(", " list ", ", ", " item ", ") > 0) return list
      return list sep item
    }
    function trunk_label(v) {
      if (v == "1") return "on/trunking"
      if (v == "2") return "off/not trunking"
      if (v == "3") return "desirable"
      if (v == "4") return "auto"
      return "unknown"
    }
    function is_2960x(m) { return (m ~ /^(WS-)?C2960X/) }
    function is_2960s(m) { return (m ~ /^(WS-)?C2960S/) }
    function is_2960(m) { return (is_2960x(m) || is_2960s(m)) }
    function c2960_rj45_limit(m) {
      if (m ~ /^WS-C2960X-24/ || m ~ /^WS-C2960S-24/) return 24
      if (m ~ /^WS-C2960X-48/ || m ~ /^WS-C2960S-48/) return 48
      return 48
    }
    function c2960_profile(m) {
      if (m ~ /^WS-C2960X-24PS/) return "cisco-2960x-24ps-24p-4sfp"
      if (m ~ /^WS-C2960X-24TS/) return "cisco-2960x-24ts-24p-4sfp"
      if (m ~ /^WS-C2960X-48FPD/) return "cisco-2960x-48fpd-48p-2x10g"
      if (m ~ /^WS-C2960X-24/) return "cisco-2960x-24p-4sfp"
      if (m ~ /^WS-C2960X-48/) return "cisco-2960x-48p-2x10g"
      if (m ~ /^WS-C2960S-48FPD/) return "cisco-2960s-48fpd-48p-2x10g"
      if (m ~ /^WS-C2960S-48/) return "cisco-2960s-48p"
      if (m ~ /^WS-C2960S-24/) return "cisco-2960s-24p-4sfp"
      if (is_2960s(m)) return "cisco-2960s-auto"
      return "cisco-2960x-auto"
    }
    function c2960_sfp_count(m) {
      if (m ~ /^WS-C2960X-24/ || m ~ /^WS-C2960S-24/) return 4
      if (m ~ /^WS-C2960X-48/ || m ~ /^WS-C2960S-48/) return 2
      return 0
    }
    function walk_confidence() {
      if (source_walk ~ /full/) return "full walk"
      if (source_walk ~ /targeted/) return "targeted walk"
      return "submitted walk"
    }
    function profile_status_for(model) {
      # The generated supported-device registry is authoritative when an exact
      # model match exists; legacy parser tables remain fallback only.
      if (registry_status == "confirmed") return "supported"
      if (registry_status == "experimental") return "experimental"
      if (model ~ /^WS-C3650-48/) return "supported"
      if (model ~ /^WS-C3650/) return "untested"
      if (model ~ /^WS-C2960X-24TS/) return "community_validated"
      if (is_2960(model)) return "experimental"
      if (model ~ /^WS-C3750-48P/) return "experimental"
      if (model ~ /^WS-C3750X/) return "experimental"
      if (model ~ /^WS-C3560CG-8PC/) return "community_validated"
      if (model == "SG500X-24") return "community_validated"
      if (model == "S5735-L8P4X-A1") return "community_validated"
      if (model == "S5720-12TP-LI-AC") return "community_validated"
      if (model == "XS1930-10") return "experimental"
      if (model == "N2128PX-ON") return "experimental"
      if (model == "Juniper EX3300-48P") return "supported"
      return "unsupported"
    }
    function support_line(status) {
      if (status == "supported") return "supported"
      if (status == "experimental") return "experimental / partially validated"
      if (status == "untested") return "untested / needs validation"
      return "unsupported"
    }
    function validation_note(status) {
      if (status == "supported") return "Validated in Switch Vision live testing."
      if (status == "experimental") return "Model detected and mapped, but not fully validated on all physical port types."
      if (status == "untested") return "Family detected, but this exact layout is not validated yet."
      return "No validated Switch Vision profile matched this device."
    }
    function sfp_note(status, model) {
      if (status == "supported") return "validated"
      if (status == "community_validated") return "real-hardware validated"
      if (is_2960(model)) return "generated from SNMP layout; physical SFP validation pending"
      if (model == "SG500X-24" || model == "S5735-L8P4X-A1" || model == "S5720-12TP-LI-AC" || model == "XS1930-10" || model == "N2128PX-ON") return "generated from contribution-backed interface names; contributor/live validation pending"
      return "review required"
    }
    function model_rank(value, score) {
      if (value == "") return 0
      score = length(value)
      # Prefer exact Cisco orderable SKUs with licence suffixes such as -E or -L.
      if (value ~ /-[A-Z]$/) score += 1000
      return score
    }
    BEGIN {
      max_if_idx = 0
      hostname = "unknown"
      cisco_hostname = ""
      model = "unknown"
      local_model = sys_model = candidate_model = generic_model = juniper_model = ""
      ios = "unknown"
      sysdescr = ""
      rj45 = sfp_gi = ten = stack_if = physical_if = if_total = 0
      stack_member_count = 0
      oper_up = oper_down = 0
      env_names = env_values = 0
      entity_temp = 0
      vlan_count = 0
      trunk_dynamic_count = 0
      trunk_status_count = 0
      likely_trunks = ""
    }
    {
      line = $0
      val = value_of(line)

      if ((line ~ /\.3\.6\.1\.2\.1\.1\.5\.0 = STRING:/) && hostname == "unknown") hostname = val
      if ((line ~ /\.3\.6\.1\.4\.1\.9\.2\.1\.3\.0 = STRING:/) && cisco_hostname == "") cisco_hostname = val
      if ((line ~ /\.3\.6\.1\.2\.1\.1\.1\.0 = STRING:/) && sysdescr == "") sysdescr = val
      if (line ~ /SG500X-24/) sg500_model = "SG500X-24"
      if (line ~ /S5735-L8P4X-A1/) huawei_s5735_model = "S5735-L8P4X-A1"
      if (line ~ /S5720-12TP-LI-AC/) huawei_s5720_model = "S5720-12TP-LI-AC"
      if (line ~ /XS1930-10/) zyxel_model = "XS1930-10"
      if (line ~ /N2128PX-ON/) dell_model = "N2128PX-ON"
      if (line ~ /N2128PX-ON, [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+,/ && match(line, /[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/)) {
        ios = substr(line, RSTART, RLENGTH)
      }
      if (tolower(line) ~ /ex3300-48p/) juniper_model = "Juniper EX3300-48P"
      if (line ~ /\.1\.3\.6\.1\.4\.1\.890\.1\.15\.3\.1\.6\.0 = STRING:/ && val != "") ios = val
      if (ios == "unknown" && match(line, /JUNOS [0-9A-Za-z._-]+/)) {
        ios = substr(line, RSTART, RLENGTH)
      }
      if ((ios == "unknown" || ios ~ /^[0-9]+\.[0-9]+$/) && line ~ /Cisco IOS Software/ && line ~ /Version [0-9][^,]*/) {
        match(line, /Version [0-9][^,]*/)
        ios = substr(line, RSTART + 8, RLENGTH - 8)
      } else if (ios == "unknown" && line ~ /Version [0-9][^,]*/) {
        match(line, /Version [0-9][^,]*/)
        ios = substr(line, RSTART + 8, RLENGTH - 8)
      }
      if (match(line, /WS-C(3650|3750X|3750|3560CG|2960X|2960S)-[A-Z0-9-]+/)) {
        model_candidate = substr(line, RSTART, RLENGTH)
        if (line ~ /\.3\.6\.1\.2\.1\.47\.1\.1\.1\.1\.(2|7|13)\./ || line ~ /\.3\.6\.1\.4\.1\.9\.5\.1\./) {
          if (model_rank(model_candidate) > model_rank(local_model)) local_model = model_candidate
        } else if (line ~ /\.3\.6\.1\.2\.1\.1\.1\.0/) {
          if (model_rank(model_candidate) > model_rank(sys_model)) sys_model = model_candidate
        } else if (model_rank(model_candidate) > model_rank(candidate_model)) candidate_model = model_candidate
      }
      if (line ~ /\.3\.6\.1\.2\.1\.1\.1\.0 = /) sys_descr_present=1
      if (line ~ /\.3\.6\.1\.2\.1\.47\.1\.1\.1\.1\.2\.[0-9]+ = STRING:/ && val ~ /WS-C(3650|3750X|3750|3560CG|2960X|2960S)-[A-Z0-9-]+/) {
        idx=oid_index(line); identity_model_descr_idx[idx]=1; identity_idx[idx]=1
      }
      if (line ~ /\.3\.6\.1\.2\.1\.47\.1\.1\.1\.1\.13\.[0-9]+ = STRING:/ && val ~ /WS-C(3650|3750X|3750|3560CG|2960X|2960S)-[A-Z0-9-]+/) {
        idx=oid_index(line); identity_model_name_idx[idx]=1; identity_idx[idx]=1
      }
      if (line ~ /\.3\.6\.1\.2\.1\.47\.1\.1\.1\.1\.11\.[0-9]+ = STRING:/) {
        idx=oid_index(line); if (val != "") identity_serial_idx[idx]=1
      }
      if (generic_model == "" && line !~ /\.1\.0\.8802\./ && line !~ /\.3\.6\.1\.4\.1\.9\.9\.23\./) {
        if (line ~ /C2960X/) generic_model = "C2960X"
        else if (line ~ /C2960S/) generic_model = "C2960S"
      }

      if (line ~ /\.3\.6\.1\.2\.1\.2\.2\.1\.2\.[0-9]+ = STRING:/) {
        idx = oid_index(line)
        if (!(idx in ifname)) {
          ifname[idx] = val
          ifname_source[idx] = "ifDescr"
          iface_name[val] = 1
          if (val ~ /^Stack/) stack_name[val] = 1
        }
        if (idx + 0 > max_if_idx) max_if_idx = idx + 0
      }
      if (line ~ /\.3\.6\.1\.2\.1\.31\.1\.1\.1\.1\.[0-9]+ = STRING:/) {
        idx = oid_index(line)
        ifname[idx] = val
        ifname_source[idx] = "ifName"
        if (idx + 0 > max_if_idx) max_if_idx = idx + 0
        iface_name[val] = 1
        if (val ~ /^Stack/) stack_name[val] = 1
      }

      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.23\.1\.1\.1\.1\.6\.[0-9]+ = STRING:/) {
        # CDP interface names can duplicate IF-MIB names in full walks.
        # Keep them for diagnostics only; do not add them to iface_name or
        # physical/front-panel counts will be doubled on some platforms.
        cdp_iface[val] = 1
      }

      if (line ~ /\.3\.6\.1\.2\.1\.2\.2\.1\.8\.[0-9]+ = INTEGER:/) {
        # net-snmp may return either "INTEGER: 1" or symbolic values like "INTEGER: up(1)".
        # Count both forms so targeted SNMP walks show real up/down totals.
        if (val == "1" || val ~ /^up\(1\)$/ || val ~ /\(1\)$/) oper_up++
        else if (val == "2" || val ~ /^down\(2\)$/ || val ~ /\(2\)$/) oper_down++
      }

      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.13\.1\.3\.1\.2\.[0-9]+ = STRING:/) {
        idx = oid_index(line)
        env_name[idx] = val
        env_names++
      }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.13\.1\.3\.1\.3\.[0-9]+ = Gauge32:/) {
        idx = oid_index(line)
        env_value[idx] = val
        env_values++
      }
      if (line ~ /\.3\.6\.1\.2\.1\.47\.1\.1\.1\.1\.2\.[0-9]+ = STRING:/ && val ~ /Temp/) {
        entity_temp++
        entity_temp_name[entity_temp] = val
      }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.46\.1\.3\.1\.1\.4\.[0-9]+\.[0-9]+ = STRING:/) {
        vlan_count++
        vlan_names = add_unique(vlan_names, val)
      }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.46\.1\.6\.1\.1\.13\.[0-9]+ = INTEGER:/) {
        idx = oid_index(line)
        trunk_dynamic_count++
        trunk_dynamic[val]++
        trunk_dynamic_by_if[idx] = val
      }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.46\.1\.6\.1\.1\.14\.[0-9]+ = INTEGER:/) {
        idx = oid_index(line)
        trunk_status_count++
        trunk_status[val]++
        trunk_status_by_if[idx] = val
      }
      if (line ~ /\.3\.6\.1\.2\.1\.17\.7\.1\.4\.5\.1\.1\.[0-9]+ = /) qbridge_pvid_count++
    }
    END {
      if (zyxel_model != "") {
        model = zyxel_model
        manufacturer = "Zyxel"
      }
      else if (huawei_s5720_model != "") {
        model = huawei_s5720_model
        manufacturer = "Huawei"
      }
      else if (huawei_s5735_model != "") {
        model = huawei_s5735_model
        manufacturer = "Huawei"
      }
      else if (sg500_model != "") {
        model = sg500_model
        manufacturer = "Cisco"
      }
      else if (juniper_model != "") {
        model = juniper_model
        manufacturer = "Juniper"
      }
      else if (dell_model != "") model = dell_model
      else if (local_model != "") model = local_model
      else if (sys_model != "") model = sys_model
      else if (candidate_model != "") model = candidate_model
      else if (generic_model != "") model = generic_model
      if (hostname == "unknown" && cisco_hostname != "") hostname = cisco_hostname
      print ""
      print "Discovery parser summary"
      print "------------------------"
      print "Hostname: " hostname
      if (cisco_hostname != "") print "Cisco local hostname: " cisco_hostname
      print "Model/platform: " model
      print "OS/software version: " ios
      if_total = ifname_native_total = ifdescr_fallback_total = 0
      for (idx in ifname) {
        if_total++
        if (ifname_source[idx] == "ifName") ifname_native_total++
        else if (ifname_source[idx] == "ifDescr") ifdescr_fallback_total++
      }
      for (n in iface_name) {
        key = n
        is_gi = (key ~ /^Gi/ || key ~ /^GigabitEthernet/)
        is_te = (key ~ /^Te/ || key ~ /^TenGigabitEthernet/)
        special = 0

        if (model == "WS-C3750-48P" && n ~ /^(Fa|FastEthernet)[0-9]+\/0\/([1-9]|[1-3][0-9]|4[0-8])$/) {
          c3750_key = n
          sub(/^FastEthernet/, "", c3750_key)
          sub(/^Fa/, "", c3750_key)
          split(c3750_key, cp, "/")
          member = cp[1] + 0
          port = cp[3] + 0
          physical_id = "Fa" member "/0/" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1; rj45_key[physical_id] = 1
            member_key[member] = 1; member_physical[member]++; member_rj45[member]++
          }
          special = 1
        } else if (model == "WS-C3750-48P" && n ~ /^(Gi|GigabitEthernet)[0-9]+\/0\/[1-4]$/) {
          c3750_key = n
          sub(/^GigabitEthernet/, "", c3750_key)
          sub(/^Gi/, "", c3750_key)
          split(c3750_key, cp, "/")
          member = cp[1] + 0
          port = cp[3] + 0
          physical_id = "Gi" member "/0/" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1; sfp_key[physical_id] = 1
            member_key[member] = 1; member_physical[member]++; member_sfp[member]++
          }
          special = 1
        } else if (model == "SG500X-24" && n ~ /^gi1\/[0-9]+$/) {
          port = n; sub(/^gi1\//, "", port)
          physical_id = "Gi1/" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1; rj45_key[physical_id] = 1
            member_key[1] = 1; member_physical[1]++; member_rj45[1]++
          }
          special = 1
        } else if (model == "SG500X-24" && n ~ /^te1\/[0-9]+$/) {
          port = n; sub(/^te1\//, "", port)
          physical_id = "Te1/" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1; ten_key[physical_id] = 1
            member_key[1] = 1; member_physical[1]++; member_ten[1]++
          }
          special = 1
        } else if (model == "S5735-L8P4X-A1" && n ~ /^GigabitEthernet0\/0\/[0-9]+$/) {
          port = n; sub(/^GigabitEthernet0\/0\//, "", port)
          physical_id = "Gi0/0/" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1; rj45_key[physical_id] = 1
            member_key[1] = 1; member_physical[1]++; member_rj45[1]++
          }
          special = 1
        } else if (model == "S5735-L8P4X-A1" && n ~ /^XGigabitEthernet0\/0\/[0-9]+$/) {
          port = n; sub(/^XGigabitEthernet0\/0\//, "", port)
          physical_id = "XGE0/0/" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1; ten_key[physical_id] = 1
            member_key[1] = 1; member_physical[1]++; member_ten[1]++
          }
          special = 1
        } else if (model == "S5720-12TP-LI-AC" && n ~ /^GigabitEthernet0\/0\/[0-9]+$/) {
          port = n; sub(/^GigabitEthernet0\/0\//, "", port)
          physical_id = "GE0/0/" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1
            member_key[1] = 1
            member_physical[1]++
            if ((port + 0) <= 8) {
              rj45_key[physical_id] = 1; member_rj45[1]++
            } else if ((port + 0) <= 12) {
              sfp_key[physical_id] = 1; member_sfp[1]++
            }
          }
          special = 1
        } else if (model == "XS1930-10" && n ~ /^swp0[0-9]$/) {
          port = n; sub(/^swp0/, "", port)
          physical_id = "swp0" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1
            member_key[1] = 1
            member_physical[1]++
            if ((port + 0) <= 7) {
              rj45_key[physical_id] = 1; member_rj45[1]++
            } else {
              ten_key[physical_id] = 1; member_ten[1]++
            }
          }
          special = 1
        }

        if (!special && model == "N2128PX-ON" && n ~ /^(Gi|GigabitEthernet)[0-9]+\/0\/[0-9]+$/) {
          dell_key = n
          sub(/^GigabitEthernet/, "", dell_key)
          sub(/^Gi/, "", dell_key)
          split(dell_key, dp, "/")
          member = dp[1] + 0
          port = dp[3] + 0
          if (member > 0 && dp[2] == "0" && port >= 1 && port <= 28) {
            physical_id = "Gi" member "/0/" port
            if (!(physical_id in physical_key)) {
              physical_key[physical_id] = 1; rj45_key[physical_id] = 1
              member_key[member] = 1; member_physical[member]++; member_rj45[member]++
            }
            special = 1
          }
        } else if (!special && model == "N2128PX-ON" && n ~ /^(Te|TenGigabitEthernet)[0-9]+\/0\/[0-9]+$/) {
          dell_key = n
          sub(/^TenGigabitEthernet/, "", dell_key)
          sub(/^Te/, "", dell_key)
          split(dell_key, dp, "/")
          member = dp[1] + 0
          port = dp[3] + 0
          if (member > 0 && dp[2] == "0" && port >= 1 && port <= 2) {
            physical_id = "Te" member "/0/" port
            if (!(physical_id in physical_key)) {
              physical_key[physical_id] = 1; ten_key[physical_id] = 1
              member_key[member] = 1; member_physical[member]++; member_ten[member]++
            }
            special = 1
          }
        }

        if (!special && model == "Juniper EX3300-48P" && n ~ /^ge-0\/0\/([0-9]|[1-3][0-9]|4[0-7])$/) {
          port = n
          sub(/^ge-0\/0\//, "", port)
          physical_id = "ge-0/0/" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1
            rj45_key[physical_id] = 1
            member_key[1] = 1
            member_physical[1]++
            member_rj45[1]++
          }
          special = 1
        } else if (!special && model == "Juniper EX3300-48P" && n ~ /^(ge|xe)-0\/1\/[0-3]$/) {
          cage = n
          sub(/^(ge|xe)-0\/1\//, "", cage)
          physical_id = "uplink-0/1/" cage
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1
            member_key[1] = 1
            member_physical[1]++
            if (n ~ /^xe-/) {
              ten_key[physical_id] = 1
              member_ten[1]++
            } else {
              sfp_key[physical_id] = 1
              member_sfp[1]++
            }
          } else if (n ~ /^xe-/ && (physical_id in sfp_key)) {
            delete sfp_key[physical_id]
            if (member_sfp[1] > 0) member_sfp[1]--
            if (!(physical_id in ten_key)) {
              ten_key[physical_id] = 1
              member_ten[1]++
            }
          }
          special = 1
        }

        if (!special && model ~ /^WS-C2960[XS]-48FPD/ && is_gi) {
          alias_key = key
          sub(/^GigabitEthernet/, "", alias_key)
          sub(/^Gi/, "", alias_key)
          if (alias_key ~ /^[0-9]+\/0\/[0-9]+$/) {
            split(alias_key, ap, "/")
            if ((ap[3] + 0) > 48) {
              alias_port = (ap[3] + 0) - 48
              if (("Te" ap[1] "/0/" alias_port) in iface_name || ("TenGigabitEthernet" ap[1] "/0/" alias_port) in iface_name) {
                special = 1
              }
            }
          }
        }

        if (!special) {
          sub(/^GigabitEthernet/, "", key)
          sub(/^TenGigabitEthernet/, "", key)
          sub(/^Gi/, "", key)
          sub(/^Te/, "", key)
          if (key ~ /^[0-9]+\/[0-9]+\/[0-9]+$/) {
            split(key, pp, "/")
            member_key[pp[1]] = 1
            physical_id = (is_te ? "Te" : (is_gi ? "Gi" : "If")) key
            if (!(physical_id in physical_key)) {
              physical_key[physical_id] = 1
              member_physical[pp[1]]++
              if (is_2960(model) && pp[2] == "0" && is_gi && (pp[3] + 0) > c2960_rj45_limit(model)) {
                sfp_key[physical_id] = 1
                member_sfp[pp[1]]++
              } else if (pp[2] == "0" && is_gi) {
                rj45_key[physical_id] = 1
                member_rj45[pp[1]]++
              }
              if (pp[2] == "1" && is_gi) {
                sfp_key[physical_id] = 1
                member_sfp[pp[1]]++
              }
              if ((is_2960(model) && pp[2] == "0" && is_te) || (pp[2] == "1" && is_te)) {
                ten_key[physical_id] = 1
                member_ten[pp[1]]++
              }
            }
          }
          if (model ~ /^WS-C3560CG-8PC/ && key ~ /^[0-9]+\/[0-9]+$/ && is_gi) {
            split(key, pp, "/")
            physical_id = "Gi" key
            if (!(physical_id in physical_key)) {
              physical_key[physical_id] = 1
              member_key[1] = 1
              member_physical[1]++
              if ((pp[2] + 0) <= 8) { rj45_key[physical_id] = 1; member_rj45[1]++ }
              else if ((pp[2] + 0) <= 10) { sfp_key[physical_id] = 1; member_sfp[1]++ }
            }
          }
        }
        if (n ~ /^Stack/) stack_key[n] = 1
      }
      for (k in physical_key) physical_if++
      for (k in rj45_key) rj45++
      for (k in sfp_key) sfp_gi++
      for (k in ten_key) ten++
      for (k in stack_key) stack_if++
      for (k in member_key) {
        stack_member_count++
        if (k + 0 > max_member) max_member = k + 0
      }
      print ""
      print "Stack summary:"
      if (model == "Juniper EX3300-48P") {
        print "- Standalone member groups detected: " (stack_member_count > 0 ? stack_member_count : 1)
        print "- Virtual Chassis support: not validated"
      } else if (stack_member_count > 0) {
        print "- Stack members detected: " stack_member_count
        for (m = 1; m <= max_member; m++) {
          if (m in member_key) {
            print "- Member " m ": " (member_rj45[m] + 0) " RJ45, " (member_sfp[m] + 0) " SFP, " (member_ten[m] + 0) " 10G, " (member_physical[m] + 0) " physical interfaces"
          }
        }
      } else {
        print "- Stack members detected: unknown"
      }
      print ""
      print "Interface summary:"
      print "- Usable interface-name entries: " if_total
      print "- Native ifName entries used: " ifname_native_total
      print "- ifDescr fallback entries used: " ifdescr_fallback_total
      print "- Physical switch interfaces detected: " physical_if
      if (model == "Juniper EX3300-48P") {
        print "- RJ45 ge-0/0/0-47 ports: " rj45
        print "- 1G SFP ge-0/1/* uplinks currently exposed: " sfp_gi
        print "- 10G SFP+ xe-0/1/* uplinks currently exposed: " ten
      } else if (model == "WS-C3750-48P") {
        print "- RJ45 FastEthernet <member>/0/1-48 ports: " rj45
        print "- 1G SFP GigabitEthernet <member>/0/1-4 uplinks: " sfp_gi
      } else if (model == "XS1930-10") {
        print "- RJ45 swp00-swp07 ports: " rj45
        print "- 10G SFP+ swp08-swp09 uplinks: " ten
      } else if (model == "N2128PX-ON") {
        print "- RJ45 Gi <member>/0/1-28 ports: " rj45
        print "- 10G SFP+ Te <member>/0/1-2 uplinks: " ten
      } else {
        print "- RJ45 Gi x/0/1-48 style ports: " rj45
        print "- SFP Gi x/1/* uplinks: " sfp_gi
        print "- 10G Te x/1/* uplinks: " ten
      }
      print "- Stack-related interfaces: " stack_if
      print "- Oper status up/down counts: " oper_up " / " oper_down
      print ""
      print "Switch Vision mapping profile:"
      profile = "unknown"
      profile_status = profile_status_for(model)
      if (model ~ /^WS-C3650-48/) profile = "cisco-3650-48p-2x10g"
      else if (is_2960(model)) profile = c2960_profile(model)
      else if (model ~ /^WS-C3750-48P/) profile = "cisco-3750-48p-48fe-4sfp"
      else if (model ~ /^WS-C3750X-24P/) profile = "cisco-3750x-24p"
      else if (model ~ /^WS-C3560CG-8PC/) profile = "cisco-3560cg-8pc-8p-2dual"
      else if (model == "Juniper EX3300-48P") profile = "juniper-ex3300-48p"
      else if (model == "SG500X-24") profile = "cisco-sg500x-24-24p-4x10g"
      else if (model == "S5735-L8P4X-A1") profile = "huawei-s5735-l8p4x-a1"
      else if (model == "S5720-12TP-LI-AC") profile = "huawei-s5720-12tp-li-ac"
      else if (model == "XS1930-10") profile = "zyxel-xs1930-10"
      else if (model == "N2128PX-ON") profile = "dell-n2128px-on"
      else if (model ~ /^WS-C3650/) profile = "cisco-3650-auto"
      print "- Matched profile: " profile
      print "- Profile status: " profile_status
      print "- Support status: " support_line(profile_status)
      print "- Validation note: " validation_note(profile_status)
      print ""
      print "Interface mapping report:"
      print "- Translation: ifIndex -> ifName/ifDescr -> member/port role -> Switch Vision sensor prefix"
      mapped_rows = 0
      unmapped_rows = 0
      for (idx = 1; idx <= max_if_idx; idx++) if (idx in ifname) {
        name = ifname[idx]
        key = name
        kind = "unknown"
        if (model == "Juniper EX3300-48P" && name ~ /^ge-0\/0\/([0-9]|[1-3][0-9]|4[0-7])$/) {
          port = name
          sub(/^ge-0\/0\//, "", port)
          mapped_rows++
          print "  - ifIndex " idx " -> " name " -> standalone RJ45 port " (port + 0)
          continue
        }
        if (model == "Juniper EX3300-48P" && name ~ /^(ge|xe)-0\/1\/[0-3]$/) {
          cage = name
          sub(/^(ge|xe)-0\/1\//, "", cage)
          xe_name = "xe-0/1/" cage
          if (name ~ /^ge-/ && (xe_name in iface_name)) continue
          mapped_rows++
          print "  - ifIndex " idx " -> " name " -> standalone SFP/SFP+ uplink cage " (cage + 0)
          continue
        }
        if (model == "SG500X-24" && name ~ /^gi1\/[0-9]+$/) {
          port = name; sub(/^gi1\//, "", port)
          mapped_rows++; print "  - ifIndex " idx " -> " name " -> standalone RJ45 port " (port + 0)
          continue
        }
        if (model == "SG500X-24" && name ~ /^te1\/[0-9]+$/) {
          port = name; sub(/^te1\//, "", port)
          mapped_rows++; print "  - ifIndex " idx " -> " name " -> standalone 10G SFP " (port + 0)
          continue
        }
        if (model == "S5735-L8P4X-A1" && name ~ /^GigabitEthernet0\/0\/[0-9]+$/) {
          port = name; sub(/^GigabitEthernet0\/0\//, "", port)
          mapped_rows++; print "  - ifIndex " idx " -> " name " -> standalone RJ45 port " (port + 0)
          continue
        }
        if (model == "S5735-L8P4X-A1" && name ~ /^XGigabitEthernet0\/0\/[0-9]+$/) {
          port = name; sub(/^XGigabitEthernet0\/0\//, "", port)
          mapped_rows++; print "  - ifIndex " idx " -> " name " -> standalone 10G uplink " (port + 0)
          continue
        }
        if (model == "S5720-12TP-LI-AC" && name ~ /^GigabitEthernet0\/0\/[0-9]+$/) {
          port = name; sub(/^GigabitEthernet0\/0\//, "", port)
          if ((port + 0) <= 8) {
            mapped_rows++; print "  - ifIndex " idx " -> " name " -> standalone RJ45 port " (port + 0)
          } else if ((port + 0) <= 12) {
            mapped_rows++; print "  - ifIndex " idx " -> " name " -> standalone 1G SFP " ((port + 0) - 8)
          }
          continue
        }
        if (model == "XS1930-10" && name ~ /^swp0[0-9]$/) {
          port = name; sub(/^swp0/, "", port)
          if ((port + 0) <= 7) {
            mapped_rows++; print "  - ifIndex " idx " -> " name " -> standalone RJ45 port " ((port + 0) + 1)
          } else {
            mapped_rows++; print "  - ifIndex " idx " -> " name " -> standalone 10G SFP+ uplink " ((port + 0) - 7)
          }
          continue
        }
        if (model == "WS-C3750-48P" && name ~ /^(Fa|FastEthernet)[0-9]+\/0\/([1-9]|[1-3][0-9]|4[0-8])$/) {
          c3750_key = name
          sub(/^FastEthernet/, "", c3750_key)
          sub(/^Fa/, "", c3750_key)
          split(c3750_key, cp, "/")
          mapped_rows++; print "  - ifIndex " idx " -> " name " -> member " (cp[1] + 0) " RJ45 FastEthernet port " (cp[3] + 0)
          continue
        }
        if (model == "WS-C3750-48P" && name ~ /^(Gi|GigabitEthernet)[0-9]+\/0\/[1-4]$/) {
          c3750_key = name
          sub(/^GigabitEthernet/, "", c3750_key)
          sub(/^Gi/, "", c3750_key)
          split(c3750_key, cp, "/")
          mapped_rows++; print "  - ifIndex " idx " -> " name " -> member " (cp[1] + 0) " 1G SFP uplink " (cp[3] + 0)
          continue
        }
        if (model == "N2128PX-ON" && name ~ /^(Gi|GigabitEthernet|Te|TenGigabitEthernet)[0-9]+\/0\/[0-9]+$/) {
          dell_key = name
          sub(/^GigabitEthernet/, "", dell_key)
          sub(/^TenGigabitEthernet/, "", dell_key)
          sub(/^Gi/, "", dell_key)
          sub(/^Te/, "", dell_key)
          split(dell_key, dp, "/")
          member = dp[1] + 0
          port = dp[3] + 0
          if ((name ~ /^(Gi|GigabitEthernet)/) && dp[2] == "0" && port >= 1 && port <= 28) {
            mapped_rows++; print "  - ifIndex " idx " -> " name " -> member " member " RJ45 port " port
            continue
          }
          if ((name ~ /^(Te|TenGigabitEthernet)/) && dp[2] == "0" && port >= 1 && port <= 2) {
            mapped_rows++; print "  - ifIndex " idx " -> " name " -> member " member " 10G SFP+ uplink " port
            continue
          }
        }
        if (model ~ /^WS-C2960[XS]-48FPD/ && (name ~ /^Gi/ || name ~ /^GigabitEthernet/)) {
          alias_key = key
          sub(/^GigabitEthernet/, "", alias_key)
          sub(/^Gi/, "", alias_key)
          if (alias_key ~ /^[0-9]+\/0\/[0-9]+$/) {
            split(alias_key, ap, "/")
            if ((ap[3] + 0) > 48) {
              alias_port = (ap[3] + 0) - 48
              if (("Te" ap[1] "/0/" alias_port) in iface_name || ("TenGigabitEthernet" ap[1] "/0/" alias_port) in iface_name) continue
            }
          }
        }
        sub(/^GigabitEthernet/, "", key)
        sub(/^TenGigabitEthernet/, "", key)
        sub(/^Gi/, "", key)
        sub(/^Te/, "", key)
        if (key ~ /^[0-9]+\/[0-9]+\/[0-9]+$/) {
          split(key, mp, "/")
          if (is_2960(model) && (name ~ /^Gi/ || name ~ /^GigabitEthernet/) && mp[2] == "0" && (mp[3] + 0) > c2960_rj45_limit(model)) kind = "SFP/uplink " ((mp[3] + 0) - c2960_rj45_limit(model))
          else if (is_2960(model) && (name ~ /^Te/ || name ~ /^TenGigabitEthernet/) && mp[2] == "0") kind = "10G SFP " mp[3]
          else if ((name ~ /^Gi/ || name ~ /^GigabitEthernet/) && mp[2] == "0") kind = "RJ45 port " mp[3]
          else if ((name ~ /^Gi/ || name ~ /^GigabitEthernet/) && mp[2] == "1") kind = "SFP/uplink " mp[3]
          else if ((name ~ /^Te/ || name ~ /^TenGigabitEthernet/) && mp[2] == "1") kind = "10G SFP " mp[3]
          else kind = "physical interface"
          mapped_rows++
          print "  - ifIndex " idx " -> " name " -> member " mp[1] " " kind
        } else if (model ~ /^WS-C3560CG-8PC/ && key ~ /^[0-9]+\/[0-9]+$/ && (name ~ /^Gi/ || name ~ /^GigabitEthernet/)) {
          split(key, mp, "/")
          if ((mp[2] + 0) <= 8) kind = "RJ45 port " mp[2]
          else kind = "dual-purpose uplink " ((mp[2] + 0) - 8)
          mapped_rows++
          print "  - ifIndex " idx " -> " name " -> standalone " kind
        } else if (name ~ /^Stack/ || name ~ /^Vl/ || name ~ /^Vlan/ || name ~ /^Po/ || name ~ /^Port-channel/ || name ~ /^Nu/) {
          # Logical/stack interfaces are useful in the walk but are not front-panel ports.
        } else {
          unmapped_rows++
        }
      }
      print "- Mapped physical interfaces: " mapped_rows
      if (unmapped_rows > 0) print "- Unmapped non-front-panel interfaces: " unmapped_rows
      print ""
      print "Discovery checks:"
      if (model == "Juniper EX3300-48P") print "- PASS: Juniper EX3300-48P model detected"
      else if (model ~ /^WS-C3650/) print "- PASS: Catalyst 3650 model detected"
      else if (is_2960x(model) && profile_status == "supported") print "- PASS: Catalyst 2960X exact model confirmed by supported-device registry"
      else if (is_2960s(model) && profile_status == "supported") print "- PASS: Catalyst 2960S exact model confirmed by supported-device registry"
      else if (is_2960x(model)) print "- WARN: Catalyst 2960X model detected; experimental validation remains"
      else if (is_2960s(model)) print "- WARN: Catalyst 2960S model detected; experimental validation remains"
      else if (model ~ /^WS-C3750-48P/) print "- INFO: Catalyst 3750 Experimental exact 48 FastEthernet + 4 x 1G SFP mapping loaded"
      else if (model ~ /^WS-C3750X/) print "- WARN: Catalyst 3750X model detected; possible/experimental only, not supported"
      else if (model ~ /^WS-C3560CG/) print "- INFO: Catalyst 3560-CG Community Validated mapping loaded; Gi0/9 and Gi0/10 retain dual-purpose combo semantics"
      else if (model == "SG500X-24") print "- INFO: Cisco SG500X-24 Community Validated mapping loaded from real-hardware contribution evidence"
      else if (model == "S5735-L8P4X-A1") print "- INFO: Huawei S5735-L8P4X-A1 Community Validated mapping loaded from repeated real-hardware evidence"
      else if (model == "S5720-12TP-LI-AC") print "- INFO: Huawei S5720-12TP-LI-AC Community Validated physical mapping loaded with 1G SFP speed safeguards"
      else if (model == "XS1930-10") print "- INFO: Zyxel XS1930-10 Experimental mapping loaded from Support My Switch contribution SV-2026-000004"
      else if (model == "N2128PX-ON") print "- INFO: Dell EMC N2128PX-ON Experimental mapping loaded from contribution evidence dated 2026-08-16"
      else print "- WARN: known Switch Vision model not confirmed"
      print (ios != "unknown" ? "- PASS: OS/software version detected" : "- WARN: OS/software version not detected")
      print (if_total > 0 ? "- PASS: usable interface-name table detected" : "- FAIL: neither ifName nor ifDescr interface names detected")
      print (physical_if > 0 ? "- PASS: physical switch interfaces detected" : "- FAIL: physical switch interfaces not detected")
      if (model == "Juniper EX3300-48P") print "- PASS: Juniper VLAN/trunk mapping uses Q-BRIDGE-MIB and derived VLAN state"
      else if (model == "XS1930-10") print (qbridge_pvid_count > 0 ? "- PASS: Zyxel PVID mapping uses Q-BRIDGE-MIB" : "- WARN: Q-BRIDGE PVID rows not detected")
      else print (trunk_status_count > 0 ? "- PASS: Cisco trunk status OIDs detected" : "- WARN: Cisco trunk status OIDs not detected")
      if (target_ip != "unknown" && target_ip != "") print "- PASS: management target provided: " target_ip
      else print "- WARN: management target not provided; provide a switch_host in the switch list or targets CSV before generator use"
      ready = (((model ~ /^WS-C3650/ || model ~ /^WS-C3750X/ || is_2960(model)) && if_total > 0 && physical_if > 0 && trunk_status_count > 0) || (model == "WS-C3750-48P" && if_total > 0 && stack_member_count > 0 && rj45 == (48 * stack_member_count) && sfp_gi == (4 * stack_member_count)) || ((model == "SG500X-24" || model == "S5735-L8P4X-A1" || model == "S5720-12TP-LI-AC") && if_total > 0 && physical_if > 0) || (model == "XS1930-10" && if_total > 0 && rj45 == 8 && ten == 2 && qbridge_pvid_count > 0) || (model == "N2128PX-ON" && if_total > 0 && stack_member_count > 0 && rj45 == (28 * stack_member_count) && ten == (2 * stack_member_count)) || (model == "Juniper EX3300-48P" && if_total > 0 && rj45 == 48))
      print "- Ready for SNMP2MQTT generation: " (ready ? "yes, review-only" : "no")
      if (profile_status == "supported") print "- Generator confidence: supported profile; review generated YAML before installing"
      else if (profile_status == "community_validated") print "- Generator confidence: community-validated profile; physical layout verified on real hardware"
      else if (profile_status == "experimental") print "- Generator confidence: experimental profile; review mapping/YAML before use"
      else if (profile_status == "untested") print "- Generator confidence: untested profile; use for lab review only"
      else print "- Generator confidence: unsupported; generator output should not be used"
      print "- SNMP2MQTT generator status: " (generator_enabled == "true" ? "enabled" : "disabled")
      print ""
      print "Model validation:"
      print "- Exact model detected: " (model != "unknown" ? "yes" : "no")
      print "- Profile status label: " profile_status
      print "- RJ45 mapping: " (rj45 > 0 ? "generated from IF-MIB/interface layout" : "not detected")
      print "- SFP/uplink mapping: " sfp_note(profile_status, model)
      if (model ~ /^S5720-12TP-LI-AC$/ || model ~ /^S5735-L8P4X-A1$/) print "- Faceplate: generic 48 RJ45 + 4 SFP fallback visual"
      else if (model == "XS1930-10") print "- Faceplate: compact 8 RJ45 + 2 SFP temporary fallback visual"
      else if (model == "N2128PX-ON") print "- Faceplate: generic 48 RJ45 + 4 SFP fallback visual; exact Dell faceplate pending"
      else print "- Faceplate: registry-selected visual"
      print ""
      print "VLAN / trunk summary:"
      print "- VLAN name entries: " vlan_count
      if (vlan_names != "") print "- VLAN names seen: " vlan_names
      if (model == "Juniper EX3300-48P") print "- Juniper VLAN source: Q-BRIDGE-MIB / derived VLAN sensors"
      else if (model == "XS1930-10") print "- Zyxel VLAN source: Q-BRIDGE-MIB PVID (" qbridge_pvid_count " row(s)); trunk/access mode not inferred"
      else print "- Cisco dynamic trunk state OIDs: " trunk_dynamic_count
      for (s in trunk_dynamic) print "  - dynamic state " s " (" trunk_label(s) "): " trunk_dynamic[s]
      if (model != "Juniper EX3300-48P") print "- Cisco trunk status OIDs: " trunk_status_count
      for (s in trunk_status) print "  - trunk status " s " (" trunk_label(s) "): " trunk_status[s]
      for (idx in trunk_status_by_if) {
        if (trunk_status_by_if[idx] == "1" && (idx in ifname)) likely_trunks = add_unique(likely_trunks, ifname[idx])
      }
      if (likely_trunks != "") print "- Likely trunk ports: " likely_trunks
      print ""
      print "Temperature summary:"
      print "- Cisco EnvMon temp names: " env_names
      print "- Cisco EnvMon temp values: " env_values
      shown = 0
      for (idx in env_name) {
        if (shown < 8) {
          shown++
          suffix = (idx in env_value ? " = " env_value[idx] " C" : "")
          print "  - " env_name[idx] suffix
        }
      }
      if (env_names > shown) print "  - ..."
      print "- ENTITY-MIB temp labels: " entity_temp
      for (i = 1; i <= entity_temp && i <= 8; i++) print "  - " entity_temp_name[i]
      if (entity_temp > 8) print "  - ..."
      print ""
      print "Switch Vision recommendation:"
      if (model == "Juniper EX3300-48P") {
        print "- Suggested profile: juniper-ex3300-48p"
        print "- Confidence: high"
        print "- Support status: supported"
      } else if (model ~ /^WS-C3650/ && stack_member_count > 1 && rj45 >= (48 * stack_member_count) && ten >= (2 * stack_member_count)) {
        print "- Suggested stack profile: cisco-3650-stack-" stack_member_count "x48p-" ten "x10g"
        print "- Per-member dashboard profile: cisco-3650-48p-2x10g"
        print "- Confidence: high"
        print "- Support status: supported"
      } else if (model ~ /^WS-C3650/ && rj45 >= 48 && ten >= 2) {
        print "- Suggested profile: cisco-3650-48p-2x10g"
        print "- Confidence: high"
        print "- Support status: supported"
      } else if (model ~ /^WS-C3650/) {
        print "- Suggested profile: cisco-3650-auto"
        print "- Confidence: medium; port layout needs review"
        print "- Support status: possible until validated"
      } else if (is_2960(model)) {
        print "- Suggested profile: " c2960_profile(model)
        if (profile_status == "supported") {
          print "- Confidence: high; exact model confirmed by supported-device registry"
          print "- Support status: supported"
          print "- Validation note: registry-confirmed model, RJ45, PoE, system sensors and uplinks"
        } else {
          print "- Confidence: experimental; based on " walk_confidence()
          print "- Support status: experimental / partially validated"
          print "- Validation note: SFP/uplink physical validation pending"
        }
      } else if (model ~ /^WS-C3750-48P/) {
        print "- Suggested profile: cisco-3750-48p-48fe-4sfp"
        print "- Confidence: experimental; exact 48 FastEthernet + 4 x 1G SFP physical contract"
        print "- Support status: experimental / field revalidation required"
      } else if (model ~ /^WS-C3750X-24P/) {
        print "- Suggested profile: cisco-3750x-24p"
        print "- Confidence: experimental; based on submitted walk"
        print "- Support status: experimental / partially validated"
      } else if (model == "SG500X-24") {
        print "- Suggested profile: cisco-sg500x-24-24p-4x10g"
        print "- Confidence: experimental; based on Support My Switch interface evidence"
        print "- Support status: experimental / partially validated"
      } else if (model == "S5735-L8P4X-A1") {
        print "- Suggested profile: huawei-s5735-l8p4x-a1"
        print "- Confidence: experimental; repeated contribution interface evidence"
        print "- Support status: experimental / partially validated"
      } else if (model == "S5720-12TP-LI-AC") {
        print "- Suggested profile: huawei-s5720-12tp-li-ac"
        print "- Confidence: experimental; ifDescr mapping confirmed by contribution SV-2026-000014"
        print "- Support status: experimental / partially validated"
      } else if (model == "XS1930-10") {
        print "- Suggested profile: zyxel-xs1930-10"
        print "- Confidence: experimental; mapping and system OIDs proven by Support My Switch contribution SV-2026-000004"
        print "- Support status: experimental / community contribution"
      } else if (model == "N2128PX-ON") {
        print "- Suggested profile: dell-n2128px-on"
        print "- Confidence: experimental; standalone and two-member stack interface topology confirmed by contribution dated 2026-08-16"
        print "- Support status: experimental / community contribution"
      } else {
        print "- Suggested profile: unknown"
        print "- Confidence: low"
        print "- Support status: unsupported"
      }
      print ""
      print "Parser notes:"
      print "- Report is read-only. No Home Assistant, MQTT, SNMP2MQTT, or dashboard files are changed."
      print "- Trunk values are decoded as a first-pass helper and still reported for review."
      print "- Stack-aware recommendation is based on detected interface member numbering."
      if (generator_enabled == "true") print "- SNMP2MQTT YAML generation is review-only. The generated file is not installed automatically."
      else print "- SNMP2MQTT YAML generation remains disabled by default."
    }
  ' "$walk_file"
}

write_walk_section() {
  walk_file="$1"
  section_title="$2"

  echo "$section_title"
  printf '%s\n' "$section_title" | sed 's/./-/g'
  echo "File: $walk_file"
  target_ip=$(target_for_walk "$walk_file")
  echo "Management target: $target_ip"
  write_csv_diagnostics_for_walk "$walk_file"
  if [ -f "$walk_file" ]; then
    line_count=$(wc -l < "$walk_file" | tr -d ' ')
    echo "SNMP walk file found: yes"
    if should_skip_walk_file "$walk_file"; then
      echo "SNMP walk skipped: failed/insufficient SNMP walk output"
      echo ""
      return 0
    fi
    echo "SNMP walk line count: $line_count"
    echo ""
    if command -v cv_write_vendor_identity_report >/dev/null 2>&1; then
      cv_write_vendor_identity_report "$walk_file"
      if command -v cv_write_capabilities_json >/dev/null 2>&1; then
        cap_switch=$(basename "$(dirname "$walk_file")" | sed 's/[^A-Za-z0-9._-]/_/g')
        [ -n "$cap_switch" ] || cap_switch="switch"
        cap_path="$CAPABILITIES_DIR/${cap_switch}-capabilities.json"
        cv_write_capabilities_json "$walk_file" "$cap_path" ""
        detected_model=$(jq -r '.device.model_text // "unknown"' "$cap_path" 2>/dev/null || printf 'unknown')
        model_override=$(switch_model_override_for_name "$cap_switch")
        case "$model_override" in ""|auto|Auto-detect|AUTO) model_override="auto" ;; esac
        effective_model="$detected_model"
        compatibility_mode=false
        if [ "$model_override" != "auto" ]; then
          effective_model="$model_override"
          compatibility_mode=true
        fi
        tmp_cap="${cap_path}.tmp"
        jq --arg detected "$detected_model" --arg override "$model_override" --arg effective "$effective_model" --argjson compat "$compatibility_mode" '
          .device.detected_model_text=$detected
          | .device.model_override=(if $override == "auto" then null else $override end)
          | .device.effective_model_text=$effective
          | .device.compatibility_mode=$compat
        ' "$cap_path" > "$tmp_cap" && mv "$tmp_cap" "$cap_path"
        if [ -x /standard_sensor_scan.py ]; then
          python3 /standard_sensor_scan.py --walk "$walk_file" --enrich "$cap_path"
        fi
        if [ -x /vendor_sensor_scan.py ]; then
          python3 /vendor_sensor_scan.py --walk "$walk_file" --enrich "$cap_path"
        fi
        registry_model="$detected_model"
        if [ -x /registry_lookup.py ]; then
          python3 /registry_lookup.py --model "$detected_model" --enrich "$cap_path" --enrich-key registry
          tmp_cap="${cap_path}.tmp"
          jq 'if (.registry.match // false) then .device.support_status=(.registry.status // .device.support_status) else . end' "$cap_path" > "$tmp_cap" && mv "$tmp_cap" "$cap_path"
          if [ "$model_override" != "auto" ]; then
            python3 /registry_lookup.py --model "$effective_model" --enrich "$cap_path" --enrich-key model_override_registry
          fi
        fi
        echo "Normalized capabilities:"
        echo "- Per-switch file: $cap_path"
        echo "- Behaviour authority: observational sidecar only; existing parser/generator remains unchanged"
        echo ""
        if [ -x /standard_sensor_scan.py ]; then
          python3 /standard_sensor_scan.py --walk "$walk_file" --report
          echo ""
        fi
        if [ -x /vendor_sensor_scan.py ]; then
          python3 /vendor_sensor_scan.py --walk "$walk_file" --enrich "$cap_path" --report
          echo ""
        fi
        if [ -x /registry_lookup.py ]; then
          python3 /registry_lookup.py --model "$registry_model" --report
          if [ "$model_override" != "auto" ]; then
            echo "Model compatibility override:"
            echo "- Detected model: $detected_model"
            echo "- Selected model override: $model_override"
            echo "- Effective visual/mapping model: $effective_model"
            echo "- Compatibility mode: experimental"
            echo "- Warning: ports, uplinks, sensors, PoE, and faceplate alignment may be incomplete or incorrect."
          else
            echo "Model compatibility override: Auto-detect"
          fi
          echo "- Registry authority: informational only; the actual detected model is never replaced"
          echo ""
        fi
      fi
    else
      echo "Vendor knowledge:"
      echo "- Database status: unavailable; existing parser fallback remains active"
      echo ""
    fi
    echo "Early checks:"
    if grep -qi "catalyst\|cisco" "$walk_file"; then
      echo "- Cisco/Catalyst text: found"
    else
      echo "- Cisco/Catalyst text: not found yet"
    fi
    if grep -q "1.3.6.1.2.1.2.2.1.8" "$walk_file" || grep -q "iso.3.6.1.2.1.2.2.1.8" "$walk_file"; then
      echo "- Interface status OIDs: found"
    else
      echo "- Interface status OIDs: not found yet"
    fi
    if awk '/\.3\.6\.1\.4\.1\.9\.9\.46\.1\.6\.1\.1\.14\.[0-9]+ = INTEGER:/ { found=1 } END { exit(found ? 0 : 1) }' "$walk_file"; then
      echo "- Cisco trunk status OIDs: found"
    else
      echo "- Cisco trunk status OIDs: not found yet"
    fi
    parser_report "$walk_file" "$target_ip"
  else
    echo "SNMP walk file found: no"
  fi
  echo ""
}


truthy() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    true|yes|on|1|enabled) return 0 ;;
    *) return 1 ;;
  esac
}

mask_value() {
  value="${1:-}"
  if [ -z "$value" ]; then
    printf 'not set'
  else
    printf '********'
  fi
}

walk_line_count() {
  f="$1"
  if [ -f "$f" ]; then
    wc -l < "$f" | tr -d ' '
  else
    printf '0'
  fi
}

walk_has_interface_name_table() {
  f="$1"
  grep -q "1.3.6.1.2.1.31.1.1.1.1" "$f" 2>/dev/null \
    || grep -q "iso.3.6.1.2.1.31.1.1.1.1" "$f" 2>/dev/null \
    || grep -q "1.3.6.1.2.1.2.2.1.2" "$f" 2>/dev/null \
    || grep -q "iso.3.6.1.2.1.2.2.1.2" "$f" 2>/dev/null
}

walk_marked_failed() {
  f="$1"
  grep -q "# Switch Vision SNMP walk result: failed" "$f" 2>/dev/null || grep -q "# Switch Vision SNMP walk result: insufficient_data" "$f" 2>/dev/null
}

is_live_walk_file() {
  base=$(basename "$1")
  case "$base" in
    live-snmpwalk.txt|live-targeted-snmpwalk.txt|live-full-snmpwalk.txt) return 0 ;;
    *) return 1 ;;
  esac
}

should_skip_walk_file() {
  f="$1"
  [ -f "$f" ] || return 1
  if walk_marked_failed "$f"; then
    return 0
  fi
  if is_live_walk_file "$f"; then
    lc=$(walk_line_count "$f")
    if [ "$lc" -lt "${LIVE_MIN_VALID_LINES:-100}" ] && ! walk_has_interface_name_table "$f"; then
      return 0
    fi
  fi
  return 1
}

write_live_summary_if_present() {
  if [ -f /tmp/switch_vision_live_walk_summary.txt ]; then
    cat /tmp/switch_vision_live_walk_summary.txt
    echo ""
  elif truthy "$RUN_LIVE_SNMPWALK"; then
    echo "SNMP walk result: not run"
    echo "- Expected summary file missing; check: $LIVE_LOG_PATH"
    echo ""
  fi
}

run_live_snmpwalk_current() {

  walk_started_iso=$(date -Iseconds)
  walk_started_epoch=$(now_epoch)
  if [ "${LIVE_LOG_APPEND:-false}" = "true" ]; then
    {
      echo ""
      echo "Switch Vision SNMP walk"
      echo "============================"
      echo "Started: $walk_started_iso"
    echo "Management IP: ${LIVE_SWITCH_IP:-not set}"
    echo "Output folder: ${LIVE_SWITCH_LABEL:-live}"
    echo "Current target: ${SELECTED_SWITCH:-not set}"
    echo "Target mapping matched: $SELECTED_SWITCH_MATCHED"
    echo "Walk mode: $LIVE_SNMPWALK_MODE"
    echo "Sensor prefix: ${DEFAULT_PREFIX:-not set}"
    echo "Output path: $LIVE_OUTPUT_PATH"
    echo "SNMP version: v2c"
    echo "Community: $(mask_value "$LIVE_SNMP_COMMUNITY")"
    echo "Timeout: $LIVE_SNMP_TIMEOUT"
    echo "Retries: $LIVE_SNMP_RETRIES"
    echo "Read-only mode: yes"
    if [ "$LIVE_SNMPWALK_MODE" = "full" ]; then
      echo ""
      echo "WARNING: Full SNMP walk may be large and slower."
      echo "Use full mode for troubleshooting, unsupported switches, or profile development."
    fi
      echo ""
    } >> "$LIVE_LOG_PATH"
  else
    {
      echo "Switch Vision SNMP walk"
      echo "============================"
      echo "Discovery app loaded: $DISCOVERY_STARTED_ISO"
      echo "Started: $walk_started_iso"
      echo "Management IP: ${LIVE_SWITCH_IP:-not set}"
      echo "Output folder: ${LIVE_SWITCH_LABEL:-live}"
      echo "Current target: ${SELECTED_SWITCH:-not set}"
      echo "Target mapping matched: $SELECTED_SWITCH_MATCHED"
      echo "Walk mode: $LIVE_SNMPWALK_MODE"
      echo "Sensor prefix: ${DEFAULT_PREFIX:-not set}"
      echo "Output path: $LIVE_OUTPUT_PATH"
      echo "SNMP version: v2c"
      echo "Community: $(mask_value "$LIVE_SNMP_COMMUNITY")"
      echo "Timeout: $LIVE_SNMP_TIMEOUT"
      echo "Retries: $LIVE_SNMP_RETRIES"
      echo "Read-only mode: yes"
      if [ "$LIVE_SNMPWALK_MODE" = "full" ]; then
        echo ""
        echo "WARNING: Full SNMP walk may be large and slower."
        echo "Use full mode for troubleshooting, unsupported switches, or profile development."
      fi
      echo ""
    } > "$LIVE_LOG_PATH"
  fi

  write_live_summary() {
    result="$1"
    reason="$2"
    attempted="${3:-0}"
    failures="${4:-0}"
    lines="${5:-0}"
    duration="${6:-0}"
    completed_iso="${7:-$(date -Iseconds)}"
    {
      echo "SNMP walk result: $result"
      echo "- Walk mode: $LIVE_SNMPWALK_MODE"
      echo "- Current target: ${SELECTED_SWITCH:-not set}"
      echo "- Target mapping matched: $SELECTED_SWITCH_MATCHED"
      echo "- Switch IP: ${LIVE_SWITCH_IP:-not set}"
      echo "- Output path: $LIVE_OUTPUT_PATH"
      echo "- Log path: $LIVE_LOG_PATH"
      echo "- Started: ${walk_started_iso:-not set}"
      echo "- Completed: $completed_iso"
      echo "- Duration: $(format_duration "$duration")"
      echo "- OID trees attempted: $attempted"
      echo "- Warnings: $failures"
      echo "- Output lines: $lines"
      if [ -n "$reason" ]; then echo "- Detail: $reason"; fi
      if [ "$result" != "PASS" ]; then
        echo "- Check: switch power, IP, community, ACL/source IP, routing, and UDP 161"
      fi
    } > /tmp/switch_vision_live_walk_summary.txt
  }

  fail_live_walk() {
    reason="$1"
    attempted="${2:-0}"
    failures="${3:-0}"
    lines="${4:-0}"
    {
      echo ""
      echo "ERROR: $reason"
      echo "SNMP connection test: FAILED"
      echo "Check switch power, IP, community, ACL/source IP, routing, and UDP 161."
    } >> "$LIVE_LOG_PATH"
    {
      echo "# Switch Vision Discovery SNMP walk"
      echo "# Generated: $(date -Iseconds)"
      echo "# Switch IP: ${LIVE_SWITCH_IP:-not set}"
      echo "# SNMP version: v2c"
      echo "# Discovery mode: $LIVE_SNMPWALK_MODE"
      echo "# Switch Vision SNMP walk result: failed"
      echo "# Failure reason: $reason"
    } > "$LIVE_OUTPUT_PATH"
    walk_completed_iso=$(date -Iseconds)
    walk_duration=$(( $(now_epoch) - ${walk_started_epoch:-$(now_epoch)} ))
    write_live_summary "FAIL" "$reason" "$attempted" "$failures" "$lines" "$walk_duration" "$walk_completed_iso"
  }

  if [ -z "${LIVE_SWITCH_IP:-}" ]; then
    fail_live_walk "switch_host / selected switch host is not set; SNMP walk skipped" 0 0 0
    return 0
  fi

  if ! command -v snmpwalk >/dev/null 2>&1; then
    fail_live_walk "snmpwalk command not found in app container" 0 0 0
    return 0
  fi

  if truthy "$LIVE_CLEAN_OUTPUT_BEFORE_WALK"; then
    echo "Clean before walk: enabled" >> "$LIVE_LOG_PATH"
    safe_clean_walk_outputs "$(dirname "$LIVE_OUTPUT_PATH")" || true
  fi

  # Fast pre-check keeps dead IPs/wrong communities from creating confusing tiny pseudo-devices.
  precheck_command="snmpwalk -On -v2c -c ******** -t $LIVE_SNMP_TIMEOUT -r $LIVE_SNMP_RETRIES $LIVE_SWITCH_IP 1.3.6.1.2.1.1.1.0"
  sv_status "Running SNMP walks" "${SELECTED_SWITCH:-${LIVE_SWITCH_LABEL:-Switch}}" "$LIVE_SWITCH_IP" "$precheck_command" "Checking SNMP connection"
  sv_debug "COMMAND: $precheck_command"
  echo "SNMP connection test: sysDescr" >> "$LIVE_LOG_PATH"
  if snmpwalk -On -v2c -c "$LIVE_SNMP_COMMUNITY" -t "$LIVE_SNMP_TIMEOUT" -r "$LIVE_SNMP_RETRIES" "$LIVE_SWITCH_IP" 1.3.6.1.2.1.1.1.0 >/tmp/switch_vision_snmp_precheck.txt 2>> "$LIVE_LOG_PATH"; then
    pre_lines=$(walk_line_count /tmp/switch_vision_snmp_precheck.txt)
    echo "SNMP connection test: PASS ($pre_lines line(s))" >> "$LIVE_LOG_PATH"
    sv_debug "RESULT: sysDescr pre-check returned $pre_lines line(s)"
  else
    fail_live_walk "No SNMP response from switch during sysDescr pre-check" 1 1 0
    return 0
  fi

  : > "$LIVE_OUTPUT_PATH"
  {
    echo "# Switch Vision Discovery SNMP walk"
    echo "# Generated: $(date -Iseconds)"
    echo "# Switch IP: $LIVE_SWITCH_IP"
    echo "# SNMP version: v2c"
    echo "# Community: ********"
    echo "# Discovery mode: $LIVE_SNMPWALK_MODE read-only walk"
    echo "# Switch Vision SNMP walk result: running"
  } >> "$LIVE_OUTPUT_PATH"

  failures=0
  total=0

  if [ "$LIVE_SNMPWALK_MODE" = "full" ]; then
    if grep -qi "Juniper" /tmp/switch_vision_snmp_precheck.txt 2>/dev/null; then
      # A root walk from OID 1 on EX3300 can time out in the standard branch
      # before lexicographic traversal ever reaches Juniper enterprise OIDs.
      # Walk the standard and Juniper enterprise roots independently so one
      # problematic branch cannot hide the other.
      FULL_OIDS="
1.3.6.1.2.1
1.3.6.1.4.1.2636
"
      echo "Running split Juniper full SNMP walk" >> "$LIVE_LOG_PATH"
      oid_total=$(printf '%s\n' "$FULL_OIDS" | awk 'NF { count++ } END { print count+0 }')
      for oid in $FULL_OIDS; do
        total=$((total + 1))
        full_command="snmpwalk -On -v2c -c ******** -t $LIVE_SNMP_TIMEOUT -r $LIVE_SNMP_RETRIES $LIVE_SWITCH_IP $oid"
        echo "Command: $full_command" >> "$LIVE_LOG_PATH"
        sv_status "Running SNMP walks" "${SELECTED_SWITCH:-${LIVE_SWITCH_LABEL:-Switch}}" "$LIVE_SWITCH_IP" "$full_command" "Reading full tree $total of $oid_total"
        sv_debug "COMMAND: $full_command"
        {
          echo ""
          echo "# --- full walk tree: $oid ---"
        } >> "$LIVE_OUTPUT_PATH"
        if snmpwalk -On -v2c -c "$LIVE_SNMP_COMMUNITY" -t "$LIVE_SNMP_TIMEOUT" -r "$LIVE_SNMP_RETRIES" "$LIVE_SWITCH_IP" "$oid" >> "$LIVE_OUTPUT_PATH" 2>> "$LIVE_LOG_PATH"; then
          echo "OK full tree: $oid" >> "$LIVE_LOG_PATH"
        else
          failures=$((failures + 1))
          echo "WARN: full snmpwalk tree failed or returned no data for $oid" >> "$LIVE_LOG_PATH"
        fi
      done
    else
      echo "Running full SNMP walk" >> "$LIVE_LOG_PATH"
      full_command="snmpwalk -On -v2c -c ******** -t $LIVE_SNMP_TIMEOUT -r $LIVE_SNMP_RETRIES $LIVE_SWITCH_IP 1"
      echo "Command: $full_command" >> "$LIVE_LOG_PATH"
      sv_status "Running SNMP walks" "${SELECTED_SWITCH:-${LIVE_SWITCH_LABEL:-Switch}}" "$LIVE_SWITCH_IP" "$full_command" "Reading all SNMP data"
      sv_debug "COMMAND: $full_command"
      {
        echo ""
        echo "# --- full walk: 1 ---"
      } >> "$LIVE_OUTPUT_PATH"
      total=1
      if snmpwalk -On -v2c -c "$LIVE_SNMP_COMMUNITY" -t "$LIVE_SNMP_TIMEOUT" -r "$LIVE_SNMP_RETRIES" "$LIVE_SWITCH_IP" 1 >> "$LIVE_OUTPUT_PATH" 2>> "$LIVE_LOG_PATH"; then
        echo "OK: full walk" >> "$LIVE_LOG_PATH"
      else
        failures=1
        echo "WARN: full snmpwalk failed or returned no data" >> "$LIVE_LOG_PATH"
      fi
    fi
  else
    # Targeted discovery OID trees. Includes explicit ifOperStatus plus the
    # standard bridge-port and PVID tables required for dynamic per-port VLAN
    # correlation on Juniper and other standards-compliant switches.
    LIVE_OIDS="
1.3.6.1.2.1.1
1.3.6.1.4.1.9.2.1.3
1.3.6.1.2.1.2.2.1
1.3.6.1.2.1.2.2.1.8
1.3.6.1.2.1.31.1.1.1
1.3.6.1.2.1.26
1.3.6.1.2.1.18.1.4.1.2
1.3.6.1.2.1.18.7.1.4.3
1.3.6.1.2.1.18.7.1.4.5.1.1
1.3.6.1.4.1.9.9.13.1.3.1
1.3.6.1.2.1.47.1.1.1.1.2
1.3.6.1.4.1.9.9.68.1.2.2.1.2
1.3.6.1.4.1.9.9.46.1.3.1.1.4
1.3.6.1.4.1.9.9.46.1.6.1.1.13
1.3.6.1.4.1.9.9.46.1.6.1.1.14
1.3.6.1.4.1.9.9.109.1.1.1.1
1.3.6.1.4.1.9.9.402.1.3.1
1.3.6.1.2.1.105.1.3.1
"

    for oid in $LIVE_OIDS; do
      total=$((total + 1))
      current_command="snmpwalk -On -v2c -c ******** -t $LIVE_SNMP_TIMEOUT -r $LIVE_SNMP_RETRIES $LIVE_SWITCH_IP $oid"
      echo "Running: $current_command" >> "$LIVE_LOG_PATH"
      oid_total=$(printf '%s\n' "$LIVE_OIDS" | awk 'NF { count++ } END { print count+0 }')
      sv_status "Running SNMP walks" "${SELECTED_SWITCH:-${LIVE_SWITCH_LABEL:-Switch}}" "$LIVE_SWITCH_IP" "$current_command" "Reading OID tree $total of $oid_total"
      sv_debug "COMMAND: $current_command"
      {
        echo ""
        echo "# --- $oid ---"
      } >> "$LIVE_OUTPUT_PATH"
      before=$(walk_line_count "$LIVE_OUTPUT_PATH")
      if snmpwalk -On -v2c -c "$LIVE_SNMP_COMMUNITY" -t "$LIVE_SNMP_TIMEOUT" -r "$LIVE_SNMP_RETRIES" "$LIVE_SWITCH_IP" "$oid" >> "$LIVE_OUTPUT_PATH" 2>> "$LIVE_LOG_PATH"; then
        after=$(walk_line_count "$LIVE_OUTPUT_PATH")
        returned=$((after - before - 1))
        [ "$returned" -lt 0 ] && returned=0
        echo "OK: $oid" >> "$LIVE_LOG_PATH"
        echo "Lines returned: $returned" >> "$LIVE_LOG_PATH"
        sv_debug "RESULT: OID $oid returned $returned line(s)"
      else
        failures=$((failures + 1))
        echo "WARN: snmpwalk failed or returned no data for $oid" >> "$LIVE_LOG_PATH"
        sv_debug "WARNING: OID $oid failed or returned no data"
      fi
    done
  fi

  # Juniper full walks can omit the enterprise branch when the agent's
  # lexicographic root walk skips or filters private MIBs. Query the supported
  # jnxOperatingTable columns explicitly so CPU, temperature, memory, fan and
  # power-supply health can be generated when the switch exposes them.
  if grep -qi "Juniper" /tmp/switch_vision_snmp_precheck.txt 2>/dev/null; then
    JUNIPER_HEALTH_OIDS="
1.3.6.1.4.1.2636.3.1.13.1.5
1.3.6.1.4.1.2636.3.1.13.1.6
1.3.6.1.4.1.2636.3.1.13.1.7
1.3.6.1.4.1.2636.3.1.13.1.8
1.3.6.1.4.1.2636.3.1.13.1.11
1.3.6.1.4.1.2636.3.1.13.1.15
"
    echo "Running Juniper health supplemental walks" >> "$LIVE_LOG_PATH"
    for oid in $JUNIPER_HEALTH_OIDS; do
      current_command="snmpwalk -On -v2c -c ******** -t $LIVE_SNMP_TIMEOUT -r $LIVE_SNMP_RETRIES $LIVE_SWITCH_IP $oid"
      echo "Running supplemental: $current_command" >> "$LIVE_LOG_PATH"
      {
        echo ""
        echo "# --- Juniper health supplemental: $oid ---"
      } >> "$LIVE_OUTPUT_PATH"
      if snmpwalk -On -v2c -c "$LIVE_SNMP_COMMUNITY" -t "$LIVE_SNMP_TIMEOUT" -r "$LIVE_SNMP_RETRIES" "$LIVE_SWITCH_IP" "$oid" >> "$LIVE_OUTPUT_PATH" 2>> "$LIVE_LOG_PATH"; then
        echo "OK supplemental: $oid" >> "$LIVE_LOG_PATH"
      else
        echo "INFO: Juniper health OID unavailable: $oid" >> "$LIVE_LOG_PATH"
      fi
    done
  fi

  line_count=$(walk_line_count "$LIVE_OUTPUT_PATH")
  result="PASS"
  reason="SNMP walk completed"
  if [ "$failures" -gt 0 ]; then
    result="WARN"
    reason="SNMP walk completed with warnings"
  fi
  if [ "$line_count" -lt "${LIVE_MIN_VALID_LINES:-100}" ] && ! walk_has_interface_name_table "$LIVE_OUTPUT_PATH"; then
    result="FAIL"
    reason="SNMP output too small or missing ifName/ifDescr interface-name table"
    echo "# Switch Vision SNMP walk result: insufficient_data" >> "$LIVE_OUTPUT_PATH"
  elif [ "$result" = "WARN" ]; then
    echo "# Switch Vision SNMP walk result: warning" >> "$LIVE_OUTPUT_PATH"
  else
    echo "# Switch Vision SNMP walk result: pass" >> "$LIVE_OUTPUT_PATH"
  fi

  walk_completed_iso=$(date -Iseconds)
  walk_duration=$(( $(now_epoch) - ${walk_started_epoch:-$(now_epoch)} ))
  echo "" >> "$LIVE_LOG_PATH"
  echo "Completed: $walk_completed_iso" >> "$LIVE_LOG_PATH"
  echo "Duration: $(format_duration "$walk_duration")" >> "$LIVE_LOG_PATH"
  echo "OID trees attempted: $total" >> "$LIVE_LOG_PATH"
  echo "OID tree warnings: $failures" >> "$LIVE_LOG_PATH"
  echo "Output lines: $line_count" >> "$LIVE_LOG_PATH"
  echo "Result: $result" >> "$LIVE_LOG_PATH"
  write_live_summary "$result" "$reason" "$total" "$failures" "$line_count" "$walk_duration" "$walk_completed_iso"

  if [ "$result" = "PASS" ] || [ "$result" = "WARN" ]; then
    if [ -n "${CURRENT_RUN_WALKS:-}" ]; then
      printf '%s
' "$LIVE_OUTPUT_PATH" >> "$CURRENT_RUN_WALKS"
      echo "Queued for current-run parse: $LIVE_OUTPUT_PATH" >> "$LIVE_LOG_PATH"
    fi
    if [ -n "${CURRENT_RUN_TARGETS:-}" ]; then
      record_current_run_target \
        "$LIVE_OUTPUT_PATH" \
        "${SELECTED_SWITCH:-${LIVE_SWITCH_LABEL:-}}" \
        "$LIVE_SWITCH_IP" \
        "${DEFAULT_PREFIX:-${LIVE_SWITCH_LABEL:-SW}}" \
        "$LIVE_SNMP_COMMUNITY" || \
        echo "WARNING: current-run target metadata could not be recorded for $LIVE_OUTPUT_PATH" >> "$LIVE_LOG_PATH"
    fi
  else
    echo "Current-run parse skipped for failed walk: $LIVE_OUTPUT_PATH" >> "$LIVE_LOG_PATH"
  fi

  # The parser consumes the exact current-run paths recorded above. Do not
  # copy targeted walks back into the shared SNMP walk root, because files
  # with the same basename would overwrite each other.
}


set_live_paths_for_current_switch() {
  LIVE_OUTPUT_DIR=${LIVE_OUTPUT_DIR%/}
  LIVE_OUTPUT_DIR=$(printf '%s' "$LIVE_OUTPUT_DIR" | sed 's#//*#/#g')
  mkdir -p "$LIVE_OUTPUT_DIR"
  if [ "$LIVE_SNMPWALK_MODE" = "full" ]; then
    LIVE_OUTPUT_PATH="$LIVE_OUTPUT_DIR/live-full-snmpwalk.txt"
  else
    LIVE_OUTPUT_PATH="$LIVE_OUTPUT_DIR/live-targeted-snmpwalk.txt"
  fi
  LIVE_OUTPUT_PATH=$(printf '%s' "$LIVE_OUTPUT_PATH" | sed 's#//*#/#g')
}


switch_model_override_for_name() {
  lookup_name="$1"
  [ -f "$CONFIG_FILE" ] || { printf 'auto'; return 0; }
  command -v jq >/dev/null 2>&1 || { printf 'auto'; return 0; }
  jq -r --arg name "$lookup_name" '
    def safe: gsub("[^A-Za-z0-9._-]"; "_");
    def enabled($sw):
      (($sw.enabled // "enabled") as $value |
        if ($value | type) == "boolean" then $value
        elif ($value | type) == "string" then
          (($value | ascii_downcase) as $state |
            ($state != "false" and $state != "disabled" and $state != "disable" and
             $state != "off" and $state != "no" and $state != "0"))
        else true end);
    [(.switches // .multi_switch_walks // [])[]?
      | select(enabled(.))
      | select((((.switch_name // .switch // .selected_switch // .name // "") | safe) == $name)
            or ((.switch_name // .switch // .selected_switch // .name // "") == $name))
      | (.switch_model // .model_override // "auto")][0] // "auto"
  ' "$CONFIG_FILE" 2>/dev/null
}

build_runtime_multi_switch_targets_csv() {
  # Build a temporary target map from the app UI rows. This makes the rest
  # of Discovery use the same resolver/generator path for UI rows and CSV rows.
  # Row values are written first, so they override matching rows in discovery-targets.csv.
  runtime_csv="/tmp/switch_vision_multi_switch_targets.csv"
  stack_map_csv="/tmp/switch_vision_stack_member_map.csv"
  wrote_rows=0
  : > "$stack_map_csv"
  echo "output_dir,folder label,switch name,member,member name,sensor prefix" > "$stack_map_csv"
  {
    echo "switch name,switch host,sensor prefix,switch snmp community,output_dir,display name"
    multi_switch_walk_rows | while IFS="$(printf "\\034")" read -r row_switch row_host row_label row_prefix row_community row_mode row_output_dir row_display_name row_switch_model || [ -n "$row_switch$row_host$row_label$row_prefix$row_community$row_mode$row_output_dir$row_display_name$row_switch_model" ]; do
      row_switch=$(clean_csv_field "$row_switch")
      row_host=$(clean_csv_field "$row_host")
      row_label=$(safe_label_value "$row_switch")
      row_prefix=$(clean_csv_field "${row_prefix:-$row_label}")
      row_community=$(clean_csv_field "${row_community:-$DEFAULT_COMMUNITY}")
      row_output_dir=$(clean_csv_field "$row_output_dir")
      row_display_name=$(clean_csv_field "$row_display_name")
      [ -n "$row_switch" ] || continue
      case "$row_switch" in \#*) continue ;; esac
      if [ -z "$row_output_dir" ]; then
        row_output_dir="$SNMPWALKS_ROOT_DIR/$(safe_label_value "$row_switch")"
      fi
      # Only write full switch definitions. Switch/mode-only legacy rows still resolve from the CSV fallback below.
      if [ -n "$row_host" ]; then
        printf '%s,%s,%s,%s,%s,%s\n' "$row_switch" "$row_host" "$row_prefix" "$row_community" "$row_output_dir" "$row_display_name"
        echo 1 > /tmp/switch_vision_runtime_csv_has_rows
      fi
    done
    multi_switch_stack_member_rows \
      | while IFS="$(printf "\\034")" read -r sm_switch sm_label sm_output_dir sm_member sm_member_name sm_prefix || [ -n "$sm_switch$sm_label$sm_output_dir$sm_member$sm_member_name$sm_prefix" ]; do
          sm_member=$(clean_csv_field "$sm_member")
          sm_prefix=$(clean_csv_field "$sm_prefix")
          [ -n "$sm_member" ] || continue
          [ -n "$sm_prefix" ] || continue
          sm_switch=$(clean_csv_field "$sm_switch")
          sm_label=$(safe_label_value "$sm_switch")
          sm_output_dir=$(clean_csv_field "$sm_output_dir")
          if [ -z "$sm_output_dir" ]; then
            sm_output_dir="$SNMPWALKS_ROOT_DIR/$(safe_label_value "$sm_switch")"
          fi
          printf '%s,%s,%s,%s,%s,%s
' "$sm_output_dir" "$sm_label" "$sm_switch" "$sm_member" "$sm_member_name" "$sm_prefix" >> "$stack_map_csv"
        done


    if [ -f "$TARGETS_CSV" ]; then
      while IFS= read -r line || [ -n "$line" ]; do
        name=$(csv_field "$line" 1)
        [ -n "$name" ] || continue
        case "$name" in \#*) continue ;; esac
        if is_targets_csv_header "$name"; then
          continue
        fi
        printf '%s
' "$line"
      done < "$TARGETS_CSV"
    fi
  } > "$runtime_csv"
  if [ -f /tmp/switch_vision_runtime_csv_has_rows ]; then
    rm -f /tmp/switch_vision_runtime_csv_has_rows
    TARGETS_CSV="$runtime_csv"
  fi
}

run_multi_switch_walks_if_enabled() {
  if ! truthy "$MULTI_SWITCH_WALKS_ENABLED"; then
    return 1
  fi
  if ! json_has_enabled_switch_rows; then
    {
      echo "Switch Vision switch-list SNMP walk"
      echo "===================================="
      echo "Discovery app loaded: $DISCOVERY_STARTED_ISO"
      echo "Started: $(date -Iseconds)"
      echo "Result: skipped"
      echo "Detail: enable_switch_list is true, but no enabled switch rows were configured. Disabled switches remain saved and are skipped."
    } > "$LIVE_LOG_PATH"
    {
      echo "SNMP walk result: SKIP"
      echo "- Mode: multi-switch"
      echo "- Detail: no enabled switch rows configured; disabled switches remain saved"
      echo "- Log path: $LIVE_LOG_PATH"
    } > /tmp/switch_vision_live_walk_summary.txt
    return 0
  fi

  multi_started_iso=$(date -Iseconds)
  multi_started_epoch=$(now_epoch)
  : > /tmp/switch_vision_live_walk_summary_all.txt
  {
    echo "Switch Vision switch-list SNMP walk"
    echo "===================================="
    echo "Discovery app loaded: $DISCOVERY_STARTED_ISO"
    echo "Started: $multi_started_iso"
    echo "Read-only mode: yes"
    echo "Switch definitions: switch-list rows first; discovery-targets.csv fallback/import supported"
    echo "Targets CSV/import path: $TARGETS_CSV"
    echo "SNMP walks root: $SNMPWALKS_ROOT_DIR"
    echo "Stack member prefixes: supported via stack_member_prefixes"
    echo ""
  } > "$LIVE_LOG_PATH"

  rm -f /tmp/switch_vision_multi_count /tmp/switch_vision_multi_pass /tmp/switch_vision_multi_warn /tmp/switch_vision_multi_fail
  original_selected="$SELECTED_SWITCH"
  original_mode="$LIVE_SNMPWALK_MODE"
  original_parse_all="$PARSE_ALL_WALKS"
  count=0
  pass_count=0
  warn_count=0
  fail_count=0
  PARSE_ALL_WALKS="true"
  SNMPWALKS_DIR="$SNMPWALKS_ROOT_DIR"

  build_runtime_multi_switch_targets_csv

  multi_switch_walk_rows | while IFS="$(printf "\\034")" read -r row_switch row_host row_label row_prefix row_community row_mode row_output_dir row_display_name row_switch_model || [ -n "$row_switch$row_host$row_label$row_prefix$row_community$row_mode$row_output_dir$row_display_name$row_switch_model" ]; do
    row_switch=$(clean_csv_field "$row_switch")
    row_host=$(clean_csv_field "$row_host")
    row_label=$(clean_csv_field "$row_label")
    row_prefix=$(clean_csv_field "$row_prefix")
    row_community=$(clean_csv_field "$row_community")
    row_output_dir=$(clean_csv_field "$row_output_dir")
    row_mode=$(lower_value "$(clean_csv_field "${row_mode:-targeted}")")
    case "$row_mode" in targeted|full) : ;; *) row_mode="targeted" ;; esac
    [ -n "$row_switch" ] || continue

    count_file=/tmp/switch_vision_multi_count
    pass_file=/tmp/switch_vision_multi_pass
    warn_file=/tmp/switch_vision_multi_warn
    fail_file=/tmp/switch_vision_multi_fail
    [ -f "$count_file" ] || echo 0 > "$count_file"
    [ -f "$pass_file" ] || echo 0 > "$pass_file"
    [ -f "$warn_file" ] || echo 0 > "$warn_file"
    [ -f "$fail_file" ] || echo 0 > "$fail_file"
    count=$(( $(cat "$count_file") + 1 )); echo "$count" > "$count_file"

    SELECTED_SWITCH="$row_switch"
    LIVE_SNMPWALK_MODE="$row_mode"
    resolve_selected_switch
    # Direct row values are authoritative when present. This keeps add/remove UI rows self-contained.
    if [ -n "$row_host" ]; then LIVE_SWITCH_IP="$row_host"; DEFAULT_HOST="$row_host"; fi
    if [ -n "$row_label" ]; then LIVE_SWITCH_LABEL=$(safe_label_value "$row_label"); fi
    if [ -n "$row_prefix" ]; then DEFAULT_PREFIX="$row_prefix"; fi
    if [ -n "$row_community" ]; then LIVE_SNMP_COMMUNITY="$row_community"; DEFAULT_COMMUNITY="$row_community"; fi
    # Always write directly to the final persistent per-switch directory.
    # switch_name is the sole folder source; display_name and legacy output_dir
    # cannot redirect a switch-list walk into a shared or temporary location.
    persistent_switch_folder=$(safe_label_value "$row_switch")
    LIVE_OUTPUT_DIR="$SNMPWALKS_ROOT_DIR/$persistent_switch_folder"
    mkdir -p "$LIVE_OUTPUT_DIR"
    set_live_paths_for_current_switch
    LIVE_LOG_APPEND="true"
    run_live_snmpwalk_current
    if [ ! -s "$LIVE_OUTPUT_PATH" ]; then
      echo "FATAL: persistent walk missing after write: $LIVE_OUTPUT_PATH" >> "$LIVE_LOG_PATH"
      n=$(( $(cat "$fail_file") + 1 )); echo "$n" > "$fail_file"
      continue
    fi
    echo "Persistent walk verified: $LIVE_OUTPUT_PATH" >> "$LIVE_LOG_PATH"

    if [ -f /tmp/switch_vision_live_walk_summary.txt ]; then
      cat /tmp/switch_vision_live_walk_summary.txt >> /tmp/switch_vision_live_walk_summary_all.txt
      echo "" >> /tmp/switch_vision_live_walk_summary_all.txt
      if grep -q "SNMP walk result: PASS" /tmp/switch_vision_live_walk_summary.txt; then
        n=$(( $(cat "$pass_file") + 1 )); echo "$n" > "$pass_file"
      elif grep -q "SNMP walk result: WARN" /tmp/switch_vision_live_walk_summary.txt; then
        n=$(( $(cat "$warn_file") + 1 )); echo "$n" > "$warn_file"
      else
        n=$(( $(cat "$fail_file") + 1 )); echo "$n" > "$fail_file"
      fi
    fi
  done

  count=$(cat /tmp/switch_vision_multi_count 2>/dev/null || echo 0)
  pass_count=$(cat /tmp/switch_vision_multi_pass 2>/dev/null || echo 0)
  warn_count=$(cat /tmp/switch_vision_multi_warn 2>/dev/null || echo 0)
  fail_count=$(cat /tmp/switch_vision_multi_fail 2>/dev/null || echo 0)
  rm -f /tmp/switch_vision_multi_count /tmp/switch_vision_multi_pass /tmp/switch_vision_multi_warn /tmp/switch_vision_multi_fail
  multi_completed_iso=$(date -Iseconds)
  multi_duration=$(( $(now_epoch) - multi_started_epoch ))
  {
    echo "Switch-list SNMP walk result: completed"
    echo "- Started: $multi_started_iso"
    echo "- Completed: $multi_completed_iso"
    echo "- Duration: $(format_duration "$multi_duration")"
    echo "- Switches walked: $count"
    echo "- PASS: $pass_count"
    echo "- WARN: $warn_count"
    echo "- FAIL/SKIP: $fail_count"
    echo "- SNMP walks root: $SNMPWALKS_ROOT_DIR"
    echo ""
    cat /tmp/switch_vision_live_walk_summary_all.txt 2>/dev/null || true
  } > /tmp/switch_vision_live_walk_summary.txt
  {
    echo ""
    echo "Switch-list completed: $multi_completed_iso"
    echo "Switch-list duration: $(format_duration "$multi_duration")"
    echo "Switches walked: $count"
    echo "PASS: $pass_count"
    echo "WARN: $warn_count"
    echo "FAIL/SKIP: $fail_count"
  } >> "$LIVE_LOG_PATH"

  SELECTED_SWITCH="$original_selected"
  LIVE_SNMPWALK_MODE="$original_mode"
  # Restore the user's explicit stored-walk preference. Multi-switch walking
  # temporarily enables parser helpers internally, but it must never turn an
  # ordinary current-run Discovery into historical-walk mode.
  PARSE_ALL_WALKS="$original_parse_all"
  SNMPWALKS_DIR="$SNMPWALKS_ROOT_DIR"
  rmdir "$SNMPWALKS_ROOT_DIR/live" 2>/dev/null || true
  return 0
}

run_live_snmpwalk_if_enabled() {
  rm -f /tmp/switch_vision_live_walk_summary.txt /tmp/switch_vision_live_walk_summary_all.txt "$CURRENT_RUN_WALKS" "$CURRENT_RUN_TARGETS"
  : > "$CURRENT_RUN_WALKS"
  : > "$CURRENT_RUN_TARGETS"
  if ! truthy "$RUN_LIVE_SNMPWALK"; then
    return 0
  fi
  if run_multi_switch_walks_if_enabled; then
    {
      echo ""
      echo "Post-walk execution: switch-list walk complete; running parser/generator now"
      echo "Post-walk execution: current-run walk list: ${CURRENT_RUN_WALKS:-/tmp/switch_vision_current_run_walks.txt}"
    } >> "$LIVE_LOG_PATH" 2>/dev/null || true
    # v0.7.12: run the post-walk parser/generator immediately after switch-list
    # walks complete. This avoids the previous queued-but-not-parsed flow where
    # current-run files were recorded but no report/YAML stage was executed.
    write_report
    write_last_run_summary
    POST_WALK_ALREADY_DONE="true"
    return 0
  fi
  LIVE_LOG_APPEND="false"
  run_live_snmpwalk_current
}

collect_multi_walks() {
  tmp_file="$1"
  : > "$tmp_file"

  # v0.7.12: after switch-list SNMP walks, parse only the walk files created in
  # this app run. This prevents old full walks or stale failed files under
  # /share/switch_vision/snmpwalks from making the post-walk stage appear stuck.
  if [ -s "${CURRENT_RUN_WALKS:-/tmp/switch_vision_current_run_walks.txt}" ]; then
    echo "Post-walk parser: using current-run walk list" >> "$LIVE_LOG_PATH" 2>/dev/null || true
    while IFS= read -r walk_file || [ -n "$walk_file" ]; do
      [ -f "$walk_file" ] || continue
      printf '%s\n' "$walk_file"
    done < "$CURRENT_RUN_WALKS" | sed 's#//*#/#g' | sort -u >> "$tmp_file"
    return 0
  fi

  # Historical walk files are opt-in only. When a Discovery run does not
  # create a current-run walk list, do not silently fall back to stale files.
  # Users who intentionally want stored/offline walks can enable parse_all_walks.
  if ! truthy "$PARSE_ALL_WALKS"; then
    echo "Post-walk parser: no current-run walks; stored walk reuse is disabled" >> "$LIVE_LOG_PATH" 2>/dev/null || true
    return 0
  fi

  scan_dir="$SNMPWALKS_ROOT_DIR"
  if truthy "$MULTI_SWITCH_WALKS_ENABLED" && json_has_configured_switch_rows && [ -f "$CONFIG_FILE" ] && command -v jq >/dev/null 2>&1; then
    echo "Post-walk parser: explicit parse_all_walks enabled; scanning enabled switch folders only" >> "$LIVE_LOG_PATH" 2>/dev/null || true
    multi_switch_walk_rows |
      while IFS="$(printf "\034")" read -r row_switch _row_host _row_label _row_prefix _row_community _row_mode _row_output_dir _row_display_name _row_switch_model || [ -n "$row_switch" ]; do
        row_switch=$(clean_csv_field "$row_switch")
        [ -n "$row_switch" ] || continue
        enabled_dir="$scan_dir/$(safe_label_value "$row_switch")"
        [ -d "$enabled_dir" ] || continue
        find "$enabled_dir" -type f \( -name '*.txt' -o -name '*.walk' -o -name '*.snmpwalk' \) 2>/dev/null
      done | sed 's#//*#/#g' | sort -u >> "$tmp_file"
    return 0
  fi

  echo "Post-walk parser: explicit parse_all_walks enabled; scanning $scan_dir" >> "$LIVE_LOG_PATH" 2>/dev/null || true
  if [ -d "$scan_dir" ]; then
    find "$scan_dir" -type f \( -name '*.txt' -o -name '*.walk' -o -name '*.snmpwalk' \) 2>/dev/null \
      | sed 's#//*#/#g' \
      | sort \
      >> "$tmp_file"
  fi
}


target_member_map_for_walk() {
  walk_file="$1"
  stack_map_csv="/tmp/switch_vision_stack_member_map.csv"
  [ -f "$stack_map_csv" ] || return 0
  result=""
  walk_dir=$(dirname "$walk_file" | sed 's#//*#/#g')
  walk_base=$(basename "$walk_dir")
  while IFS= read -r line || [ -n "$line" ]; do
    out_dir=$(csv_field "$line" 1 | sed 's#//*#/#g')
    label=$(csv_field "$line" 2)
    member=$(csv_field "$line" 4)
    mprefix=$(csv_field "$line" 6)
    [ -n "$member" ] || continue
    [ -n "$mprefix" ] || continue
    case "$out_dir" in output_dir) continue ;; esac
    if [ "$walk_dir" = "$out_dir" ] || [ "$walk_base" = "$label" ]; then
      if [ -n "$result" ]; then result="$result,"; fi
      result="$result$member=$mprefix"
    fi
  done < "$stack_map_csv"
  printf '%s' "$result"
}

write_generated_yaml_for_walk() {
  walk_file="$1"
  target_ip="$2"
  prefix="$3"
  community="$4"
  member_map="${5:-}"
  source_name=$(basename "$walk_file")
  generator_raw_tmp="/tmp/switch_vision_generator_raw_$$.yaml"
  rm -f "$generator_raw_tmp"
  if [ "$target_ip" = "unknown" ] || [ -z "$target_ip" ]; then
    echo "# ERROR: Missing management target for $source_name; generated YAML refused."
    return 1
  fi

  awk -v host="$target_ip" -v prefix="$prefix" -v community="$community" -v source_name="$source_name" -v member_map="$member_map" '
    function value_of(line, v) {
      v = line
      sub(/^[^=]*= /, "", v)
      sub(/^[A-Za-z0-9-]+: /, "", v)
      gsub(/\r/, "", v)
      gsub(/^"/, "", v)
      gsub(/"$/, "", v)
      return v
    }
    function oid_index(line, s) {
      # Remove the value first. Some STRING values (for example Juniper
      # logical interfaces such as ge-0/0/42.0) contain dots; stripping up to
      # the last dot before removing the value incorrectly returned index 0.
      s = line
      sub(/[[:space:]]*=.*/, "", s)
      sub(/^.*\./, "", s)
      return s + 0
    }
    function member_label(member, letters, number) {
      # A standalone Catalyst can retain an internal member number other than 1
      # (for example Gi2/0/1 after stack history). It is still one management
      # target and must use the configured switch prefix unchanged.
      if (stack_members <= 1) return prefix
      if ((member "") in member_prefix) return member_prefix[member ""]
      if (match(prefix, /^[A-Za-z]+[0-9]+$/)) {
        letters = prefix
        sub(/[0-9]+$/, "", letters)
        number = prefix
        sub(/^[A-Za-z]+/, "", number)
        return letters (number + member - 1)
      }
      if (prefix ~ /^[A-Za-z]+$/) return prefix member
      return prefix "-M" member
    }
    function is_2960x(m) { return (m ~ /^(WS-)?C2960X/) }
    function is_2960s(m) { return (m ~ /^(WS-)?C2960S/) }
    function is_2960(m) { return (is_2960x(m) || is_2960s(m)) }
    function c2960_rj45_limit(m) {
      if (m ~ /^WS-C2960X-24/ || m ~ /^WS-C2960S-24/) return 24
      if (m ~ /^WS-C2960X-48/ || m ~ /^WS-C2960S-48/) return 48
      return 48
    }
    function physical_label(name, idx, key, parts, member, port, label) {
      if (model == "WS-C3750-48P" && name ~ /^(Fa|FastEthernet)[0-9]+\/0\/([1-9]|[1-3][0-9]|4[0-8])$/) {
        key = name
        sub(/^FastEthernet/, "", key)
        sub(/^Fa/, "", key)
        split(key, parts, "/")
        return member_label(parts[1] + 0) " Port " (parts[3] + 0)
      }
      if (model == "WS-C3750-48P" && name ~ /^(Gi|GigabitEthernet)[0-9]+\/0\/[1-4]$/) {
        key = name
        sub(/^GigabitEthernet/, "", key)
        sub(/^Gi/, "", key)
        split(key, parts, "/")
        return member_label(parts[1] + 0) " SFP 1G " (parts[3] + 0)
      }
      if (model == "N2128PX-ON" && name ~ /^(Gi|GigabitEthernet|Te|TenGigabitEthernet)[0-9]+\/0\/[0-9]+$/) {
        key = name
        sub(/^GigabitEthernet/, "", key)
        sub(/^TenGigabitEthernet/, "", key)
        sub(/^Gi/, "", key)
        sub(/^Te/, "", key)
        split(key, parts, "/")
        member = parts[1] + 0
        port = parts[3] + 0
        label = member_label(member)
        if ((name ~ /^(Gi|GigabitEthernet)/) && parts[2] == "0" && port >= 1 && port <= 28) return label " Port " port
        if ((name ~ /^(Te|TenGigabitEthernet)/) && parts[2] == "0" && port >= 1 && port <= 2) return label " SFP 10G " port
      }
      if (model == "SG500X-24" && name ~ /^gi1\/[0-9]+$/) {
        port = name; sub(/^gi1\//, "", port); return prefix " Port " (port + 0)
      }
      if (model == "SG500X-24" && name ~ /^te1\/[0-9]+$/) {
        port = name; sub(/^te1\//, "", port); return prefix " SFP 10G " (port + 0)
      }
      if (model == "S5735-L8P4X-A1" && name ~ /^GigabitEthernet0\/0\/[0-9]+$/) {
        port = name; sub(/^GigabitEthernet0\/0\//, "", port); return prefix " Port " (port + 0)
      }
      if (model == "S5735-L8P4X-A1" && name ~ /^XGigabitEthernet0\/0\/[0-9]+$/) {
        port = name; sub(/^XGigabitEthernet0\/0\//, "", port); return prefix " SFP 10G " (port + 0)
      }
      if (model == "S5720-12TP-LI-AC" && name ~ /^GigabitEthernet0\/0\/[0-9]+$/) {
        port = name; sub(/^GigabitEthernet0\/0\//, "", port)
        if ((port + 0) <= 8) return prefix " Port " (port + 0)
        if ((port + 0) <= 12) return prefix " SFP 1G " ((port + 0) - 8)
      }
      if (model == "XS1930-10" && name ~ /^swp0[0-9]$/) {
        port = name; sub(/^swp0/, "", port)
        if ((port + 0) <= 7) return prefix " Port " ((port + 0) + 1)
        return prefix " SFP 10G " ((port + 0) - 7)
      }
      if (name ~ /^ge-0\/0\/[0-9]+$/) {
        port = name
        sub(/^ge-0\/0\//, "", port)
        return prefix " Port " (port + 0)
      }
      if (name ~ /^(xe|ge)-0\/1\/[0-3]$/) {
        port = name
        sub(/^(xe|ge)-0\/1\//, "", port)
        return prefix " SFP 10G " ((port + 0) + 1)
      }
      key = name
      sub(/^GigabitEthernet/, "", key)
      sub(/^TenGigabitEthernet/, "", key)
      sub(/^Gi/, "", key)
      sub(/^Te/, "", key)
      if (model ~ /^WS-C3560CG-8PC/ && key ~ /^0\/[0-9]+$/) {
        split(key, parts, "/")
        port = parts[2] + 0
        if (port <= 8) return prefix " Port " port
        if (port <= 10) return prefix " Uplink " (port - 8)
      }
      split(key, parts, "/")
      member = parts[1] + 0
      port = parts[3] + 0
      label = member_label(member)
      if (is_2960(model) && (name ~ /^Gi/ || name ~ /^GigabitEthernet/) && parts[2] == "0" && port > c2960_rj45_limit(model)) return label " Uplink " (port - c2960_rj45_limit(model))
      if (is_2960(model) && (name ~ /^Te/ || name ~ /^TenGigabitEthernet/) && parts[2] == "0") return label " SFP 10G " port
      if ((name ~ /^Gi/ || name ~ /^GigabitEthernet/) && parts[2] == "0") return label " Port " port
      if ((name ~ /^Gi/ || name ~ /^GigabitEthernet/) && parts[2] == "1") return label " Uplink " port
      if ((name ~ /^Te/ || name ~ /^TenGigabitEthernet/) && parts[2] == "1") return label " SFP 10G " port
      return label " Interface " idx
    }
    function chunk_label(start, arr) {
      split(phys_label[start], arr, " ")
      if (arr[1] != "") return arr[1]
      return prefix
    }
    function juniper_suffix(line, base, oid) {
      oid=line
      sub(/[[:space:]]*=.*/, "", oid)
      sub("^\\.", "", oid)
      base="1.3.6.1.4.1.2636.3.1.13.1."
      sub("^" base "[0-9]+\\.", "", oid)
      return oid
    }
    function yaml_sensor(oid, name) {
      print "  - oid: " oid
      print "    name: " name
    }
    function physical_speed_cap_mbps(model, label) {
      if (model == "S5720-12TP-LI-AC" && label ~ /(^| )SFP 1G /) return 1000
      if (model == "WS-C3750-48P" && label ~ / Port /) return 100
      if (model == "WS-C3750-48P" && label ~ / SFP 1G /) return 1000
      return 0
    }
    function yaml_speed_sensor(model, idx, label, has_highspeed, has_ifspeed, cap_mbps) {
      cap_mbps = physical_speed_cap_mbps(model, label)
      if (has_highspeed) {
        yaml_sensor("1.3.6.1.2.1.31.1.1.1.15." idx, label " Speed Mbps")
        if (cap_mbps > 0) print "    template: \"{{ [value | int, " cap_mbps "] | min }}\""
      } else if (has_ifspeed) {
        yaml_sensor("1.3.6.1.2.1.2.2.1.5." idx, label " Speed Bps")
        if (cap_mbps > 0) print "    template: \"{{ [value | int, " (cap_mbps * 1000000) "] | min }}\""
      }
    }
    function yaml_interface_sensor(primary, secondary, name, attribute, icon) {
      print "  - name: " name
      print "    source: interface"
      print "    interfaces:"
      print "      - " primary
      print "      - " secondary
      print "    attribute: " attribute
      if (icon != "") print "    icon: " icon
    }
    function yaml_juniper_vlan_sensor(interface_name, name, attribute, icon) {
      print "  - name: " name
      print "    source: juniper_ex_vlan"
      print "    interface: " interface_name
      print "    attribute: " attribute
      if (icon != "") print "    icon: " icon
    }
    function yaml_juniper_vlan_candidates_sensor(primary, secondary, name, attribute, icon) {
      print "  - name: " name
      print "    source: juniper_ex_vlan"
      print "    interfaces:"
      print "      - " primary
      print "      - " secondary
      print "    attribute: " attribute
      if (icon != "") print "    icon: " icon
    }
    function yaml_target_header(name, interval) {
      print ""
      print "- host: " host
      print "  name: " name
      print "  version: 2c"
      print "  community: " community
      print "  device_manufacturer: " manufacturer
      print "  device_model: " model
      print "  scan_interval: " interval
      print "  sensors:"
    }
    function temp_role(name) {
      if (name ~ /Inlet/) return "Temperature Inlet"
      if (name ~ /Outlet/) return "Temperature Outlet"
      if (name ~ /HotSpot/) return "Temperature"
      return "Temperature"
    }
    function temp_member(name, arr) {
      if (match(name, /Switch [0-9]+/)) {
        split(substr(name, RSTART, RLENGTH), arr, " ")
        return arr[2] + 0
      }
      return 1
    }
    function model_rank(value, score) {
      if (value == "") return 0
      score = length(value)
      if (value ~ /-[A-Z]$/) score += 1000
      return score
    }
    BEGIN {
      model="unknown"; manufacturer="Cisco"; maxidx=0; maxcpu=0; maxpoe=0; maxstdpoe=0; maxtemp=0; physical_count=0
      if (member_map != "") {
        split(member_map, mm_items, ",")
        for (mmi in mm_items) {
          split(mm_items[mmi], mm_parts, "=")
          if (mm_parts[1] != "" && mm_parts[2] != "") member_prefix[mm_parts[1] ""] = mm_parts[2]
        }
      }
    }
    {
      line=$0; val=value_of(line)
      lower_line=tolower(line)
      if (lower_line ~ /ex3300-48p/) {
        juniper_model="Juniper EX3300-48P"
      }
      if (line ~ /SG500X-24/) sg500_model="SG500X-24"
      if (line ~ /S5735-L8P4X-A1/) huawei_s5735_model="S5735-L8P4X-A1"
      if (line ~ /S5720-12TP-LI-AC/) huawei_s5720_model="S5720-12TP-LI-AC"
      if (line ~ /XS1930-10/) zyxel_model="XS1930-10"
      if (line ~ /N2128PX-ON/) dell_model="N2128PX-ON"
      if (line ~ /WS-C3750-48P/) c3750_model="WS-C3750-48P"
      if (match(line, /WS-C(3650|3750X|3750|3560CG|2960X|2960S)-[A-Z0-9-]+/)) {
        model_candidate=substr(line, RSTART, RLENGTH)
        if (line ~ /\.3\.6\.1\.2\.1\.47\.1\.1\.1\.1\.(2|7|13)\./ || line ~ /\.3\.6\.1\.4\.1\.9\.5\.1\./) {
          if (model_rank(model_candidate) > model_rank(local_model)) local_model=model_candidate
        } else if (line ~ /\.3\.6\.1\.2\.1\.1\.1\.0/) {
          if (model_rank(model_candidate) > model_rank(sys_model)) sys_model=model_candidate
        } else if (model_rank(model_candidate) > model_rank(candidate_model)) candidate_model=model_candidate
      }
      if (generic_model == "" && line !~ /\.1\.0\.8802\./ && line !~ /\.3\.6\.1\.4\.1\.9\.9\.23\./) {
        if (line ~ /C2960X/) generic_model="C2960X"
        else if (line ~ /C2960S/) generic_model="C2960S"
      }
      if (line ~ /\.3\.6\.1\.2\.1\.2\.2\.1\.2\.[0-9]+ = STRING:/) {
        idx=oid_index(line)
        if (!(idx in ifname)) { ifname[idx]=val; ifname_source[idx]="ifDescr" }
        if (idx>maxidx) maxidx=idx
      }
      if (line ~ /\.3\.6\.1\.2\.1\.31\.1\.1\.1\.1\.[0-9]+ = STRING:/) {
        idx=oid_index(line); ifname[idx]=val; ifname_source[idx]="ifName"; if (idx>maxidx) maxidx=idx
        # Junos exposes switching/VLAN membership against the logical .0 IFL,
        # while link state and counters remain on the physical interface. Keep
        # a dynamic port-to-logical-ifIndex map for later bridge/PVID joins.
        if (val ~ /^ge-0\/0\/[0-9]+\.0$/) {
          logical_port=val
          sub(/^ge-0\/0\//, "", logical_port)
          sub(/\.0$/, "", logical_port)
          juniper_logical_ifindex[logical_port + 0]=idx
        }
        if (c3750_model != "" && val ~ /^(Fa|FastEthernet)[0-9]+\/0\/([1-9]|[1-3][0-9]|4[0-8])$/) {
          physical_count++
          c3750_key=val
          sub(/^FastEthernet/, "", c3750_key)
          sub(/^Fa/, "", c3750_key)
          split(c3750_key, c3750_parts, "/")
          physical_member[c3750_parts[1] + 0] = 1
        } else if (c3750_model != "" && val ~ /^(Gi|GigabitEthernet)[0-9]+\/0\/[1-4]$/) {
          physical_count++
          c3750_key=val
          sub(/^GigabitEthernet/, "", c3750_key)
          sub(/^Gi/, "", c3750_key)
          split(c3750_key, c3750_parts, "/")
          physical_member[c3750_parts[1] + 0] = 1
        } else if (sg500_model != "" && val ~ /^(gi|te)1\/[0-9]+$/) {
          physical_count++
          physical_member[1] = 1
        } else if (huawei_s5735_model != "" && val ~ /^(GigabitEthernet|XGigabitEthernet)0\/0\/[0-9]+$/) {
          physical_count++
          physical_member[1] = 1
        } else if (huawei_s5720_model != "" && val ~ /^GigabitEthernet0\/0\/([1-9]|1[0-2])$/) {
          physical_count++
          physical_member[1] = 1
        } else if (zyxel_model != "" && val ~ /^swp0[0-9]$/) {
          physical_count++
          physical_member[1] = 1
        } else if (val ~ /^(Gi|GigabitEthernet|Te|TenGigabitEthernet)[0-9]+\/[0-9]+\/[0-9]+$/ || val ~ /^(Gi|GigabitEthernet)0\/([1-9]|10)$/) {
          physical_count++
          member_key=val
          sub(/^GigabitEthernet/, "", member_key)
          sub(/^TenGigabitEthernet/, "", member_key)
          sub(/^Gi/, "", member_key)
          sub(/^Te/, "", member_key)
          split(member_key, member_parts, "/")
          if (model ~ /^WS-C3560CG-8PC/ && member_key ~ /^0\/[0-9]+$/) physical_member[1] = 1
          else physical_member[member_parts[1]] = 1
        } else if (val ~ /^ge-0\/0\/[0-9]+$/) {
          port_no=val
          sub(/^ge-0\/0\//, "", port_no)
          if ((port_no + 0) >= 0 && (port_no + 0) <= 47) {
            physical_count++
            physical_member[1] = 1
          }
        } else if (val ~ /^(xe|ge)-0\/1\/[0-3]$/) {
          # Juniper EX3300 uplink cages. Junos may expose a populated cage as
          # xe-0/1/N (10G) or ge-0/1/N (1G). Both names map to TE1-TE4 and the
          # logical .0 interfaces remain excluded.
          physical_count++
          physical_member[1] = 1
        }
      }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.68\.1\.2\.2\.1\.2\.[0-9]+ = /) { idx=oid_index(line); vlan_id_idx[idx]=1 }
      # Standard Q-BRIDGE-MIB VLAN correlation used by Juniper and any future
      # platform that exposes VLAN PVIDs through logical bridge interfaces.
      # dot1dBasePortIfIndex maps bridge-port -> logical ifIndex.
      if (line ~ /\.3\.6\.1\.2\.1\.17\.1\.4\.1\.2\.[0-9]+ = INTEGER:/) {
        bridge_port=oid_index(line)
        bridge_ifindex=val + 0
        if (bridge_ifindex > 0) bridge_for_ifindex[bridge_ifindex]=bridge_port
      }
      # dot1qPvid maps bridge-port -> current PVID/native VLAN. Presence is
      # recorded from the walk so generated YAML never references a missing row.
      if (line ~ /\.3\.6\.1\.2\.1\.17\.7\.1\.4\.5\.1\.1\.[0-9]+ = /) {
        bridge_port=oid_index(line)
        qbridge_pvid_idx[bridge_port]=1
      }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.46\.1\.6\.1\.1\.14\.[0-9]+ = /) { idx=oid_index(line); trunk_status_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.31\.1\.1\.1\.18\.[0-9]+ = /) { idx=oid_index(line); alias_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.31\.1\.1\.1\.6\.[0-9]+ = /) { idx=oid_index(line); hc_in_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.31\.1\.1\.1\.10\.[0-9]+ = /) { idx=oid_index(line); hc_out_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.2\.2\.1\.10\.[0-9]+ = /) { idx=oid_index(line); legacy_in_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.2\.2\.1\.16\.[0-9]+ = /) { idx=oid_index(line); legacy_out_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.31\.1\.1\.1\.15\.[0-9]+ = /) { idx=oid_index(line); highspeed_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.2\.2\.1\.5\.[0-9]+ = /) { idx=oid_index(line); ifspeed_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.109\.1\.1\.1\.1\.6\.[0-9]+ = Gauge32:/) { idx=oid_index(line); cpu_idx[idx]=1; if(idx>maxcpu) maxcpu=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.109\.1\.1\.1\.1\.7\.[0-9]+ = Gauge32:/) { idx=oid_index(line); cpu_idx[idx]=1; if(idx>maxcpu) maxcpu=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.109\.1\.1\.1\.1\.8\.[0-9]+ = Gauge32:/) { idx=oid_index(line); cpu_idx[idx]=1; if(idx>maxcpu) maxcpu=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.402\.1\.3\.1\.2\.[0-9]+ = /) { idx=oid_index(line); poe_name_idx[idx]=1; poe_idx[idx]=1; if(idx>maxpoe) maxpoe=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.402\.1\.3\.1\.3\.[0-9]+ = /) { idx=oid_index(line); poe_status_idx[idx]=1; poe_idx[idx]=1; if(idx>maxpoe) maxpoe=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.402\.1\.3\.1\.4\.[0-9]+ = /) { idx=oid_index(line); poe_used_idx[idx]=1; poe_idx[idx]=1; if(idx>maxpoe) maxpoe=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.402\.1\.3\.1\.5\.[0-9]+ = /) { idx=oid_index(line); poe_budget_idx[idx]=1; poe_idx[idx]=1; if(idx>maxpoe) maxpoe=idx }
      # POWER-ETHERNET-MIB aggregate fallback used by Catalyst models such
      # as the 2960S when CISCO-POWER-ETHERNET-EXT-MIB totals are absent.
      # These standard aggregate values are reported in watts.
      if (line ~ /\.3\.6\.1\.2\.1\.105\.1\.3\.1\.1\.2\.[0-9]+ = /) { idx=oid_index(line); std_poe_budget_idx[idx]=1; if(idx>maxstdpoe) maxstdpoe=idx }
      if (line ~ /\.3\.6\.1\.2\.1\.105\.1\.3\.1\.1\.4\.[0-9]+ = /) { idx=oid_index(line); std_poe_used_idx[idx]=1; if(idx>maxstdpoe) maxstdpoe=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.13\.1\.3\.1\.2\.[0-9]+ = STRING:/) { idx=oid_index(line); temp_name[idx]=val; temp_idx[idx]=1; if(idx>maxtemp) maxtemp=idx }

      # Zyxel XS1930-10 contribution-proven identity and health OIDs.
      # Emit only exact rows present in the current walk; enterprise-tree
      # proximity alone is never treated as proof of a sensor.
      if (line ~ /\.3\.6\.1\.4\.1\.890\.1\.15\.3\.1\.6\.0 = /) zyxel_firmware_present=1
      if (line ~ /\.3\.6\.1\.4\.1\.890\.1\.15\.3\.1\.11\.0 = /) zyxel_model_present=1
      if (line ~ /\.3\.6\.1\.4\.1\.890\.1\.15\.3\.1\.12\.0 = /) zyxel_serial_present=1
      if (line ~ /\.3\.6\.1\.4\.1\.890\.1\.15\.3\.2\.4\.0 = /) zyxel_cpu_current_present=1
      if (line ~ /\.3\.6\.1\.4\.1\.890\.1\.15\.3\.2\.5\.0 = /) zyxel_memory_present=1
      if (line ~ /\.3\.6\.1\.4\.1\.890\.1\.15\.3\.2\.7\.0 = /) zyxel_cpu_5sec_present=1
      if (line ~ /\.3\.6\.1\.4\.1\.890\.1\.15\.3\.2\.8\.0 = /) zyxel_cpu_1min_present=1
      if (line ~ /\.3\.6\.1\.4\.1\.890\.1\.15\.3\.2\.9\.0 = /) zyxel_cpu_5min_present=1
      if (line ~ /\.3\.6\.1\.4\.1\.890\.1\.15\.3\.26\.1\.1\.1\.2\.[0-9]+ = /) { idx=oid_index(line); zyxel_fan_descr[idx]=val; zyxel_fan_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.890\.1\.15\.3\.26\.1\.1\.1\.3\.[0-9]+ = /) { idx=oid_index(line); zyxel_fan_rpm[idx]=1; zyxel_fan_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.890\.1\.15\.3\.26\.1\.1\.1\.7\.[0-9]+ = /) { idx=oid_index(line); zyxel_fan_status[idx]=1; zyxel_fan_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.890\.1\.15\.3\.26\.1\.2\.1\.2\.[0-9]+ = /) { idx=oid_index(line); zyxel_temp_descr[idx]=val; zyxel_temp_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.890\.1\.15\.3\.26\.1\.2\.1\.3\.[0-9]+ = /) { idx=oid_index(line); zyxel_temp_current[idx]=1; zyxel_temp_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.890\.1\.15\.3\.26\.1\.2\.1\.7\.[0-9]+ = /) { idx=oid_index(line); zyxel_temp_status[idx]=1; zyxel_temp_idx[idx]=1 }

      # Juniper chassis operating table. The four-part suffix identifies the
      # same physical subject across description, state, temperature, CPU,
      # buffer and installed-memory columns. Only values present in the walk
      # are emitted later.
      if (line ~ /\.3\.6\.1\.4\.1\.2636\.3\.1\.13\.1\.5\./) { suffix=juniper_suffix(line); jnx_descr[suffix]=val; jnx_subject[suffix]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.2636\.3\.1\.13\.1\.6\./) { suffix=juniper_suffix(line); jnx_state[suffix]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.2636\.3\.1\.13\.1\.7\./) { suffix=juniper_suffix(line); jnx_temp[suffix]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.2636\.3\.1\.13\.1\.8\./) { suffix=juniper_suffix(line); jnx_cpu[suffix]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.2636\.3\.1\.13\.1\.11\./) { suffix=juniper_suffix(line); jnx_buffer[suffix]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.2636\.3\.1\.13\.1\.15\./) { suffix=juniper_suffix(line); jnx_memory[suffix]=1 }

      # Identity evidence is walk-aware. Only emit OIDs that were actually
      # returned by the switch so generated SNMP2MQTT YAML never references a
      # missing ENTITY-MIB row.
      if (line ~ /\.3\.6\.1\.2\.1\.1\.1\.0 = /) sys_descr_present=1
      if (line ~ /\.3\.6\.1\.2\.1\.47\.1\.1\.1\.1\.2\.[0-9]+ = /) {
        idx=oid_index(line)
        if (val ~ /^WS-C[0-9A-Z-]+$/ || val ~ /^Juniper EX3300-48P Ethernet Switch$/) {
          identity_idx[idx]=1
          identity_model_descr_idx[idx]=1
        }
      }
      if (line ~ /\.3\.6\.1\.2\.1\.47\.1\.1\.1\.1\.13\.[0-9]+ = /) {
        idx=oid_index(line)
        if (val ~ /^WS-C[0-9A-Z-]+$/ || val ~ /^Juniper EX3300-48P Ethernet Switch$/) {
          identity_idx[idx]=1
          identity_model_name_idx[idx]=1
        }
      }
      if (line ~ /\.3\.6\.1\.2\.1\.47\.1\.1\.1\.1\.11\.[0-9]+ = /) {
        idx=oid_index(line)
        # A chassis serial is accepted only for an index already identified as
        # a switch model. This prevents power-supply, fan, and module serials
        # from creating duplicate member Serial entities.
        if ((idx in identity_idx) && val != "" && val !~ /^(N\/A|NA|unknown|not specified)$/) {
          identity_serial_idx[idx]=1
        }
      }
    }
    END {
      if (zyxel_model != "") {
        model = zyxel_model
        manufacturer = "Zyxel"
      }
      else if (huawei_s5720_model != "") {
        model = huawei_s5720_model
        manufacturer = "Huawei"
      }
      else if (huawei_s5735_model != "") {
        model = huawei_s5735_model
        manufacturer = "Huawei"
      }
      else if (sg500_model != "") {
        model = sg500_model
        manufacturer = "Cisco"
      }
      else if (juniper_model != "") {
        model = juniper_model
        manufacturer = "Juniper"
      }
      else if (dell_model != "") {
        model = dell_model
        manufacturer = "Dell"
      }
      else if (c3750_model != "") model = c3750_model
      else if (local_model != "") model = local_model
      else if (sys_model != "") model = sys_model
      else if (candidate_model != "") model = candidate_model
      else if (generic_model != "") model = generic_model
      print "# Device source: " source_name
      print "# Target host: " host
      print "# Prefix: " prefix
      if (member_map != "") print "# Stack member prefixes: " member_map
      print "# Detected model: " model

      stack_members=0
      for (m in physical_member) stack_members++
      status_interval = 30
      traffic_interval = 10
      print "# Stack-safe polling: " stack_members " member(s), " physical_count " physical interfaces"
      print "# Status interval: " status_interval "s"
      print "# Traffic interval: " traffic_interval "s"

      # Build an ordered physical-interface list once, then emit small target chunks.
      # SNMP2MQTT may use grouped SNMP requests per target; very large groups can trigger
      # SNMP TooBig responses on Catalyst stacks. Keep chunks deliberately conservative.
      phys_n = 0
      for (idx=1; idx<=maxidx; idx++) if (idx in ifname) {
        name=ifname[idx]
        if ((model == "WS-C3750-48P" && name ~ /^(Fa|FastEthernet)[0-9]+\/0\/([1-9]|[1-3][0-9]|4[0-8])$/) || (model == "WS-C3750-48P" && name ~ /^(Gi|GigabitEthernet)[0-9]+\/0\/[1-4]$/) || (model == "SG500X-24" && name ~ /^(gi|te)1\/[0-9]+$/) || (model == "S5735-L8P4X-A1" && name ~ /^(GigabitEthernet|XGigabitEthernet)0\/0\/[0-9]+$/) || (model == "S5720-12TP-LI-AC" && name ~ /^GigabitEthernet0\/0\/([1-9]|1[0-2])$/) || (model == "XS1930-10" && name ~ /^swp0[0-9]$/) || name ~ /^(Gi|GigabitEthernet|Te|TenGigabitEthernet)[0-9]+\/[0-9]+\/[0-9]+$/ || (model ~ /^WS-C3560CG-8PC/ && name ~ /^(Gi|GigabitEthernet)0\/([1-9]|10)$/) || name ~ /^ge-0\/0\/[0-9]+$/ || name ~ /^(xe|ge)-0\/1\/[0-3]$/) {
          if (model == "Juniper EX3300-48P" && name ~ /^(xe|ge)-0\/1\/[0-3]$/) continue
          if (name ~ /^ge-0\/0\/[0-9]+$/) {
            port_no=name
            sub(/^ge-0\/0\//, "", port_no)
            if ((port_no + 0) < 0 || (port_no + 0) > 47) continue
          }
          phys_n++
          phys_idx[phys_n] = idx
          phys_label[phys_n] = physical_label(name, idx)
        }
      }

      status_chunk_size = 12
      traffic_chunk_size = 8
      vlan_chunk_size = 8
      slow_iface_chunk_size = 12
      print "# Chunked polling: status " status_chunk_size " ports/target, traffic " traffic_chunk_size " ports/target, VLAN/trunk " vlan_chunk_size " ports/target, slow interface " slow_iface_chunk_size " ports/target"
      vlan_oid_count=0
      for (v in vlan_id_idx) vlan_oid_count++
      qbridge_pvid_rows=0
      for (v in qbridge_pvid_idx) qbridge_pvid_rows++
      if (model == "XS1930-10") print "# Walk-aware VLAN source: Q-BRIDGE PVID rows=" qbridge_pvid_rows "; trunk/access mode is not inferred"
      else print "# Walk-aware VLAN ID sensors: " vlan_oid_count " exact VLAN OID(s) found; missing VLAN OIDs are skipped"

      chunk=0
      for (start=1; start<=phys_n; start+=status_chunk_size) {
        chunk++
        yaml_target_header("Switch Vision " chunk_label(start) " Status " sprintf("%02d", chunk), status_interval)
        stop=start + status_chunk_size - 1
        if (stop > phys_n) stop = phys_n
        for (i=start; i<=stop; i++) {
          idx=phys_idx[i]
          label=phys_label[i]
          yaml_sensor("1.3.6.1.2.1.2.2.1.8." idx, label " Status")
        }
      }

      if (model == "Juniper EX3300-48P") {
        yaml_target_header("Switch Vision " prefix " SFP Status", status_interval)
        for (cage=0; cage<4; cage++) {
          label=prefix " SFP 10G " (cage + 1)
          primary="xe-0/1/" cage
          secondary="ge-0/1/" cage
          yaml_interface_sensor(primary, secondary, label " Status", "oper_status", "")
        }
      }

      chunk=0
      skipped_hc=0
      for (start=1; start<=phys_n; start+=traffic_chunk_size) {
        stop=start + traffic_chunk_size - 1
        if (stop > phys_n) stop = phys_n
        traffic_sensor_count=0
        for (i=start; i<=stop; i++) {
          idx=phys_idx[i]
          if ((idx in hc_in_idx) || (idx in legacy_in_idx)) traffic_sensor_count++
          if ((idx in hc_out_idx) || (idx in legacy_out_idx)) traffic_sensor_count++
        }
        if (traffic_sensor_count > 0) {
          chunk++
          yaml_target_header("Switch Vision " chunk_label(start) " Traffic " sprintf("%02d", chunk), traffic_interval)
          for (i=start; i<=stop; i++) {
            idx=phys_idx[i]
            label=phys_label[i]
            if (idx in hc_in_idx) yaml_sensor("1.3.6.1.2.1.31.1.1.1.6." idx, label " RX Bytes")
            else if (idx in legacy_in_idx) { yaml_sensor("1.3.6.1.2.1.2.2.1.10." idx, label " RX Bytes"); legacy_counter_fallbacks++ }
            else skipped_hc++
            if (idx in hc_out_idx) yaml_sensor("1.3.6.1.2.1.31.1.1.1.10." idx, label " TX Bytes")
            else if (idx in legacy_out_idx) { yaml_sensor("1.3.6.1.2.1.2.2.1.16." idx, label " TX Bytes"); legacy_counter_fallbacks++ }
            else skipped_hc++
          }
        } else {
          skipped_hc += (stop-start+1) * 2
        }
      }
      print "# Walk-aware traffic counters: " skipped_hc " missing counter OID(s) skipped; " (legacy_counter_fallbacks + 0) " legacy 32-bit counter fallback(s) used"

      if (model == "Juniper EX3300-48P") {
        yaml_target_header("Switch Vision " prefix " SFP Traffic", traffic_interval)
        for (cage=0; cage<4; cage++) {
          label=prefix " SFP 10G " (cage + 1)
          primary="xe-0/1/" cage
          secondary="ge-0/1/" cage
          yaml_interface_sensor(primary, secondary, label " RX Bytes", "rx_bytes", "")
          yaml_interface_sensor(primary, secondary, label " TX Bytes", "tx_bytes", "")
        }
      }

      chunk=0
      for (start=1; start<=phys_n; start+=vlan_chunk_size) {
        chunk++
        yaml_target_header("Switch Vision " chunk_label(start) " VLAN and trunk " sprintf("%02d", chunk), 30)
        stop=start + vlan_chunk_size - 1
        if (stop > phys_n) stop = phys_n
        for (i=start; i<=stop; i++) {
          idx=phys_idx[i]
          label=phys_label[i]
          vlan_emitted=0
          if (idx in vlan_id_idx) {
            yaml_sensor("1.3.6.1.4.1.9.9.68.1.2.2.1.2." idx, label " VLAN ID")
            vlan_emitted=1
          }
          # Zyxel XS1930-10 maps dot1dBasePortIfIndex directly to its
          # physical swp ifIndex values. Use Q-BRIDGE PVID only when the
          # current walk proves both sides of that join.
          if (!vlan_emitted && model == "XS1930-10" && ifname[idx] ~ /^swp0[0-9]$/) {
            bridge_idx=bridge_for_ifindex[idx]
            if (bridge_idx > 0 && (bridge_idx in qbridge_pvid_idx)) {
              yaml_sensor("1.3.6.1.2.1.18.7.1.4.5.1.1." bridge_idx, label " VLAN ID")
              vlan_emitted=1
              zyxel_vlan_count++
            }
          }
          # Juniper EX switching VLANs are indexed through the matching .0
          # logical interface and bridge-port table rather than physical ifIndex.
          # Resolve every value from the current walk; no port, bridge index,
          # interface-range name, or VLAN ID is hard-coded.
          if (!vlan_emitted && ifname[idx] ~ /^ge-0\/0\/[0-9]+$/) {
            juniper_port=ifname[idx]
            sub(/^ge-0\/0\//, "", juniper_port)
            logical_idx=juniper_logical_ifindex[juniper_port + 0]
            bridge_idx=bridge_for_ifindex[logical_idx]
            if (logical_idx > 0 && bridge_idx > 0 && (bridge_idx in qbridge_pvid_idx)) {
              yaml_sensor("1.3.6.1.2.1.18.7.1.4.5.1.1." bridge_idx, label " VLAN ID")
              vlan_emitted=1
              juniper_vlan_count++
            }
          }
          if (!vlan_emitted) skipped_vlan_id++
          if (idx in trunk_status_idx) yaml_sensor("1.3.6.1.4.1.9.9.46.1.6.1.1.14." idx, label " Trunk Status")
          else skipped_trunk_status++
          if (idx in alias_idx) yaml_sensor("1.3.6.1.2.1.31.1.1.1.18." idx, label " Alias")
          else skipped_alias++
        }
      }

      if (manufacturer == "Juniper") {
        # SNMP2MQTT core v0.9.9 can derive complete Juniper EX VLAN state from
        # the numeric Juniper/Q-BRIDGE tables. Keep these sensors together in
        # one dedicated target so the collector performs one correlated table
        # read per poll instead of repeating the same walks for every chunk.
        yaml_target_header("Switch Vision " prefix " Juniper VLAN State", 30)
        juniper_derived_count=0
        for (i=1; i<=phys_n; i++) {
          idx=phys_idx[i]
          interface_name=ifname[idx]
          label=phys_label[i]
          yaml_juniper_vlan_sensor(interface_name, label " VLAN Mode", "mode", "mdi:lan-connect")
          yaml_juniper_vlan_sensor(interface_name, label " Native VLAN", "native_vlan", "mdi:tag-outline")
          yaml_juniper_vlan_sensor(interface_name, label " VLANs", "vlans", "mdi:tag-multiple-outline")
          yaml_juniper_vlan_sensor(interface_name, label " Tagged VLANs", "tagged_vlans", "mdi:tag-multiple")
          yaml_juniper_vlan_sensor(interface_name, label " Untagged VLANs", "untagged_vlans", "mdi:tag-off-outline")
          yaml_juniper_vlan_sensor(interface_name, label " VLAN Summary", "summary", "mdi:information-outline")
          juniper_derived_count += 6
        }
        if (model == "Juniper EX3300-48P") {
          for (cage=0; cage<4; cage++) {
            label=prefix " SFP 10G " (cage + 1)
            primary="xe-0/1/" cage
            secondary="ge-0/1/" cage
            yaml_juniper_vlan_candidates_sensor(primary, secondary, label " VLAN Mode", "mode", "mdi:lan-connect")
            yaml_juniper_vlan_candidates_sensor(primary, secondary, label " Native VLAN", "native_vlan", "mdi:tag-outline")
            yaml_juniper_vlan_candidates_sensor(primary, secondary, label " VLANs", "vlans", "mdi:tag-multiple-outline")
            yaml_juniper_vlan_candidates_sensor(primary, secondary, label " Tagged VLANs", "tagged_vlans", "mdi:tag-multiple")
            yaml_juniper_vlan_candidates_sensor(primary, secondary, label " Untagged VLANs", "untagged_vlans", "mdi:tag-off-outline")
            yaml_juniper_vlan_candidates_sensor(primary, secondary, label " VLAN Summary", "summary", "mdi:information-outline")
            juniper_derived_count += 6
          }
        }
        print "# Juniper EX derived VLAN sensors emitted: " juniper_derived_count

        logical_count=0
        bridge_count=0
        pvid_count=0
        join_count=0
        for (p in juniper_logical_ifindex) {
          logical_count++
          logical_idx=juniper_logical_ifindex[p]
          bridge_idx=bridge_for_ifindex[logical_idx]
          if (bridge_idx > 0 && (bridge_idx in qbridge_pvid_idx)) join_count++
        }
        for (b in bridge_for_ifindex) bridge_count++
        for (q in qbridge_pvid_idx) pvid_count++
        print "# Juniper VLAN correlation: logical interfaces=" logical_count ", bridge mappings=" bridge_count ", PVID rows=" pvid_count ", successful joins=" join_count
        print "# Dynamic Juniper Q-BRIDGE PVID sensors emitted: " (juniper_vlan_count + 0)
      }

      yaml_target_header("Switch Vision " prefix " Slow System", 300)
      yaml_sensor("1.3.6.1.2.1.1.3.0", prefix " Uptime")

      # Identity sensors share the existing Slow System poll group. This keeps
      # static device details lightweight while ensuring they are created on
      # the first SNMP2MQTT poll after a restart.
      if (sys_descr_present) {
        member_seen=0
        for (m in physical_member) {
          label=member_label(m)
          yaml_sensor("1.3.6.1.2.1.1.1.0", label " System Description")
          member_seen=1
        }
        if (!member_seen) yaml_sensor("1.3.6.1.2.1.1.1.0", prefix " System Description")
      }
      for (idx in identity_idx) {
        member_no=int(idx / 1000)
        if (member_no < 1) member_no=1
        label=member_label(member_no)
        if (idx in identity_model_name_idx) yaml_sensor("1.3.6.1.2.1.47.1.1.1.1.13." idx, label " Model")
        else if (idx in identity_model_descr_idx) yaml_sensor("1.3.6.1.2.1.47.1.1.1.1.2." idx, label " Model")
        if (idx in identity_serial_idx) yaml_sensor("1.3.6.1.2.1.47.1.1.1.1.11." idx, label " Serial")
      }

      if (model == "XS1930-10") {
        if (zyxel_model_present) yaml_sensor("1.3.6.1.4.1.890.1.15.3.1.11.0", prefix " Model")
        if (zyxel_firmware_present) yaml_sensor("1.3.6.1.4.1.890.1.15.3.1.6.0", prefix " Firmware")
        if (zyxel_serial_present) yaml_sensor("1.3.6.1.4.1.890.1.15.3.1.12.0", prefix " Serial")
      }

      cpu_member=0
      for (idx=1; idx<=maxcpu; idx++) if (idx in cpu_idx) {
        cpu_member++
        label=member_label(cpu_member)
        yaml_sensor("1.3.6.1.4.1.9.9.109.1.1.1.1.6." idx, label " CPU 5sec")
        yaml_sensor("1.3.6.1.4.1.9.9.109.1.1.1.1.7." idx, label " CPU 1min")
        yaml_sensor("1.3.6.1.4.1.9.9.109.1.1.1.1.8." idx, label " CPU 5min")
      }
      # Juniper EX/QFX health sensors. Prefer the Routing Engine for the
      # dashboard CPU and temperature entities; retain fan and power-supply
      # state sensors using the component descriptions returned by the switch.
      if (manufacturer == "Juniper") {
        for (suffix in jnx_subject) {
          descr=jnx_descr[suffix]
          if (descr ~ /Routing Engine/) {
            if (suffix in jnx_cpu) yaml_sensor("1.3.6.1.4.1.2636.3.1.13.1.8." suffix, prefix " CPU")
            if (suffix in jnx_temp) yaml_sensor("1.3.6.1.4.1.2636.3.1.13.1.7." suffix, prefix " Temperature")
            if (suffix in jnx_buffer) yaml_sensor("1.3.6.1.4.1.2636.3.1.13.1.11." suffix, prefix " Memory Used Percent")
            if (suffix in jnx_memory) yaml_sensor("1.3.6.1.4.1.2636.3.1.13.1.15." suffix, prefix " Memory Total MB")
          }
          if (descr ~ /FAN|Fan|fan/) {
            if (suffix in jnx_state) yaml_sensor("1.3.6.1.4.1.2636.3.1.13.1.6." suffix, prefix " Fans")
          }
          if (descr ~ /Power Supply|PEM|PSU/) {
            if (suffix in jnx_state) yaml_sensor("1.3.6.1.4.1.2636.3.1.13.1.6." suffix, prefix " PSU Status")
          }
        }
      }

      if (model == "XS1930-10") {
        if (zyxel_cpu_current_present) yaml_sensor("1.3.6.1.4.1.890.1.15.3.2.4.0", prefix " CPU")
        if (zyxel_cpu_5sec_present) yaml_sensor("1.3.6.1.4.1.890.1.15.3.2.7.0", prefix " CPU 5sec")
        if (zyxel_cpu_1min_present) yaml_sensor("1.3.6.1.4.1.890.1.15.3.2.8.0", prefix " CPU 1min")
        if (zyxel_cpu_5min_present) yaml_sensor("1.3.6.1.4.1.890.1.15.3.2.9.0", prefix " CPU 5min")
        if (zyxel_memory_present) yaml_sensor("1.3.6.1.4.1.890.1.15.3.2.5.0", prefix " Memory Utilization")
        fan_status_primary=0
        for (idx in zyxel_fan_idx) {
          if (idx in zyxel_fan_rpm) yaml_sensor("1.3.6.1.4.1.890.1.15.3.26.1.1.1.3." idx, prefix " Fan " idx " RPM")
          if (idx in zyxel_fan_status) {
            if (!fan_status_primary) {
              yaml_sensor("1.3.6.1.4.1.890.1.15.3.26.1.1.1.7." idx, prefix " Fans")
              fan_status_primary=1
            } else {
              yaml_sensor("1.3.6.1.4.1.890.1.15.3.26.1.1.1.7." idx, prefix " Fan " idx " Status")
            }
          }
        }
        for (idx in zyxel_temp_idx) {
          descr=zyxel_temp_descr[idx]
          if (descr == "") descr="Sensor " idx
          if (idx in zyxel_temp_current) {
            if (toupper(descr) == "BOARD") yaml_sensor("1.3.6.1.4.1.890.1.15.3.26.1.2.1.3." idx, prefix " Temperature")
            else yaml_sensor("1.3.6.1.4.1.890.1.15.3.26.1.2.1.3." idx, prefix " Temperature " descr)
          }
          if (idx in zyxel_temp_status) {
            if (toupper(descr) == "BOARD") yaml_sensor("1.3.6.1.4.1.890.1.15.3.26.1.2.1.7." idx, prefix " Temperature Status")
            else yaml_sensor("1.3.6.1.4.1.890.1.15.3.26.1.2.1.7." idx, prefix " Temperature " descr " Status")
          }
        }
      }

      for (idx=1; idx<=maxpoe; idx++) if (idx in poe_idx) {
        label=member_label(idx)
        if (idx in poe_name_idx) yaml_sensor("1.3.6.1.4.1.9.9.402.1.3.1.2." idx, label " PoE Supply Name")
        if (idx in poe_status_idx) yaml_sensor("1.3.6.1.4.1.9.9.402.1.3.1.3." idx, label " PoE Supply Status")
        poe_unit = (model ~ /2960X|2960S/ ? "W" : "mW")
        if (idx in poe_used_idx) yaml_sensor("1.3.6.1.4.1.9.9.402.1.3.1.4." idx, label " PoE Used " poe_unit)
        if (idx in poe_budget_idx) yaml_sensor("1.3.6.1.4.1.9.9.402.1.3.1.5." idx, label " PoE Budget " poe_unit)
      }

      # Prefer Cisco extended totals when present. Fall back independently for
      # used and budget values to the standard POWER-ETHERNET-MIB aggregates.
      # This creates the expected 0 / 740 W sensors on WS-C2960S-48FPD-L.
      ext_used_present=0
      ext_budget_present=0
      for (idx in poe_used_idx) ext_used_present=1
      for (idx in poe_budget_idx) ext_budget_present=1
      for (idx=1; idx<=maxstdpoe; idx++) {
        label=member_label(idx)
        if (!ext_used_present && (idx in std_poe_used_idx)) yaml_sensor("1.3.6.1.2.1.105.1.3.1.1.4." idx, label " PoE Used W")
        if (!ext_budget_present && (idx in std_poe_budget_idx)) yaml_sensor("1.3.6.1.2.1.105.1.3.1.1.2." idx, label " PoE Budget W")
      }
      for (idx=1; idx<=maxtemp; idx++) if (idx in temp_idx) {
        role=temp_role(temp_name[idx])
        member=temp_member(temp_name[idx])
        label=member_label(member)
        yaml_sensor("1.3.6.1.4.1.9.9.13.1.3.1.3." idx, label " " role)
        if (role == "Temperature") yaml_sensor("1.3.6.1.4.1.9.9.13.1.3.1.6." idx, label " Temperature Status")
      }

      chunk=0
      for (start=1; start<=phys_n; start+=slow_iface_chunk_size) {
        chunk++
        yaml_target_header("Switch Vision " chunk_label(start) " Slow Interfaces " sprintf("%02d", chunk), 300)
        stop=start + slow_iface_chunk_size - 1
        if (stop > phys_n) stop = phys_n
        for (i=start; i<=stop; i++) {
          idx=phys_idx[i]
          label=phys_label[i]
          yaml_sensor("1.3.6.1.2.1.2.2.1.7." idx, label " Admin Status")
          yaml_speed_sensor(model, idx, label, (idx in highspeed_idx), (idx in ifspeed_idx))
        }
      }

      if (model == "Juniper EX3300-48P") {
        yaml_target_header("Switch Vision " prefix " SFP Slow Interfaces", 300)
        for (cage=0; cage<4; cage++) {
          label=prefix " SFP 10G " (cage + 1)
          primary="xe-0/1/" cage
          secondary="ge-0/1/" cage
          yaml_interface_sensor(primary, secondary, label " Admin Status", "admin_status", "")
          yaml_interface_sensor(primary, secondary, label " Speed Mbps", "speed_mbps", "")
          yaml_interface_sensor(primary, secondary, label " Alias", "alias", "")
        }
      }
    }
  ' "$walk_file" > "$generator_raw_tmp" || {
    rm -f "$generator_raw_tmp"
    echo "Generated YAML source parser failed for: $walk_file" >> "$LIVE_LOG_PATH" 2>/dev/null || true
    return 1
  }
  if ! awk '
    # YAML parses a bare `sensors:` key as null. Some model/polling chunks are
    # intentionally empty, so make those blocks explicit empty lists while
    # leaving populated sensor sequences untouched.
    function flush_pending_empty() {
      if (pending_sensors) {
        print "  sensors: []"
        pending_sensors=0
      }
    }
    {
      if (pending_sensors) {
        if ($0 ~ /^  - /) {
          print "  sensors:"
          pending_sensors=0
          print
          next
        }
        if ($0 ~ /^$/ || $0 ~ /^- host:/) {
          print "  sensors: []"
          pending_sensors=0
          print
          next
        }
        print "  sensors:"
        pending_sensors=0
      }
      if ($0 == "  sensors:") {
        pending_sensors=1
        next
      }
      print
    }
    END { flush_pending_empty() }
  ' "$generator_raw_tmp"; then
    rm -f "$generator_raw_tmp"
    echo "Generated YAML formatter failed for: $walk_file" >> "$LIVE_LOG_PATH" 2>/dev/null || true
    return 1
  fi
  rm -f "$generator_raw_tmp"
}

generator_has_unknown_targets() {
  tmp_walks="$1"
  while IFS= read -r walk_file; do
    [ -f "$walk_file" ] || continue
    target_ip=$(target_for_walk "$walk_file")
    if [ "$target_ip" = "unknown" ] || [ -z "$target_ip" ]; then
      return 0
    fi
  done < "$tmp_walks"
  return 1
}



model_metadata_for_generated_card() {
  selected_name="$1"
  field="$2"
  [ -n "$selected_name" ] || return 0
  safe_name=$(printf '%s' "$selected_name" | sed 's/[^A-Za-z0-9._-]/_/g')
  cap_file="$CAPABILITIES_DIR/${safe_name}-capabilities.json"
  [ -f "$cap_file" ] || return 0
  jq -r --arg field "$field" '
    if $field == "detected" then (.device.detected_model_text // .device.model_text // empty)
    elif $field == "override" then (.device.model_override // empty)
    elif $field == "effective" then (.device.effective_model_text // .device.model_text // empty)
    else empty end
  ' "$cap_file" 2>/dev/null | awk 'NF && $0 != "unknown" { print; exit }'
}

exact_model_for_generated_card() {
  model_metadata_for_generated_card "$1" effective
}

calibration_profile_for_generated_card() {
  selected_name="$1"
  [ -n "$selected_name" ] || return 0
  safe_name=$(printf '%s' "$selected_name" | sed 's/[^A-Za-z0-9._-]/_/g')
  cap_file="$CAPABILITIES_DIR/${safe_name}-capabilities.json"
  [ -f "$cap_file" ] || return 0
  jq -r '
    if ((.device.model_override // "") | length) > 0 then
      (.model_override_registry.calibration_profile // .registry.calibration_profile // empty)
    else
      (.registry.calibration_profile // empty)
    end
  ' "$cap_file" 2>/dev/null | awk 'NF && $0 != "null" { print; exit }'
}

card_port_counts_for_generated_card() {
  selected_name="$1"
  [ -n "$selected_name" ] || return 0
  safe_name=$(printf '%s' "$selected_name" | sed 's/[^A-Za-z0-9._-]/_/g')
  cap_file="$CAPABILITIES_DIR/${safe_name}-capabilities.json"
  [ -f "$cap_file" ] || return 0
  jq -r '
    (if ((.device.model_override // "") | length) > 0 then
       (.model_override_registry.ports // .registry.ports // {})
     else
       (.registry.ports // {})
     end) as $ports |
    ($ports.rj45 // empty) as $rj45 |
    # `uplinks` is the physical cage count. Media capability fields may overlap
    # on dual-rate ports (for example EX3300 SFP/SFP+), so summing them can
    # double-count the same physical uplink positions.
    ($ports.uplinks // (($ports.gigabit_sfp // 0) + ($ports.ten_gigabit_sfp_plus // 0))) as $sfp |
    if ($rj45 | type) == "number" and ($sfp | type) == "number" then "\($rj45)\t\($sfp)" else empty end
  ' "$cap_file" 2>/dev/null | awk 'NF && $0 != "null" { print; exit }'
}

emit_generated_card_port_counts() {
  selected_name="$1"
  counts=$(card_port_counts_for_generated_card "$selected_name")
  [ -n "$counts" ] || return 0
  card_rj45=$(printf '%s' "$counts" | awk -F '\t' '{print $1}')
  card_sfp=$(printf '%s' "$counts" | awk -F '\t' '{print $2}')
  case "$card_rj45" in ''|*[!0-9]*) return 0 ;; esac
  case "$card_sfp" in ''|*[!0-9]*) return 0 ;; esac
  echo "        port_count: ${card_rj45}"
  echo "        sfp_port_count: ${card_sfp}"
}

build_juniper_port_mode_metadata() {
  output_file="$1"
  : > "$output_file"
  helper="/juniper_vlan_modes.py"
  [ -f "$helper" ] || helper="$(dirname "$0")/juniper_vlan_modes.py"
  [ -f "$helper" ] || return 0

  tmp_walks="/tmp/switch_vision_dashboard_mode_walks.txt"
  collect_multi_walks "$tmp_walks"
  while IFS= read -r walk_file; do
    [ -f "$walk_file" ] || continue
    prefix=$(target_prefix_for_walk "$walk_file")
    safe_prefix=$(printf '%s' "$prefix" | tr '[:upper:]' '[:lower:]')
    python3 "$helper" "$walk_file" 2>/dev/null | while IFS="$(printf '\t')" read -r port mode pvid allowed || [ -n "$port" ]; do
      [ -n "$port" ] || continue
      printf '%s\t%s\t%s\t%s\t%s\n' "$safe_prefix" "$port" "$mode" "$pvid" "$allowed" >> "$output_file"
    done
  done < "$tmp_walks"
}

emit_generated_port_metadata() {
  prefix="$1"
  metadata_file="$2"
  [ -s "$metadata_file" ] || return 0
  rows=$(awk -F '\t' -v p="$prefix" '$1 == p { count++ } END { print count+0 }' "$metadata_file")
  [ "$rows" -gt 0 ] || return 0
  echo "        ports:"
  awk -F '\t' -v p="$prefix" '
    $1 == p {
      print "          \"" $2 "\":"
      print "            mode: " $3
      print "            native_vlan: \"" $4 "\""
      print "            vlan: \"" $4 "\""
      if ($5 != "") print "            allowed_vlans: \"" $5 "\""
    }
  ' "$metadata_file"
}

yaml_quote() {
  # Emit one YAML-safe double-quoted scalar. JSON strings are valid YAML and
  # correctly escape quotes, backslashes, control characters and newlines.
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import json,sys; print(json.dumps(sys.stdin.read(), ensure_ascii=False))'
  else
    # Minimal fallback for installations without python3. Discovery normally
    # has Python available, but keep generated YAML safe for common characters.
    sed ':a;N;$!ba;s/\\/\\\\/g;s/"/\\"/g;s/\r/\\r/g;s/\n/\\n/g' | sed 's/^/"/;s/$/"/'
  fi
}

write_generated_dashboard_card() {
  port_mode_metadata="/tmp/switch_vision_generated_port_modes.tsv"
  build_juniper_port_mode_metadata "$port_mode_metadata"
  # This is a review/copy helper only. Discovery does not write Lovelace dashboards.
  {
    echo "# Switch Vision generated dashboard card examples"
    echo "# Generated: $(date -Iseconds)"
    echo "# Source: Switch Vision Discovery v$SWITCH_VISION_DISCOVERY_VERSION"
    echo "# Review/copy only. This file is not installed automatically."
    echo "# Card visuals are selected from the model registry; generic faceplates are reusable across vendors."
    echo "views:"
    echo "  - title: Switch Vision"
    echo "    path: switch-vision"
    echo "    type: custom:vertical-layout"
    echo "    layout:"
    echo "      width: 800"
    echo "      max_cols: 1"
    echo "    cards:"
    echo "      - type: markdown"
    echo "        content: |"
    echo "          ## Switch Vision"
    echo ""
    echo "          Generated review-only card examples."

    if truthy "${GENERATED_CARD_SNMP_ENABLED:-false}" && command -v jq >/dev/null 2>&1 && [ -f "$CONFIG_FILE" ]; then
      tmp_cards="/tmp/switch_vision_generated_card_rows.tsv"
      jq -r '
        # SWITCH_VISION_GENERATED_CARD_ROWS_JQ_BEGIN
        def enabled($sw):
          (($sw.enabled // "enabled") as $value |
            if ($value | type) == "boolean" then $value
            elif ($value | type) == "string" then
              (($value | ascii_downcase) as $state |
                ($state != "false" and $state != "disabled" and $state != "disable" and
                 $state != "off" and $state != "no" and $state != "0"))
            else true end);
        def swname($sw): ($sw.switch_name // $sw.switch // $sw.selected_switch // $sw.name // "");
        def swlabel($sw): (swname($sw) // "live");
        def swprefix($sw): ($sw.sensor_prefix // $sw.entity_prefix // $sw.prefix // swlabel($sw));
        def member_id($m): (($m.member // $m.member_number // "") | tostring);
        def display_name($value):
          (($value // "") | tostring) as $name |
          if ($name | test("^sw[0-9]+$"; "i")) then ($name | ascii_upcase) else $name end;
        def default_member_key($sw): display_name(swprefix($sw) // swname($sw));
        def member_key($m; $fallback): display_name($m.profile // $m.sensor_prefix // $m.entity_prefix // $m.prefix // $fallback);
        def parent_title($sw): (($sw.display_name // $sw.card_title // "") | tostring);
        def row_safe($value):
          ((if $value == null then "" else ($value | tostring) end) |
            gsub("[\u0000-\u001f\u007f]"; " "));
        def clean_header_title($value):
          if ($value | type) == "string" then
            ($value | if (ascii_downcase == "true" or ascii_downcase == "false") then "" else . end)
          else "" end;
        def parent_header_title($sw): clean_header_title($sw.card_header_title // "");
        def member_header_title($m; $sw): clean_header_title($m.card_header_title // $sw.card_header_title // "");
        def member_display($m; $fallback): display_name($m.display_name // $m.member_name // $m.name // $fallback);
        (.switches // .multi_switch_walks // [])[]? as $sw |
          select(enabled($sw)) |
          swname($sw) as $name |
          ($sw.switch_host // $sw.host // $sw.manual_switch_host // "") as $host |
          ([ (.stack_member_prefixes // [])[]? | select((.switch_name // .switch // .selected_switch // .name // "") == $name) ]) as $members |
          (if ($members | length) > 0 then
            (($members | map(select(member_id(.) == "1")) | .[0]) // null) as $m1 |
            (if $m1 == null then
              (default_member_key($sw)) as $key |
              (if (parent_title($sw) | length) > 0 then parent_title($sw) else $key end) as $title |
              [[ $key, $name, swprefix($sw), $host, "1", $title, parent_header_title($sw) ]]
            else
              (member_key($m1; default_member_key($sw))) as $key |
              (member_display($m1; (if (parent_title($sw) | length) > 0 then parent_title($sw) else $key end))) as $title |
              [[ $key, $name, ($m1.sensor_prefix // $m1.entity_prefix // $m1.prefix // swprefix($sw)), $host, "1", $title, member_header_title($m1; $sw) ]]
            end)
            +
            ($members | map(select(member_id(.) != "1") |
              (member_key(.; ($name + "_M" + member_id(.)))) as $key |
              (member_display(.; $key)) as $title |
              [ $key, $name, (.sensor_prefix // .entity_prefix // .prefix // swprefix($sw)), $host, member_id(.), $title, member_header_title(.; $sw) ]
            ))
          else
            (default_member_key($sw)) as $key |
            (if (parent_title($sw) | length) > 0 then parent_title($sw) else $key end) as $title |
            [[ $key, $name, swprefix($sw), $host, "", $title, parent_header_title($sw) ]]
          end)[] | map(row_safe(.)) | join("\u001c")
        # SWITCH_VISION_GENERATED_CARD_ROWS_JQ_END
      ' "$CONFIG_FILE" > "$tmp_cards" 2>/dev/null || true

      card_row_separator="$(printf '\034')"
      first_prefix_by_switch=""
      while IFS="$card_row_separator" read -r member_name selected prefix host member_num card_title card_header_title || [ -n "$member_name" ]; do
        [ -n "$member_name" ] || continue
        safe_prefix=$(printf '%s' "$prefix" | tr '[:upper:]' '[:lower:]')
        echo ""
        echo "      - type: custom:switch-vision-3650"
        printf "        title: %s\n" "$(printf '%s' "${card_title:-Switch Vision}" | yaml_quote)"
        printf "        member: %s\n" "$(printf '%s' "$member_name" | yaml_quote)"
        printf "        selected_switch: %s\n" "$(printf '%s' "$member_name" | yaml_quote)"
        printf "        discovery_selected_switch: %s\n" "$(printf '%s' "$selected" | yaml_quote)"
        detected_model=$(model_metadata_for_generated_card "$selected" detected)
        override_model=$(model_metadata_for_generated_card "$selected" override)
        effective_model=$(model_metadata_for_generated_card "$selected" effective)
        if [ -n "$effective_model" ]; then
          printf "        switch_model: %s\n" "$(printf '%s' "$effective_model" | yaml_quote)"
        fi
        emit_generated_card_port_counts "$selected"
        case "${effective_model:-${detected_model:-}}" in
          *Juniper*EX3300-48P*)
            # EX3300 copper interfaces and physical faceplate labels are zero-based.
            # Keep the 48 calibrated positions, but map slot 1..48 to label/entity 0..47.
            echo "        port_label_offset: -1"
            echo "        port_entity_offset: -1"
            ;;
        esac
        if [ -n "$override_model" ]; then
          echo "        model_override: true"
          printf "        detected_switch_model: %s\n" "$(printf '%s' "${detected_model:-unknown}" | yaml_quote)"
          echo "        # Experimental compatibility override selected in Discovery."
        fi
        registry_calibration_profile=$(calibration_profile_for_generated_card "$selected")
        generated_calibration_profile=${registry_calibration_profile:-$member_name}
        printf "        calibration_profile: %s\n" "$(printf '%s' "$generated_calibration_profile" | yaml_quote)"
        echo "        calibration_profile_load: true"
        echo "        calibration_profile_auto_load: true"
        echo "        calibration_button: true"
        echo "        activity_hold_seconds: 12"
        if [ -n "${card_header_title:-}" ]; then
          printf "        card_header_title: %s\n" "$(printf '%s' "$card_header_title" | yaml_quote)"
        fi
        if [ -n "$host" ]; then
          printf "        switch_ip: %s\n" "$(printf '%s' "$host" | yaml_quote)"
          printf "        management_ip: %s\n" "$(printf '%s' "$host" | yaml_quote)"
        fi
        configured_member_count=$(awk -v FS="$card_row_separator" -v sel="$selected" '$2 == sel && $5 != "" { count++ } END { print count+0 }' "$tmp_cards")
        has_primary_member=$(awk -v FS="$card_row_separator" -v sel="$selected" '$2 == sel && $5 == "1" { found=1 } END { print found+0 }' "$tmp_cards")
        if [ -n "$member_num" ] && [ "$configured_member_count" -gt 1 ] && [ "$has_primary_member" -eq 1 ]; then
          # Every card in a confirmed multi-member stack must carry the same
          # stack-enabled state, including member 1.
          echo "        stack_enabled: true"
          echo "        stack_member_number: ${member_num}"
        fi
        if [ -n "$member_num" ] && [ "$member_num" != "1" ] && [ "$configured_member_count" -gt 1 ] && [ "$has_primary_member" -eq 1 ]; then
          # Uptime is stack-wide; inherit member 1 uptime only for an explicitly configured stack.
          first_prefix=$(awk -v FS="$card_row_separator" -v sel="$selected" '$2 == sel && $5 == "1" { print tolower($3); exit }' "$tmp_cards")
          [ -n "$first_prefix" ] || first_prefix="$safe_prefix"
          echo "        stack_uptime_mode: inherit_stack"
          echo "        stack_uptime_source: sensor.${first_prefix}_uptime"
        fi
        echo "        model_entity: sensor.${safe_prefix}_model"
        echo "        os_entity: sensor.${safe_prefix}_system_description"
        case "${effective_model:-${detected_model:-}}" in
          *XS1930-10*) echo "        firmware_entity: sensor.${safe_prefix}_firmware" ;;
          *) echo "        firmware_entity: sensor.${safe_prefix}_system_description" ;;
        esac
        echo "        serial_entity: sensor.${safe_prefix}_serial"
        case "${effective_model:-${detected_model:-}}" in
          *Juniper*EX3300-48P*)
            echo "        cpu_entity: sensor.${safe_prefix}_cpu"
            echo "        temperature_entity: sensor.${safe_prefix}_temperature"
            echo "        fans_entity: sensor.${safe_prefix}_fans"
            echo "        psu_entity: sensor.${safe_prefix}_psu_status"
            ;;
          *XS1930-10*)
            echo "        cpu_entity: sensor.${safe_prefix}_cpu"
            echo "        temperature_entity: sensor.${safe_prefix}_temperature"
            echo "        fans_entity: sensor.${safe_prefix}_fans"
            ;;
          *)
            echo "        cpu_entity: sensor.${safe_prefix}_cpu_5min"
            echo "        temperature_entity: sensor.${safe_prefix}_temperature"
            ;;
        esac
        echo "        poe_used_entity: sensor.${safe_prefix}_poe_used"
        echo "        poe_budget_entity: sensor.${safe_prefix}_poe_budget"
        echo "        status_entity_prefix: sensor.${safe_prefix}_port_"
        echo "        status_entity_suffix: _status"
        case "${effective_model:-${detected_model:-}}" in
          *S5720-12TP-LI-AC*|*WS-C3750-48P*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_1g_{port}_status" ;;
          *) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_10g_{port}_status" ;;
        esac
        emit_generated_port_metadata "$safe_prefix" "$port_mode_metadata"
      done < "$tmp_cards"
    elif truthy "${GENERATED_CARD_SNMP_ENABLED:-false}"; then
      profile="${SELECTED_SWITCH:-${LIVE_SWITCH_LABEL:-SW1}}"
      label="${LIVE_SWITCH_LABEL:-$(lower_value "$profile")}"
      prefix="${DEFAULT_PREFIX:-$label}"
      host="${LIVE_SWITCH_IP:-${DEFAULT_HOST:-}}"
      safe_prefix=$(printf '%s' "$prefix" | tr '[:upper:]' '[:lower:]')
      echo ""
      echo "      - type: custom:switch-vision-3650"
      echo "        title: Switch Vision"
      echo "        member: ${profile}"
      echo "        selected_switch: ${profile}"
      exact_model=$(exact_model_for_generated_card "$profile")
      if [ -n "$exact_model" ]; then
        echo "        switch_model: ${exact_model}"
      fi
      emit_generated_card_port_counts "$profile"
      case "${exact_model:-}" in
        *Juniper*EX3300-48P*)
          echo "        port_label_offset: -1"
          echo "        port_entity_offset: -1"
          ;;
      esac
      registry_calibration_profile=$(calibration_profile_for_generated_card "$profile")
      generated_calibration_profile=${registry_calibration_profile:-$profile}
      echo "        calibration_profile: ${generated_calibration_profile}"
      echo "        calibration_profile_load: true"
      echo "        calibration_button: true"
      echo "        activity_hold_seconds: 12"
      echo "        status_entity_prefix: sensor.${safe_prefix}_port_"
      echo "        status_entity_suffix: _status"
      case "${exact_model:-}" in
        *S5720-12TP-LI-AC*|*WS-C3750-48P*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_1g_{port}_status" ;;
        *) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_10g_{port}_status" ;;
      esac
      emit_generated_port_metadata "$safe_prefix" "$port_mode_metadata"
      if [ -n "$host" ]; then
        echo "        switch_ip: ${host}"
      fi
    fi

    # UniFi2MQTT is an independent normalized discovery source. It does not
    # require a duplicate SNMP target row. Devices with an exact registry match
    # and an available generic visual profile are appended as live cards.
    unifi_snapshot="/share/switch_vision/unifi/devices.json"
    unifi_registry="/opt/switch-vision/devices/supported_devices.json"
    unifi_helper="/unifi_dashboard_cards.py"
    [ -f "$unifi_helper" ] || unifi_helper="$(dirname "$0")/unifi_dashboard_cards.py"
    if [ -f "$unifi_snapshot" ] && [ -f "$unifi_registry" ] && [ -f "$unifi_helper" ]; then
      echo ""
      echo "      # UniFi API devices (Switch Vision UniFi2MQTT)"
      python3 "$unifi_helper" --snapshot "$unifi_snapshot" --registry "$unifi_registry" --indent 6 --summary 2>/dev/null || \
        echo "      # UniFi snapshot was present but could not be converted into dashboard cards."
    fi
  } > "$GENERATED_CARD_PATH"
}

quarantine_invalid_generated_live_yaml() {
  guard="$1"
  GENERATED_YAML_PREVIOUS_STATE="missing"
  [ -f "$GENERATED_YAML_PATH" ] || return 0
  if python3 "$guard" --validate "$GENERATED_YAML_PATH" >/dev/null 2>&1; then
    GENERATED_YAML_PREVIOUS_STATE="valid"
    return 0
  fi
  quarantine_path="${GENERATED_YAML_PATH}.invalid.$(date +%Y%m%dT%H%M%S)"
  if mv "$GENERATED_YAML_PATH" "$quarantine_path"; then
    GENERATED_YAML_PREVIOUS_STATE="quarantined_invalid"
    echo "Invalid previous generated YAML quarantined: $quarantine_path" >> "$LIVE_LOG_PATH" 2>/dev/null || true
  else
    GENERATED_YAML_PREVIOUS_STATE="invalid_quarantine_failed"
    echo "WARNING: invalid previous generated YAML could not be quarantined: $GENERATED_YAML_PATH" >> "$LIVE_LOG_PATH" 2>/dev/null || true
  fi
}

report_generated_yaml_failure_state() {
  case "${GENERATED_YAML_PREVIOUS_STATE:-unknown}" in
    valid) echo "- Previous valid generated YAML preserved unchanged." ;;
    quarantined_invalid) echo "- Previous invalid generated YAML was quarantined; no broken live handoff remains." ;;
    missing) echo "- No live generated YAML is available until a valid generation succeeds." ;;
    invalid_quarantine_failed) echo "- WARNING: previous invalid generated YAML could not be quarantined; review the Discovery log." ;;
    *) echo "- Previous generated YAML state could not be determined; review the Discovery log." ;;
  esac
}

write_generated_yaml() {
  tmp_walks="$1"
  GENERATED_YAML_PUBLISHED="false"
  GENERATED_YAML_GENERATOR_FAILED="false"
  GENERATED_YAML_PREVIOUS_STATE="unknown"
  candidate_path="${GENERATED_YAML_PATH}.candidate.$$"
  guard="/generated_yaml_guard.py"
  [ -f "$guard" ] || guard="$(dirname "$0")/generated_yaml_guard.py"
  echo "Generating SNMP2MQTT YAML candidate: $candidate_path" >> "$LIVE_LOG_PATH" 2>/dev/null || true
  rm -f "$candidate_path"
  {
    echo "# Switch Vision generated SNMP2MQTT YAML"
    echo "# Source: Switch Vision Discovery v$SWITCH_VISION_DISCOVERY_VERSION"
    echo "# Product: Switch Vision"
    echo "# Product source: Switch Vision Discovery v$SWITCH_VISION_DISCOVERY_VERSION"
    echo "# Generated: $(date -Iseconds)"
    echo "# Review before use. This file is not installed automatically."
    echo "# Output path: $GENERATED_YAML_PATH"
    echo "# App/container path: /share/switch_vision"
    echo "# HAOS host/SSH path may appear as: /root/share/switch_vision"
    echo "# Optional per-file mapping: $TARGETS_CSV"
    echo "# CSV format: switch name,switch host,sensor prefix,switch snmp community,output_dir,display name"
    echo "# Polling groups: chunked status 30s, chunked traffic 10s, walk-aware VLAN/trunk 30s, slow system/interface 300s"
    echo "targets:"
    while IFS= read -r walk_file; do
      [ -f "$walk_file" ] || continue
      echo "Generating YAML from: $walk_file" >> "$LIVE_LOG_PATH" 2>/dev/null || true
      target_ip=$(target_for_walk "$walk_file")
      prefix=$(target_prefix_for_walk "$walk_file")
      community=$(target_community_for_walk "$walk_file")
      member_map=$(target_member_map_for_walk "$walk_file")
      if ! write_generated_yaml_for_walk "$walk_file" "$target_ip" "$prefix" "$community" "$member_map"; then
        GENERATED_YAML_GENERATOR_FAILED="true"
        echo "Generated YAML target generation failed for: $walk_file" >> "$LIVE_LOG_PATH" 2>/dev/null || true
      fi
    done < "$tmp_walks"
  } > "$candidate_path"

  if [ "$GENERATED_YAML_GENERATOR_FAILED" = "true" ]; then
    rm -f "$candidate_path"
    if [ -f "$guard" ]; then
      quarantine_invalid_generated_live_yaml "$guard"
    fi
    echo "Generated YAML candidate refused because one or more target generators failed." >> "$LIVE_LOG_PATH" 2>/dev/null || true
    return 0
  fi

  if [ ! -f "$guard" ]; then
    rm -f "$candidate_path"
    echo "Generated YAML candidate refused: semantic guard is missing: $guard" >> "$LIVE_LOG_PATH" 2>/dev/null || true
    return 0
  fi

  if python3 "$guard" --publish "$candidate_path" "$GENERATED_YAML_PATH"; then
    GENERATED_YAML_PUBLISHED="true"
    echo "Generated YAML published atomically: $GENERATED_YAML_PATH" >> "$LIVE_LOG_PATH" 2>/dev/null || true
  else
    guard_status=$?
    rm -f "$candidate_path"
    quarantine_invalid_generated_live_yaml "$guard"
    echo "Generated YAML candidate refused (guard status $guard_status); previous live state: $GENERATED_YAML_PREVIOUS_STATE." >> "$LIVE_LOG_PATH" 2>/dev/null || true
  fi
}

write_report() {
  sv_status "Identifying exact models and interfaces" "All configured switches" "multiple" "Parser and registry lookup" "Reading completed SNMP walk files"
  sv_debug "STAGE: Identifying exact models and interfaces"
  tmp_walks="/tmp/switch_vision_walk_files.txt"
  echo "Post-walk stage: collecting walk files for parse/report" >> "$LIVE_LOG_PATH" 2>/dev/null || true
  collect_multi_walks "$tmp_walks"
  if [ -s "${CURRENT_RUN_WALKS:-/tmp/switch_vision_current_run_walks.txt}" ]; then
    echo "Current-run walks detected; parse_all_walks is ignored for this run" >> "$LIVE_LOG_PATH" 2>/dev/null || true
  fi
  multi_count=$(wc -l < "$tmp_walks" | tr -d ' ')
  echo "Post-walk stage: $multi_count walk file(s) queued for parse" >> "$LIVE_LOG_PATH" 2>/dev/null || true

  # Capability JSON is a generated cache, not an archive. Rebuild it from the
  # source set selected for this run so removed/disabled SNMP switches do not
  # remain visible in Devices or Diagnostics.
  mkdir -p "$CAPABILITIES_DIR"
  rm -f "$CAPABILITIES_DIR"/*-capabilities.json 2>/dev/null || true

  GENERATED_CARD_SNMP_ENABLED="false"
  if [ "$multi_count" -gt 0 ]; then
    GENERATED_CARD_SNMP_ENABLED="true"
  elif legacy_single_walk_allowed; then
    # Legacy single-walk import remains available only through the explicit
    # parse_all_walks opt-in.
    GENERATED_CARD_SNMP_ENABLED="true"
  else
    # No SNMP source was selected for this run. Remove the old generated bridge
    # YAML so it cannot be mistaken for current Discovery output.
    rm -f "$GENERATED_YAML_PATH" 2>/dev/null || true
  fi

  {
    echo "Switch Vision Discovery Parser"
    echo "============================="
    echo ""
    echo "Status: read-only parser"
    echo "Storage path note:"
    echo "- App/container path: /share/switch_vision"
    echo "- HAOS host/SSH path may appear as: /root/share/switch_vision"
    echo "- These refer to the same Home Assistant shared folder when using the HAOS host shell."
    echo "Input path: $INPUT_PATH"
    echo "Walk root: $SNMPWALKS_ROOT_DIR"
    if json_has_configured_switch_rows; then
      echo "Walk folder mode: per switch_name"
    else
      echo "SNMP walks directory: $SNMPWALKS_DIR"
    fi
    echo "Targets CSV: $TARGETS_CSV"
    echo "Current target: ${SELECTED_SWITCH:-not set}"
    if [ -n "${SELECTED_SWITCH:-}" ]; then
      echo "Target mapping matched: $SELECTED_SWITCH_MATCHED"
      echo "Management IP: ${LIVE_SWITCH_IP:-not set}"
      echo "Output folder: ${LIVE_SWITCH_LABEL:-live}"
      echo "Resolved sensor prefix: ${DEFAULT_PREFIX:-auto}"
      echo "Sensor prefix example: $(entity_prefix_example "${DEFAULT_PREFIX:-sw}")"
      echo "Output directory: ${LIVE_OUTPUT_DIR:-not set}"
      if [ "$SELECTED_SWITCH_MATCHED" != "yes" ]; then
        echo "Available switches: ${SELECTED_SWITCH_AVAILABLE:-none}"
      fi
    fi
    echo "Parse all walks: $PARSE_ALL_WALKS"
    echo "SNMP2MQTT generator enabled: $GENERATE_SNMP2MQTT"
    echo "Generated YAML path: $GENERATED_YAML_PATH"
    echo "Generated dashboard card path: $GENERATED_CARD_PATH"
    echo "SNMP walks enabled: $RUN_LIVE_SNMPWALK"
    echo "Multi-switch walks enabled: $MULTI_SWITCH_WALKS_ENABLED"
    echo "SNMP walk mode: $LIVE_SNMPWALK_MODE"
    if json_has_configured_switch_rows; then
      echo "Management IP: per switch row"
      echo "Output folder: derived from switch_name"
      echo "Resolved SNMP community: per switch row"
      echo "Clean output before walk: $LIVE_CLEAN_OUTPUT_BEFORE_WALK"
      echo "Current output path: per-switch under $SNMPWALKS_ROOT_DIR"
    else
      echo "Management IP: ${LIVE_SWITCH_IP:-not set}"
      echo "Output folder: ${LIVE_SWITCH_LABEL:-live}"
      echo "Resolved SNMP community: $(mask_value "$LIVE_SNMP_COMMUNITY")"
      echo "Clean output before walk: $LIVE_CLEAN_OUTPUT_BEFORE_WALK"
      echo "Current output path: $LIVE_OUTPUT_PATH"
    fi
    echo "SNMP log path: $LIVE_LOG_PATH"
    echo "Report path: $REPORT_PATH"
    echo "Discovery app loaded: $DISCOVERY_STARTED_ISO"
    echo "Generated: $(date -Iseconds)"
    echo ""

    write_live_summary_if_present

    if [ "$multi_count" -gt 0 ]; then
      echo "Multi-walk mode: yes"
      echo "Walk files found: $multi_count"
      echo ""
      i=0
      while IFS= read -r walk_file; do
        i=$((i + 1))
        base=$(basename "$walk_file")
        echo "Parsing walk file $i/$multi_count: $walk_file" >> "$LIVE_LOG_PATH" 2>/dev/null || true
        write_walk_section "$walk_file" "Device $i: $base"
      done < "$tmp_walks"
      if [ "$GENERATE_SNMP2MQTT" = "true" ]; then
        echo "Generated YAML summary"
        echo "----------------------"
        if generator_has_unknown_targets "$tmp_walks"; then
          rm -f "$GENERATED_YAML_PATH"
          echo "- FAIL: generated YAML not written because one or more management targets are unknown."
          echo "- Add a valid switch_host to the switch list or targets CSV, then restart Discovery."
          echo "- Generated file: not written"
        else
          sv_status "Generating SNMP2MQTT YAML" "All discovered switches" "multiple" "write_generated_yaml" "Creating generated-snmp2mqtt.yaml"
          sv_debug "STAGE: Generating SNMP2MQTT YAML"
          sv_status "Generating SNMP2MQTT YAML" "Selected switch" "${LIVE_SWITCH_IP:-not set}" "write_generated_yaml" "Creating generated-snmp2mqtt.yaml"
          sv_debug "STAGE: Generating SNMP2MQTT YAML"
          write_generated_yaml "$tmp_walks"
          if [ "${GENERATED_YAML_PUBLISHED:-false}" = "true" ]; then
            echo "- Generated file: $GENERATED_YAML_PATH"
            echo "- Validation: PASS (non-empty target list); published atomically."
          else
            echo "- FAIL: generated YAML candidate did not contain a valid non-empty target list."
            report_generated_yaml_failure_state
          fi
          echo "- Review-only output; it has not been installed."
          echo "- Polling groups: chunked status 30s, chunked traffic 10s, walk-aware VLAN/trunk 30s, slow system/interface 300s"
          if grep -q "CHANGE_ME" "$GENERATED_YAML_PATH" 2>/dev/null; then
            echo "- FAIL: CHANGE_ME found in generated YAML; do not use this file."
          elif grep -q "Temperature HotSpot" "$GENERATED_YAML_PATH" 2>/dev/null; then
            echo "- WARN: HotSpot duplicate labels found; review generated YAML."
          else
            echo "- PASS: duplicate HotSpot/Temperature labels avoided."
            echo "- PASS: all generated YAML targets have management hosts."
            echo "- PASS: VLAN ID sensors are walk-aware; missing VLAN OIDs are skipped."
          fi
        fi
        echo ""
      fi
      echo "Overall summary"
      echo "---------------"
      echo "- Multi-walk parser completed. Review each device section above."
      echo "- Ready checks and interface mapping are shown per device."
      echo "- SNMP2MQTT generator status: $GENERATE_SNMP2MQTT (review-only; no automatic install)."
      echo "- Report is read-only. No Home Assistant, MQTT, SNMP2MQTT, or dashboard files are changed."
    elif legacy_single_walk_allowed; then
      echo "Multi-walk mode: no"
      echo ""
      write_walk_section "$INPUT_PATH" "Single walk: $(basename "$INPUT_PATH")"
      if [ "$GENERATE_SNMP2MQTT" = "true" ]; then
        printf '%s
' "$INPUT_PATH" > "$tmp_walks"
        echo "Generated YAML summary"
        echo "----------------------"
        if generator_has_unknown_targets "$tmp_walks"; then
          rm -f "$GENERATED_YAML_PATH"
          echo "- FAIL: generated YAML not written because the management target is unknown."
          echo "- Add a valid switch_host to the switch list or targets CSV, then restart Discovery."
          echo "- Generated file: not written"
        else
          write_generated_yaml "$tmp_walks"
          if [ "${GENERATED_YAML_PUBLISHED:-false}" = "true" ]; then
            echo "- Generated file: $GENERATED_YAML_PATH"
            echo "- Validation: PASS (non-empty target list); published atomically."
          else
            echo "- FAIL: generated YAML candidate did not contain a valid non-empty target list."
            report_generated_yaml_failure_state
          fi
          echo "- Review-only output; it has not been installed."
        fi
        echo ""
      fi
    else
      echo "Multi-walk mode: no"
      echo "SNMP source active for this run: no"
      echo ""
      echo "Historical SNMP walks were ignored."
      echo "- New walks are used only when Run SNMP Walks creates them in this run."
      echo "- Stored/offline walks are parsed only when parse_all_walks is explicitly enabled."
      echo "- UniFi API devices remain independent and can still generate dashboard cards."
      echo ""
      echo "Generated SNMP2MQTT YAML: removed/not generated for this run."
    fi
  } > "$REPORT_PATH"
  echo "Report written: $REPORT_PATH" >> "$LIVE_LOG_PATH" 2>/dev/null || true

  # Dashboard generation is source-independent. SNMP cards are included only
  # when this run selected SNMP data; UniFi API cards can be generated alone.
  sv_status "Generating dashboard card YAML" "Current discovery sources" "multiple" "write_generated_dashboard_card" "Creating generated-dashboard-card.yaml"
  sv_debug "STAGE: Generating dashboard card YAML"
  write_generated_dashboard_card
  {
    echo ""
    echo "Generated dashboard card summary"
    echo "--------------------------------"
    echo "- Generated file: $GENERATED_CARD_PATH"
    echo "- SNMP cards included: $GENERATED_CARD_SNMP_ENABLED"
    if [ -f /share/switch_vision/unifi/devices.json ]; then
      echo "- UniFi API snapshot: available"
    else
      echo "- UniFi API snapshot: not available"
    fi
    echo "- Review/copy only; it has not been installed."
  } >> "$REPORT_PATH"
}


write_last_run_summary() {
  {
    summary_generated_iso=$(date -Iseconds)
    summary_duration=$(( $(now_epoch) - DISCOVERY_STARTED_EPOCH ))
    echo "Switch Vision Discovery last run"
    echo "Discovery app loaded: $DISCOVERY_STARTED_ISO"
    echo "Generated: $summary_generated_iso"
    echo "Discovery runtime so far: $(format_duration "$summary_duration")"
    if json_has_configured_switch_rows; then
      echo "Switch-list mode: enabled"
      echo "Current target: switch list"
      echo "Target mapping matched: switch-list rows"
      echo "Walk mode: per-switch"
      echo "SNMP walks enabled: $RUN_LIVE_SNMPWALK"
      echo "Multi-switch walks enabled: $MULTI_SWITCH_WALKS_ENABLED"
      echo "Management IP: per switch row"
      echo "Output folder: per switch row"
      echo "Sensor prefix: per switch row / stack_member_prefixes"
      echo "Output: per switch folder under $SNMPWALKS_ROOT_DIR"
    else
      echo "Current target: ${SELECTED_SWITCH:-not set}"
      echo "Target mapping matched: $SELECTED_SWITCH_MATCHED"
      echo "Walk mode: $LIVE_SNMPWALK_MODE"
      echo "SNMP walks enabled: $RUN_LIVE_SNMPWALK"
      echo "Multi-switch walks enabled: $MULTI_SWITCH_WALKS_ENABLED"
      echo "Management IP: ${LIVE_SWITCH_IP:-not set}"
      echo "Output folder: ${LIVE_SWITCH_LABEL:-live}"
        echo "Sensor prefix example: $(entity_prefix_example "${DEFAULT_PREFIX:-sw}")"
      echo "Output: $LIVE_OUTPUT_PATH"
    fi
    echo "Walk directory: $SNMPWALKS_DIR"
    echo "Report: $REPORT_PATH"
    echo "Generated YAML: $GENERATED_YAML_PATH"
    echo "Generated dashboard card: $GENERATED_CARD_PATH"
    if [ -f /tmp/switch_vision_live_walk_summary.txt ]; then
      echo ""
      cat /tmp/switch_vision_live_walk_summary.txt
    fi
  } > "$LAST_RUN_SUMMARY_PATH"
}

run_live_snmpwalk_if_enabled
if [ "${POST_WALK_ALREADY_DONE:-false}" != "true" ]; then
  echo "Post-walk execution: running standard parser/generator path" >> "$LIVE_LOG_PATH" 2>/dev/null || true
  if json_has_enabled_switch_rows; then
    build_runtime_multi_switch_targets_csv
  fi
  write_report
  write_last_run_summary
else
  echo "Post-walk execution: already completed after switch-list walk" >> "$LIVE_LOG_PATH" 2>/dev/null || true
fi
cat "$REPORT_PATH"
echo ""
GENERATE_SUPPORT_MY_SWITCH_BUNDLE=$(json_get generate_support_my_switch_bundle "false")
if [ "$GENERATE_SUPPORT_MY_SWITCH_BUNDLE" = "true" ]; then
  echo "Support My Switch: preparing contribution bundle..."
  SUPPORT_MASK_MANAGEMENT_IPS=$(json_get support_mask_management_ips "true")
  SUPPORT_MASK_MAC_ADDRESSES=$(json_get support_mask_mac_addresses "true")
  SUPPORT_MASK_HOSTNAMES=$(json_get support_mask_hostnames "true")
  SUPPORT_MASK_VLAN_NAMES=$(json_get support_mask_vlan_names "false")
  SUPPORT_MASK_INTERFACE_DESCRIPTIONS=$(json_get support_mask_interface_descriptions "false")
  SUPPORT_CONTRIBUTOR_TYPE=$(json_get support_contributor_type "anonymous")
  SUPPORT_CONTRIBUTOR_VALUE=$(json_get support_contributor_value "")
  SWITCH_VISION_DISCOVERY_VERSION="$SWITCH_VISION_DISCOVERY_VERSION" \
    SUPPORT_MASK_MANAGEMENT_IPS="$SUPPORT_MASK_MANAGEMENT_IPS" \
    SUPPORT_MASK_MAC_ADDRESSES="$SUPPORT_MASK_MAC_ADDRESSES" \
    SUPPORT_MASK_HOSTNAMES="$SUPPORT_MASK_HOSTNAMES" \
    SUPPORT_MASK_VLAN_NAMES="$SUPPORT_MASK_VLAN_NAMES" \
    SUPPORT_MASK_INTERFACE_DESCRIPTIONS="$SUPPORT_MASK_INTERFACE_DESCRIPTIONS" \
    SUPPORT_CONTRIBUTOR_TYPE="$SUPPORT_CONTRIBUTOR_TYPE" \
    SUPPORT_CONTRIBUTOR_VALUE="$SUPPORT_CONTRIBUTOR_VALUE" \
    /support_my_switch.sh
  echo ""
fi
sv_status "Complete" "All configured switches" "complete" "" "Discovery complete"
sv_debug "STAGE: Discovery complete"
echo "Switch Vision Discovery run complete. Web UI remains available."
