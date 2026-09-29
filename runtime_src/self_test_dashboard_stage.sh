# Switch Vision Discovery self-test generated-dashboard regression module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# Generated dashboard rows must obey the same enabled-state predicate as the
# walk/parser/generator path. Exercise the exact jq program embedded in the
# production dashboard-card writer so a disabled saved switch cannot render a
# stale/offline card, while legacy rows without explicit state remain enabled.
card_rows_jq="$tmp_dir/generated-card-rows.jq"
awk '
  /SWITCH_VISION_GENERATED_CARD_ROWS_JQ_BEGIN/ { capture=1; next }
  /SWITCH_VISION_GENERATED_CARD_ROWS_JQ_END/ { capture=0; next }
  capture { print }
' "$DASHBOARD_STAGE_SOURCE" > "$card_rows_jq"
[ -s "$card_rows_jq" ] || { echo "ERROR: generated-card jq program was not found" >&2; exit 1; }

card_fixture="$tmp_dir/generated-card-enabled-filter.json"
cat > "$card_fixture" <<'JSON_CARD_ENABLED_FILTER'
{
  "switches": [
    {
      "switch_name": "STACK_ENABLED",
      "switch_host": "192.0.2.31",
      "sensor_prefix": "sw1",
      "display_name": "Enabled Stack",
      "enabled": "enabled"
    },
    {
      "switch_name": "SW_DISABLED",
      "switch_host": "192.0.2.32",
      "sensor_prefix": "sw_disabled",
      "display_name": "Disabled Switch",
      "enabled": "disabled"
    },
    {
      "switch_name": "SW_LEGACY",
      "switch_host": "192.0.2.33",
      "sensor_prefix": "sw_legacy",
      "display_name": "Legacy Enabled"
    }
  ],
  "stack_member_prefixes": [
    {"switch_name": "STACK_ENABLED", "member": "1", "sensor_prefix": "sw1", "display_name": "STACK 1"},
    {"switch_name": "STACK_ENABLED", "member": "2", "sensor_prefix": "sw2", "display_name": "STACK 2"},
    {"switch_name": "SW_DISABLED", "member": "1", "sensor_prefix": "sw_disabled", "display_name": "SHOULD NOT RENDER"}
  ]
}
JSON_CARD_ENABLED_FILTER

card_rows="$tmp_dir/generated-card-enabled-filter.rows"
jq -r -f "$card_rows_jq" "$card_fixture" > "$card_rows"
[ "$(wc -l < "$card_rows" | tr -d ' ')" = "3" ] || {
  echo "ERROR: expected two enabled stack cards plus one legacy card" >&2
  cat "$card_rows" >&2
  exit 1
}
grep -q 'STACK_ENABLED' "$card_rows"
grep -q 'SW_LEGACY' "$card_rows"
! grep -q 'SW_DISABLED' "$card_rows"
! grep -q 'SHOULD NOT RENDER' "$card_rows"
printf "%s\n" "Switch Vision generated-card enabled-state regression: PASS"
