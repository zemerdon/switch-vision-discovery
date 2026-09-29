# Switch Vision Discovery generated-dashboard-card stage module.
# Sourced by discovery_job.sh after shared model/registry/card helpers are defined.
# Keep dashboard-card behavior shell-native; this module is an extraction boundary.

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
