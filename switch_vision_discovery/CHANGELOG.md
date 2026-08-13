# Changelog

## 2.1.4

- Fixes generated SNMP2MQTT YAML validation for Juniper EX VLAN helper sensors, which intentionally use `source: juniper_ex_vlan` with `interface` and `attribute` instead of a direct `oid`.
- Keeps direct SNMP sensors strict: ordinary sensors still require an OID, and unknown derived sensor sources remain rejected.
- Validates Juniper VLAN helper interface, attribute, and the supported attribute set before allowing generated YAML to be applied.
- Adds packaged-runtime regression coverage for valid and invalid source-aware generated-YAML sensor schemas.

## 2.1.3

- Fixes fresh installs so the blank starter switch row is treated as zero configured SNMP switches instead of being walked as a bogus target.
- Replaces whitespace-sensitive TSV switch-row parsing with a non-whitespace field separator so empty optional fields remain in their correct positions.
- Applies the same field-preserving parsing to stack-member rows.
- Aligns the packaged Discovery job version marker with the v2.1.3 app/runtime version.
- Adds packaged-runtime regression coverage for blank starter rows and field-position preservation.

## 2.1.2

- Fixes the repository-backed container runtime layout so the supported-device registry, vendor database, and MIB database are installed under `/opt/switch-vision/` where Discovery expects them.
- Fixes **Discovery Settings** to resolve the installed repository-backed Discovery slug dynamically instead of linking to retired `local_switch_vision_discovery`.
- Corrects UniFi2MQTT installation guidance to use Switch Vision Installer instead of the retired bundled-local-app workflow.
- Stops counting the blank switch-list placeholder as an imported configured switch.
- Extends packaged-runtime regression tests to require a real supported-device registry match and to reject the retired local Discovery configuration URL.


## 2.1.1

- First standalone public Home Assistant app repository release.
- Carries the Switch Vision Discovery/Hub runtime from Switch Vision v2.1.1.
- Adds UniFi2MQTT Hub settings/status support and smart UniFi availability states.
- Keeps SNMP discovery, Support My Switch, diagnostics, configuration import/export, and generated dashboard/SNMP2MQTT workflows.
- Moves Discovery distribution away from the Home Assistant local-app `/addons` path to normal Supervisor repository/version tracking.
