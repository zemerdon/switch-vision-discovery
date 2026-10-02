# Switch Vision Discovery report-stage module.
# Sourced by discovery_job.sh after shared walk/CSV helpers are defined.
# Keep report/parser behavior shell-native; this module is an extraction boundary.

parser_report() {
  walk_file="$1"
  target_ip="$2"
  registry_model=""
  registry_match="no"
  registry_status=""
  registry_mapping_profile=""
  registry_dashboard_support="no"
  if command -v cv_cap_extract_model_text >/dev/null 2>&1 && [ -f "$REGISTRY_LOOKUP" ]; then
    registry_model=$(cv_cap_extract_model_text "$walk_file")
    registry_report=$(python3 "$REGISTRY_LOOKUP" --registry "$DEVICE_REGISTRY" --model "$registry_model" --report 2>/dev/null || true)
    registry_match=$(printf '%s\n' "$registry_report" | awk -F': ' '/^- Registry match:/ {print $2; exit}')
    registry_status=$(printf '%s\n' "$registry_report" | awk -F': ' '/^- Registry status:/ {print $2; exit}')
    registry_mapping_profile=$(printf '%s\n' "$registry_report" | awk -F': ' '/^- Mapping profile:/ {print $2; exit}')
    registry_dashboard_support=$(printf '%s\n' "$registry_report" | awk -F': ' '/^- Dashboard support:/ {print $2; exit}')
  fi
  awk -v target_ip="$target_ip" -v generator_enabled="$GENERATE_SNMP2MQTT" -v source_walk="$walk_file" -v registry_model="$registry_model" -v registry_match="$registry_match" -v registry_status="$registry_status" -v registry_mapping_profile="$registry_mapping_profile" -v registry_dashboard_support="$registry_dashboard_support" '
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
      if (m ~ /^WS-C2960XR-48/ || m ~ /^WS-C2960X-48/ || m ~ /^WS-C2960S-48/) return 48
      return 48
    }
    function c2960_profile(m) {
      if (m ~ /^WS-C2960XR-48LPS-I$/) return "cisco-2960xr-48lps-48p-4sfp"
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
      if (m ~ /^WS-C2960XR-48LPS-I$/) return 4
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
      if (registry_status == "community_validated") return "community_validated"
      if (registry_status == "experimental") return "experimental"
      if (registry_status == "detected") return "detected"
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
      if (model == "CRS328-24P-4S+") return "experimental"
      if (model == "Juniper EX3300-48P") return "supported"
      return "unsupported"
    }
    function support_line(status) {
      if (status == "supported") return "supported"
      if (status == "community_validated") return "community validated"
      if (status == "experimental") return "experimental / partially validated"
      if (status == "detected") return "detected / exact model known"
      if (status == "untested") return "untested / needs validation"
      return "unsupported"
    }
    function validation_note(status) {
      if (status == "supported") return "Validated in Switch Vision live testing."
      if (status == "community_validated") return "Independent real-hardware field validation is recorded for this exact model."
      if (status == "experimental") return "Model detected and mapped, but not fully validated on all physical port types."
      if (status == "detected") return "Exact model is registered, but the complete implementation contract is still pending."
      if (status == "untested") return "Family detected, but this exact layout is not validated yet."
      return "No validated Switch Vision profile matched this device."
    }
    function sfp_note(status, model) {
      if (status == "supported") return "validated"
      if (status == "community_validated") return "real-hardware validated"
      if (is_2960(model)) return "generated from SNMP layout; physical SFP validation pending"
      if (model == "SG500X-24" || model == "S5735-L8P4X-A1" || model == "S5720-12TP-LI-AC" || model == "XS1930-10" || model == "GS1915-24EP" || model == "N2128PX-ON" || model == "CRS328-24P-4S+") return "generated from contribution-backed interface names; contributor/live validation pending"
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
      if (line ~ /SG350-20/ || line ~ /1\.3\.6\.1\.4\.1\.9\.6\.1\.95\.20\.1/) sg350_model = "SG350-20"
      if (line ~ /SG200-26/ || line ~ /1\.3\.6\.1\.4\.1\.9\.6\.1\.88\.26\.1/) sg200_model = "SG200-26"
      if (line ~ /S5735-L8P4X-A1/) huawei_s5735_model = "S5735-L8P4X-A1"
      if (line ~ /S5720-12TP-LI-AC/) huawei_s5720_model = "S5720-12TP-LI-AC"
      if (line ~ /XS1930-10/) zyxel_model = "XS1930-10"
      else if (line ~ /GS1915-24EP/) zyxel_model = "GS1915-24EP"
      if (line ~ /CRS328-24P-4S\+/) mikrotik_model = "CRS328-24P-4S+"
      if (line !~ /\.1\.0\.8802\./ && line !~ /\.3\.6\.1\.4\.1\.9\.9\.23\./ && tolower(line) ~ /j8693a/ && tolower(line) ~ /3500yl-48g/) hp_3500yl_model = "HP J8693A Switch 3500yl-48G"
      if ((line ~ /1\.3\.6\.1\.4\.1\.11\.2\.3\.7\.11\.138/) || (line !~ /\.1\.0\.8802\./ && line !~ /\.3\.6\.1\.4\.1\.9\.9\.23\./ && (tolower(line) ~ /j9774a/ || tolower(line) ~ /2530-8g-poep/))) hp_2530_model = "HP J9774A 2530-8G-PoEP"
      if ((line ~ /1\.3\.6\.1\.4\.1\.11\.2\.3\.7\.11\.104/) || (line !~ /\.1\.0\.8802\./ && tolower(line) ~ /procurve 1810g[[:space:]]*-[[:space:]]*24/)) hp_1810g_model = "HP ProCurve 1810G-24"
      if (line !~ /\.1\.0\.8802\./ && line !~ /\.3\.6\.1\.4\.1\.9\.9\.23\./ && line ~ /N4032F/) dell_n4032f_model = "N4032F"
      if (line !~ /\.1\.0\.8802\./ && line !~ /\.3\.6\.1\.4\.1\.9\.9\.23\./ && line ~ /N2128PX-ON/) dell_model = "N2128PX-ON"
      if (line !~ /\.1\.0\.8802\./ && line !~ /\.3\.6\.1\.4\.1\.9\.9\.23\./ && line ~ /3524GT-PWR\+/) avaya_model = "3524GT-PWR+"
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
      if (match(line, /WS-C(3850|3650|3750X|3750|3560CG|2960XR|2960X|2960S)-[A-Z0-9-]+/)) {
        model_candidate = substr(line, RSTART, RLENGTH)
        if (line ~ /\.3\.6\.1\.2\.1\.47\.1\.1\.1\.1\.(2|7|13)\./ || line ~ /\.3\.6\.1\.4\.1\.9\.5\.1\./) {
          if (model_rank(model_candidate) > model_rank(local_model)) local_model = model_candidate
        } else if (line ~ /\.3\.6\.1\.2\.1\.1\.1\.0/) {
          if (model_rank(model_candidate) > model_rank(sys_model)) sys_model = model_candidate
        } else if (model_rank(model_candidate) > model_rank(candidate_model)) candidate_model = model_candidate
      }
      if (line ~ /\.3\.6\.1\.2\.1\.1\.1\.0 = /) sys_descr_present=1
      if (line ~ /\.3\.6\.1\.2\.1\.47\.1\.1\.1\.1\.2\.[0-9]+ = STRING:/ && val ~ /WS-C(3850|3650|3750X|3750|3560CG|2960XR|2960X|2960S)-[A-Z0-9-]+/) {
        idx=oid_index(line); identity_model_descr_idx[idx]=1; identity_idx[idx]=1
      }
      if (line ~ /\.3\.6\.1\.2\.1\.47\.1\.1\.1\.1\.13\.[0-9]+ = STRING:/ && val ~ /WS-C(3850|3650|3750X|3750|3560CG|2960XR|2960X|2960S)-[A-Z0-9-]+/) {
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
      if (mikrotik_model != "") {
        model = mikrotik_model
        manufacturer = "MikroTik"
      }
      else if (zyxel_model != "") {
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
      else if (sg350_model != "") {
        model = sg350_model
        manufacturer = "Cisco"
      }
      else if (sg200_model != "") {
        model = sg200_model
        manufacturer = "Cisco"
      }
      else if (sg500_model != "") {
        model = sg500_model
        manufacturer = "Cisco"
      }
      else if (juniper_model != "") {
        model = juniper_model
        manufacturer = "Juniper"
      }
      else if (hp_2530_model != "") {
        model = hp_2530_model
        manufacturer = "HP"
      }
      else if (hp_1810g_model != "") {
        model = hp_1810g_model
        manufacturer = "HP"
      }
      else if (hp_3500yl_model != "") {
        model = hp_3500yl_model
        manufacturer = "HP"
      }
      else if (avaya_model != "") {
        model = avaya_model
        manufacturer = "Avaya"
      }
      else if (dell_n4032f_model != "") {
        model = dell_n4032f_model
        manufacturer = "Dell"
      }
      else if (dell_model != "") model = dell_model
      else if (local_model != "") model = local_model
      else if (sys_model != "") model = sys_model
      else if (candidate_model != "") model = candidate_model
      else if (generic_model != "") model = generic_model
      report_model = model
      if (registry_match == "yes" && registry_model != "") report_model = registry_model
      if (hostname == "unknown" && cisco_hostname != "") hostname = cisco_hostname
      print ""
      print "Discovery parser summary"
      print "------------------------"
      print "Hostname: " hostname
      if (cisco_hostname != "") print "Cisco local hostname: " cisco_hostname
      print "Model/platform: " report_model
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

        if (model == "WS-C3850-12XS-E" && n ~ /^(Te|TenGigabitEthernet)[0-9]+\/0\/([1-9]|1[0-2])$/) {
          c3850_key = n
          sub(/^TenGigabitEthernet/, "", c3850_key)
          sub(/^Te/, "", c3850_key)
          split(c3850_key, cp, "/")
          member = cp[1] + 0
          port = cp[3] + 0
          physical_id = "Te" member "/0/" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1; ten_key[physical_id] = 1
            member_key[member] = 1; member_physical[member]++; member_ten[member]++
          }
          special = 1
        } else if (model == "WS-C3850-12XS-E" && n ~ /^(Te|TenGigabitEthernet)[0-9]+\/1\/[0-9]+$/) {
          # IOS can expose empty network-module-bay interfaces in IF-MIB.
          # They are software-visible but not physical factory front-panel ports.
          special = 1
        } else if (model == "WS-C3750-48P" && n ~ /^(Fa|FastEthernet)[0-9]+\/0\/([1-9]|[1-3][0-9]|4[0-8])$/) {
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
        } else if (model == "GS1915-24EP" && n ~ /^swp(0[0-9]|1[0-9]|2[0-3])$/) {
          port = n; sub(/^swp/, "", port)
          physical_id = "gs1915-swp" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1; rj45_key[physical_id] = 1
            member_key[1] = 1; member_physical[1]++; member_rj45[1]++
          }
          special = 1
        } else if (model == "CRS328-24P-4S+" && n ~ /^ether([1-9]|1[0-9]|2[0-4])$/) {
          port = n; sub(/^ether/, "", port)
          physical_id = "ether" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1; rj45_key[physical_id] = 1
            member_key[1] = 1; member_physical[1]++; member_rj45[1]++
          }
          special = 1
        } else if (model == "CRS328-24P-4S+" && n ~ /^sfp-sfpplus[1-4]$/) {
          port = n; sub(/^sfp-sfpplus/, "", port)
          physical_id = "sfp-sfpplus" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1; ten_key[physical_id] = 1
            member_key[1] = 1; member_physical[1]++; member_ten[1]++
          }
          special = 1
        } else if (model == "HP J9774A 2530-8G-PoEP" && n ~ /^([1-9]|10)$/) {
          port = n + 0
          physical_id = "hp2530-" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1
            member_key[1] = 1
            member_physical[1]++
            if (port <= 8) {
              rj45_key[physical_id] = 1; member_rj45[1]++
            } else {
              sfp_key[physical_id] = 1; member_sfp[1]++
            }
          }
          special = 1
        } else if (model == "HP ProCurve 1810G-24" && n ~ /^([1-9]|1[0-9]|2[0-4])$/) {
          port = n + 0
          physical_id = "hp1810g-" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1
            member_key[1] = 1
            member_physical[1]++
            if (port <= 22) {
              rj45_key[physical_id] = 1; member_rj45[1]++
            } else {
              sfp_key[physical_id] = 1; member_sfp[1]++
            }
          }
          special = 1
        } else if (model == "HP J8693A Switch 3500yl-48G" && n ~ /^([1-9]|[1-3][0-9]|4[0-8])$/) {
          port = n + 0
          physical_id = "hp-" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1
            member_key[1] = 1
            member_physical[1]++
            if (port <= 44) {
              rj45_key[physical_id] = 1; member_rj45[1]++
            } else {
              sfp_key[physical_id] = 1; member_sfp[1]++
            }
          }
          special = 1
        } else if (model == "HP J8693A Switch 3500yl-48G" && n ~ /^A[1-4]$/) {
          port = n
          sub(/^A/, "", port)
          physical_id = "hp-rear-10g-" port
          if (!(physical_id in physical_key)) {
            physical_key[physical_id] = 1; ten_key[physical_id] = 1
            member_key[1] = 1; member_physical[1]++; member_ten[1]++
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
      if (model == "WS-C3850-12XS-E") {
        print "- Fixed 10G SFP+ Te <member>/0/1-12 ports: " ten
        print "- Empty network-module bay Te <member>/1/* rows: non-physical"
      } else if (model == "Juniper EX3300-48P") {
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
      } else if (model == "CRS328-24P-4S+") {
        print "- RJ45 ether1-ether24 ports: " rj45
        print "- 10G SFP+ sfp-sfpplus1-sfp-sfpplus4 uplinks: " ten
      } else if (model == "HP J9774A 2530-8G-PoEP") {
        print "- Fixed PoE+ RJ45 logical ports 1-8: " rj45
        print "- Dual-personality copper/SFP logical ports 9-10: " sfp_gi
      } else if (model == "HP ProCurve 1810G-24") {
        print "- Fixed RJ45 logical ports 1-22: " rj45
        print "- Dual-personality copper/SFP logical ports 23-24: " sfp_gi
      } else if (model == "HP J8693A Switch 3500yl-48G") {
        print "- Fixed RJ45 logical ports 1-44: " rj45
        print "- Dual-personality copper/SFP logical ports 45-48: " sfp_gi
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
      profile_status = profile_status_for(report_model)
      if (registry_mapping_profile != "" && registry_mapping_profile != "not assigned") profile = registry_mapping_profile
      else if (report_model == "WS-C3850-12XS-E") profile = "cisco-3850-12xs-12x10g"
      else if (report_model ~ /^WS-C3650-48/) profile = "cisco-3650-48p-2x10g"
      else if (is_2960(report_model)) profile = c2960_profile(report_model)
      else if (report_model ~ /^WS-C3750-48P/) profile = "cisco-3750-48p-48fe-4sfp"
      else if (report_model ~ /^WS-C3750X-24P/) profile = "cisco-3750x-24p"
      else if (report_model ~ /^WS-C3560CG-8PC/) profile = "cisco-3560cg-8pc-8p-2dual"
      else if (report_model == "Juniper EX3300-48P") profile = "juniper-ex3300-48p"
      else if (report_model == "SG500X-24") profile = "cisco-sg500x-24-24p-4x10g"
      else if (report_model == "S5735-L8P4X-A1") profile = "huawei-s5735-l8p4x-a1"
      else if (report_model == "S5720-12TP-LI-AC") profile = "huawei-s5720-12tp-li-ac"
      else if (report_model == "XS1930-10") profile = "zyxel-xs1930-10"
      else if (report_model == "N2128PX-ON") profile = "dell-n2128px-on"
      else if (report_model == "CRS328-24P-4S+") profile = "mikrotik-crs328-24p-4splus"
      else if (report_model == "UDM Pro") profile = "ubiquiti-udm-pro-api"
      else if (report_model == "US 8 60W") profile = "ubiquiti-us-8-60w-api"
      else if (report_model == "US-8-150W") profile = "ubiquiti-us-8-150w-snmp"
      else if (report_model == "US XG 16") profile = "ubiquiti-us-xg-16-api"
      else if (report_model == "US-24-250W") profile = "ubiquiti-us-24-250w-snmp"
      else if (report_model == "US 48") profile = "ubiquiti-us-48-api"
      else if (report_model ~ /^WS-C3650/) profile = "cisco-3650-auto"
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
        if (model == "GS1915-24EP" && name ~ /^swp(0[0-9]|1[0-9]|2[0-3])$/) {
          port = name; sub(/^swp/, "", port)
          mapped_rows++; print "  - ifIndex " idx " -> " name " -> standalone RJ45 port " ((port + 0) + 1)
          continue
        }
        if (model == "CRS328-24P-4S+" && name ~ /^ether([1-9]|1[0-9]|2[0-4])$/) {
          port = name; sub(/^ether/, "", port)
          mapped_rows++; print "  - ifIndex " idx " -> " name " -> standalone RJ45 port " (port + 0)
          continue
        }
        if (model == "CRS328-24P-4S+" && name ~ /^sfp-sfpplus[1-4]$/) {
          port = name; sub(/^sfp-sfpplus/, "", port)
          mapped_rows++; print "  - ifIndex " idx " -> " name " -> standalone 10G SFP+ uplink " (port + 0)
          continue
        }
        if (model == "HP J9774A 2530-8G-PoEP" && name ~ /^([1-9]|10)$/) {
          port = name + 0
          if (port <= 8) {
            mapped_rows++; print "  - ifIndex " idx " -> " name " -> standalone PoE+ RJ45 port " port
          } else {
            mapped_rows++; print "  - ifIndex " idx " -> " name " -> dual-personality copper/SFP uplink " (port - 8)
          }
          continue
        }
        if (model == "HP ProCurve 1810G-24" && name ~ /^([1-9]|1[0-9]|2[0-4])$/) {
          port = name + 0
          if (port <= 22) {
            mapped_rows++; print "  - ifIndex " idx " -> " name " -> standalone RJ45 port " port
          } else {
            mapped_rows++; print "  - ifIndex " idx " -> " name " -> dual-personality copper/SFP uplink " (port - 22)
          }
          continue
        }
        if (model == "HP J8693A Switch 3500yl-48G" && name ~ /^([1-9]|[1-3][0-9]|4[0-8])$/) {
          port = name + 0
          if (port <= 44) {
            mapped_rows++; print "  - ifIndex " idx " -> " name " -> standalone RJ45 port " port
          } else {
            mapped_rows++; print "  - ifIndex " idx " -> " name " -> dual-personality copper/SFP uplink " (port - 44)
          }
          continue
        }
        if (model == "HP J8693A Switch 3500yl-48G" && name ~ /^A[1-4]$/) {
          port = name
          sub(/^A/, "", port)
          mapped_rows++; print "  - ifIndex " idx " -> " name " -> optional rear 10G module port " (port + 0)
          continue
        }
        if (model == "WS-C3850-12XS-E" && name ~ /^(Te|TenGigabitEthernet)[0-9]+\/0\/([1-9]|1[0-2])$/) {
          c3850_key = name
          sub(/^TenGigabitEthernet/, "", c3850_key)
          sub(/^Te/, "", c3850_key)
          split(c3850_key, cp, "/")
          mapped_rows++; print "  - ifIndex " idx " -> " name " -> member " (cp[1] + 0) " fixed 10G SFP+ port " (cp[3] + 0)
          continue
        }
        if (model == "WS-C3850-12XS-E" && name ~ /^(Te|TenGigabitEthernet)[0-9]+\/1\/[0-9]+$/) {
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
      if (registry_match == "yes") print "- PASS: exact model matched in Switch Vision supported-device registry: " report_model " (" profile_status ")"
      else if (model == "Juniper EX3300-48P") print "- PASS: Juniper EX3300-48P model detected"
      else if (model == "WS-C3850-12XS-E") print "- PASS: Catalyst 3850-12XS exact factory/no-module model detected"
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
      else if (model == "CRS328-24P-4S+") print "- INFO: MikroTik CRS328 Experimental 24 RJ45 + 4 SFP+ mapping loaded from privacy-processed community hardware evidence"
      else print "- WARN: known Switch Vision model not confirmed"
      print (ios != "unknown" ? "- PASS: OS/software version detected" : "- WARN: OS/software version not detected")
      print (if_total > 0 ? "- PASS: usable interface-name table detected" : "- FAIL: neither ifName nor ifDescr interface names detected")
      print (physical_if > 0 ? "- PASS: physical switch interfaces detected" : "- FAIL: physical switch interfaces not detected")
      if (report_model == "Juniper EX3300-48P") print "- PASS: Juniper VLAN/trunk mapping uses Q-BRIDGE-MIB and derived VLAN state"
      else if (report_model == "XS1930-10") print (qbridge_pvid_count > 0 ? "- PASS: Zyxel PVID mapping uses Q-BRIDGE-MIB" : "- WARN: Q-BRIDGE PVID rows not detected")
      else if (profile ~ /^cisco-/) print (trunk_status_count > 0 ? "- PASS: Cisco trunk status OIDs detected" : "- WARN: Cisco trunk status OIDs not detected")
      if (target_ip != "unknown" && target_ip != "") print "- PASS: management target provided: " target_ip
      else print "- WARN: management target not provided; provide a switch_host in the switch list or targets CSV before generator use"
      registry_ready = (registry_match == "yes" && registry_dashboard_support == "yes" && profile != "unknown" && if_total > 0)
      c3850_ready = (model == "WS-C3850-12XS-E" && if_total > 0 && rj45 == 0 && ten == 12)
      ready = (registry_ready || c3850_ready || ((model ~ /^WS-C3650/ || model ~ /^WS-C3750X/ || is_2960(model)) && if_total > 0 && physical_if > 0) || (model == "WS-C3750-48P" && if_total > 0 && stack_member_count > 0 && rj45 == (48 * stack_member_count) && sfp_gi == (4 * stack_member_count)) || ((model == "SG500X-24" || model == "S5735-L8P4X-A1" || model == "S5720-12TP-LI-AC") && if_total > 0 && physical_if > 0) || (model == "XS1930-10" && if_total > 0 && rj45 == 8 && ten == 2 && qbridge_pvid_count > 0) || (model == "N2128PX-ON" && if_total > 0 && stack_member_count > 0 && rj45 == (28 * stack_member_count) && ten == (2 * stack_member_count)) || (model == "CRS328-24P-4S+" && if_total > 0 && rj45 == 24 && ten == 4) || (model == "Juniper EX3300-48P" && if_total > 0 && rj45 == 48) || (model == "UDM Pro" && if_total > 0 && rj45 == 9 && ten == 2) || (model == "US 8 60W" && if_total > 0 && rj45 == 8) || (model == "US-8-150W" && if_total > 0 && rj45 == 8 && sfp_gi == 2) || (model == "US-24-250W" && if_total > 0 && rj45 == 24 && sfp_gi == 2) || (model == "US 48" && if_total > 0 && rj45 == 48 && ten == 2 && sfp_gi == 2))
      print "- Ready for SNMP2MQTT generation: " (ready ? "yes, review-only" : "no")
      if (profile_status == "supported") print "- Generator confidence: supported profile; review generated YAML before installing"
      else if (profile_status == "community_validated") print "- Generator confidence: community-validated profile; physical layout verified on real hardware"
      else if (profile_status == "experimental") print "- Generator confidence: experimental profile; review mapping/YAML before use"
      else if (profile_status == "detected") print "- Generator confidence: exact topology detected; dashboard/profile generation remains disabled pending verified visual support"
      else if (profile_status == "untested") print "- Generator confidence: untested profile; use for lab review only"
      else print "- Generator confidence: unsupported; generator output should not be used"
      print "- SNMP2MQTT generator status: " (generator_enabled == "true" ? "enabled" : "disabled")
      print ""
      print "Model validation:"
      print "- Exact model detected: " ((registry_match == "yes" || report_model != "unknown") ? "yes" : "no")
      print "- Profile status label: " profile_status
      print "- RJ45 mapping: " (rj45 > 0 ? "generated from IF-MIB/interface layout" : "not detected")
      print "- SFP/uplink mapping: " sfp_note(profile_status, report_model)
      if (report_model ~ /^S5720-12TP-LI-AC$/ || report_model ~ /^S5735-L8P4X-A1$/) print "- Faceplate: generic 48 RJ45 + 4 SFP fallback visual"
      else if (report_model == "XS1930-10") print "- Faceplate: compact 8 RJ45 + 2 SFP temporary fallback visual"
      else if (report_model == "N2128PX-ON") print "- Faceplate: dedicated Dell 28 RJ45 + 2 SFP+ visual; current-build alignment confirmed"
      else if (report_model == "CRS328-24P-4S+") print "- Faceplate: neutral 24 RJ45 + 4 SFP temporary fallback visual; exact MikroTik alignment pending"
      else print "- Faceplate: registry-selected visual"
      print ""
      print "VLAN / trunk summary:"
      print "- VLAN name entries: " vlan_count
      if (vlan_names != "") print "- VLAN names seen: " vlan_names
      if (report_model == "Juniper EX3300-48P") {
        print "- Juniper VLAN source: Q-BRIDGE-MIB / derived VLAN sensors"
      } else if (report_model == "XS1930-10") {
        print "- Zyxel VLAN source: Q-BRIDGE-MIB PVID (" qbridge_pvid_count " row(s)); trunk/access mode not inferred"
      } else if (profile ~ /^cisco-/) {
        print "- Cisco dynamic trunk state OIDs: " trunk_dynamic_count
        for (s in trunk_dynamic) print "  - dynamic state " s " (" trunk_label(s) "): " trunk_dynamic[s]
        print "- Cisco trunk status OIDs: " trunk_status_count
        for (s in trunk_status) print "  - trunk status " s " (" trunk_label(s) "): " trunk_status[s]
        for (idx in trunk_status_by_if) {
          if (trunk_status_by_if[idx] == "1" && (idx in ifname)) likely_trunks = add_unique(likely_trunks, ifname[idx])
        }
        if (likely_trunks != "") print "- Likely trunk ports: " likely_trunks
      }
      print ""
      print "Temperature summary:"
      if (profile ~ /^cisco-/) {
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
      }
      print "- ENTITY-MIB temp labels: " entity_temp
      for (i = 1; i <= entity_temp && i <= 8; i++) print "  - " entity_temp_name[i]
      if (entity_temp > 8) print "  - ..."
      print ""
      print "Switch Vision recommendation:"
      if (registry_match == "yes") {
        print "- Suggested profile: " profile
        if (profile_status == "supported") print "- Confidence: high; exact registered model is confirmed supported"
        else if (profile_status == "community_validated") print "- Confidence: high; exact registered model is community validated"
        else if (profile_status == "experimental") print "- Confidence: experimental; exact registered model and mapping profile matched"
        else if (profile_status == "detected") print "- Confidence: detected; exact registry identity is known but the implementation contract is incomplete"
        else print "- Confidence: " profile_status
        print "- Support status: " support_line(profile_status)
        print "- Validation note: " validation_note(profile_status)
      } else if (model == "Juniper EX3300-48P") {
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
      } else if (model == "CRS328-24P-4S+") {
        print "- Suggested profile: mikrotik-crs328-24p-4splus"
        print "- Confidence: experimental; exact 24 ether + 4 sfp-sfpplus physical topology confirmed by privacy-processed community hardware evidence"
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
      if (generator_enabled == "true") print "- Generated SNMP2MQTT YAML is the authoritative Discovery handoff consumed by Switch Vision SNMP2MQTT after a successful handoff."
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
        cap_switch=$(target_switch_for_walk "$walk_file" | sed 's/[^A-Za-z0-9._-]/_/g')
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
        jq --arg detected "$detected_model" --arg override "$model_override" --arg effective "$effective_model" --arg target "$target_ip" --argjson compat "$compatibility_mode" '
          .device.detected_model_text=$detected
          | .device.model_override=(if $override == "auto" then null else $override end)
          | .device.effective_model_text=$effective
          | .device.management_target=(if ($target | length) > 0 and $target != "unknown" then $target else null end)
          | .device.compatibility_mode=$compat
        ' "$cap_path" > "$tmp_cap" && mv "$tmp_cap" "$cap_path"
        if [ -x /standard_sensor_scan.py ]; then
          python3 /standard_sensor_scan.py --walk "$walk_file" --enrich "$cap_path"
        fi
        if [ -x /vendor_sensor_scan.py ]; then
          python3 /vendor_sensor_scan.py --walk "$walk_file" --enrich "$cap_path"
        fi
        registry_model="$detected_model"
        if [ -f "$REGISTRY_LOOKUP" ]; then
          python3 "$REGISTRY_LOOKUP" --registry "$DEVICE_REGISTRY" --model "$detected_model" --enrich "$cap_path" --enrich-key registry
          tmp_cap="${cap_path}.tmp"
          jq 'if (.registry.match // false) then .device.support_status=(.registry.status // .device.support_status) else . end' "$cap_path" > "$tmp_cap" && mv "$tmp_cap" "$cap_path"
          if [ "$model_override" != "auto" ]; then
            python3 "$REGISTRY_LOOKUP" --registry "$DEVICE_REGISTRY" --model "$effective_model" --enrich "$cap_path" --enrich-key model_override_registry
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
        if [ -f "$REGISTRY_LOOKUP" ]; then
          python3 "$REGISTRY_LOOKUP" --registry "$DEVICE_REGISTRY" --model "$registry_model" --report
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
    if [ "${CV_ID_VENDOR:-}" = "cisco" ]; then
      if grep -qi "catalyst\|cisco" "$walk_file"; then
        echo "- Cisco/Catalyst text: found"
      else
        echo "- Cisco/Catalyst text: not found yet"
      fi
    fi
    if grep -q "1.3.6.1.2.1.2.2.1.8" "$walk_file" || grep -q "iso.3.6.1.2.1.2.2.1.8" "$walk_file"; then
      echo "- Interface status OIDs: found"
    else
      echo "- Interface status OIDs: not found yet"
    fi
    if [ "${CV_ID_VENDOR:-}" = "cisco" ]; then
      if awk '/\.3\.6\.1\.4\.1\.9\.9\.46\.1\.6\.1\.1\.14\.[0-9]+ = INTEGER:/ { found=1 } END { exit(found ? 0 : 1) }' "$walk_file"; then
        echo "- Cisco trunk status OIDs: found"
      else
        echo "- Cisco trunk status OIDs: not found yet"
      fi
    fi
    parser_report "$walk_file" "$target_ip"
  else
    echo "SNMP walk file found: no"
  fi
  echo ""
}
