from __future__ import annotations

from pathlib import Path

ROOT = Path(".")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        raise SystemExit(f"missing expected text in {path}: {old[:160]!r}")
    write(path, text.replace(old, new, 1))


# Version contract.
replace_once("switch_vision_discovery/config.yaml", 'version: "2.1.41"', 'version: "2.1.42"')
replace_once("runtime_src/run.sh", 'SWITCH_VISION_DISCOVERY_VERSION="2.1.41"', 'SWITCH_VISION_DISCOVERY_VERSION="2.1.42"')
replace_once("runtime_src/discovery_job.sh", 'SWITCH_VISION_DISCOVERY_VERSION="2.1.41"', 'SWITCH_VISION_DISCOVERY_VERSION="2.1.42"')

# The declarative 3750 profile already exists. Wire the normalized capability
# classifier to the exact physical contract instead of letting Gi ports fall
# through the generic RJ45 classification.
replace_once(
    "runtime_src/opt/switch-vision/vendors/interface.sh",
    "    *C2960S*|*C2960X*)\n",
    '''    *C3750-48P*)
      CV_CAP_FRONT_PANEL_AWARE="true"
      CV_CAP_PLATFORM="c3750_48p"
      CV_CAP_RJ45_LIMIT="48"
      ;;
    *C2960S*|*C2960X*)
''',
)
replace_once(
    "runtime_src/opt/switch-vision/vendors/interface.sh",
    '''      if [ "${CV_CAP_FRONT_PANEL_AWARE:-false}" = "true" ]; then
''',
    '''      if [ "${CV_CAP_PLATFORM:-generic}" = "c3750_48p" ]; then
        case "$short_name" in
          [0-9]*/0/[1-4]) printf 'sfp' ;;
          *) printf 'other' ;;
        esac
        return 0
      fi

      if [ "${CV_CAP_FRONT_PANEL_AWARE:-false}" = "true" ]; then
''',
)
replace_once(
    "runtime_src/opt/switch-vision/vendors/interface.sh",
    '''    FastEthernet*|Fa*)
      short_name=$(printf '%s' "$name" | sed -E 's/^FastEthernet//; s/^Fa//')
      case "$short_name" in
        0|0/0|*/0/0) printf 'other' ;;
        *) printf 'rj45' ;;
      esac
      ;;
''',
    '''    FastEthernet*|Fa*)
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
''',
)

# Patch the legacy parser/generator path as well; the YAML profile metadata is
# informational and does not itself drive these embedded AWK mappings.
path = "runtime_src/discovery_job.sh"
text = read(path)
old_regex = "WS-C(3650|3750X|3560CG|2960X|2960S)-[A-Z0-9-]+"
new_regex = "WS-C(3650|3750X|3750|3560CG|2960X|2960S)-[A-Z0-9-]+"
count = text.count(old_regex)
if count < 4:
    raise SystemExit(f"expected Catalyst model regex >=4 times, found {count}")
text = text.replace(old_regex, new_regex)

old = '      if (model ~ /^WS-C3750X/) return "experimental"\n'
new = '      if (model ~ /^WS-C3750-48P/) return "experimental"\n      if (model ~ /^WS-C3750X/) return "experimental"\n'
if old not in text:
    raise SystemExit("missing profile status anchor")
text = text.replace(old, new, 1)

anchor = '''        if (model == "SG500X-24" && n ~ /^gi1\\/[0-9]+$/) {
'''
insert = '''        if (model == "WS-C3750-48P" && n ~ /^(Fa|FastEthernet)[0-9]+\\/0\\/([1-9]|[1-3][0-9]|4[0-8])$/) {
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
        } else if (model == "WS-C3750-48P" && n ~ /^(Gi|GigabitEthernet)[0-9]+\\/0\\/[1-4]$/) {
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
        } else if (model == "SG500X-24" && n ~ /^gi1\\/[0-9]+$/) {
'''
if anchor not in text:
    raise SystemExit("missing parser special-classification anchor")
text = text.replace(anchor, insert, 1)

old = '''      } else if (model == "XS1930-10") {
        print "- RJ45 swp00-swp07 ports: " rj45
'''
new = '''      } else if (model == "WS-C3750-48P") {
        print "- RJ45 FastEthernet <member>/0/1-48 ports: " rj45
        print "- 1G SFP GigabitEthernet <member>/0/1-4 uplinks: " sfp_gi
      } else if (model == "XS1930-10") {
        print "- RJ45 swp00-swp07 ports: " rj45
'''
if old not in text:
    raise SystemExit("missing interface summary anchor")
text = text.replace(old, new, 1)

old = '      else if (model ~ /^WS-C3750X-24P/) profile = "cisco-3750x-24p"\n'
new = '      else if (model ~ /^WS-C3750-48P/) profile = "cisco-3750-48p-48fe-4sfp"\n      else if (model ~ /^WS-C3750X-24P/) profile = "cisco-3750x-24p"\n'
if old not in text:
    raise SystemExit("missing profile selection anchor")
text = text.replace(old, new, 1)

anchor = '''        if (model == "N2128PX-ON" && name ~ /^(Gi|GigabitEthernet|Te|TenGigabitEthernet)[0-9]+\\/0\\/[0-9]+$/) {
'''
insert = '''        if (model == "WS-C3750-48P" && name ~ /^(Fa|FastEthernet)[0-9]+\\/0\\/([1-9]|[1-3][0-9]|4[0-8])$/) {
          c3750_key = name
          sub(/^FastEthernet/, "", c3750_key)
          sub(/^Fa/, "", c3750_key)
          split(c3750_key, cp, "/")
          mapped_rows++; print "  - ifIndex " idx " -> " name " -> member " (cp[1] + 0) " RJ45 FastEthernet port " (cp[3] + 0)
          continue
        }
        if (model == "WS-C3750-48P" && name ~ /^(Gi|GigabitEthernet)[0-9]+\\/0\\/[1-4]$/) {
          c3750_key = name
          sub(/^GigabitEthernet/, "", c3750_key)
          sub(/^Gi/, "", c3750_key)
          split(c3750_key, cp, "/")
          mapped_rows++; print "  - ifIndex " idx " -> " name " -> member " (cp[1] + 0) " 1G SFP uplink " (cp[3] + 0)
          continue
        }
        if (model == "N2128PX-ON" && name ~ /^(Gi|GigabitEthernet|Te|TenGigabitEthernet)[0-9]+\\/0\\/[0-9]+$/) {
'''
if anchor not in text:
    raise SystemExit("missing mapping report anchor")
text = text.replace(anchor, insert, 1)

old = '      else if (model ~ /^WS-C3750X/) print "- WARN: Catalyst 3750X model detected; possible/experimental only, not supported"\n'
new = '      else if (model ~ /^WS-C3750-48P/) print "- INFO: Catalyst 3750 Experimental exact 48 FastEthernet + 4 x 1G SFP mapping loaded"\n      else if (model ~ /^WS-C3750X/) print "- WARN: Catalyst 3750X model detected; possible/experimental only, not supported"\n'
if old not in text:
    raise SystemExit("missing Discovery checks anchor")
text = text.replace(old, new, 1)

old = '((model ~ /^WS-C3650/ || model ~ /^WS-C3750X/ || is_2960(model)) && if_total > 0 && physical_if > 0 && trunk_status_count > 0)'
new = '((model ~ /^WS-C3650/ || model ~ /^WS-C3750X/ || is_2960(model)) && if_total > 0 && physical_if > 0 && trunk_status_count > 0) || (model == "WS-C3750-48P" && if_total > 0 && stack_member_count > 0 && rj45 == (48 * stack_member_count) && sfp_gi == (4 * stack_member_count))'
if old not in text:
    raise SystemExit("missing ready expression")
text = text.replace(old, new, 1)

old = '''      } else if (model ~ /^WS-C3750X-24P/) {
        print "- Suggested profile: cisco-3750x-24p"
'''
new = '''      } else if (model ~ /^WS-C3750-48P/) {
        print "- Suggested profile: cisco-3750-48p-48fe-4sfp"
        print "- Confidence: experimental; exact 48 FastEthernet + 4 x 1G SFP physical contract"
        print "- Support status: experimental / field revalidation required"
      } else if (model ~ /^WS-C3750X-24P/) {
        print "- Suggested profile: cisco-3750x-24p"
'''
if old not in text:
    raise SystemExit("missing recommendation anchor")
text = text.replace(old, new, 1)

# Generator exact model marker.
old = '      if (line ~ /N2128PX-ON/) dell_model="N2128PX-ON"\n'
new = '      if (line ~ /N2128PX-ON/) dell_model="N2128PX-ON"\n      if (line ~ /WS-C3750-48P/) c3750_model="WS-C3750-48P"\n'
if old not in text:
    raise SystemExit("missing generator model anchor")
text = text.replace(old, new, 1)

old = '''      else if (dell_model != "") {
        model = dell_model
        manufacturer = "Dell"
      }
      else if (local_model != "") model = local_model
'''
new = '''      else if (dell_model != "") {
        model = dell_model
        manufacturer = "Dell"
      }
      else if (c3750_model != "") model = c3750_model
      else if (local_model != "") model = local_model
'''
if old not in text:
    raise SystemExit("missing generator model selection anchor")
text = text.replace(old, new, 1)

anchor = '''        if (sg500_model != "" && val ~ /^(gi|te)1\\/[0-9]+$/) {
'''
insert = '''        if (c3750_model != "" && val ~ /^(Fa|FastEthernet)[0-9]+\\/0\\/([1-9]|[1-3][0-9]|4[0-8])$/) {
          physical_count++
          c3750_key=val
          sub(/^FastEthernet/, "", c3750_key)
          sub(/^Fa/, "", c3750_key)
          split(c3750_key, c3750_parts, "/")
          physical_member[c3750_parts[1] + 0] = 1
        } else if (c3750_model != "" && val ~ /^(Gi|GigabitEthernet)[0-9]+\\/0\\/[1-4]$/) {
          physical_count++
          c3750_key=val
          sub(/^GigabitEthernet/, "", c3750_key)
          sub(/^Gi/, "", c3750_key)
          split(c3750_key, c3750_parts, "/")
          physical_member[c3750_parts[1] + 0] = 1
        } else if (sg500_model != "" && val ~ /^(gi|te)1\\/[0-9]+$/) {
'''
if anchor not in text:
    raise SystemExit("missing generator physical count anchor")
text = text.replace(anchor, insert, 1)

anchor = '''      if (model == "N2128PX-ON" && name ~ /^(Gi|GigabitEthernet|Te|TenGigabitEthernet)[0-9]+\\/0\\/[0-9]+$/) {
'''
insert = '''      if (model == "WS-C3750-48P" && name ~ /^(Fa|FastEthernet)[0-9]+\\/0\\/([1-9]|[1-3][0-9]|4[0-8])$/) {
        key=name
        sub(/^FastEthernet/, "", key)
        sub(/^Fa/, "", key)
        split(key, parts, "/")
        return member_label(parts[1] + 0) " Port " (parts[3] + 0)
      }
      if (model == "WS-C3750-48P" && name ~ /^(Gi|GigabitEthernet)[0-9]+\\/0\\/[1-4]$/) {
        key=name
        sub(/^GigabitEthernet/, "", key)
        sub(/^Gi/, "", key)
        split(key, parts, "/")
        return member_label(parts[1] + 0) " SFP 1G " (parts[3] + 0)
      }
      if (model == "N2128PX-ON" && name ~ /^(Gi|GigabitEthernet|Te|TenGigabitEthernet)[0-9]+\\/0\\/[0-9]+$/) {
'''
if anchor not in text:
    raise SystemExit("missing physical label anchor")
text = text.replace(anchor, insert, 1)

old = '''      if (model == "S5720-12TP-LI-AC" && label ~ /(^| )SFP 1G /) return 1000
      return 0
'''
new = '''      if (model == "S5720-12TP-LI-AC" && label ~ /(^| )SFP 1G /) return 1000
      if (model == "WS-C3750-48P" && label ~ / Port /) return 100
      if (model == "WS-C3750-48P" && label ~ / SFP 1G /) return 1000
      return 0
'''
if old not in text:
    raise SystemExit("missing speed cap anchor")
text = text.replace(old, new, 1)

old = '(model == "SG500X-24" && name ~ /^(gi|te)1\\/[0-9]+$/)'
new = '(model == "WS-C3750-48P" && name ~ /^(Fa|FastEthernet)[0-9]+\\/0\\/([1-9]|[1-3][0-9]|4[0-8])$/) || (model == "WS-C3750-48P" && name ~ /^(Gi|GigabitEthernet)[0-9]+\\/0\\/[1-4]$/) || ' + old
if old not in text:
    raise SystemExit("missing physical list condition")
text = text.replace(old, new, 1)

old = '*S5720-12TP-LI-AC*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_1g_{port}_status" ;;'
new = '*S5720-12TP-LI-AC*|*WS-C3750-48P*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_1g_{port}_status" ;;'
count = text.count(old)
if count < 2:
    raise SystemExit(f"expected two generated-card SFP template anchors, found {count}")
text = text.replace(old, new)
write(path, text)

# Generic registry -> real profile referential integrity.
path = "tools/check_component_contracts.py"
text = read(path)
old = '''    discovery_registry_path = Path(
        "runtime_src/opt/switch-vision/devices/supported_devices.json"
    )
'''
new = old + '    discovery_profiles_path = Path("runtime_src/profiles/switch-vision-profiles.yaml")\n'
if old not in text:
    raise SystemExit("missing component contract path anchor")
text = text.replace(old, new, 1)
old = '''    discovery_registry = json.loads(discovery_registry_path.read_text(encoding="utf-8"))
    core_registry = json.loads(fetch_text(args.core_registry_url))
'''
new = '''    discovery_registry = json.loads(discovery_registry_path.read_text(encoding="utf-8"))
    profile_payload = yaml.safe_load(discovery_profiles_path.read_text(encoding="utf-8")) or {}
    discovery_profiles = profile_payload.get("profiles") or {}
    if not isinstance(discovery_profiles, dict):
        errors.append("Discovery profile file does not contain a profiles mapping")
        discovery_profiles = {}
    for item in discovery_registry.get("devices", []):
        if not isinstance(item, dict):
            continue
        model = str(item.get("model") or "").strip() or "<unknown>"
        mapping_profile = str(item.get("mapping_profile") or "").strip()
        if mapping_profile and mapping_profile not in discovery_profiles:
            errors.append(f"{model}: mapping_profile {mapping_profile!r} is not defined in shipped profiles")
    core_registry = json.loads(fetch_text(args.core_registry_url))
'''
if old not in text:
    raise SystemExit("missing component contract registry anchor")
write(path, text.replace(old, new, 1))

# Existing declared-contract regression also pins stock visual geometry.
path = "tools/test_c3750_48p_contract.py"
text = read(path)
old = 'assert device["mapping_profile"] == "cisco-3750-48p-48fe-4sfp"\n'
new = old + 'assert device["default_faceplate"] == "faceplates/48rj45-4sfp.png"\nassert device["calibration_profile"] == "default_cisco_48_port"\n'
if old not in text:
    raise SystemExit("missing c3750 contract anchor")
write(path, text.replace(old, new, 1))

# End-to-end synthetic walk: exercise the actual capability classifier, parser,
# generator labels and speed caps rather than only checking metadata.
write(
    "tools/test_c3750_48p_live_mapping.py",
    r'''from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

with tempfile.TemporaryDirectory(prefix="sv-c3750-") as td:
    work = Path(td)
    walk = work / "c3750.txt"
    report = work / "report.txt"
    generated = work / "generated.yaml"
    card = work / "card.yaml"
    targets = work / "targets.csv"
    last_run = work / "last-run.txt"
    caps = work / "capabilities"
    options = work / "options.json"

    lines = [
        '.1.3.6.1.2.1.1.1.0 = STRING: "Cisco IOS Software, WS-C3750-48P"',
        '.1.3.6.1.2.1.1.5.0 = STRING: "c3750-test"',
    ]
    idx = 1
    for port in range(1, 49):
        lines.append(f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: "Fa1/0/{port}"')
        lines.append(f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: up(1)')
        lines.append(f'.1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 100')
        idx += 1
    for port in range(1, 5):
        lines.append(f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: "Gi1/0/{port}"')
        lines.append(f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: up(1)')
        lines.append(f'.1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 1000')
        idx += 1
    walk.write_text("\n".join(lines) + "\n", encoding="utf-8")
    targets.write_text(
        f"switch name,switch host,sensor prefix,switch snmp community,output_dir,display name\n{walk.name},192.0.2.10,C3750,public,{work},C3750\n",
        encoding="utf-8",
    )
    options.write_text(
        json.dumps({
            "input_path": str(walk),
            "snmpwalks_dir": str(work),
            "report_path": str(report),
            "parse_all_walks": True,
            "generate_snmp2mqtt": True,
            "targets_csv": str(targets),
            "generated_yaml_path": str(generated),
            "generated_card_path": str(card),
            "last_run_summary_path": str(last_run),
            "run_snmp_walks": False,
            "enable_switch_list": False,
        }),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update({
        "SWITCH_VISION_OPTIONS_FILE": str(options),
        "CV_VENDOR_DIR": str(ROOT / "runtime_src/opt/switch-vision/vendors"),
        "CV_MIB_DATABASE_DIR": str(ROOT / "runtime_src/opt/switch-vision/mib_database"),
        "SWITCH_VISION_CAPABILITIES_DIR": str(caps),
    })
    result = subprocess.run(
        ["sh", str(ROOT / "runtime_src/discovery_job.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout

    report_text = report.read_text(encoding="utf-8")
    assert "Model/platform: WS-C3750-48P" in report_text, report_text
    assert "- Physical switch interfaces detected: 52" in report_text, report_text
    assert "- RJ45 FastEthernet <member>/0/1-48 ports: 48" in report_text, report_text
    assert "- 1G SFP GigabitEthernet <member>/0/1-4 uplinks: 4" in report_text, report_text
    assert "- Matched profile: cisco-3750-48p-48fe-4sfp" in report_text, report_text

    cap_files = list(caps.glob("*-capabilities.json"))
    assert cap_files, "normalized capabilities JSON was not generated"
    cap = json.loads(cap_files[0].read_text(encoding="utf-8"))
    summary = cap["summary"]
    assert summary["physical_count"] == 52, summary
    assert summary["rj45_count"] == 48, summary
    assert summary["sfp_count"] == 4, summary
    assert summary["sfp_plus_count"] == 0, summary
    assert summary["uplink_count"] == 4, summary

    yaml_text = generated.read_text(encoding="utf-8")
    assert "C3750 Port 48 Status" in yaml_text, yaml_text
    assert "C3750 SFP 1G 4 Status" in yaml_text, yaml_text
    assert "C3750 Port 49 Status" not in yaml_text, yaml_text
    assert "C3750 SFP 10G" not in yaml_text, yaml_text
    assert "[value | int, 100] | min" in yaml_text, "FastEthernet speed cap missing"
    assert "[value | int, 1000] | min" in yaml_text, "1G SFP speed cap missing"

print("Switch Vision Discovery Catalyst 3750 live mapping: PASS")
''',
)

# Add the live regression to permanent component CI.
path = ".github/workflows/check-component-contracts.yml"
text = read(path)
anchor = '''      - name: Check Catalyst 3750 exact-model contract
        run: python3 tools/test_c3750_48p_contract.py
'''
addition = anchor + '''      - name: Check Catalyst 3750 live 48+4 mapping
        run: python3 tools/test_c3750_48p_live_mapping.py
'''
if anchor not in text:
    raise SystemExit("missing c3750 workflow anchor")
write(path, text.replace(anchor, addition, 1))

# Public release notes.
path = "switch_vision_discovery/CHANGELOG.md"
text = read(path)
entry = '''## 2.1.42

- Correct live Cisco `WS-C3750-48P` interface classification to the stock 48-RJ45 + 4-SFP layout: 48 × 10/100 FastEthernet access ports plus four physical 1G SFP uplinks.
- Prevent `Gi<member>/0/1-4` on this exact model from falling through the generic Catalyst RJ45 classifier.
- Generate the four uplinks as 1G SFP entities, cap FastEthernet capability at 100 Mbps and SFP capability at 1000 Mbps, and keep SFP+ disabled for this model.
- Add a synthetic end-to-end 3750 walk regression proving 52 physical interfaces, 48 RJ45, four 1G SFP uplinks, correct generated YAML labels, and the stock `48rj45-4sfp.png` visual contract.
- Add generic registry-to-profile referential-integrity validation so any exact device that names a missing mapping profile fails CI.

'''
header = "# Changelog\n\n"
if not text.startswith(header):
    raise SystemExit("unexpected changelog header")
write(path, header + entry + text[len(header):])

write(
    "switch_vision_discovery/release-fragments/2.1.42.md",
    '''# Discovery 2.1.42

- Fix Cisco WS-C3750-48P live classification to 48 FastEthernet RJ45 + 4 x 1G SFP on the stock 48+4 faceplate.
- Keep FastEthernet capped at 100 Mbps and the four SFP cages capped at 1G; no SFP+ is advertised.
- Add end-to-end synthetic-walk and registry/profile integrity regressions so the 48+4 mapping is exercised by CI rather than only declared in metadata.
- Public release text remains anonymous and contains no private contribution identifiers.
''',
)
