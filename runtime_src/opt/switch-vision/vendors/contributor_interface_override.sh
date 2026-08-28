#!/usr/bin/env sh

# Contributor-backed exact-model interface classifier overlay.
#
# This function is sourced after interface.sh and intentionally keeps every
# new exception model-specific. Generic Linux, lowercase Gi/Te, numeric, and
# 0/N names must remain non-physical unless an exact contributed model proves
# their front-panel meaning.
cv_interface_class_for_name() {
  name="$1"

  # Dell PowerConnect 5548P contribution: 48 fixed copper ports plus two
  # 10G SFP+ uplinks. Its IF-MIB uses lowercase gi1/0/N and te1/0/N names.
  if [ "${CV_CAP_MODEL_TEXT:-}" = "PowerConnect 5548P" ]; then
    case "$name" in
      gi1/0/*|Gi1/0/*|GigabitEthernet1/0/*)
        port_number=${name##*/}
        case "$port_number" in
          ''|*[!0-9]*) printf 'other' ;;
          *) [ "$port_number" -ge 1 ] && [ "$port_number" -le 48 ] && printf 'rj45' || printf 'other' ;;
        esac
        return 0
        ;;
      te1/0/*|Te1/0/*|TenGigabitEthernet1/0/*)
        port_number=${name##*/}
        case "$port_number" in 1|2) printf 'sfp_plus' ;; *) printf 'other' ;; esac
        return 0
        ;;
      *) printf 'other'; return 0 ;;
    esac
  fi

  # Catalyst 3750X-48P contribution: Gi member/0/1-48 are the access ports.
  # The C3KX network module can expose Gi aliases for cages also represented
  # by Te names; suppress those aliases so one physical cage is counted once.
  if [ "${CV_CAP_MODEL_TEXT:-}" = "WS-C3750X-48P" ]; then
    case "$name" in
      GigabitEthernet*|Gi*)
        short_name=$(printf '%s' "$name" | sed -E 's/^GigabitEthernet//; s/^Gi//')
        slot_number=$(printf '%s' "$short_name" | awk -F/ 'NF == 3 {print $2}')
        port_number=${short_name##*/}
        case "$port_number" in
          ''|*[!0-9]*) printf 'other' ;;
          *)
            if [ "$slot_number" = "0" ] && [ "$port_number" -ge 1 ] && [ "$port_number" -le 48 ]; then
              printf 'rj45'
            elif [ "$slot_number" = "1" ] && [ "$port_number" -ge 1 ] && [ "$port_number" -le 4 ]; then
              member_number=${short_name%%/*}
              if [ -n "${CV_CAP_IFNAME_LIST:-}" ] && {
                grep -Fxq "Te${member_number}/1/${port_number}" "$CV_CAP_IFNAME_LIST" 2>/dev/null ||
                grep -Fxq "TenGigabitEthernet${member_number}/1/${port_number}" "$CV_CAP_IFNAME_LIST" 2>/dev/null;
              }; then
                printf 'other'
              else
                printf 'sfp'
              fi
            else
              printf 'other'
            fi
            ;;
        esac
        return 0
        ;;
      TenGigabitEthernet*|Te*)
        short_name=$(printf '%s' "$name" | sed -E 's/^TenGigabitEthernet//; s/^Te//')
        slot_number=$(printf '%s' "$short_name" | awk -F/ 'NF == 3 {print $2}')
        port_number=${short_name##*/}
        if [ "$slot_number" = "1" ]; then
          case "$port_number" in 1|2) printf 'sfp_plus' ;; *) printf 'other' ;; esac
        else
          printf 'other'
        fi
        return 0
        ;;
      StackPort*|StackSub*|Stack*) printf 'stack'; return 0 ;;
      Vlan*|Loopback*|Port-channel*|Null*|Control*) printf 'virtual'; return 0 ;;
      *) printf 'other'; return 0 ;;
    esac
  fi

  # Cisco SG350-20 contribution: gi1..gi20 are the 20 logical front-panel
  # positions. Keep the two dual-personality combo positions neutral as
  # `uplink`; do not guess whether copper or SFP is populated from ifName alone.
  if [ "${CV_CAP_MODEL_TEXT:-}" = "SG350-20" ]; then
    case "$name" in
      gi*|Gi*)
        port_number=$(printf '%s' "$name" | sed -E 's/^[Gg][Ii]//')
        case "$port_number" in
          ''|*[!0-9]*) printf 'other' ;;
          *)
            if [ "$port_number" -ge 1 ] && [ "$port_number" -le 16 ]; then
              printf 'rj45'
            elif [ "$port_number" -ge 17 ] && [ "$port_number" -le 18 ]; then
              printf 'uplink'
            elif [ "$port_number" -ge 19 ] && [ "$port_number" -le 20 ]; then
              printf 'sfp'
            else
              printf 'other'
            fi
            ;;
        esac
        return 0
        ;;
      *) printf 'other'; return 0 ;;
    esac
  fi

  # UniFi Pro HD 24 PoE contribution: 0/1-0/24 are copper and 0/25-0/28
  # are SFP+. The compact model string is normalized by model_identity.sh.
  if [ "${CV_CAP_MODEL_TEXT:-}" = "USW Pro HD 24 PoE" ]; then
    case "$name" in
      0/*)
        port_number=${name#0/}
        case "$port_number" in
          ''|*[!0-9]*) printf 'other' ;;
          *)
            if [ "$port_number" -ge 1 ] && [ "$port_number" -le 24 ]; then
              printf 'rj45'
            elif [ "$port_number" -ge 25 ] && [ "$port_number" -le 28 ]; then
              printf 'sfp_plus'
            else
              printf 'other'
            fi
            ;;
        esac
        return 0
        ;;
      *) printf 'other'; return 0 ;;
    esac
  fi

  # UniFi Pro XG 8 PoE contribution: 0/1-0/8 copper, 0/9-0/10 SFP+.
  if [ "${CV_CAP_MODEL_TEXT:-}" = "USW Pro XG 8 PoE" ]; then
    case "$name" in
      0/*)
        port_number=${name#0/}
        case "$port_number" in
          ''|*[!0-9]*) printf 'other' ;;
          *)
            if [ "$port_number" -ge 1 ] && [ "$port_number" -le 8 ]; then
              printf 'rj45'
            elif [ "$port_number" -ge 9 ] && [ "$port_number" -le 10 ]; then
              printf 'sfp_plus'
            else
              printf 'other'
            fi
            ;;
        esac
        return 0
        ;;
      *) printf 'other'; return 0 ;;
    esac
  fi

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
            if [ "$slot_number" = "0" ] && [ "$port_number" -ge 1 ] && [ "$port_number" -le 28 ]; then
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
            if [ "$slot_number" = "0" ]; then printf 'sfp_plus'; else printf 'other'; fi
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
      case "$name" in *.*) printf 'other'; return 0 ;; esac
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
      case "$short_name" in 0/0|0|*/0/0) printf 'other'; return 0 ;; esac

      if [ "${CV_CAP_PLATFORM:-generic}" = "c3750_48p" ]; then
        case "$short_name" in [0-9]*/0/[1-4]) printf 'sfp' ;; *) printf 'other' ;; esac
        return 0
      fi

      if [ "${CV_CAP_FRONT_PANEL_AWARE:-false}" = "true" ]; then
        if [ "${CV_CAP_PLATFORM:-generic}" = "c3650" ]; then
          slot_number=$(printf '%s' "$short_name" | awk -F/ 'NF >= 3 {print $(NF-1)}')
          if [ -n "$slot_number" ] && [ "$slot_number" != "0" ]; then printf 'sfp'; return 0; fi
        fi
        port_number=${short_name##*/}
        case "$port_number" in
          ''|*[!0-9]*) : ;;
          *)
            if [ "$port_number" -gt "${CV_CAP_RJ45_LIMIT:-48}" ]; then
              if [ "${CV_CAP_PLATFORM:-generic}" = "huawei_s5720_12tp_li_ac" ] && [ "$port_number" -le 12 ]; then
                printf 'sfp'
              elif [ "${CV_CAP_PLATFORM:-generic}" = "c2960" ]; then
                case "$CV_CAP_MODEL_TEXT" in
                  *C2960S-48FPD*|*C2960X-48FPD*)
                    alias_number=$((port_number - CV_CAP_RJ45_LIMIT))
                    if [ -n "${CV_CAP_IFNAME_LIST:-}" ] && {
                      grep -Fxq "Te1/0/$alias_number" "$CV_CAP_IFNAME_LIST" 2>/dev/null ||
                      grep -Fxq "TenGigabitEthernet1/0/$alias_number" "$CV_CAP_IFNAME_LIST" 2>/dev/null;
                    }; then printf 'other'; else printf 'sfp'; fi
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
            if [ "$slot_number" = "0" ] && [ "$port_number" -ge 1 ] && [ "$port_number" -le 48 ]; then printf 'rj45'; else printf 'other'; fi
            ;;
        esac
      else
        case "$short_name" in 0|0/0|*/0/0) printf 'other' ;; *) printf 'rj45' ;; esac
      fi
      ;;
    swp0[0-9])
      if [ "${CV_CAP_PLATFORM:-generic}" = "zyxel_xs1930_10" ]; then
        port_number=${name#swp0}
        case "$port_number" in [0-7]) printf 'rj45' ;; 8|9) printf 'sfp_plus' ;; *) printf 'other' ;; esac
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
