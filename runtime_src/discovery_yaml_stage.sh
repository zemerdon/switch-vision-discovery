# Switch Vision Discovery generated-YAML stage module.
# Sourced by discovery_job.sh after shared walk/target helpers are defined.
# Keep generated-YAML behavior shell-native; this module is an extraction boundary.

write_generated_yaml_for_walk() {
  walk_file="$1"
  target_ip="$2"
  prefix="$3"
  community="$4"
  member_map="${5:-}"
  source_name=$(basename "$walk_file")
  source_key=$(basename "$(dirname "$walk_file")")
  generator_raw_tmp="/tmp/switch_vision_generator_raw_$$.yaml"
  rm -f "$generator_raw_tmp"
  if [ "$target_ip" = "unknown" ] || [ -z "$target_ip" ]; then
    echo "# ERROR: Missing management target for $source_name; generated YAML refused."
    return 1
  fi

  awk -v host="$target_ip" -v prefix="$prefix" -v community="$community" -v source_name="$source_name" -v source_key="$source_key" -v member_map="$member_map" '
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
    function oid_pair_key(line, s, parts, n) {
      s = line
      sub(/[[:space:]]*=.*/, "", s)
      sub(/^\./, "", s)
      n = split(s, parts, ".")
      if (n < 2) return ""
      return parts[n-1] "." parts[n]
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
      if (m ~ /^WS-C2960XR-48/ || m ~ /^WS-C2960X-48/ || m ~ /^WS-C2960S-48/) return 48
      return 48
    }
    function physical_label(name, idx, key, parts, member, port, label) {
      if (model == "SR-S25G3420F" && name ~ /^HisgmiiEthernet([1-9]|1[0-6])$/) {
        port=name
        sub(/^HisgmiiEthernet/, "", port)
        return prefix " Port " (port + 0)
      }
      if (model == "SR-S25G3420F" && name ~ /^TenGigabitEthernet[1-4]$/) {
        port=name
        sub(/^TenGigabitEthernet/, "", port)
        return prefix " SFP 10G " (port + 0)
      }
      if (model == "WS-C3850-12XS-E" && name ~ /^(Te|TenGigabitEthernet)[0-9]+\/0\/([1-9]|1[0-2])$/) {
        key = name
        sub(/^TenGigabitEthernet/, "", key)
        sub(/^Te/, "", key)
        split(key, parts, "/")
        return member_label(parts[1] + 0) " SFP 10G " (parts[3] + 0)
      }
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
      if (model == "HP J9774A 2530-8G-PoEP" && name ~ /^([1-9]|10)$/) {
        port = name + 0
        return prefix " Port " port
      }
      if (model == "HP ProCurve 1810G-24" && name ~ /^([1-9]|1[0-9]|2[0-4])$/) {
        port = name + 0
        return prefix " Port " port
      }
      if (model == "HP J8693A Switch 3500yl-48G" && name ~ /^([1-9]|[1-3][0-9]|4[0-8])$/) {
        port = name + 0
        return prefix " Port " port
      }
      if (model == "HP J8693A Switch 3500yl-48G" && name ~ /^A[1-4]$/) {
        port = name
        sub(/^A/, "", port)
        return prefix " Rear 10G " (port + 0)
      }
      if (model == "3524GT-PWR+" && name ~ /^(Gi|GigabitEthernet)1\/0\/([1-9]|1[0-9]|20)$/) {
        port = name
        sub(/^GigabitEthernet1\/0\//, "", port)
        sub(/^Gi1\/0\//, "", port)
        return prefix " Port " (port + 0)
      }
      if (model == "3524GT-PWR+" && name ~ /^(Gi|GigabitEthernet)1\/1\/[1-4]$/) {
        port = name
        sub(/^GigabitEthernet1\/1\//, "", port)
        sub(/^Gi1\/1\//, "", port)
        return prefix " SFP 1G " (port + 0)
      }
      if (model == "N4032F" && name ~ /^(Te|TenGigabitEthernet)1\/0\/([1-9]|1[0-9]|2[0-4])$/) {
        port = name
        sub(/^TenGigabitEthernet1\/0\//, "", port)
        sub(/^Te1\/0\//, "", port)
        return prefix " SFP 10G " (port + 0)
      }
      if (model == "N4032F" && name ~ /^(Fo|FortyGigabitEthernet)1\/1\/[12]$/) {
        port = name
        sub(/^FortyGigabitEthernet1\/1\//, "", port)
        sub(/^Fo1\/1\//, "", port)
        return prefix " Rear QSFP 40G " (port + 0)
      }
      if (model == "SG350-20" && name ~ /^[Gg][Ii]([1-9]|1[0-9]|20)$/) {
        port = name
        sub(/^[Gg][Ii]/, "", port)
        port += 0
        if (port <= 18) return prefix " Port " port
        return prefix " SFP 1G " (port - 16)
      }
      if (model == "SG200-26" && name ~ /^[Gg][Ii]([1-9]|1[0-9]|2[0-6])$/) {
        port = name
        sub(/^[Gg][Ii]/, "", port)
        port += 0
        return prefix " Port " port
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
      if (model == "GS1915-24EP" && name ~ /^swp(0[0-9]|1[0-9]|2[0-3])$/) {
        port = name; sub(/^swp/, "", port)
        return prefix " Port " ((port + 0) + 1)
      }
      if (model == "GS1900-8" && name ~ /^GigabitEthernet[1-8]$/) {
        port = name; sub(/^GigabitEthernet/, "", port)
        return prefix " Port " (port + 0)
      }
      if (model == "CRS328-24P-4S+" && name ~ /^ether([1-9]|1[0-9]|2[0-4])$/) {
        port = name; sub(/^ether/, "", port)
        return prefix " Port " (port + 0)
      }
      if (model == "CRS328-24P-4S+" && name ~ /^sfp-sfpplus[1-4]$/) {
        port = name; sub(/^sfp-sfpplus/, "", port)
        return prefix " SFP 10G " (port + 0)
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
      if (is_2960(model) && (name ~ /^Gi/ || name ~ /^GigabitEthernet/) && parts[2] == "0" && port > c2960_rj45_limit(model)) {
        # 24-port Catalyst 2960X models expose Gi1/0/25-28 as four physical
        # 1G SFP cages. Preserve the IOS source identity, but publish them in
        # the card/entity namespace as SFP 1G 1-4 to match the faceplate.
        if (model ~ /^(WS-)?C2960X-24/ || model ~ /^WS-C2960XR-48LPS-I$/) return label " SFP 1G " (port - c2960_rj45_limit(model))
        return label " Uplink " (port - c2960_rj45_limit(model))
      }
      if (is_2960(model) && (name ~ /^Te/ || name ~ /^TenGigabitEthernet/) && parts[2] == "0") return label " SFP 10G " port
      if ((name ~ /^Gi/ || name ~ /^GigabitEthernet/) && parts[2] == "0") return label " Port " port
      if ((model ~ /^(WS-)?C2960X-24/ || model ~ /^WS-C2960XR-48LPS-I$/) && (name ~ /^Gi/ || name ~ /^GigabitEthernet/) && parts[2] == "1") return label " SFP 1G " port
      if ((name ~ /^Gi/ || name ~ /^GigabitEthernet/) && parts[2] == "1") return label " Uplink " port
      if ((name ~ /^Te/ || name ~ /^TenGigabitEthernet/) && parts[2] == "1") return label " SFP 10G " port
      return label " Interface " idx
    }
    function cisco_poe_port_label(ent_idx, candidate, label) {
      candidate = ent_name[ent_idx]
      if (candidate != "") {
        label = physical_label(candidate, ent_idx)
        if (label ~ / Port [0-9]+$/) return label
      }
      candidate = ent_descr[ent_idx]
      if (candidate != "") {
        label = physical_label(candidate, ent_idx)
        if (label ~ / Port [0-9]+$/) return label
      }
      return ""
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
    function yaml_sensor_meta(oid, name, transform, unit, device_class, state_class, icon) {
      yaml_sensor(oid, name)
      if (transform != "") print "    transform: " transform
      if (unit != "") print "    unit_of_measurement: \"" unit "\""
      if (device_class != "") print "    device_class: " device_class
      if (state_class != "") print "    state_class: " state_class
      if (icon != "") print "    icon: " icon
    }
    function poe_aggregate_name(name, ordinal) {
      # Preserve the historical primary entity identity for the first
      # chassis/PSE aggregate. Some devices expose multiple aggregate rows;
      # suffix only repeated names so generated Home Assistant identities
      # remain globally unique without model- or vendor-specific exceptions.
      ordinal = ++poe_aggregate_name_count[name]
      if (ordinal == 1) return name
      return name " Group " ordinal
    }
    function yaml_poe_aggregate_sensor(oid, name) {
      yaml_sensor(oid, poe_aggregate_name(name))
    }
    function yaml_poe_aggregate_sensor_meta(oid, name, transform, unit, device_class, state_class, icon) {
      yaml_sensor_meta(oid, poe_aggregate_name(name), transform, unit, device_class, state_class, icon)
    }
    function physical_speed_cap_mbps(model, label) {
      if (model == "SR-S25G3420F" && label ~ / Port /) return 2500
      if (model == "SR-S25G3420F" && label ~ / SFP 10G /) return 10000
      if (model == "HP J9774A 2530-8G-PoEP") return 1000
      if (model == "HP ProCurve 1810G-24") return 1000
      if (model == "HP J8693A Switch 3500yl-48G" && label ~ / Rear 10G /) return 10000
      if (model == "HP J8693A Switch 3500yl-48G") return 1000
      if (model == "S5720-12TP-LI-AC" && label ~ /(^| )SFP 1G /) return 1000
      if (model == "WS-C3750-48P" && label ~ / Port /) return 100
      if (model == "WS-C3750-48P" && label ~ / SFP 1G /) return 1000
      return 0
    }
    function yaml_speed_sensor(model, idx, label, has_highspeed, has_ifspeed, cap_mbps) {
      cap_mbps = physical_speed_cap_mbps(model, label)
      if (has_highspeed) {
        yaml_sensor("1.3.6.1.2.1.31.1.1.1.15." idx, label " Speed Mbps")
        if (model == "SR-S25G3420F" && label ~ / Port /) print "    template: \"{{ \047unknown\047 if (value | int) in [0, 1410] else ([value | int, 2500] | min) }}\""
        else if (model == "SR-S25G3420F" && label ~ / SFP 10G /) print "    template: \"{{ \047unknown\047 if (value | int) == 0 else ([value | int, 10000] | min) }}\""
        else if (cap_mbps > 0) print "    template: \"{{ [value | int, " cap_mbps "] | min }}\""
      } else if (has_ifspeed) {
        yaml_sensor("1.3.6.1.2.1.2.2.1.5." idx, label " Speed Bps")
        if (model == "SR-S25G3420F" && label ~ / Port /) print "    template: \"{{ \047unknown\047 if (value | int) in [0, 1410065408] else ([value | int, 2500000000] | min) }}\""
        else if (model == "SR-S25G3420F" && label ~ / SFP 10G /) print "    template: \"{{ \047unknown\047 if (value | int) in [0, 1410065408] else value | int }}\""
        else if (cap_mbps > 4294) print "    template: \"{{ " (cap_mbps * 1000000) " if (value | int) >= 4294967295 else ([value | int, " (cap_mbps * 1000000) "] | min) }}\""
        else if (cap_mbps > 0) print "    template: \"{{ [value | int, " (cap_mbps * 1000000) "] | min }}\""
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
    function yaml_qbridge_vlan_sensor(interface_name, name, attribute, icon) {
      print "  - name: " name
      print "    source: qbridge_vlan"
      print "    interface: " interface_name
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
      model="unknown"; manufacturer="Unknown"; maxidx=0; maxcpu=0; maxpoe=0; maxstdpoe=0; maxtemp=0; maxfan=0; maxpsu=0; maxhostcpu=0; maxmikropoe=0; physical_count=0
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
      if (line ~ /SG350-20/ || line ~ /1\.3\.6\.1\.4\.1\.9\.6\.1\.95\.20\.1/) sg350_model="SG350-20"
      if (line ~ /SG200-26/ || line ~ /1\.3\.6\.1\.4\.1\.9\.6\.1\.88\.26\.1/) sg200_model="SG200-26"
      if (line ~ /S5735-L8P4X-A1/) huawei_s5735_model="S5735-L8P4X-A1"
      if (line ~ /S5720-12TP-LI-AC/) huawei_s5720_model="S5720-12TP-LI-AC"
      if (line ~ /XS1930-10/) zyxel_model="XS1930-10"
      else if (line ~ /GS1915-24EP/) zyxel_model="GS1915-24EP"
      else if ((line ~ /\.1\.3\.6\.1\.2\.1\.1\.1\.0 = / || line ~ /\.1\.3\.6\.1\.4\.1\.890\.1\.15\.3\.1\.11\.0 = /) && line ~ /GS1900-8/) zyxel_model="GS1900-8"
      if (line !~ /\.1\.0\.8802\./ && line ~ /SR-S25G3420F/) sirivision_model="SR-S25G3420F"
      if (line ~ /CRS328-24P-4S\+/) mikrotik_model="CRS328-24P-4S+"
      if (line !~ /\.1\.0\.8802\./ && line !~ /\.3\.6\.1\.4\.1\.9\.9\.23\./ && tolower(line) ~ /j8693a/ && tolower(line) ~ /3500yl-48g/) hp_3500yl_model="HP J8693A Switch 3500yl-48G"
      if ((line ~ /1\.3\.6\.1\.4\.1\.11\.2\.3\.7\.11\.138/) || (line !~ /\.1\.0\.8802\./ && line !~ /\.3\.6\.1\.4\.1\.9\.9\.23\./ && (tolower(line) ~ /j9774a/ || tolower(line) ~ /2530-8g-poep/))) hp_2530_model="HP J9774A 2530-8G-PoEP"
      if ((line ~ /1\.3\.6\.1\.4\.1\.11\.2\.3\.7\.11\.104/) || (line !~ /\.1\.0\.8802\./ && tolower(line) ~ /procurve 1810g[[:space:]]*-[[:space:]]*24/)) hp_1810g_model="HP ProCurve 1810G-24"
      if (line !~ /\.1\.0\.8802\./ && line !~ /\.3\.6\.1\.4\.1\.9\.9\.23\./ && line ~ /N4032F/) dell_n4032f_model="N4032F"
      if (line !~ /\.1\.0\.8802\./ && line !~ /\.3\.6\.1\.4\.1\.9\.9\.23\./ && line ~ /N2128PX-ON/) dell_model="N2128PX-ON"
      if (line !~ /\.1\.0\.8802\./ && line !~ /\.3\.6\.1\.4\.1\.9\.9\.23\./ && line ~ /3524GT-PWR\+/) avaya_model="3524GT-PWR+"
      if (line ~ /WS-C3850-12XS/) c3850_model="WS-C3850-12XS"
      if (line ~ /WS-C3750-48P/) c3750_model="WS-C3750-48P"
      if (match(line, /WS-C(3850|3650|3750X|3750|3560CG|2960XR|2960X|2960S)-[A-Z0-9-]+/)) {
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
        if (c3850_model != "") {
          if (val ~ /^(Te|TenGigabitEthernet)[0-9]+\/0\/([1-9]|1[0-2])$/) {
            physical_count++
            c3850_key=val
            sub(/^TenGigabitEthernet/, "", c3850_key)
            sub(/^Te/, "", c3850_key)
            split(c3850_key, c3850_parts, "/")
            physical_member[c3850_parts[1] + 0] = 1
          }
        } else if (c3750_model != "" && val ~ /^(Fa|FastEthernet)[0-9]+\/0\/([1-9]|[1-3][0-9]|4[0-8])$/) {
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
        } else if (sg350_model != "" && val ~ /^[Gg][Ii]([1-9]|1[0-9]|20)$/) {
          physical_count++
          physical_member[1] = 1
        } else if (sg200_model != "" && val ~ /^[Gg][Ii]([1-9]|1[0-9]|2[0-6])$/) {
          physical_count++
          physical_member[1] = 1
        } else if (sg500_model != "" && val ~ /^(gi|te)1\/[0-9]+$/) {
          physical_count++
          physical_member[1] = 1
        } else if (huawei_s5735_model != "" && val ~ /^(GigabitEthernet|XGigabitEthernet)0\/0\/[0-9]+$/) {
          physical_count++
          physical_member[1] = 1
        } else if (huawei_s5720_model != "" && val ~ /^GigabitEthernet0\/0\/([1-9]|1[0-2])$/) {
          physical_count++
          physical_member[1] = 1
        } else if (sirivision_model != "" && val ~ /^(HisgmiiEthernet([1-9]|1[0-6])|TenGigabitEthernet[1-4])$/) {
          physical_count++
          physical_member[1] = 1
        } else if (zyxel_model == "XS1930-10" && val ~ /^swp0[0-9]$/) {
          physical_count++
          physical_member[1] = 1
        } else if (zyxel_model == "GS1915-24EP" && val ~ /^swp(0[0-9]|1[0-9]|2[0-3])$/) {
          physical_count++
          physical_member[1] = 1
        } else if (zyxel_model == "GS1900-8" && val ~ /^GigabitEthernet[1-8]$/) {
          physical_count++
          physical_member[1] = 1
        } else if (mikrotik_model != "" && val ~ /^(ether([1-9]|1[0-9]|2[0-4])|sfp-sfpplus[1-4])$/) {
          physical_count++
          physical_member[1] = 1
        } else if (hp_2530_model != "" && val ~ /^([1-9]|10)$/) {
          physical_count++
          physical_member[1] = 1
        } else if (hp_1810g_model != "" && val ~ /^([1-9]|1[0-9]|2[0-4])$/) {
          physical_count++
          physical_member[1] = 1
        } else if (hp_3500yl_model != "" && val ~ /^([1-9]|[1-3][0-9]|4[0-8])$/) {
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
      if (line ~ /\.3\.6\.1\.2\.1\.17\.7\.1\.4\.2\.1\.4\.[0-9]+\.[0-9]+ = /) qbridge_current_egress_rows++
      if (line ~ /\.3\.6\.1\.2\.1\.17\.7\.1\.4\.3\.1\.2\.[0-9]+ = /) qbridge_static_egress_rows++
      if (line ~ /\.3\.6\.1\.2\.1\.17\.7\.1\.4\.3\.1\.4\.[0-9]+ = /) qbridge_static_untagged_rows++
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.46\.1\.6\.1\.1\.14\.[0-9]+ = /) { idx=oid_index(line); trunk_status_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.31\.1\.1\.1\.18\.[0-9]+ = /) { idx=oid_index(line); alias_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.31\.1\.1\.1\.6\.[0-9]+ = /) { idx=oid_index(line); hc_in_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.31\.1\.1\.1\.10\.[0-9]+ = /) { idx=oid_index(line); hc_out_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.2\.2\.1\.10\.[0-9]+ = /) { idx=oid_index(line); legacy_in_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.2\.2\.1\.16\.[0-9]+ = /) { idx=oid_index(line); legacy_out_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.31\.1\.1\.1\.15\.[0-9]+ = /) { idx=oid_index(line); highspeed_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.2\.2\.1\.5\.[0-9]+ = /) { idx=oid_index(line); ifspeed_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.25\.3\.3\.1\.2\.[0-9]+ = /) { idx=oid_index(line); host_cpu_idx[idx]=1; if(idx>maxhostcpu) maxhostcpu=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.14988\.1\.1\.3\.100\.1\.2\.[0-9]+ = STRING:/) { idx=oid_index(line); mt_gauge_name[idx]=val; mt_gauge_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.14988\.1\.1\.3\.100\.1\.3\.[0-9]+ = /) { idx=oid_index(line); mt_gauge_value_idx[idx]=1; mt_gauge_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.14988\.1\.1\.3\.100\.1\.4\.[0-9]+ = /) { idx=oid_index(line); mt_gauge_unit[idx]=val+0; mt_gauge_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.14988\.1\.1\.15\.1\.1\.2\.[0-9]+ = STRING:/) { idx=oid_index(line); mt_poe_name[idx]=val; mt_poe_idx[idx]=1; if(idx>maxmikropoe) maxmikropoe=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.14988\.1\.1\.15\.1\.1\.3\.[0-9]+ = /) { idx=oid_index(line); mt_poe_status_idx[idx]=1; mt_poe_idx[idx]=1; if(idx>maxmikropoe) maxmikropoe=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.14988\.1\.1\.15\.1\.1\.4\.[0-9]+ = /) { idx=oid_index(line); mt_poe_voltage_idx[idx]=1; mt_poe_idx[idx]=1; if(idx>maxmikropoe) maxmikropoe=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.14988\.1\.1\.15\.1\.1\.5\.[0-9]+ = /) { idx=oid_index(line); mt_poe_current_idx[idx]=1; mt_poe_idx[idx]=1; if(idx>maxmikropoe) maxmikropoe=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.14988\.1\.1\.15\.1\.1\.6\.[0-9]+ = /) { idx=oid_index(line); mt_poe_power_idx[idx]=1; mt_poe_idx[idx]=1; if(idx>maxmikropoe) maxmikropoe=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.109\.1\.1\.1\.1\.6\.[0-9]+ = Gauge32:/) { idx=oid_index(line); cpu_idx[idx]=1; if(idx>maxcpu) maxcpu=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.109\.1\.1\.1\.1\.7\.[0-9]+ = Gauge32:/) { idx=oid_index(line); cpu_idx[idx]=1; if(idx>maxcpu) maxcpu=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.109\.1\.1\.1\.1\.8\.[0-9]+ = Gauge32:/) { idx=oid_index(line); cpu_idx[idx]=1; if(idx>maxcpu) maxcpu=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.402\.1\.3\.1\.2\.[0-9]+ = /) { idx=oid_index(line); poe_name_idx[idx]=1; poe_idx[idx]=1; if(idx>maxpoe) maxpoe=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.402\.1\.3\.1\.3\.[0-9]+ = /) { idx=oid_index(line); poe_status_idx[idx]=1; poe_idx[idx]=1; if(idx>maxpoe) maxpoe=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.402\.1\.3\.1\.4\.[0-9]+ = /) { idx=oid_index(line); poe_used_idx[idx]=1; poe_idx[idx]=1; if(idx>maxpoe) maxpoe=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.402\.1\.3\.1\.5\.[0-9]+ = /) { idx=oid_index(line); poe_budget_idx[idx]=1; poe_idx[idx]=1; if(idx>maxpoe) maxpoe=idx }

      # Cisco ENVMON fan and power-supply state. These are curated read-only
      # state tables; emit only rows actually returned by the current walk.
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.13\.1\.4\.1\.2\.[0-9]+ = /) { idx=oid_index(line); fan_descr[idx]=val; if(idx>maxfan) maxfan=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.13\.1\.4\.1\.3\.[0-9]+ = /) { idx=oid_index(line); fan_state_idx[idx]=1; if(idx>maxfan) maxfan=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.13\.1\.5\.1\.2\.[0-9]+ = /) { idx=oid_index(line); psu_descr[idx]=val; if(idx>maxpsu) maxpsu=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.13\.1\.5\.1\.3\.[0-9]+ = /) { idx=oid_index(line); psu_state_idx[idx]=1; if(idx>maxpsu) maxpsu=idx }

      # RFC 3621 per-port PoE rows are indexed by group.port and the port
      # numbering itself is implementation-specific. The Cisco extension exposes
      # cpeExtPsePortEntPhyIndex for the authoritative ENTITY-MIB join.
      if (line ~ /\.3\.6\.1\.2\.1\.105\.1\.1\.1\.3\.[0-9]+\.[0-9]+ = /) { key=oid_pair_key(line); std_poe_port_admin[key]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.105\.1\.1\.1\.6\.[0-9]+\.[0-9]+ = /) { key=oid_pair_key(line); std_poe_port_detect[key]=1 }
      if (line ~ /\.3\.6\.1\.2\.1\.105\.1\.1\.1\.10\.[0-9]+\.[0-9]+ = /) { key=oid_pair_key(line); std_poe_port_class[key]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.402\.1\.2\.1\.9\.[0-9]+\.[0-9]+ = /) { key=oid_pair_key(line); cisco_poe_power[key]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.9\.9\.402\.1\.2\.1\.11\.[0-9]+\.[0-9]+ = /) { key=oid_pair_key(line); cisco_poe_entphy[key]=val + 0 }

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

      # ENTITY-MIB physical names/descriptions are also used to join Cisco
      # per-port PoE rows to real front-panel interfaces. A PoE row is never
      # emitted unless this join resolves to one exact physical RJ45 port.
      if (line ~ /\.3\.6\.1\.2\.1\.47\.1\.1\.1\.1\.2\.[0-9]+ = /) {
        idx=oid_index(line); ent_descr[idx]=val
      }
      if (line ~ /\.3\.6\.1\.2\.1\.47\.1\.1\.1\.1\.7\.[0-9]+ = /) {
        idx=oid_index(line); ent_name[idx]=val
      }

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
      # Dell N2128PX-ON optical diagnostics observed in verified field evidence.
      # The table row suffix is the same IF-MIB index used by the two Te uplinks
      # in both current full walks, allowing the diagnostics to bind directly
      # to the evidenced physical SFP+ ports rather than anonymous rows.
      if (line ~ /\.3\.6\.1\.4\.1\.674\.10895\.5000\.2\.6132\.1\.1\.43\.1\.(18|19)\.1\.[0-9]+\.[0-9]+ = /) { idx=oid_index(line); dell_optic_row_idx[idx]=1; if (idx > dell_optic_max_row) dell_optic_max_row=idx }
      if (line ~ /\.3\.6\.1\.4\.1\.674\.10895\.5000\.2\.6132\.1\.1\.43\.1\.18\.1\.2\.[0-9]+ = /) { idx=oid_index(line); dell_optic_temp_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.674\.10895\.5000\.2\.6132\.1\.1\.43\.1\.18\.1\.3\.[0-9]+ = /) { idx=oid_index(line); dell_optic_voltage_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.674\.10895\.5000\.2\.6132\.1\.1\.43\.1\.18\.1\.4\.[0-9]+ = /) { idx=oid_index(line); dell_optic_current_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.674\.10895\.5000\.2\.6132\.1\.1\.43\.1\.18\.1\.5\.[0-9]+ = /) { idx=oid_index(line); dell_optic_tx_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.674\.10895\.5000\.2\.6132\.1\.1\.43\.1\.18\.1\.6\.[0-9]+ = /) { idx=oid_index(line); dell_optic_rx_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.674\.10895\.5000\.2\.6132\.1\.1\.43\.1\.18\.1\.9\.[0-9]+ = /) { idx=oid_index(line); dell_optic_status_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.674\.10895\.5000\.2\.6132\.1\.1\.43\.1\.19\.1\.2\.[0-9]+ = /) { idx=oid_index(line); dell_optic_vendor_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.674\.10895\.5000\.2\.6132\.1\.1\.43\.1\.19\.1\.6\.[0-9]+ = /) { idx=oid_index(line); dell_optic_part_idx[idx]=1 }
      if (line ~ /\.3\.6\.1\.4\.1\.674\.10895\.5000\.2\.6132\.1\.1\.43\.1\.19\.1\.9\.[0-9]+ = /) { idx=oid_index(line); dell_optic_type_idx[idx]=1 }
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
      else if (dell_model != "") {
        model = dell_model
        manufacturer = "Dell"
      }
      else if (sirivision_model != "") {
        model = sirivision_model
        manufacturer = "Sirivision"
      }
      else if (c3750_model != "") { model = c3750_model; manufacturer = "Cisco" }
      else if (local_model != "") { model = local_model; manufacturer = "Cisco" }
      else if (sys_model != "") { model = sys_model; manufacturer = "Cisco" }
      else if (candidate_model != "") { model = candidate_model; manufacturer = "Cisco" }
      else if (generic_model != "") { model = generic_model; manufacturer = "Cisco" }
      print "# Device source: " source_name
      print "# Switch key: " source_key
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
        if ((model == "SR-S25G3420F" && name ~ /^(HisgmiiEthernet([1-9]|1[0-6])|TenGigabitEthernet[1-4])$/) || (model == "WS-C3750-48P" && name ~ /^(Fa|FastEthernet)[0-9]+\/0\/([1-9]|[1-3][0-9]|4[0-8])$/) || (model == "WS-C3750-48P" && name ~ /^(Gi|GigabitEthernet)[0-9]+\/0\/[1-4]$/) || (model == "SG350-20" && name ~ /^[Gg][Ii]([1-9]|1[0-9]|20)$/) || (model == "SG200-26" && name ~ /^[Gg][Ii]([1-9]|1[0-9]|2[0-6])$/) || (model == "SG500X-24" && name ~ /^(gi|te)1\/[0-9]+$/) || (model == "S5735-L8P4X-A1" && name ~ /^(GigabitEthernet|XGigabitEthernet)0\/0\/[0-9]+$/) || (model == "S5720-12TP-LI-AC" && name ~ /^GigabitEthernet0\/0\/([1-9]|1[0-2])$/) || (model == "XS1930-10" && name ~ /^swp0[0-9]$/) || (model == "GS1915-24EP" && name ~ /^swp(0[0-9]|1[0-9]|2[0-3])$/) || (model == "GS1900-8" && name ~ /^GigabitEthernet[1-8]$/) || (model == "HP J9774A 2530-8G-PoEP" && name ~ /^([1-9]|10)$/) || (model == "HP ProCurve 1810G-24" && name ~ /^([1-9]|1[0-9]|2[0-4])$/) || ((model == "HP J8693A Switch 3500yl-48G" && name ~ /^([1-9]|[1-3][0-9]|4[0-8])$/) || (model == "HP J8693A Switch 3500yl-48G" && name ~ /^A[1-4]$/)) || (model == "N4032F" && name ~ /^(Fo|FortyGigabitEthernet)1\/1\/[12]$/) || name ~ /^(Gi|GigabitEthernet|Te|TenGigabitEthernet)[0-9]+\/[0-9]+\/[0-9]+$/ || (model ~ /^WS-C3560CG-8PC/ && name ~ /^(Gi|GigabitEthernet)0\/([1-9]|10)$/) || name ~ /^ge-0\/0\/[0-9]+$/ || name ~ /^(xe|ge)-0\/1\/[0-3]$/ || (model == "CRS328-24P-4S+" && name ~ /^(ether([1-9]|1[0-9]|2[0-4])|sfp-sfpplus[1-4])$/)) {
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

      # Resolve Cisco PoE table rows to the same physical labels used by the
      # dashboard. If multiple PSE rows resolve to one physical port, mark that
      # port ambiguous and emit nothing for it.
      if (manufacturer == "Cisco") {
        for (key in cisco_poe_entphy) {
          ent_idx=cisco_poe_entphy[key] + 0
          if (ent_idx <= 0) continue
          poe_label=cisco_poe_port_label(ent_idx)
          if (poe_label == "") continue
          for (i=1; i<=phys_n; i++) {
            if (phys_label[i] == poe_label) {
              if (poe_key_for_phys[i] == "") poe_key_for_phys[i]=key
              else if (poe_key_for_phys[i] != key) poe_key_for_phys[i]="AMBIGUOUS"
            }
          }
        }
      }

      # Reviewed GS1915-24EP field evidence exposes one RFC 3621 PSE group
      # whose port indexes 1-12 align exactly with IF-MIB swp00-swp11 /
      # physical ports 1-12. Keep this mapping exact-model and fail closed if
      # either the IF-MIB identity or the standard PSE row is absent.
      if (model == "GS1915-24EP") {
        for (i=1; i<=phys_n; i++) {
          idx=phys_idx[i] + 0
          if (idx < 1 || idx > 12) continue
          expected_name=sprintf("swp%02d", idx - 1)
          if (ifname[idx] != expected_name) continue
          key="1." idx
          if ((key in std_poe_port_admin) || (key in std_poe_port_detect) || (key in std_poe_port_class)) {
            poe_key_for_phys[i]=key
          }
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
      if (model == "GS1900-8") print "# Walk-aware VLAN source: Q-BRIDGE PVID rows=" qbridge_pvid_rows ", current egress rows=" (qbridge_current_egress_rows + 0) ", static egress rows=" (qbridge_static_egress_rows + 0) ", static untagged rows=" (qbridge_static_untagged_rows + 0)
      else if (model == "XS1930-10") print "# Walk-aware VLAN source: Q-BRIDGE PVID rows=" qbridge_pvid_rows "; trunk/access mode is not inferred"
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

      # Cisco per-port PoE is emitted only for an exact ENTITY-MIB join.
      # Keep chunks small to avoid oversized grouped SNMP requests.
      poe_chunk=0
      for (start=1; start<=phys_n; start+=8) {
        stop=start + 7
        if (stop > phys_n) stop=phys_n
        poe_sensor_count=0
        for (i=start; i<=stop; i++) {
          key=poe_key_for_phys[i]
          if (key == "" || key == "AMBIGUOUS") continue
          if ((key in std_poe_port_detect) || (key in std_poe_port_class) || (key in cisco_poe_power)) poe_sensor_count++
        }
        if (poe_sensor_count > 0) {
          poe_chunk++
          yaml_target_header("Switch Vision " chunk_label(start) " PoE Ports " sprintf("%02d", poe_chunk), 30)
          for (i=start; i<=stop; i++) {
            key=poe_key_for_phys[i]
            if (key == "" || key == "AMBIGUOUS") continue
            label=phys_label[i]
            if (model == "GS1915-24EP" && (key in std_poe_port_admin)) yaml_sensor("1.3.6.1.2.1.105.1.1.1.3." key, label " PoE Admin Code")
            if (key in std_poe_port_detect) yaml_sensor("1.3.6.1.2.1.105.1.1.1.6." key, label " PoE Status Code")
            if (key in std_poe_port_class) yaml_sensor("1.3.6.1.2.1.105.1.1.1.10." key, label " PoE Class Code")
            if (key in cisco_poe_power) yaml_sensor_meta("1.3.6.1.4.1.9.9.402.1.2.1.9." key, label " PoE Power", "value / 1000", "W", "power", "measurement", "mdi:flash")
          }
        }
      }

      if (model == "Juniper EX3300-48P") {
        # EX3300 uplink identity/state watcher: keep the four dual-personality cages on a fast,
        # lightweight cadence while traffic/VLAN/slow groups retain their normal intervals.
        yaml_target_header("Switch Vision " prefix " SFP Status", 5)
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

      if (model == "N2128PX-ON" && dell_optic_max_row > 0) {
        yaml_target_header("Switch Vision " prefix " Optical diagnostics", 30)
        for (idx=1; idx<=dell_optic_max_row; idx++) if ((idx in dell_optic_row_idx) && (idx in ifname) && ifname[idx] ~ /^(Te|TenGigabitEthernet)[0-9]+\/0\/[12]$/) {
          label=physical_label(ifname[idx], idx)
          if (idx in dell_optic_temp_idx) yaml_sensor_meta("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.18.1.2." idx, label " Temperature", "value / 10", "°C", "temperature", "measurement", "mdi:thermometer")
          if (idx in dell_optic_voltage_idx) yaml_sensor_meta("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.18.1.3." idx, label " Voltage", "value / 1000", "V", "voltage", "measurement", "mdi:current-dc")
          if (idx in dell_optic_current_idx) yaml_sensor_meta("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.18.1.4." idx, label " Current", "value / 10", "mA", "current", "measurement", "mdi:current-dc")
          if (idx in dell_optic_tx_idx) yaml_sensor_meta("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.18.1.5." idx, label " TX Optical Power", "value / 1000", "dBm", "", "measurement", "mdi:laser-pointer")
          if (idx in dell_optic_rx_idx) yaml_sensor_meta("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.18.1.6." idx, label " RX Optical Power", "value / 1000", "dBm", "", "measurement", "mdi:signal")
          if (idx in dell_optic_status_idx) yaml_sensor("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.18.1.9." idx, label " Optical Status")
          if (idx in dell_optic_vendor_idx) yaml_sensor("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.19.1.2." idx, label " Transceiver Vendor")
          if (idx in dell_optic_part_idx) yaml_sensor("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.19.1.6." idx, label " Transceiver Part")
          if (idx in dell_optic_type_idx) yaml_sensor("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.19.1.9." idx, label " Media Type")
        }
      }

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
          if (!vlan_emitted && ((model == "XS1930-10" && ifname[idx] ~ /^swp0[0-9]$/) || (model == "GS1915-24EP" && ifname[idx] ~ /^swp(0[0-9]|1[0-9]|2[0-3])$/))) {
            bridge_idx=bridge_for_ifindex[idx]
            if (bridge_idx > 0 && (bridge_idx in qbridge_pvid_idx)) {
              yaml_sensor("1.3.6.1.2.1.17.7.1.4.5.1.1." bridge_idx, label " VLAN ID")
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
              yaml_sensor("1.3.6.1.2.1.17.7.1.4.5.1.1." bridge_idx, label " VLAN ID")
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

      if (model == "GS1900-8") {
        qbridge_join_count=0
        for (i=1; i<=phys_n; i++) {
          idx=phys_idx[i]
          bridge_idx=bridge_for_ifindex[idx]
          if (bridge_idx > 0 && (bridge_idx in qbridge_pvid_idx)) qbridge_join_count++
        }
        qbridge_membership_ready=((qbridge_current_egress_rows + qbridge_static_egress_rows) > 0 && qbridge_static_untagged_rows > 0)
        if (phys_n > 0 && qbridge_join_count == phys_n && qbridge_membership_ready) {
          yaml_target_header("Switch Vision " prefix " Q-BRIDGE VLAN State", 30)
          qbridge_derived_count=0
          for (i=1; i<=phys_n; i++) {
            idx=phys_idx[i]
            interface_name=ifname[idx]
            label=phys_label[i]
            yaml_qbridge_vlan_sensor(interface_name, label " VLAN Mode", "mode", "mdi:lan-connect")
            yaml_qbridge_vlan_sensor(interface_name, label " Native VLAN", "native_vlan", "mdi:tag-outline")
            yaml_qbridge_vlan_sensor(interface_name, label " VLANs", "vlans", "mdi:tag-multiple-outline")
            yaml_qbridge_vlan_sensor(interface_name, label " Tagged VLANs", "tagged_vlans", "mdi:tag-multiple")
            yaml_qbridge_vlan_sensor(interface_name, label " Untagged VLANs", "untagged_vlans", "mdi:tag-off-outline")
            qbridge_derived_count += 5
          }
          print "# Q-BRIDGE derived VLAN sensors emitted: " qbridge_derived_count
        } else {
          print "# Q-BRIDGE derived VLAN sensors skipped: physical=" phys_n ", joins=" qbridge_join_count ", current egress rows=" (qbridge_current_egress_rows + 0) ", static egress rows=" (qbridge_static_egress_rows + 0) ", static untagged rows=" (qbridge_static_untagged_rows + 0)
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
      if (model == "SR-S25G3420F") {
        print "  - name: " prefix " Uptime"
        print "    source: sirivision_uptime"
      } else {
        yaml_sensor("1.3.6.1.2.1.1.3.0", prefix " Uptime")
      }

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
      # Multiple ENTITY-MIB rows can describe one member. Select one observed
      # row per entity, preferring entPhysicalModelName over description and
      # then the lowest index, rather than publishing competing bindings.
      for (idx in identity_idx) {
        member_no=int(idx / 1000)
        if (member_no < 1) member_no=1
        label=member_label(member_no)
        rank=(idx in identity_model_name_idx) ? 0 : 1
        prior=model_identity_index[label]
        if (!prior || rank < model_identity_rank[label] || (rank == model_identity_rank[label] && idx+0 < prior+0)) {
          model_identity_index[label]=idx
          model_identity_rank[label]=rank
        }
        if ((idx in identity_serial_idx) && (!serial_identity_index[label] || idx+0 < serial_identity_index[label]+0)) serial_identity_index[label]=idx
      }
      for (label in model_identity_index) {
        idx=model_identity_index[label]
        if (idx in identity_model_name_idx) yaml_sensor("1.3.6.1.2.1.47.1.1.1.1.13." idx, label " Model")
        else yaml_sensor("1.3.6.1.2.1.47.1.1.1.1.2." idx, label " Model")
      }
      for (label in serial_identity_index) {
        idx=serial_identity_index[label]
        yaml_sensor("1.3.6.1.2.1.47.1.1.1.1.11." idx, label " Serial")
      }

      if (model == "XS1930-10" || model == "GS1915-24EP") {
        if (zyxel_model_present) yaml_sensor("1.3.6.1.4.1.890.1.15.3.1.11.0", prefix " Model")
        if (zyxel_firmware_present) yaml_sensor("1.3.6.1.4.1.890.1.15.3.1.6.0", prefix " Firmware")
        if (zyxel_serial_present) yaml_sensor("1.3.6.1.4.1.890.1.15.3.1.12.0", prefix " Serial")
      }

      # MikroTik CRS328 real-hardware contribution evidence exposes CPU via
      # HOST-RESOURCES-MIB, health gauges via MIKROTIK-MIB mtxrGaugeTable and
      # per-port PoE via mtxrPOETable. Emit only rows proven present in the
      # current walk. The gauge table reports engineering units directly;
      # dW/dV table columns are converted to W/V with safe SNMP2MQTT transforms.
      if (model == "CRS328-24P-4S+") {
        primary_cpu=0
        for (idx=1; idx<=maxhostcpu; idx++) if (idx in host_cpu_idx) {
          if (!primary_cpu) {
            yaml_sensor_meta("1.3.6.1.2.1.25.3.3.1.2." idx, prefix " CPU", "", "%", "", "measurement", "mdi:cpu-64-bit")
            primary_cpu=1
          } else {
            yaml_sensor_meta("1.3.6.1.2.1.25.3.3.1.2." idx, prefix " CPU " idx, "", "%", "", "measurement", "mdi:cpu-64-bit")
          }
        }
        for (idx in mt_gauge_idx) if ((idx in mt_gauge_value_idx) && (idx in mt_gauge_unit)) {
          lname=tolower(mt_gauge_name[idx])
          unit_code=mt_gauge_unit[idx]
          if (lname == "cpu-temperature" && unit_code == 1) {
            yaml_sensor_meta("1.3.6.1.4.1.14988.1.1.3.100.1.3." idx, prefix " Temperature", "", "°C", "temperature", "measurement", "mdi:thermometer")
          } else if (lname ~ /^board-temperature/ && unit_code == 1) {
            yaml_sensor_meta("1.3.6.1.4.1.14988.1.1.3.100.1.3." idx, prefix " Board Temperature", "", "°C", "temperature", "measurement", "mdi:thermometer")
          } else if (lname == "poe-out-consumption" && unit_code == 5) {
            yaml_poe_aggregate_sensor_meta("1.3.6.1.4.1.14988.1.1.3.100.1.3." idx, prefix " PoE Used", "value / 10", "W", "power", "measurement", "mdi:flash")
          } else if (lname ~ /^fan[0-9]+-speed$/ && unit_code == 2) {
            fan_label=lname; sub(/^fan/, "", fan_label); sub(/-speed$/, "", fan_label)
            yaml_sensor_meta("1.3.6.1.4.1.14988.1.1.3.100.1.3." idx, prefix " Fan " fan_label " RPM", "", "rpm", "", "measurement", "mdi:fan")
          } else if (lname ~ /^psu[0-9]+-voltage$/ && unit_code == 3) {
            psu_label=lname; sub(/^psu/, "", psu_label); sub(/-voltage$/, "", psu_label)
            yaml_sensor_meta("1.3.6.1.4.1.14988.1.1.3.100.1.3." idx, prefix " PSU " psu_label " Voltage", "value / 10", "V", "voltage", "measurement", "mdi:current-dc")
          } else if (lname ~ /^psu[0-9]+-current$/ && unit_code == 4) {
            psu_label=lname; sub(/^psu/, "", psu_label); sub(/-current$/, "", psu_label)
            yaml_sensor_meta("1.3.6.1.4.1.14988.1.1.3.100.1.3." idx, prefix " PSU " psu_label " Current", "value / 10", "A", "current", "measurement", "mdi:current-dc")
          }
        }
        for (idx=1; idx<=maxmikropoe; idx++) if (idx in mt_poe_idx) {
          port_name=mt_poe_name[idx]
          port_no=idx
          if (port_name ~ /^ether([1-9]|1[0-9]|2[0-4])$/) { port_no=port_name; sub(/^ether/, "", port_no); port_no += 0 }
          if (port_no >= 1 && port_no <= 24) {
            if (idx in mt_poe_power_idx) yaml_sensor_meta("1.3.6.1.4.1.14988.1.1.15.1.1.6." idx, prefix " Port " port_no " PoE Power", "value / 10", "W", "power", "measurement", "mdi:flash")
            if (idx in mt_poe_voltage_idx) yaml_sensor_meta("1.3.6.1.4.1.14988.1.1.15.1.1.4." idx, prefix " Port " port_no " PoE Voltage", "value / 10", "V", "voltage", "measurement", "mdi:current-dc")
            if (idx in mt_poe_current_idx) yaml_sensor_meta("1.3.6.1.4.1.14988.1.1.15.1.1.5." idx, prefix " Port " port_no " PoE Current", "", "mA", "current", "measurement", "mdi:current-dc")
            if (idx in mt_poe_status_idx) yaml_sensor("1.3.6.1.4.1.14988.1.1.15.1.1.3." idx, prefix " Port " port_no " PoE Status Code")
          }
        }
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
            if (suffix in jnx_state) yaml_sensor("1.3.6.1.4.1.2636.3.1.13.1.6." suffix, prefix " Fan " suffix " State")
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
        if (zyxel_memory_present) yaml_sensor("1.3.6.1.4.1.890.1.15.3.2.4.3", prefix " Memory Utilization")
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

      # Cisco ENVMON fan/PSU state sensors. Keep per-member naming when the
      # ENVMON description identifies a stack member; standalone switches use
      # the configured prefix unchanged.
      delete fan_member_count
      for (idx=1; idx<=maxfan; idx++) if (idx in fan_state_idx) {
        member=temp_member(fan_descr[idx])
        fan_member_count[member]++
        label=member_label(member)
        yaml_sensor("1.3.6.1.4.1.9.9.13.1.4.1.3." idx, label " Fan " fan_member_count[member] " State")
      }
      delete psu_member_count
      for (idx=1; idx<=maxpsu; idx++) if (idx in psu_state_idx) {
        member=temp_member(psu_descr[idx])
        psu_member_count[member]++
        label=member_label(member)
        yaml_sensor("1.3.6.1.4.1.9.9.13.1.5.1.3." idx, label " PSU " psu_member_count[member] " State")
      }

      for (idx=1; idx<=maxpoe; idx++) if (idx in poe_idx) {
        label=member_label(idx)
        if (idx in poe_name_idx) yaml_poe_aggregate_sensor("1.3.6.1.4.1.9.9.402.1.3.1.2." idx, label " PoE Supply Name")
        if (idx in poe_status_idx) yaml_poe_aggregate_sensor("1.3.6.1.4.1.9.9.402.1.3.1.3." idx, label " PoE Supply Status")
        poe_unit = (model ~ /2960X|2960S/ ? "W" : "mW")
        if (idx in poe_used_idx) yaml_poe_aggregate_sensor("1.3.6.1.4.1.9.9.402.1.3.1.4." idx, label " PoE Used " poe_unit)
        if (idx in poe_budget_idx) yaml_poe_aggregate_sensor("1.3.6.1.4.1.9.9.402.1.3.1.5." idx, label " PoE Budget " poe_unit)
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
        if (!ext_used_present && (idx in std_poe_used_idx)) yaml_poe_aggregate_sensor("1.3.6.1.2.1.105.1.3.1.1.4." idx, label " PoE Used W")
        if (!ext_budget_present && (idx in std_poe_budget_idx)) yaml_poe_aggregate_sensor("1.3.6.1.2.1.105.1.3.1.1.2." idx, label " PoE Budget W")
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

new_generated_yaml_id() {
  # This is an opaque, high-entropy load marker.  It is deliberately not a
  # credential fingerprint or a hash of generated YAML (which can include a
  # low-entropy SNMP community).  SNMP2MQTT reports it only after parsing this
  # exact file, allowing Discovery to distinguish configuration activation
  # from later retained discovery publication.
  if [ -r /proc/sys/kernel/random/uuid ]; then
    tr '[:upper:]' '[:lower:]' < /proc/sys/kernel/random/uuid | tr -d '\\n'
    return 0
  fi
  if command -v uuidgen >/dev/null 2>&1; then
    uuidgen | tr '[:upper:]' '[:lower:]'
    return 0
  fi
  return 1
}

write_generated_yaml() {
  tmp_walks="$1"
  GENERATED_YAML_PUBLISHED="false"
  GENERATED_YAML_GENERATOR_FAILED="false"
  GENERATED_YAML_PREVIOUS_STATE="unknown"
  candidate_path="${GENERATED_YAML_PATH}.candidate.$$"
  GENERATED_YAML_GENERATION_ID=$(new_generated_yaml_id) || {
    echo "Generated YAML candidate refused: secure generation ID is unavailable." >> "$LIVE_LOG_PATH" 2>/dev/null || true
    return 0
  }
  guard="/generated_yaml_guard.py"
  [ -f "$guard" ] || guard="$(dirname "$0")/generated_yaml_guard.py"
  echo "Generating SNMP2MQTT YAML candidate: $candidate_path" >> "$LIVE_LOG_PATH" 2>/dev/null || true
  rm -f "$candidate_path"
  {
    echo "# Switch Vision generated SNMP2MQTT YAML"
    echo "# Switch Vision generation ID: $GENERATED_YAML_GENERATION_ID"
    echo "# Source: Switch Vision Discovery v$SWITCH_VISION_DISCOVERY_VERSION"
    echo "# Product: Switch Vision"
    echo "# Product source: Switch Vision Discovery v$SWITCH_VISION_DISCOVERY_VERSION"
    echo "# Generated: $(date -Iseconds)"
    echo "# Authoritative Discovery handoff. Switch Vision SNMP2MQTT imports this file after a successful Discovery run."
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
