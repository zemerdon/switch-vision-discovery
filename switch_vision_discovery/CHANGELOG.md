# Changelog

## 2.1.6

- Harden Support My Switch privacy processing for loose/canonical/Cisco-style MAC addresses.
- Always mask device serial numbers while preserving stable correlation inside contribution bundles.
- Expand credential sanitization to SNMP command-line communities, authorization headers, URL credentials, and the positional community field in `discovery-targets.csv`.
- Add always-enforced residual audits for credentials and serial numbers; bundles are withheld when either category remains.
- Bump sanitization/report schema to version 12 and add regression coverage for the new privacy guarantees.

## 2.1.5

- Reconciles the legacy human-readable Discovery parser with the current Juniper EX3300-48P registry and capability path.
- Detects EX3300-48P and JUNOS correctly in the legacy report instead of reporting an unknown/unsupported platform.
- Maps 48 zero-based `ge-0/0/N` copper ports and the currently exposed dual-rate `ge-0/1/N` / `xe-0/1/N` uplink cages without fabricating empty IF-MIB interfaces.
- Reports the confirmed `juniper-ex3300-48p` profile and supported status while keeping Virtual Chassis explicitly unvalidated.
- Keeps the working v2.1.4 Juniper generated-YAML validator and SNMP2MQTT generator behaviour unchanged.
- Adds packaged regression guards for the EX3300 legacy parser and support-metadata reconciliation.

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
