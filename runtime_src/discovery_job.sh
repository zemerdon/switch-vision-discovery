#!/usr/bin/env sh
set -eu

SWITCH_VISION_DISCOVERY_VERSION="3.0.11"
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
GENERATED_CARD_FULL_PATH="${SWITCH_VISION_GENERATED_CARD_FULL_PATH:-}"
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
DISCOVERY_STARTED_ISO="${SWITCH_VISION_DISCOVERY_STARTED_ISO:-$(date -Iseconds)}"
DISCOVERY_STARTED_EPOCH="${SWITCH_VISION_DISCOVERY_STARTED_EPOCH:-$(date +%s)}"
COLLECTION_ONLY="${SWITCH_VISION_COLLECTION_ONLY:-false}"
CURRENT_RUN_WALKS="${SWITCH_VISION_CURRENT_RUN_WALKS:-/tmp/switch_vision_current_run_walks_$$.txt}"
CURRENT_RUN_TARGETS="${SWITCH_VISION_CURRENT_RUN_TARGETS:-/tmp/switch_vision_current_run_targets_$$.txt}"
LIVE_WALK_SUMMARY="/tmp/switch_vision_live_walk_summary_$$.txt"
LIVE_WALK_SUMMARY_ALL="/tmp/switch_vision_live_walk_summary_all_$$.txt"
SNMP_PRECHECK_PATH="/tmp/switch_vision_snmp_precheck_$$.txt"
RUNTIME_CSV_HAS_ROWS="/tmp/switch_vision_runtime_csv_has_rows_$$"
MULTI_COUNT_FILE="/tmp/switch_vision_multi_count_$$"
MULTI_PASS_FILE="/tmp/switch_vision_multi_pass_$$"
MULTI_WARN_FILE="/tmp/switch_vision_multi_warn_$$"
MULTI_FAIL_FILE="/tmp/switch_vision_multi_fail_$$"
GENERATED_CARD_FALLBACK_WALKS=""
UNIFI_BOUND_IDS=""
CAPABILITIES_DIR="${SWITCH_VISION_CAPABILITIES_DIR:-/share/switch_vision/capabilities}"
POST_WALK_ALREADY_DONE="false"
GENERATED_CARD_SNMP_ENABLED="false"
DISCOVERY_EXIT_STATUS="0"

cleanup_discovery_scratch() {
  rm -f \
    "/tmp/switch_vision_current_run_walks_$$.txt" \
    "/tmp/switch_vision_current_run_targets_$$.txt" \
    "/tmp/switch_vision_multi_switch_targets_$$.csv" \
    "/tmp/switch_vision_stack_member_map_$$.csv" \
    "/tmp/switch_vision_dashboard_mode_walks_$$.txt" \
    "/tmp/switch_vision_generated_port_modes_$$.tsv" \
    "/tmp/switch_vision_generated_card_rows_$$.tsv" \
    "/tmp/switch_vision_generated_dashboard_raw_$$.yaml" \
    "/tmp/switch_vision_walk_files_$$.txt" \
    "$LIVE_WALK_SUMMARY" \
    "$LIVE_WALK_SUMMARY_ALL" \
    "$SNMP_PRECHECK_PATH" \
    "$RUNTIME_CSV_HAS_ROWS" \
    "$MULTI_COUNT_FILE" \
    "$MULTI_PASS_FILE" \
    "$MULTI_WARN_FILE" \
    "$MULTI_FAIL_FILE" \
    /tmp/switch_vision_generator_raw_$$.yaml 2>/dev/null || true
  if [ -n "${GENERATED_CARD_FALLBACK_WALKS:-}" ]; then
    rm -f "$GENERATED_CARD_FALLBACK_WALKS" 2>/dev/null || true
  fi
  if [ -n "${UNIFI_BOUND_IDS:-}" ]; then
    rm -f "$UNIFI_BOUND_IDS" 2>/dev/null || true
  fi
}
trap cleanup_discovery_scratch EXIT

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
RUNTIME_DIR="${SWITCH_VISION_RUNTIME_DIR:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)}"
REGISTRY_LOOKUP="${SWITCH_VISION_REGISTRY_LOOKUP:-/registry_lookup.py}"
DEVICE_REGISTRY="${SWITCH_VISION_DEVICE_REGISTRY:-/opt/switch-vision/devices/supported_devices.json}"
if [ ! -f "$REGISTRY_LOOKUP" ] && [ -f "$RUNTIME_DIR/registry_lookup.py" ]; then
  REGISTRY_LOOKUP="$RUNTIME_DIR/registry_lookup.py"
fi
if [ ! -f "$DEVICE_REGISTRY" ] && [ -f "$RUNTIME_DIR/opt/switch-vision/devices/supported_devices.json" ]; then
  DEVICE_REGISTRY="$RUNTIME_DIR/opt/switch-vision/devices/supported_devices.json"
fi
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
if [ -z "${GENERATED_CARD_FULL_PATH:-}" ]; then
  case "$GENERATED_CARD_PATH" in
    *.yaml) GENERATED_CARD_FULL_PATH="${GENERATED_CARD_PATH%.yaml}.full.yaml" ;;
    *) GENERATED_CARD_FULL_PATH="${GENERATED_CARD_PATH}.full" ;;
  esac
fi
GENERATED_CARD_FULL_PATH=$(printf '%s' "$GENERATED_CARD_FULL_PATH" | sed 's#//*#/#g')
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
mkdir -p "$REPORT_DIR" "${SWITCH_VISION_SHARE_DIR:-/share/switch_vision}" "$CAPABILITIES_DIR" "$SNMPWALKS_DIR" "$(dirname "$GENERATED_YAML_PATH")" "$(dirname "$GENERATED_CARD_PATH")" "$(dirname "$GENERATED_CARD_FULL_PATH")" "$(dirname "$LIVE_LOG_PATH")"
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
SELECTED_SWITCH_RESOLVED_HOST=""
SELECTED_SWITCH_RESOLVED_LABEL=""
SELECTED_SWITCH_RESOLVED_PREFIX=""
SELECTED_SWITCH_RESOLVED_COMMUNITY=""
SELECTED_SWITCH_RESOLVED_OUTPUT_DIR=""

reset_selected_switch_resolution() {
  SELECTED_SWITCH_MATCHED="no"
  SELECTED_SWITCH_AVAILABLE=""
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

target_switch_for_walk() {
  walk_file="$1"

  if current_switch=$(current_run_target_field_for_walk "$walk_file" switch 2>/dev/null) && [ -n "$current_switch" ]; then
    printf '%s' "$current_switch"
    return 0
  fi

  if [ -f "$TARGETS_CSV" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      name=$(csv_field "$line" 1)
      [ -n "$name" ] || continue
      case "$name" in \#*) continue ;; esac
      if is_targets_csv_header "$name"; then
        continue
      fi
      if csv_row_matches_walk "$line" "$walk_file"; then
        printf '%s' "$name"
        return 0
      fi
    done < "$TARGETS_CSV"
  fi

  parent=$(basename "$(dirname "$walk_file")")
  if [ -n "$parent" ] && [ "$parent" != "." ] && [ "$parent" != "/" ]; then
    printf '%s' "$parent"
    return 0
  fi

  strip_walk_ext "$(basename "$walk_file")"
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

. "$RUNTIME_DIR/discovery_report_stage.sh"



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
  original_summary="${SWITCH_VISION_ORIGINAL_LIVE_WALK_SUMMARY:-}"
  if [ -n "$original_summary" ] && [ -f "$original_summary" ]; then
    cat "$original_summary"
    echo ""
  elif [ -f "$LIVE_WALK_SUMMARY" ]; then
    cat "$LIVE_WALK_SUMMARY"
    echo ""
  elif truthy "${SWITCH_VISION_ORIGINAL_RUN_SNMP_WALKS:-$RUN_LIVE_SNMPWALK}"; then
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
    } > "$LIVE_WALK_SUMMARY"
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
  if snmpwalk -On -v2c -c "$LIVE_SNMP_COMMUNITY" -t "$LIVE_SNMP_TIMEOUT" -r "$LIVE_SNMP_RETRIES" "$LIVE_SWITCH_IP" 1.3.6.1.2.1.1.1.0 >"$SNMP_PRECHECK_PATH" 2>> "$LIVE_LOG_PATH"; then
    pre_lines=$(walk_line_count "$SNMP_PRECHECK_PATH")
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
    if grep -qi "Juniper" "$SNMP_PRECHECK_PATH" 2>/dev/null; then
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
    # Targeted discovery OID trees. Prefer broad, standards-based evidence so
    # newly contributed hardware arrives with useful identity, topology,
    # telemetry and PoE context even before a vendor profile exists. Vendor
    # enterprise supplements remain deliberately narrow below; do not replace
    # this with an uncontrolled private-enterprise-tree walk.
    LIVE_OIDS="
1.3.6.1.2.1.1
1.3.6.1.2.1.2.2.1
1.3.6.1.2.1.31.1.1.1
1.3.6.1.2.1.10.7
1.3.6.1.2.1.26
1.3.6.1.2.1.17.1.1
1.3.6.1.2.1.17.1.4.1.2
1.3.6.1.2.1.17.7.1.4.3
1.3.6.1.2.1.17.7.1.4.5.1.1
1.3.6.1.2.1.25.3.3.1.2
1.3.6.1.2.1.47.1.1.1.1
1.3.6.1.2.1.99.1.1.1
1.3.6.1.2.1.105.1.1.1
1.3.6.1.2.1.105.1.3.1
1.3.6.1.4.1.9.2.1.3
1.3.6.1.4.1.9.9.13.1.3.1
1.3.6.1.4.1.9.9.13.1.4.1
1.3.6.1.4.1.9.9.13.1.5.1
1.3.6.1.4.1.9.9.68.1.2.2.1.2
1.3.6.1.4.1.9.9.46.1.3.1.1.4
1.3.6.1.4.1.9.9.46.1.6.1.1.13
1.3.6.1.4.1.9.9.46.1.6.1.1.14
1.3.6.1.4.1.9.9.109.1.1.1.1
1.3.6.1.4.1.9.9.402.1.2.1
1.3.6.1.4.1.9.9.402.1.3.1
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
  if grep -qi "Juniper" "$SNMP_PRECHECK_PATH" 2>/dev/null; then
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

  # MikroTik supplemental telemetry is intentionally narrow. Never walk the
  # complete 14988 enterprise tree because RouterOS exposes unrelated/private
  # objects there; collect only standard CPU/sensor tables plus known health
  # and PoE-Out subtrees for review.
  if grep -Eqi 'MikroTik|RouterOS|CRS328-24P-4S\+' "$SNMP_PRECHECK_PATH" 2>/dev/null; then
    MIKROTIK_SUPPLEMENTAL_OIDS="
1.3.6.1.2.1.25.3.3.1.2
1.3.6.1.2.1.99.1.1.1
1.3.6.1.4.1.14988.1.1.3
1.3.6.1.4.1.14988.1.1.15.1.1
"
    echo "Running MikroTik supplemental telemetry walks" >> "$LIVE_LOG_PATH"
    for oid in $MIKROTIK_SUPPLEMENTAL_OIDS; do
      current_command="snmpwalk -On -v2c -c ******** -t $LIVE_SNMP_TIMEOUT -r $LIVE_SNMP_RETRIES $LIVE_SWITCH_IP $oid"
      echo "Running supplemental: $current_command" >> "$LIVE_LOG_PATH"
      {
        echo ""
        echo "# --- MikroTik supplemental: $oid ---"
      } >> "$LIVE_OUTPUT_PATH"
      if snmpwalk -On -v2c -c "$LIVE_SNMP_COMMUNITY" -t "$LIVE_SNMP_TIMEOUT" -r "$LIVE_SNMP_RETRIES" "$LIVE_SWITCH_IP" "$oid" >> "$LIVE_OUTPUT_PATH" 2>> "$LIVE_LOG_PATH"; then
        echo "OK supplemental: $oid" >> "$LIVE_LOG_PATH"
      else
        echo "INFO: MikroTik supplemental OID unavailable: $oid" >> "$LIVE_LOG_PATH"
      fi
    done
  fi

  # Dell N2128PX-ON transceiver diagnostics live under a narrow enterprise
  # table that is not part of the standards-based targeted walk set. Full mode
  # already walks from root OID 1; targeted mode explicitly adds only the two
  # reviewed DDMI/identity subtrees proven by current hardware evidence.
  if [ "$LIVE_SNMPWALK_MODE" != "full" ] && grep -Eqi 'N2128PX-ON' "$SNMP_PRECHECK_PATH" 2>/dev/null; then
    DELL_N2128_OPTICAL_OIDS="
1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.18
1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.19
"
    echo "Running Dell N2128PX-ON optical supplemental walks" >> "$LIVE_LOG_PATH"
    for oid in $DELL_N2128_OPTICAL_OIDS; do
      current_command="snmpwalk -On -v2c -c ******** -t $LIVE_SNMP_TIMEOUT -r $LIVE_SNMP_RETRIES $LIVE_SWITCH_IP $oid"
      echo "Running supplemental: $current_command" >> "$LIVE_LOG_PATH"
      {
        echo ""
        echo "# --- Dell N2128PX-ON optical supplemental: $oid ---"
      } >> "$LIVE_OUTPUT_PATH"
      if snmpwalk -On -v2c -c "$LIVE_SNMP_COMMUNITY" -t "$LIVE_SNMP_TIMEOUT" -r "$LIVE_SNMP_RETRIES" "$LIVE_SWITCH_IP" "$oid" >> "$LIVE_OUTPUT_PATH" 2>> "$LIVE_LOG_PATH"; then
        echo "OK supplemental: $oid" >> "$LIVE_LOG_PATH"
      else
        echo "INFO: Dell N2128PX-ON optical OID unavailable: $oid" >> "$LIVE_LOG_PATH"
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
  runtime_csv="/tmp/switch_vision_multi_switch_targets_$$.csv"
  stack_map_csv="/tmp/switch_vision_stack_member_map_$$.csv"
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
        echo 1 > "$RUNTIME_CSV_HAS_ROWS"
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
  if [ -f "$RUNTIME_CSV_HAS_ROWS" ]; then
    rm -f "$RUNTIME_CSV_HAS_ROWS"
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
    } > "$LIVE_WALK_SUMMARY"
    return 0
  fi

  multi_started_iso=$(date -Iseconds)
  multi_started_epoch=$(now_epoch)
  : > "$LIVE_WALK_SUMMARY_ALL"
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

  rm -f "$MULTI_COUNT_FILE" "$MULTI_PASS_FILE" "$MULTI_WARN_FILE" "$MULTI_FAIL_FILE"
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

    count_file="$MULTI_COUNT_FILE"
    pass_file="$MULTI_PASS_FILE"
    warn_file="$MULTI_WARN_FILE"
    fail_file="$MULTI_FAIL_FILE"
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

    if [ -f "$LIVE_WALK_SUMMARY" ]; then
      cat "$LIVE_WALK_SUMMARY" >> "$LIVE_WALK_SUMMARY_ALL"
      echo "" >> "$LIVE_WALK_SUMMARY_ALL"
      if grep -q "SNMP walk result: PASS" "$LIVE_WALK_SUMMARY"; then
        n=$(( $(cat "$pass_file") + 1 )); echo "$n" > "$pass_file"
      elif grep -q "SNMP walk result: WARN" "$LIVE_WALK_SUMMARY"; then
        n=$(( $(cat "$warn_file") + 1 )); echo "$n" > "$warn_file"
      else
        n=$(( $(cat "$fail_file") + 1 )); echo "$n" > "$fail_file"
      fi
    fi
  done

  count=$(cat "$MULTI_COUNT_FILE" 2>/dev/null || echo 0)
  pass_count=$(cat "$MULTI_PASS_FILE" 2>/dev/null || echo 0)
  warn_count=$(cat "$MULTI_WARN_FILE" 2>/dev/null || echo 0)
  fail_count=$(cat "$MULTI_FAIL_FILE" 2>/dev/null || echo 0)
  rm -f "$MULTI_COUNT_FILE" "$MULTI_PASS_FILE" "$MULTI_WARN_FILE" "$MULTI_FAIL_FILE"

  # Fail closed if a configured row somehow completed without a PASS/WARN/FAIL
  # classification. A target that was not positively classified can never be
  # promoted into current-run parsing.
  classified_count=$((pass_count + warn_count + fail_count))
  if [ "$classified_count" -lt "$count" ]; then
    fail_count=$((fail_count + count - classified_count))
  fi
  useful_count=$((pass_count + warn_count))
  multi_result="completed"
  multi_status=0
  if [ "$fail_count" -gt 0 ]; then
    if [ "$useful_count" -gt 0 ]; then
      multi_result="PARTIAL"
      multi_status=11
    elif [ "$count" -gt 0 ]; then
      multi_result="FAILED"
      multi_status=2
    fi
  fi

  multi_completed_iso=$(date -Iseconds)
  multi_duration=$(( $(now_epoch) - multi_started_epoch ))
  {
    echo "Switch-list SNMP walk result: $multi_result"
    echo "- Started: $multi_started_iso"
    echo "- Completed: $multi_completed_iso"
    echo "- Duration: $(format_duration "$multi_duration")"
    echo "- Switches walked: $count"
    echo "- PASS: $pass_count"
    echo "- WARN: $warn_count"
    echo "- FAIL/SKIP: $fail_count"
    echo "- SNMP walks root: $SNMPWALKS_ROOT_DIR"
    echo ""
    cat "$LIVE_WALK_SUMMARY_ALL" 2>/dev/null || true
  } > "$LIVE_WALK_SUMMARY"
  {
    echo ""
    echo "Switch-list completed: $multi_completed_iso"
    echo "Switch-list result: $multi_result"
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
  return "$multi_status"
}

run_live_snmpwalk_if_enabled() {
  rm -f "$LIVE_WALK_SUMMARY" "$LIVE_WALK_SUMMARY_ALL" "$CURRENT_RUN_WALKS" "$CURRENT_RUN_TARGETS"
  : > "$CURRENT_RUN_WALKS"
  : > "$CURRENT_RUN_TARGETS"
  if ! truthy "$RUN_LIVE_SNMPWALK"; then
    return 0
  fi
  # A switch-list return code is a collection classification, not permission
  # to skip the safe report/generation phase. Preserve PARTIAL (11) and hard
  # all-target failure (2) until that phase finishes; 1 remains the internal
  # "switch-list mode not enabled" sentinel for the legacy single-target path.
  multi_status=0
  run_multi_switch_walks_if_enabled || multi_status=$?
  case "$multi_status" in
    0|11|2)
      {
        echo ""
        echo "Post-walk execution: switch-list walk complete"
        echo "Post-walk execution: current-run walk list: ${CURRENT_RUN_WALKS:-/tmp/switch_vision_current_run_walks_$$.txt}"
      } >> "$LIVE_LOG_PATH" 2>/dev/null || true
      # The physical-contract wrapper uses collection-only mode for the first
      # phase. In that mode, stop after live evidence collection so model parsing,
      # card generation and last-run reporting happen exactly once after the
      # current-run physical contracts have been validated.
      if truthy "$COLLECTION_ONLY"; then
        echo "Post-walk execution: collection-only mode; parser/generator deferred to physical-contract authority" >> "$LIVE_LOG_PATH" 2>/dev/null || true
        POST_WALK_ALREADY_DONE="true"
        if [ "$multi_status" -ne 0 ]; then
          DISCOVERY_EXIT_STATUS="$multi_status"
        fi
        return 0
      fi

      # Legacy/direct execution still owns its complete post-walk path.
      # Failed targets were never queued, and the user's stored-walk preference
      # has already been restored.
      write_report
      write_last_run_summary
      POST_WALK_ALREADY_DONE="true"
      if [ "$multi_status" -ne 0 ]; then
        DISCOVERY_EXIT_STATUS="$multi_status"
      fi
      return 0
      ;;
    1)
      : # Multi-switch mode is disabled; continue with legacy single-target mode.
      ;;
    *)
      return "$multi_status"
      ;;
  esac

  LIVE_LOG_APPEND="false"
  run_live_snmpwalk_current
}

collect_multi_walks() {
  tmp_file="$1"
  : > "$tmp_file"

  # v0.7.12: after switch-list SNMP walks, parse only the walk files created in
  # this app run. This prevents old full walks or stale failed files under
  # /share/switch_vision/snmpwalks from making the post-walk stage appear stuck.
  if [ -s "${CURRENT_RUN_WALKS:-/tmp/switch_vision_current_run_walks_$$.txt}" ]; then
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
  stack_map_csv="/tmp/switch_vision_stack_member_map_$$.csv"
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

. "$RUNTIME_DIR/discovery_yaml_stage.sh"

walk_model_for_generated_card() {
  selected_name="$1"
  [ -n "$selected_name" ] || return 0
  tmp_walks="/tmp/switch_vision_card_model_walks_$$.txt"
  collect_multi_walks "$tmp_walks"
  while IFS= read -r walk_file; do
    [ -f "$walk_file" ] || continue
    walk_switch=$(target_switch_for_walk "$walk_file")
    [ "$walk_switch" = "$selected_name" ] || continue
    if command -v cv_cap_extract_model_text >/dev/null 2>&1; then
      cv_cap_extract_model_text "$walk_file"
    else
      grep -Eio 'N4032F|N2128PX-ON|3524GT-PWR\+|HP J9774A 2530-8G-PoEP|J9774A|HP J8693A Switch 3500yl-48G' "$walk_file" 2>/dev/null | head -n 1 || true
    fi
    rm -f "$tmp_walks"
    return 0
  done < "$tmp_walks"
  rm -f "$tmp_walks"
}

model_metadata_for_generated_card() {
  selected_name="$1"
  field="$2"
  [ -n "$selected_name" ] || return 0
  safe_name=$(printf '%s' "$selected_name" | sed 's/[^A-Za-z0-9._-]/_/g')
  cap_file="$CAPABILITIES_DIR/${safe_name}-capabilities.json"
  value=""
  if [ -f "$cap_file" ]; then
    value=$(jq -r --arg field "$field" '
      if $field == "detected" then (.device.detected_model_text // .device.model_text // empty)
      elif $field == "override" then (.device.model_override // empty)
      elif $field == "effective" then (.device.effective_model_text // .device.model_text // empty)
      else empty end
    ' "$cap_file" 2>/dev/null | awk 'NF && $0 != "unknown" { print; exit }')
  fi
  if [ -z "$value" ] && { [ "$field" = "detected" ] || [ "$field" = "effective" ]; }; then
    value=$(walk_model_for_generated_card "$selected_name")
  fi
  [ -n "$value" ] && printf '%s\n' "$value"
  return 0
}

exact_model_for_generated_card() {
  model_metadata_for_generated_card "$1" effective
}

device_mac_for_generated_card() {
  selected_name="$1"
  [ -n "$selected_name" ] || return 0
  safe_name=$(printf '%s' "$selected_name" | sed 's/[^A-Za-z0-9._-]/_/g')
  cap_file="$CAPABILITIES_DIR/${safe_name}-capabilities.json"
  [ -f "$cap_file" ] || return 0
  jq -r '.device.mac_address // empty' "$cap_file" 2>/dev/null | awk 'NF && $0 != "null" { print; exit }'
}

calibration_profile_for_generated_card() {
  selected_name="$1"
  [ -n "$selected_name" ] || return 0
  safe_name=$(printf '%s' "$selected_name" | sed 's/[^A-Za-z0-9._-]/_/g')
  cap_file="$CAPABILITIES_DIR/${safe_name}-capabilities.json"
  if [ -f "$cap_file" ]; then
    value=$(jq -r '
      if ((.device.model_override // "") | length) > 0 then
        (.model_override_registry.calibration_profile // .registry.calibration_profile // empty)
      else
        (.registry.calibration_profile // empty)
      end
    ' "$cap_file" 2>/dev/null | awk 'NF && $0 != "null" { print; exit }')
    [ -n "$value" ] && { printf '%s\n' "$value"; return 0; }
  fi
  model=$(exact_model_for_generated_card "$selected_name")
  [ -n "$model" ] && [ -f "$DEVICE_REGISTRY" ] || return 0
  jq -r --arg model "$model" '
    first(.devices[]? | select((.model // "") == $model) | .calibration_profile // empty)
  ' "$DEVICE_REGISTRY" 2>/dev/null | awk 'NF && $0 != "null" { print; exit }'
}

frontend_hold_for_generated_card() {
  selected_name="$1"
  [ -n "$selected_name" ] || return 1
  safe_name=$(printf '%s' "$selected_name" | sed 's/[^A-Za-z0-9._-]/_/g')
  cap_file="$CAPABILITIES_DIR/${safe_name}-capabilities.json"
  if [ -f "$cap_file" ] && jq -e '
    if ((.device.model_override // "") | length) > 0 then
      ((.model_override_registry.frontend_hold // .registry.frontend_hold // false) == true)
    else
      ((.registry.frontend_hold // false) == true)
    end
  ' "$cap_file" >/dev/null 2>&1; then
    return 0
  fi
  hold_model=$(model_metadata_for_generated_card "$selected_name" effective)
  [ -n "$hold_model" ] && [ -f "$DEVICE_REGISTRY" ] || return 1
  jq -e --arg model "$hold_model" '
    any(.devices[]?; ((.model // "") == $model) and ((.frontend_hold // false) == true))
  ' "$DEVICE_REGISTRY" >/dev/null 2>&1
}

frontend_hold_reason_for_generated_card() {
  selected_name="$1"
  [ -n "$selected_name" ] || return 0
  safe_name=$(printf '%s' "$selected_name" | sed 's/[^A-Za-z0-9._-]/_/g')
  cap_file="$CAPABILITIES_DIR/${safe_name}-capabilities.json"
  if [ -f "$cap_file" ]; then
    reason=$(jq -r '
      if ((.device.model_override // "") | length) > 0 then
        (.model_override_registry.frontend_hold_reason // .registry.frontend_hold_reason // empty)
      else
        (.registry.frontend_hold_reason // empty)
      end
    ' "$cap_file" 2>/dev/null | awk 'NF && $0 != "null" { print; exit }')
    [ -n "$reason" ] && { printf '%s\n' "$reason"; return 0; }
  fi
  hold_model=$(model_metadata_for_generated_card "$selected_name" effective)
  [ -n "$hold_model" ] && [ -f "$DEVICE_REGISTRY" ] || return 0
  jq -r --arg model "$hold_model" '
    first(.devices[]? | select((.model // "") == $model) | .frontend_hold_reason // empty)
  ' "$DEVICE_REGISTRY" 2>/dev/null | awk 'NF && $0 != "null" { print; exit }'
}

observed_n4032_rear_qsfp_count_for_generated_card() {
  selected_name="$1"
  [ -n "$selected_name" ] || { printf '0\n'; return 0; }
  tmp_walks="/tmp/switch_vision_n4032_rear_walks_$$.txt"
  collect_multi_walks "$tmp_walks"
  tmp_names="/tmp/switch_vision_n4032_rear_names_$$.txt"
  : > "$tmp_names"
  while IFS= read -r walk_file; do
    [ -f "$walk_file" ] || continue
    walk_switch=$(target_switch_for_walk "$walk_file")
    [ "$walk_switch" = "$selected_name" ] || continue
    grep -Eo '(Fo|FortyGigabitEthernet)1/1/[12]' "$walk_file" 2>/dev/null >> "$tmp_names" || true
  done < "$tmp_walks"
  count=$(sort -u "$tmp_names" 2>/dev/null | awk 'NF { count++ } END { print count+0 }')
  rm -f "$tmp_walks" "$tmp_names"
  case "$count" in 0|1|2) printf '%s\n' "$count" ;; *) printf '2\n' ;; esac
}

card_port_counts_for_generated_card() {
  selected_name="$1"
  [ -n "$selected_name" ] || return 0
  safe_name=$(printf '%s' "$selected_name" | sed 's/[^A-Za-z0-9._-]/_/g')
  cap_file="$CAPABILITIES_DIR/${safe_name}-capabilities.json"
  model=$(exact_model_for_generated_card "$selected_name")
  counts=""

  if [ -f "$cap_file" ]; then
    counts=$(jq -r '
      (if ((.device.model_override // "") | length) > 0 then
         (.model_override_registry.ports // .registry.ports // {})
       else
         (.registry.ports // {})
       end) as $ports |
      ($ports.rj45 // empty) as $fixed_rj45 |
      ($ports.combo_ports // 0) as $combo |
      (($fixed_rj45 // 0) + ($combo // 0)) as $rj45 |
      ($ports.uplinks // (($ports.gigabit_sfp // 0) + ($ports.ten_gigabit_sfp_plus // 0))) as $sfp |
      if ($fixed_rj45 | type) == "number" and ($combo | type) == "number" and ($sfp | type) == "number"
      then "\($rj45)\t\($sfp)"
      else empty end
    ' "$cap_file" 2>/dev/null | awk 'NF && $0 != "null" { print; exit }')
  fi

  if [ -z "$counts" ] && [ -n "$model" ] && [ -f "$DEVICE_REGISTRY" ]; then
    counts=$(jq -r --arg model "$model" '
      first(.devices[]? | select((.model // "") == $model) | .ports // empty) as $ports |
      if ($ports | type) == "object" then
        ($ports.rj45 // empty) as $fixed_rj45 |
        ($ports.combo_ports // 0) as $combo |
        (($fixed_rj45 // 0) + ($combo // 0)) as $rj45 |
        ($ports.uplinks // (($ports.gigabit_sfp // 0) + ($ports.ten_gigabit_sfp_plus // 0))) as $sfp |
        if ($fixed_rj45 | type) == "number" and ($combo | type) == "number" and ($sfp | type) == "number"
        then "\($rj45)\t\($sfp)"
        else empty end
      else empty end
    ' "$DEVICE_REGISTRY" 2>/dev/null | awk 'NF && $0 != "null" { print; exit }')
  fi

  [ -n "$counts" ] || return 0
  card_rj45=$(printf '%s' "$counts" | awk -F '\t' '{print $1}')
  card_sfp=$(printf '%s' "$counts" | awk -F '\t' '{print $2}')
  if [ "$model" = "N4032F" ]; then
    rear_qsfp=$(observed_n4032_rear_qsfp_count_for_generated_card "$selected_name")
    case "$rear_qsfp" in ''|*[!0-9]*) rear_qsfp=0 ;; esac
    [ "$rear_qsfp" -gt 2 ] && rear_qsfp=2
    card_sfp=$((card_sfp + rear_qsfp))
  fi
  printf '%s\t%s\n' "$card_rj45" "$card_sfp"
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

card_sfp_logical_port_map_for_generated_card() {
  selected_name="$1"
  [ -n "$selected_name" ] || return 0
  safe_name=$(printf '%s' "$selected_name" | sed 's/[^A-Za-z0-9._-]/_/g')
  cap_file="$CAPABILITIES_DIR/${safe_name}-capabilities.json"
  logical_map=""

  if [ -f "$cap_file" ]; then
    logical_map=$(jq -c '
      (if ((.device.model_override // "") | length) > 0 then
         (.model_override_registry.ports // .registry.ports // {})
       else
         (.registry.ports // {})
       end) as $ports |
      ($ports.combo_logical_ports // []) |
      if type == "array" and length > 0 then . else empty end
    ' "$cap_file" 2>/dev/null | awk 'NF && $0 != "null" && $0 != "[]" { print; exit }')
  fi

  if [ -z "$logical_map" ] && [ -f "$DEVICE_REGISTRY" ]; then
    model=$(exact_model_for_generated_card "$selected_name")
    if [ -n "$model" ]; then
      logical_map=$(jq -c --arg model "$model" '
        first(.devices[]? | select((.model // "") == $model) | .ports.combo_logical_ports // empty) as $map |
        if ($map | type) == "array" and ($map | length) > 0 then $map else empty end
      ' "$DEVICE_REGISTRY" 2>/dev/null | awk 'NF && $0 != "null" && $0 != "[]" { print; exit }')
    fi
  fi

  if [ -n "$logical_map" ]; then
    printf '%s\n' "$logical_map"
  fi
  return 0
}

emit_generated_card_sfp_logical_port_map() {
  selected_name="$1"
  logical_map=$(card_sfp_logical_port_map_for_generated_card "$selected_name")
  [ -n "$logical_map" ] || return 0
  echo "        sfp_logical_port_map: ${logical_map}"
}

build_juniper_port_mode_metadata() {
  output_file="$1"
  : > "$output_file"
  helper="/juniper_vlan_modes.py"
  [ -f "$helper" ] || helper="$(dirname "$0")/juniper_vlan_modes.py"
  [ -f "$helper" ] || return 0

  tmp_walks="/tmp/switch_vision_dashboard_mode_walks_$$.txt"
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
  port_mode_metadata="/tmp/switch_vision_generated_port_modes_$$.tsv"
  build_juniper_port_mode_metadata "$port_mode_metadata"
  unifi_snapshot="${SWITCH_VISION_UNIFI_SNAPSHOT:-${SWITCH_VISION_SHARE_DIR:-/share/switch_vision}/unifi/devices.json}"
  unifi_registry="${SWITCH_VISION_DEVICE_REGISTRY:-/opt/switch-vision/devices/supported_devices.json}"
  unifi_helper="${SWITCH_VISION_UNIFI_DASHBOARD_HELPER:-/unifi_dashboard_cards.py}"
  [ -f "$unifi_helper" ] || unifi_helper="$(dirname "$0")/unifi_dashboard_cards.py"
  UNIFI_BOUND_IDS=$(mktemp "${TMPDIR:-/tmp}/switch_vision_unifi_bound_ids.XXXXXX")
  unifi_bound_ids="$UNIFI_BOUND_IDS"
  # This is the native Switch Vision dashboard source; manual Lovelace use remains optional.
  {
    echo "# Switch Vision generated dashboard card examples"
    echo "# Generated: $(date -Iseconds)"
    echo "# Source: Switch Vision Discovery v$SWITCH_VISION_DISCOVERY_VERSION"
    echo "# Native Switch Vision dashboard source. The native panel reads this file automatically; manual Lovelace use remains optional."
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
    echo "          Generated Native Switch Vision dashboard source. Manual YAML/Lovelace use is optional."

    if truthy "${GENERATED_CARD_SNMP_ENABLED:-false}" && command -v jq >/dev/null 2>&1 && [ -f "$CONFIG_FILE" ] && json_has_configured_switch_rows; then
      tmp_cards="/tmp/switch_vision_generated_card_rows_$$.tsv"
      if jq -r '
        # SWITCH_VISION_GENERATED_CARD_ROWS_JQ_BEGIN
        def enabled($sw):
          (($sw.enabled // "enabled") as $value |
            if ($value | type) == "boolean" then $value
            elif ($value | type) == "string" then
              (($value | ascii_downcase) as $state |
                ($state != "false" and $state != "disabled" and $state != "disable" and
                 $state != "off" and $state != "no" and $state != "0"))
            else true end);
        def first_nonempty($values; $fallback):
          (($values
            | map(if . == null then "" else tostring end)
            | map(select(length > 0))
            | .[0]) // $fallback);
        def swname($sw): first_nonempty([$sw.switch_name, $sw.switch, $sw.selected_switch, $sw.name]; "");
        def swlabel($sw): first_nonempty([swname($sw)]; "live");
        def swprefix($sw): first_nonempty([$sw.sensor_prefix, $sw.entity_prefix, $sw.prefix, swlabel($sw)]; swlabel($sw));
        def member_id($m): (($m.member // $m.member_number // "") | tostring);
        def display_name($value):
          (($value // "") | tostring) as $name |
          if ($name | test("^sw[0-9]+$"; "i")) then ($name | ascii_upcase) else $name end;
        def default_member_key($sw): display_name(first_nonempty([swprefix($sw), swname($sw)]; "Switch Vision"));
        def member_key($m; $fallback): display_name(first_nonempty([$m.profile, $m.sensor_prefix, $m.entity_prefix, $m.prefix]; $fallback));
        def member_prefix($m; $fallback): first_nonempty([$m.sensor_prefix, $m.entity_prefix, $m.prefix]; $fallback);
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
        (.dashboard_switches // .switches // .multi_switch_walks // [])[]? as $sw |
          select(enabled($sw)) |
          swname($sw) as $name |
          ($sw.switch_host // $sw.host // $sw.manual_switch_host // "") as $host |
          ([ (.dashboard_stack_member_prefixes // .stack_member_prefixes // [])[]? | select((.switch_name // .switch // .selected_switch // .name // "") == $name) ]) as $members |
          (if ($members | length) > 0 then
            (($members | map(select(member_id(.) == "1")) | .[0]) // null) as $m1 |
            (if $m1 == null then
              (default_member_key($sw)) as $key |
              (if (parent_title($sw) | length) > 0 then parent_title($sw) else $key end) as $title |
              [[ $key, $name, swprefix($sw), $host, "1", $title, parent_header_title($sw) ]]
            else
              (member_key($m1; default_member_key($sw))) as $key |
              (member_display($m1; (if (parent_title($sw) | length) > 0 then parent_title($sw) else $key end))) as $title |
              [[ $key, $name, member_prefix($m1; swprefix($sw)), $host, "1", $title, member_header_title($m1; $sw) ]]
            end)
            +
            ($members | map(select(member_id(.) != "1") |
              (member_key(.; ($name + "_M" + member_id(.)))) as $key |
              (member_display(.; $key)) as $title |
              [ $key, $name, member_prefix(.; swprefix($sw)), $host, member_id(.), $title, member_header_title(.; $sw) ]
            ))
          else
            (default_member_key($sw)) as $key |
            (if (parent_title($sw) | length) > 0 then parent_title($sw) else $key end) as $title |
            [[ $key, $name, swprefix($sw), $host, "", $title, parent_header_title($sw) ]]
          end)[] | map(row_safe(.)) | join("\u001c")
        # SWITCH_VISION_GENERATED_CARD_ROWS_JQ_END
      ' "$CONFIG_FILE" > "$tmp_cards" 2>/dev/null; then
        :
      else
        rm -f "$tmp_cards"
        echo "Generated dashboard card row extraction failed; preserving the previous dashboard." >> "$LIVE_LOG_PATH" 2>/dev/null || true
        return 1
      fi

      card_row_separator="$(printf '\034')"
      while IFS="$card_row_separator" read -r member_name selected prefix host member_num card_title card_header_title || [ -n "$member_name" ]; do
        [ -n "$member_name" ] || continue
        if frontend_hold_for_generated_card "$selected"; then
          hold_model=$(model_metadata_for_generated_card "$selected" effective)
          hold_reason=$(frontend_hold_reason_for_generated_card "$selected")
          [ -n "$hold_reason" ] || hold_reason="Frontend presentation is intentionally held until dedicated faceplate geometry is designed and reviewed."
          echo ""
          echo "      - type: markdown"
          echo "        content: |"
          printf "          ### %s\n" "${card_title:-Switch Vision}"
          printf "          **%s is discovered and telemetry-capable, but its Switch Vision card is intentionally not bound to a faceplate yet.**\n" "${hold_model:-Switch}"
          printf "          %s\n" "$hold_reason"
          continue
        fi
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
        emit_generated_card_sfp_logical_port_map "$selected"
        case "${effective_model:-${detected_model:-}}" in
          *Juniper*EX3300-48P*)
            # Data/entity numbering may differ from the stock faceplate labels.
            # Keep presentation owned by the selected profile/calibration.
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
          if [ -f "$unifi_snapshot" ] && [ -f "$unifi_registry" ] && [ -f "$unifi_helper" ]; then
            unifi_binding_tmp="/tmp/switch_vision_unifi_binding_$$.yaml"
            device_mac=$(device_mac_for_generated_card "$selected")
            if python3 "$unifi_helper" --snapshot "$unifi_snapshot" --registry "$unifi_registry" --binding-ip "$host" --binding-mac "$device_mac" --indent 8 > "$unifi_binding_tmp" 2>/dev/null; then
              # One UniFi controller device can describe the whole management
              # address, but an SNMP stack renders one card per member. Suppress
              # the duplicate standalone UniFi card in either case, and only
              # bind API telemetry onto a non-stack SNMP card.
              if [ -z "$member_num" ]; then
                cat "$unifi_binding_tmp"
              fi
              matched_unifi_id=$(python3 "$unifi_helper" --snapshot "$unifi_snapshot" --registry "$unifi_registry" --binding-ip "$host" --binding-mac "$device_mac" --binding-id-only 2>/dev/null || true)
              [ -n "$matched_unifi_id" ] && printf '%s\n' "$matched_unifi_id" >> "$unifi_bound_ids"
            fi
            rm -f "$unifi_binding_tmp"
          fi
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
          *CRS328-24P-4S+*)
            echo "        cpu_entity: sensor.${safe_prefix}_cpu"
            echo "        temperature_entity: sensor.${safe_prefix}_temperature"
            echo "        fans_entity: sensor.${safe_prefix}_fan_1_rpm"
            ;;
          *)
            echo "        cpu_entity: sensor.${safe_prefix}_cpu_5min"
            echo "        temperature_entity: sensor.${safe_prefix}_temperature"
            ;;
        esac
        echo "        poe_used_entity: sensor.${safe_prefix}_poe_used"
        echo "        poe_budget_entity: sensor.${safe_prefix}_poe_budget"
        echo "        entity_prefix: ${safe_prefix}"
        echo "        status_entity_prefix: sensor.${safe_prefix}_port_"
        echo "        status_entity_suffix: _status"
        case "${effective_model:-${detected_model:-}}" in
          *J8693A*|*3500yl-48G*|*WS-C3560CG-8PC-S*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_uplink_{port}_status" ;;
          *3524GT-PWR+*|*SG350-20*|*S5720-12TP-LI-AC*|*WS-C3750-48P*|*WS-C2960X-24PS-L*|*WS-C2960X-24TS-L*|*WS-C2960XR-48LPS-I*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_1g_{port}_status" ;;
          *) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_10g_{port}_status" ;;
        esac
        emit_generated_port_metadata "$safe_prefix" "$port_mode_metadata"
      done < "$tmp_cards"
    elif truthy "${GENERATED_CARD_SNMP_ENABLED:-false}"; then
      profile="${SELECTED_SWITCH:-}"
      fallback_walk=""
      if [ -z "$profile" ]; then
        GENERATED_CARD_FALLBACK_WALKS=$(mktemp "${TMPDIR:-/tmp}/switch_vision_generated_card_fallback_walks.XXXXXX")
        fallback_walks="$GENERATED_CARD_FALLBACK_WALKS"
        collect_multi_walks "$fallback_walks"
        fallback_walk=$(sed -n '1p' "$fallback_walks" 2>/dev/null || true)
        rm -f "$fallback_walks"
        GENERATED_CARD_FALLBACK_WALKS=""
        if [ -n "$fallback_walk" ]; then
          profile=$(target_switch_for_walk "$fallback_walk")
        fi
      fi
      [ -n "$profile" ] || profile="${LIVE_SWITCH_LABEL:-SW1}"
      label="${LIVE_SWITCH_LABEL:-$(lower_value "$profile")}"
      prefix="${DEFAULT_PREFIX:-}"
      host="${LIVE_SWITCH_IP:-${DEFAULT_HOST:-}}"
      if [ -n "$fallback_walk" ]; then
        [ -n "$prefix" ] || prefix=$(target_prefix_for_walk "$fallback_walk")
        [ -n "$host" ] || host=$(target_for_walk "$fallback_walk")
      fi
      [ -n "$prefix" ] || prefix="$label"
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
      emit_generated_card_sfp_logical_port_map "$profile"
      case "${exact_model:-}" in
        *Juniper*EX3300-48P*)
          echo "        port_entity_offset: -1"
          ;;
      esac
      registry_calibration_profile=$(calibration_profile_for_generated_card "$profile")
      generated_calibration_profile=${registry_calibration_profile:-$profile}
      echo "        calibration_profile: ${generated_calibration_profile}"
      echo "        calibration_profile_load: true"
      echo "        calibration_button: true"
      echo "        activity_hold_seconds: 12"
      echo "        entity_prefix: ${safe_prefix}"
      echo "        status_entity_prefix: sensor.${safe_prefix}_port_"
      echo "        status_entity_suffix: _status"
      case "${exact_model:-}" in
        *J8693A*|*3500yl-48G*|*WS-C3560CG-8PC-S*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_uplink_{port}_status" ;;
        *3524GT-PWR+*|*SG350-20*|*S5720-12TP-LI-AC*|*WS-C3750-48P*|*WS-C2960X-24PS-L*|*WS-C2960X-24TS-L*|*WS-C2960XR-48LPS-I*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_1g_{port}_status" ;;
        *) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_10g_{port}_status" ;;
      esac
      emit_generated_port_metadata "$safe_prefix" "$port_mode_metadata"
      if [ -n "$host" ]; then
        echo "        switch_ip: ${host}"
        echo "        management_ip: ${host}"
        if [ -f "$unifi_snapshot" ] && [ -f "$unifi_registry" ] && [ -f "$unifi_helper" ]; then
          unifi_binding_tmp="/tmp/switch_vision_unifi_binding_$$.yaml"
          device_mac=$(device_mac_for_generated_card "$profile")
          if python3 "$unifi_helper" --snapshot "$unifi_snapshot" --registry "$unifi_registry" --binding-ip "$host" --binding-mac "$device_mac" --indent 8 > "$unifi_binding_tmp" 2>/dev/null; then
            cat "$unifi_binding_tmp"
            matched_unifi_id=$(python3 "$unifi_helper" --snapshot "$unifi_snapshot" --registry "$unifi_registry" --binding-ip "$host" --binding-mac "$device_mac" --binding-id-only 2>/dev/null || true)
            [ -n "$matched_unifi_id" ] && printf '%s\n' "$matched_unifi_id" >> "$unifi_bound_ids"
          fi
          rm -f "$unifi_binding_tmp"
        fi
      fi
    fi

    # UniFi2MQTT is a normalized discovery/telemetry source. A device already
    # reconciled into an SNMP card by unique hardware MAC, or unique management
    # IP when no MAC match is available, is excluded by its exact UniFi device
    # ID so one physical switch produces one card. Unmatched API devices remain
    # live standalone cards.
    if [ -f "$unifi_snapshot" ] && [ -f "$unifi_registry" ] && [ -f "$unifi_helper" ]; then
      echo ""
      echo "      # UniFi API devices (Switch Vision UniFi2MQTT)"
      python3 "$unifi_helper" --snapshot "$unifi_snapshot" --registry "$unifi_registry" --exclude-id-file "$unifi_bound_ids" --indent 6 --summary 2>/dev/null || \
        echo "      # UniFi snapshot was present but could not be converted into dashboard cards."
    fi
  } > "/tmp/switch_vision_generated_dashboard_raw_$$.yaml"

  device_control_path="${SWITCH_VISION_DEVICE_CONTROL_PATH:-${SWITCH_VISION_SHARE_DIR:-/share/switch_vision}/device-control.json}"
  device_order_helper="${SWITCH_VISION_DASHBOARD_DEVICE_ORDER_HELPER:-/dashboard_device_order.py}"
  [ -f "$device_order_helper" ] || device_order_helper="$(dirname "$0")/dashboard_device_order.py"
  if [ -f "$device_order_helper" ]; then
    python3 "$device_order_helper" \
      --fresh "/tmp/switch_vision_generated_dashboard_raw_$$.yaml" \
      --source "$GENERATED_CARD_FULL_PATH" \
      --dashboard "$GENERATED_CARD_PATH" \
      --control "$device_control_path" \
      --options "$CONFIG_FILE"
  else
    cp "/tmp/switch_vision_generated_dashboard_raw_$$.yaml" "$GENERATED_CARD_PATH"
  fi

  rm -f "$port_mode_metadata" "$unifi_bound_ids" "/tmp/switch_vision_generated_dashboard_raw_$$.yaml"
  UNIFI_BOUND_IDS=""
}

write_report() {
  report_snmp_walks_enabled="${SWITCH_VISION_ORIGINAL_RUN_SNMP_WALKS:-$RUN_LIVE_SNMPWALK}"
  sv_status "Identifying exact models and interfaces" "All configured switches" "multiple" "Parser and registry lookup" "Reading completed SNMP walk files"
  sv_debug "STAGE: Identifying exact models and interfaces"
  tmp_walks="/tmp/switch_vision_walk_files_$$.txt"
  echo "Post-walk stage: collecting walk files for parse/report" >> "$LIVE_LOG_PATH" 2>/dev/null || true
  collect_multi_walks "$tmp_walks"
  if [ -s "${CURRENT_RUN_WALKS:-/tmp/switch_vision_current_run_walks_$$.txt}" ]; then
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
    echo "SNMP walks enabled: $report_snmp_walks_enabled"
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
          echo "- Handoff source: Switch Vision SNMP2MQTT imports this generated file after Discovery completes."
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
          echo "- Handoff source: Switch Vision SNMP2MQTT imports this generated file after Discovery completes."
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
    echo "- Native panel source: automatically consumed by Switch Vision; manual YAML/Lovelace use is optional."
  } >> "$REPORT_PATH"
}


write_last_run_summary() {
  summary_snmp_walks_enabled="${SWITCH_VISION_ORIGINAL_RUN_SNMP_WALKS:-$RUN_LIVE_SNMPWALK}"
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
      echo "SNMP walks enabled: $summary_snmp_walks_enabled"
      echo "Multi-switch walks enabled: $MULTI_SWITCH_WALKS_ENABLED"
      echo "Management IP: per switch row"
      echo "Output folder: per switch row"
      echo "Sensor prefix: per switch row / stack_member_prefixes"
      echo "Output: per switch folder under $SNMPWALKS_ROOT_DIR"
    else
      echo "Current target: ${SELECTED_SWITCH:-not set}"
      echo "Target mapping matched: $SELECTED_SWITCH_MATCHED"
      echo "Walk mode: $LIVE_SNMPWALK_MODE"
      echo "SNMP walks enabled: $summary_snmp_walks_enabled"
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
    summary_source="${SWITCH_VISION_ORIGINAL_LIVE_WALK_SUMMARY:-$LIVE_WALK_SUMMARY}"
    if [ -f "$summary_source" ]; then
      echo ""
      cat "$summary_source"
    fi
  } > "$LAST_RUN_SUMMARY_PATH"
}

run_live_snmpwalk_if_enabled

# The physical-contract entrypoint deliberately separates live evidence
# collection from authoritative parsing/generation. Collection-only mode must
# not emit a report/card, a last-run summary, a Support My Switch bundle, or the
# user-facing "Discovery complete" marker; the second authority pass owns those.
if truthy "$COLLECTION_ONLY"; then
  collection_summary_path="${SWITCH_VISION_COLLECTION_SUMMARY_PATH:-}"
  if [ -n "$collection_summary_path" ] && [ -f "$LIVE_WALK_SUMMARY" ]; then
    mkdir -p "$(dirname "$collection_summary_path")"
    cp "$LIVE_WALK_SUMMARY" "$collection_summary_path"
  fi
  collection_no_snmp_targets="false"
  if [ "$DISCOVERY_EXIT_STATUS" = "0" ] && [ ! -s "$CURRENT_RUN_WALKS" ]; then
    if truthy "$MULTI_SWITCH_WALKS_ENABLED" && ! json_has_enabled_switch_rows; then
      collection_no_snmp_targets="true"
    else
      DISCOVERY_EXIT_STATUS="2"
    fi
  fi
  case "$DISCOVERY_EXIT_STATUS" in
    0)
      if truthy "$collection_no_snmp_targets"; then
        sv_status "Evidence collection skipped" "All configured switches" "not configured" "SNMP collection" "No enabled SNMP targets are configured; continuing with independent API/dashboard sources"
        sv_debug "STAGE: Evidence collection skipped; no enabled SNMP targets"
        echo "Switch Vision live SNMP collection skipped because no enabled SNMP targets are configured. Continuing with independent API/dashboard sources."
      else
        sv_status "Evidence collection complete" "All configured switches" "complete" "SNMP collection" "Live SNMP evidence collected; validating physical contracts"
        sv_debug "STAGE: Evidence collection complete"
        echo "Switch Vision live evidence collection complete. Physical-contract validation is next."
      fi
      exit 0
      ;;
    11)
      sv_status "Evidence collection complete with warnings" "All configured switches" "partial" "SNMP collection" "Useful live evidence collected; failed targets excluded from authority processing"
      sv_debug "STAGE: Evidence collection partial"
      echo "Switch Vision live evidence collection completed with PARTIAL results. Safe current-run evidence was preserved."
      exit 11
      ;;
    *)
      sv_status "Evidence collection failed" "All configured switches" "failed" "SNMP collection" "No safe current-run evidence is available for authority processing"
      sv_debug "STAGE: Evidence collection failed"
      echo "Switch Vision live evidence collection failed."
      exit "$DISCOVERY_EXIT_STATUS"
      ;;
  esac
fi

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
case "${DISCOVERY_EXIT_STATUS:-0}" in
  0)
    sv_status "Complete" "All configured switches" "complete" "" "Discovery complete"
    sv_debug "STAGE: Discovery complete"
    echo "Switch Vision Discovery run complete. Web UI remains available."
    ;;
  11)
    sv_status "Complete with warnings" "All configured switches" "partial" "" "Discovery partial; safe current-run results preserved"
    sv_debug "STAGE: Discovery partial"
    echo "Switch Vision Discovery run completed with PARTIAL results. Safe current-run evidence was preserved."
    exit 11
    ;;
  *)
    sv_status "Failed" "All configured switches" "failed" "" "Discovery live collection failed"
    sv_debug "STAGE: Discovery failed"
    echo "Switch Vision Discovery run failed. Safe report state was written without historical walk fallback."
    exit "$DISCOVERY_EXIT_STATUS"
    ;;
esac
