#!/usr/bin/env sh

cv_cap_extract_model_text() {
  walk_file="$1"
  # ENTITY-MIB model names are more precise than sysDescr for 24/48-port
  # variants. Fall back to sysDescr/family when no explicit model is present.
  model=$(grep -Eio 'WS-C[0-9A-Za-z][0-9A-Za-z._-]*|SG500X-24|S5735-L8P4X-A1|S5720-12TP-LI-AC|XS1930-10|N2128PX-ON|ex3300-48p' "$walk_file" 2>/dev/null | head -n 1 || true)
  if [ -n "$model" ]; then
    case "$model" in
      [Ee][Xx]3300-48[Pp]) printf 'Juniper EX3300-48P' ;;
      *) printf '%s' "$model" ;;
    esac
  else
    printf '%s %s' "${CV_ID_FAMILY:-}" "${CV_ID_SYS_DESCR:-}"
  fi
}

cv_cap_set_front_panel_profile() {
  walk_file="$1"
  CV_CAP_RJ45_LIMIT="48"
  CV_CAP_FRONT_PANEL_AWARE="false"
  CV_CAP_PLATFORM="generic"
  CV_CAP_MODEL_TEXT=$(cv_cap_extract_model_text "$walk_file")

  case "$CV_CAP_MODEL_TEXT" in
    *C3650*)
      CV_CAP_FRONT_PANEL_AWARE="true"
      CV_CAP_PLATFORM="c3650"
      case "$CV_CAP_MODEL_TEXT" in
        *-24*|*24P*|*24T*|*24L*) CV_CAP_RJ45_LIMIT="24" ;;
        *) CV_CAP_RJ45_LIMIT="48" ;;
      esac
      ;;
    *C3750-48P*)
      CV_CAP_FRONT_PANEL_AWARE="true"
      CV_CAP_PLATFORM="c3750_48p"
      CV_CAP_RJ45_LIMIT="48"
      ;;
    *C2960S*|*C2960X*)
      CV_CAP_FRONT_PANEL_AWARE="true"
      CV_CAP_PLATFORM="c2960"
      case "$CV_CAP_MODEL_TEXT" in
        *-24*|*24P*|*24T*|*24L*) CV_CAP_RJ45_LIMIT="24" ;;
        *) CV_CAP_RJ45_LIMIT="48" ;;
      esac
      ;;
    *Juniper*EX3300-48P*)
      CV_CAP_FRONT_PANEL_AWARE="true"
      CV_CAP_PLATFORM="juniper_ex3300_48p"
      CV_CAP_RJ45_LIMIT="48"
      ;;
    *SG500X-24*)
      CV_CAP_FRONT_PANEL_AWARE="true"
      CV_CAP_PLATFORM="cisco_sg500x_24"
      CV_CAP_RJ45_LIMIT="24"
      ;;
    *S5735-L8P4X-A1*)
      CV_CAP_FRONT_PANEL_AWARE="true"
      CV_CAP_PLATFORM="huawei_s5735_l8p4x_a1"
      CV_CAP_RJ45_LIMIT="8"
      ;;
    *S5720-12TP-LI-AC*)
      CV_CAP_FRONT_PANEL_AWARE="true"
      CV_CAP_PLATFORM="huawei_s5720_12tp_li_ac"
      CV_CAP_RJ45_LIMIT="8"
      ;;
    *N2128PX-ON*)
      CV_CAP_FRONT_PANEL_AWARE="true"
      CV_CAP_PLATFORM="dell_n2128px_on"
      CV_CAP_RJ45_LIMIT="28"
      ;;
    *J8693A*3500yl-48G*|*J8693A*3500YL-48G*|*3500yl-48G*J8693A*|*3500YL-48G*J8693A*)
      # Exact HP 3500yl-48G hardware: 44 fixed copper logical ports and
      # four dual-personality copper/mini-GBIC logical ports.
      CV_CAP_FRONT_PANEL_AWARE="true"
      CV_CAP_PLATFORM="hp_3500yl_48g"
      CV_CAP_RJ45_LIMIT="44"
      ;;
    *CRS328-24P-4S+*)
      CV_CAP_FRONT_PANEL_AWARE="true"
      CV_CAP_PLATFORM="mikrotik_crs328_24p_4splus"
      CV_CAP_RJ45_LIMIT="24"
      ;;
    *XS1930-10*)
      CV_CAP_FRONT_PANEL_AWARE="true"
      CV_CAP_PLATFORM="zyxel_xs1930_10"
      CV_CAP_RJ45_LIMIT="8"
      ;;
  esac
}

cv_interface_class_for_name() {
  name="$1"

  # HP J8693A / 3500yl-48G exposes its physical logical ports as
  # numeric ifName values. Keep this exact-model exception ahead of the
  # generic name parser so numeric interfaces on other vendors stay excluded.
  if [ "${CV_CAP_PLATFORM:-generic}" = "hp_3500yl_48g" ]; then
    case "$name" in
      [1-9]|[1-3][0-9]|4[0-4]) printf 'rj45'; return 0 ;;
      4[5-8]) printf 'uplink'; return 0 ;;
      *) printf 'other'; return 0 ;;
    esac
  fi

  # MikroTik CRS328 exposes stable RouterOS front-panel names. Keep the
  # exact-model rule narrow so generic RouterOS bridge/loopback interfaces
  # never become physical ports on unrelated models.
  if [ "${CV_CAP_PLATFORM:-generic}" = "mikrotik_crs328_24p_4splus" ]; then
    case "$name" in
      ether[1-9]|ether1[0-9]|ether2[0-4]) printf 'rj45'; return 0 ;;
      sfp-sfpplus[1-4]) printf 'sfp_plus'; return 0 ;;
      bridge|lo) printf 'virtual'; return 0 ;;
      *) printf 'other'; return 0 ;;
    esac
  fi

  # Dell N2128PX-ON uses Cisco-like Gi/Te names, but its Te uplinks live
  # in slot 0. Handle the exact Dell platform before the generic parser
  # so other vendors keep their existing Gi/Te behaviour unchanged.
  if [ "${CV_CAP_PLATFORM:-generic}" = "dell_n2128px_on" ]; then
    case "$name" in
      Gi[0-9]*/0/*|GigabitEthernet[0-9]*/0/*)
        short_name=$(printf '%s' "$name" | sed -E 's/^GigabitEthernet//; s/^Gi//')
        slot_number=$(printf '%s' "$short_name" | awk -F/ 'NF == 3 {print $2}')
        port_number=${short_name##*/}
        case "$port_number" in
          ''|*[!0-9]*) printf 'other' ;;
          *)
            if [ "$slot_number" = "0" ] &&
               [ "$port_number" -ge 1 ] &&
               [ "$port_number" -le 28 ]; then
              printf 'rj45'
            else
              printf 'other'
            fi
            ;;
        esac
        return 0
        ;;
      Te[0-9]*/0/*|TenGigabitEthernet[0-9]*/0/*)
        short_name=$(printf '%s' "$name" | sed -E 's/^TenGigabitEthernet//; s/^Te//')
        slot_number=$(printf '%s' "$short_name" | awk -F/ 'NF == 3 {print $2}')
        port_number=${short_name##*/}
        case "$port_number" in
          1|2)
            if [ "$slot_number" = "0" ]; then
              printf 'sfp_plus'
            else
              printf 'other'
            fi
            ;;
          *) printf 'other' ;;
        esac
        return 0
        ;;
    esac
  fi

  case "$name" in
    gi1/[0-9]*)
      if [ "${CV_CAP_PLATFORM:-generic}" = "cisco_sg500x_24" ]; then printf 'rj45'; else printf 'other'; fi
      ;;
    te1/[0-9]*)
      if [ "${CV_CAP_PLATFORM:-generic}" = "cisco_sg500x_24" ]; then printf 'sfp_plus'; else printf 'other'; fi
      ;;
    ge-[0-9]*/[0-9]*/[0-9]*|xe-[0-9]*/[0-9]*/[0-9]*)
      case "$name" in
        *.*) printf 'other'; return 0 ;;
      esac
      if [ "${CV_CAP_PLATFORM:-generic}" = "juniper_ex3300_48p" ]; then
        case "$name" in
          ge-0/0/*)
            port_number=${name##*/}
            case "$port_number" in ''|*[!0-9]*) printf 'other' ;; *) [ "$port_number" -le 47 ] && printf 'rj45' || printf 'other' ;; esac
            return 0
            ;;
          xe-0/1/[0-3]) printf 'sfp_plus'; return 0 ;;
          ge-0/1/[0-3])
            cage=${name#ge-}
            if [ -n "${CV_CAP_IFNAME_LIST:-}" ] && grep -Fxq "xe-$cage" "$CV_CAP_IFNAME_LIST" 2>/dev/null; then printf 'other'; else printf 'sfp_plus'; fi
            return 0
            ;;
        esac
      fi
      printf 'other'
      ;;
    GigabitEthernet*|Gi*)
      short_name=$(printf '%s' "$name" | sed -E 's/^GigabitEthernet//; s/^Gi//')
      # Dedicated management ports are not front-panel data interfaces.
      case "$short_name" in
        0/0|0|*/0/0)
          printf 'other'
          return 0
          ;;
      esac

      if [ "${CV_CAP_PLATFORM:-generic}" = "c3750_48p" ]; then
        case "$short_name" in
          [0-9]*/0/[1-4]) printf 'sfp' ;;
          *) printf 'other' ;;
        esac
        return 0
      fi

      if [ "${CV_CAP_FRONT_PANEL_AWARE:-false}" = "true" ]; then
        # Catalyst 3650 network-module GigabitEthernet uplinks are 1G SFP.
        # The TenGigabitEthernet names are classified separately as SFP+.
        if [ "${CV_CAP_PLATFORM:-generic}" = "c3650" ]; then
          slot_number=$(printf '%s' "$short_name" | awk -F/ 'NF >= 3 {print $(NF-1)}')
          if [ -n "$slot_number" ] && [ "$slot_number" != "0" ]; then
            printf 'sfp'
            return 0
          fi
        fi
        port_number=${short_name##*/}
        case "$port_number" in
          ''|*[!0-9]*) : ;;
          *)
            if [ "$port_number" -gt "${CV_CAP_RJ45_LIMIT:-48}" ]; then
              if [ "${CV_CAP_PLATFORM:-generic}" = "huawei_s5720_12tp_li_ac" ] && [ "$port_number" -le 12 ]; then
                printf 'sfp'
              elif [ "${CV_CAP_PLATFORM:-generic}" = "c2960" ]; then
                # 24-port 2960S/X models expose four genuine 1G SFP ports.
                # 48FPD models additionally expose Gi aliases for the same two
                # physical SFP+ cages represented by Te1/0/1-2; suppress those
                # aliases so normalized physical counts are not doubled.
                case "$CV_CAP_MODEL_TEXT" in
                  *C2960S-48FPD*|*C2960X-48FPD*)
                    alias_number=$((port_number - CV_CAP_RJ45_LIMIT))
                    if [ -n "${CV_CAP_IFNAME_LIST:-}" ] && {
                      grep -Fxq "Te1/0/$alias_number" "$CV_CAP_IFNAME_LIST" 2>/dev/null ||
                      grep -Fxq "TenGigabitEthernet1/0/$alias_number" "$CV_CAP_IFNAME_LIST" 2>/dev/null;
                    }; then
                      printf 'other'
                    else
                      printf 'sfp'
                    fi
                    ;;
                  *) printf 'sfp' ;;
                esac
              else
                printf 'sfp_plus'
              fi
              return 0
            fi
            ;;
        esac
      fi
      printf 'rj45'
      ;;
    FastEthernet*|Fa*)
      short_name=$(printf '%s' "$name" | sed -E 's/^FastEthernet//; s/^Fa//')
      if [ "${CV_CAP_PLATFORM:-generic}" = "c3750_48p" ]; then
        slot_number=$(printf '%s' "$short_name" | awk -F/ 'NF == 3 {print $2}')
        port_number=${short_name##*/}
        case "$port_number" in
          ''|*[!0-9]*) printf 'other' ;;
          *)
            if [ "$slot_number" = "0" ] && [ "$port_number" -ge 1 ] && [ "$port_number" -le 48 ]; then
              printf 'rj45'
            else
              printf 'other'
            fi
            ;;
        esac
      else
        case "$short_name" in
          0|0/0|*/0/0) printf 'other' ;;
          *) printf 'rj45' ;;
        esac
      fi
      ;;
    swp0[0-9])
      if [ "${CV_CAP_PLATFORM:-generic}" = "zyxel_xs1930_10" ]; then
        port_number=${name#swp0}
        case "$port_number" in
          [0-7]) printf 'rj45' ;;
          8|9) printf 'sfp_plus' ;;
          *) printf 'other' ;;
        esac
      else
        printf 'other'
      fi
      ;;
    XGigabitEthernet*|XGE*|TenGigabitEthernet*|Te*) printf 'sfp_plus' ;;
    FortyGigabitEthernet*|Fo*|TwentyFiveGigE*|HundredGigE*) printf 'sfp_plus' ;;
    StackPort*|StackSub*|Stack*) printf 'stack' ;;
    Vlan*|Loopback*|Port-channel*|Null*|Control*) printf 'virtual' ;;
    *) printf 'other' ;;
  esac
}

cv_write_capabilities_json() {
  walk_file="$1"
  output_path="$2"
  latest_path="$3"
  mkdir -p "$(dirname "$output_path")"
  if [ -n "${latest_path:-}" ]; then mkdir -p "$(dirname "$latest_path")"; fi

  cv_detect_vendor_identity "$walk_file"
  cv_cap_set_front_panel_profile "$walk_file"

  tmp_ports=$(mktemp)
  CV_CAP_IFNAME_LIST=$(mktemp)
  awk '
    function norm(s){sub(/^\./,"",s);sub(/^iso\./,"1.",s);return s}
    function value(line) {
      sub(/^[^=]*=[[:space:]]*/,"",line)
      sub(/^[A-Za-z0-9-]+:[[:space:]]*/,"",line)
      gsub(/^"|"$/,"",line)
      gsub(/\r/,"",line)
      sub(/[[:space:]]+$/,"",line)
      return line
    }
    {
      oid=norm($1)
      ifname_base="1.3.6.1.2.1.31.1.1.1.1."
      ifdescr_base="1.3.6.1.2.1.2.2.1.2."
      if (index(oid,ifname_base)==1) {
        idx=substr(oid,length(ifname_base)+1)
        ifname[idx]=value($0)
        if ((idx+0)>maxidx) maxidx=idx+0
      } else if (index(oid,ifdescr_base)==1) {
        idx=substr(oid,length(ifdescr_base)+1)
        ifdescr[idx]=value($0)
        if ((idx+0)>maxidx) maxidx=idx+0
      }
    }
    END {
      for (idx=0; idx<=maxidx; idx++) {
        if (idx in ifname) print idx "\t" ifname[idx]
        else if (idx in ifdescr) print idx "\t" ifdescr[idx]
      }
    }
  ' "$walk_file" > "$CV_CAP_IFNAME_LIST.raw"
  cut -f2 "$CV_CAP_IFNAME_LIST.raw" > "$CV_CAP_IFNAME_LIST"
  while IFS="$(printf '\t')" read -r idx name; do
    [ -n "$idx" ] || continue
    CV_CAP_IF_INDEX="$idx"
    media=$(cv_interface_class_for_name "$name")
    physical=true
    case "$media" in virtual|stack|other) physical=false ;; esac
    jq -cn \
      --argjson idx "$idx" \
      --arg name "$name" \
      --arg media "$media" \
      --argjson physical "$physical" \
      '{if_index:$idx,name:$name,media:$media,physical:$physical}'
  done < "$CV_CAP_IFNAME_LIST.raw" > "$tmp_ports"

  capability_version="${SWITCH_VISION_DISCOVERY_VERSION:-unknown}"
  jq -s \
    --arg schema "1" \
    --arg product "Switch Vision" \
    --arg version "$capability_version" \
    --arg vendor "$CV_ID_VENDOR" \
    --arg vendor_name "$CV_ID_VENDOR_NAME" \
    --arg adapter "$CV_ID_ADAPTER" \
    --arg family "$CV_ID_FAMILY" \
    --arg support "$CV_ID_SUPPORT_STATUS" \
    --arg sys_object_id "$CV_ID_SYS_OBJECT_ID" \
    --arg sys_name "$CV_ID_SYS_NAME" \
    --arg model_text "$CV_CAP_MODEL_TEXT" \
    --arg walk_file "$walk_file" \
    '{schema_version:($schema|tonumber),product:$product,release:$version,generated_at:(now|todateiso8601),source_walk:$walk_file,device:{vendor:$vendor,vendor_name:$vendor_name,adapter:$adapter,family:$family,model_text:$model_text,support_status:$support,sys_object_id:$sys_object_id,sys_name:$sys_name},capabilities:{standard_interfaces:true,identity:true,stack:null,vlan_trunk:null,environment:null,poe:null},interfaces:.,summary:{interface_count:length,physical_count:(map(select(.physical))|length),rj45_count:(map(select(.media=="rj45"))|length),sfp_count:(map(select(.media=="sfp"))|length),sfp_plus_count:(map(select(.media=="sfp_plus"))|length),uplink_count:(map(select(.media=="sfp" or .media=="sfp_plus" or .media=="uplink"))|length),stack_count:(map(select(.media=="stack"))|length),virtual_count:(map(select(.media=="virtual"))|length)}}' \
    "$tmp_ports" > "$output_path"

  if [ -n "${latest_path:-}" ]; then cp "$output_path" "$latest_path"; fi
  rm -f "$tmp_ports" "$CV_CAP_IFNAME_LIST" "$CV_CAP_IFNAME_LIST.raw"
  CV_CAPABILITIES_PATH="$output_path"
}
