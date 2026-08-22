from pathlib import Path

profiles = Path("runtime_src/profiles/switch-vision-profiles.yaml")
text = profiles.read_text(encoding="utf-8")
profile_name = "ubiquiti-us-48-poe-500w-api"
if f"  {profile_name}:\n" not in text:
    anchor = "  cisco-3750-48p-48fe-4sfp:\n"
    if anchor not in text:
        raise SystemExit("missing Catalyst 3750 profile anchor")
    block = '''  ubiquiti-us-48-poe-500w-api:
    status: experimental
    vendor: Ubiquiti
    family: UniFi Switch
    model_patterns:
    - US 48 PoE 500W
    layout:
      members: 1
      rj45_ports: 48
      sfp_1g_ports: 2
      sfp_10g_ports: 2
    interface_patterns:
      rj45:
      - api-port-{port}
      sfp_1g:
      - api-port-51
      - api-port-52
      sfp_10g:
      - api-port-49
      - api-port-50
    notes:
    - Existing registry evidence defines API ports 1-48 as 1G RJ45, 49-50 as 10G SFP+, and 51-52 as 1G SFP.
    - This profile repairs a pre-existing registry-to-profile reference gap; it does not promote the model beyond Experimental.
'''
    text = text.replace(anchor, block + anchor, 1)
    profiles.write_text(text, encoding="utf-8")

changelog = Path("switch_vision_discovery/CHANGELOG.md")
ctext = changelog.read_text(encoding="utf-8")
bullet = "- Repair the pre-existing `US 48 PoE 500W` registry/profile reference by adding its declared 48-RJ45 + 2-SFP+ + 2-SFP API mapping profile.\n"
if bullet not in ctext:
    anchor = "- Add generic registry-to-profile referential-integrity validation so any exact device that names a missing mapping profile fails CI.\n"
    if anchor not in ctext:
        raise SystemExit("missing 2.1.42 changelog anchor")
    ctext = ctext.replace(anchor, anchor + bullet, 1)
    changelog.write_text(ctext, encoding="utf-8")

fragment = Path("switch_vision_discovery/release-fragments/2.1.42.md")
ftext = fragment.read_text(encoding="utf-8")
bullet = "- Repair the existing US 48 PoE 500W declarative API profile reference uncovered by the new integrity check; support status remains Experimental.\n"
if bullet not in ftext:
    anchor = "- Add end-to-end synthetic-walk and registry/profile integrity regressions so the 48+4 mapping is exercised by CI rather than only declared in metadata.\n"
    if anchor not in ftext:
        raise SystemExit("missing 2.1.42 release-fragment anchor")
    ftext = ftext.replace(anchor, anchor + bullet, 1)
    fragment.write_text(ftext, encoding="utf-8")
