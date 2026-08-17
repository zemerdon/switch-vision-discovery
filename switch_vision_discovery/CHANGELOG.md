# Changelog

## v2.1.22 — Immutable Home Assistant base image

- Pin the Discovery container's Home Assistant `base:3.22` image to its resolved immutable multi-architecture OCI digest.
- Preserve automatic amd64 and arm64 platform selection through the pinned OCI index.
- Prevent future Discovery rebuilds from silently consuming a different `base:3.22` image without an explicit source change.
- Discovery runtime logic, device profiles, Support My Switch behavior, privacy defaults, SNMP2MQTT generation, UniFi diagnostics, and validated Juniper EX3300 behavior are unchanged.

## v2.1.21 — Support My Switch privacy-safe defaults

- Enable VLAN-name masking by default for new Support My Switch configurations.
- Enable interface-description masking by default for new Support My Switch configurations.
- Management IP, MAC-address, and hostname masking remain enabled by default.
- Existing saved Home Assistant app options are preserved; this release does not silently override a contributor who already changed either privacy control.
- Preserve switch detection, generated dashboard/SNMP2MQTT output, Dell N2128PX-ON support, UniFi diagnostics, and Juniper EX3300 live-interface behaviour unchanged.
- Add a packaged regression protecting the runtime-side privacy-option contract.

## v2.1.20 — Dell EMC Networking N2128PX-ON Experimental support

- Adds Experimental Dell EMC Networking N2128PX-ON support from a Support My Switch bundle received 2026-08-16.
- Confirms sysObjectID `1.3.6.1.4.1.674.10895.3077` across standalone and two-member stack captures.
- Maps `Gi<member>/0/1-28` as 28 RJ45 ports and `Te<member>/0/1-2` as two 10G SFP+ uplinks per member.
- Adds exact Dell model extraction, front-panel capability classification, parser/report mapping, SNMP2MQTT labels, registry metadata, and mapping-profile coverage.
- Records matching topology on firmware 6.7.1.27 and 6.6.0.7.
- Uses the generic 48 RJ45 + 4 SFP visual temporarily while preserving the real 28 RJ45 + 2 uplink card counts.
- Keeps VLAN/trunk semantics, detailed PoE presentation, rendered dashboard validation, and Dell-specific faceplate calibration Experimental/pending.
- Preserves the validated Juniper EX3300 live-interface path unchanged.
- Disambiguates this Dell evidence by date because its locally generated contribution ID collides with an older `SV-2026-000004` Zyxel contribution ID.

## 2.1.19

- Adds four Experimental UniFi API profile families from Support My Switch contribution `SV-2026-000057`: `USW Flex Mini`, `USW Pro 24`, `US 8 60W`, and `UniFi Dream Machine PRO SE`.
- Records `USW Flex Mini` from three independent live devices as five 1G RJ45 ports with no PoE-output metadata exposed.
- Records `USW Pro 24` as 24 1G RJ45 ports plus two confirmed 10G SFP+ uplinks and no PoE output.
- Records `US 8 60W` as eight 1G RJ45 ports with 802.3af PoE output capability on ports 5-8 only.
- Records `UniFi Dream Machine PRO SE` as ports 1-8 1G PoE RJ45, port 9 2.5G RJ45, and ports 10-11 10G SFP+; ports 9-11 remain role-neutral pending WAN/LAN validation.
- Independently revalidates the existing `USW-24-PoE` Experimental profile as 24 1G RJ45 + two 1G SFP uplinks with PoE output on ports 1-16 only.
- Adds regression coverage distinguishing `USW-24-PoE` 1G SFP uplinks from `USW Pro 24` 10G SFP+ uplinks.
- Adds contribution-backed card-emission coverage for all four new model families, including all three contributed Flex Mini devices.
- Preserves `per_port_traffic: false`; SNMP remains required where per-port traffic/Activity LED telemetry is needed.
- Keeps all new profiles Experimental pending rendered-dashboard/faceplate validation.
- Preserves the validated Juniper EX3300 live-interface implementation and registry entry unchanged.

## 2.1.18

- Adds Experimental UniFi API dashboard support for five models from Support My Switch contribution `SV-2026-000003`: `USW-24-PoE`, `USW-16-PoE`, `USW-Lite-8-PoE`, `USW Flex 2.5G 8 PoE`, and `USW Flex`.
- Adds exact registry entries and API mapping profiles using live contributed port topology, connector, negotiated-speed, PoE, CPU, memory, uptime, and uplink evidence.
- Records `USW-24-PoE` as 24 RJ45 + 2x 1G SFP, with PoE on ports 1-16.
- Records `USW-16-PoE` as 16 RJ45 + 2x 1G SFP, with PoE on ports 1-8.
- Records `USW-Lite-8-PoE` as 8 RJ45, with PoE on ports 1-4.
- Records `USW Flex 2.5G 8 PoE` as eight 2.5G PoE RJ45 ports, one 10G RJ45 port, and one 10G SFP+ port.
- Records `USW Flex` as five 1G RJ45 ports, with contributed PoE-output metadata on ports 2-5.
- Preserves real API port counts when a dedicated Switch Vision visual is not yet available and uses the existing universal temporary visual fallback where required.
- Keeps all five models Experimental pending rendered-dashboard validation.
- Records that the current UniFi API path does not expose reliable per-port RX/TX traffic; SNMP remains required for per-port Activity LED animation.
- Adds contribution regression coverage ensuring all five models emit dashboard cards from the authoritative runtime registry.
- Preserves the validated Juniper EX3300 live-interface implementation and registry entry unchanged.

## 2.1.17

- Adds first-class support for the privacy-safe UniFi2MQTT `diagnostics.json` introduced in UniFi2MQTT v2.0.43.
- Exposes UniFi polling status, poll stage, accepted/rejected device counts, safe model names, feature names, and switch-classification reasons through Discovery diagnostics.
- Includes sanitized UniFi diagnostic evidence in Support My Switch contribution bundles so controller/API/classification failures can be diagnosed even when no `devices.json` snapshot was produced.
- Adds defense-in-depth allowlist sanitization for UniFi diagnostic bundles; credentials, controller addresses, device identifiers, names, MAC addresses, IP addresses, and serial numbers are not accepted into the diagnostic evidence.
- Fixes stale/default switch rows with no switch name or host but a leftover sensor prefix being treated as configured switches and causing `requires switch_name for a stable identity`.
- Fixes generated dashboard and SNMP2MQTT headers reporting stale `Switch Vision Discovery v2.1.14`; runtime-generated files now report v2.1.17.
- Adds regression coverage for stale switch placeholders, UniFi diagnostic privacy, persistent UniFi polling failures, and safe diagnostic classification data.
- Preserves the validated Juniper EX3300 interface/SFP discovery implementation unchanged.

## 2.1.16

- Adds Experimental UniFi API dashboard support for `US 48 PoE 500W` from live Support My Switch evidence.
- Registers 48 RJ45 ports, two 1G SFP ports, two 10G SFP+ ports, and PoE capability.
- Uses the existing 48 RJ45 + 4 SFP visual and `default_cisco_48_port` calibration profile.
- Adds regression coverage for 48+4 UniFi card generation and confirms `UPS 2U` is never emitted as a switch card.
- Records that the current UniFi API path does not expose reliable per-port RX/TX traffic for this device; SNMP is required for per-port Activity LED animation.
- Preserves all Discovery v2.1.14 EX3300 live SFP/SFP+ runtime code unchanged.

## 2.1.15

- Adds a **Copy Debug Info** button beneath Discovery debug output.
- Reuses the existing Home Assistant Ingress-compatible clipboard fallback.
- Applies an additional client-side credential sanitisation pass before debug text is copied.
- Masks common community strings, passwords, tokens, API keys, authentication secrets, SNMP command-line credentials, and URL credentials.
- Provides clear copied/error status feedback without changing Discovery execution, polling, generation, or device handling.
- Preserves Discovery v2.1.14 Juniper EX3300 live SFP/SFP+ behaviour unchanged.

## 2.1.14

- Adds live Juniper EX3300 SFP/SFP+ cage resolution with Switch Vision SNMP2MQTT Core v0.9.9.
- Always generates all four EX3300 uplink cages from the confirmed hardware profile, even when an empty cage is absent from the current IF-MIB walk.
- Generates ordered `xe-0/1/N` then `ge-0/1/N` interface candidates so 10G/1G mode changes, hot-plug events, and Junos ifIndex changes are followed at runtime without rerunning Discovery.
- Moves EX3300 uplink status, admin status, speed, RX/TX counters, and alias sensors away from fixed numeric ifIndex OIDs.
- Extends Juniper VLAN helper sensors to use the same live interface candidates for all four uplink cages.
- Extends generated-YAML validation and self-tests for `source: interface` and candidate interface lists.
- Preserves existing fixed-OID generation for EX3300 copper ports and all existing non-EX3300 devices.

## 2.1.13

- Makes Home Assistant Supervisor the single authoritative persistence path for Discovery options. Configuration import and startup migrations no longer edit `/data/options.json` directly.
- Adds one exclusive Discovery operation coordinator so Discovery, Support My Switch bundle creation, configuration import, device-state changes, SNMP reset, and UniFi2MQTT install/settings mutations cannot race each other. Conflicting requests fail with HTTP 409; Stop Discovery remains available while Discovery is running.
- Rejects duplicate saved `switch_name` values and generated `sensor_prefix` identities across switch rows and stack-member prefixes, including disabled rows. Member 1 may intentionally reuse its own parent prefix for a stack.
- Validates the authoritative Supervisor inventory before a Discovery run snapshot is written, so duplicate identities entered through native Home Assistant Configuration fail closed before any SNMP command starts.
- Changes nested `snmp_community` to Home Assistant's native `password` schema type so community strings are masked in the app configuration UI without changing stored values.
- Stops creating the secret-bearing `options.before-import.json` import backup and removes any legacy copy left by an earlier import. Imports preserve unrelated current Supervisor options/secrets and verify the saved result directly with Supervisor.
- Configuration export now reads the authoritative Supervisor options instead of a potentially stale local copy.
- Preserves v2.1.12 disabled-dashboard filtering, v2.1.11 live Supervisor run snapshots, and v2.1.10 privacy protections.

## 2.1.12

- Fixes disabled saved switches continuing to render as stale/offline cards in `generated-dashboard-card.yaml` even though v2.1.11 correctly excluded them from SNMP walking and active SNMP2MQTT generation.
- Applies the same Enabled/Disabled predicate used by the walk/parser path directly to the production generated-dashboard row selector.
- Excludes all stack-member cards belonging to a disabled parent switch while keeping the saved switch and stack-member configuration intact for later re-enable.
- Keeps legacy pre-v2.1.8 rows without an explicit state backward-compatible by treating them as Enabled.
- Adds an executable regression against the exact jq program used by the dashboard-card writer, proving enabled stacks render, disabled switches do not render, and legacy rows remain enabled.
- Preserves all v2.1.11 authoritative Supervisor run-option handling and v2.1.10 full-walk privacy protections.

## 2.1.11

- Fixes Discovery walking switches that were disabled from **Switch Vision Hub → Devices** or Home Assistant Configuration while the Discovery app remained running.
- Captures a fresh authoritative Home Assistant Supervisor options snapshot immediately before every Discovery run and passes that exact snapshot to the Discovery job.
- Stops the runtime walk/parser/generator path from depending on a potentially stale `/data/options.json` copy for switch enable/disable decisions.
- Fails closed when authoritative Supervisor options cannot be read: no SNMP walk is started rather than risking use of stale switch state.
- Keeps disabled switches saved while excluding them from walking, parsing, generation, stack-member mappings, and current-run source selection.
- Adds regression coverage for the full **toggle state → authoritative run snapshot → Discovery job** contract while preserving all v2.1.10 full-walk privacy protections.

## 2.1.10

- Fixes a Support My Switch privacy leak exposed by full Cisco SNMP walks: ENTITY-MIB `entLogicalCommunity` values are now always redacted, including VLAN-qualified community forms.
- Bumps Support My Switch sanitization/report schema to version 13 and blocks contribution readiness if any unredacted logical-community value survives the residual credential audit.
- Splits Juniper full walks into the standard MIB and Juniper enterprise tree so a timeout in one branch cannot prevent collection of the other; partial full walks are marked `warning`, never `pass`.
- Reconciles exact-model support status with the authoritative supported-device registry so confirmed Catalyst 2960S/2960X models are no longer reported as Experimental by legacy contribution/report paths.
- Corrects normalized uplink capability counts: WS-C2960S-48FPD-L and WS-C2960X-48FPD-L deduplicate Gi aliases for their two physical dual-rate SFP+ cages; WS-C2960X-24PS-L retains four genuine 1G SFP uplinks; Catalyst 3650 distinguishes 1G SFP from 10G SFP+ uplinks.
- Adds regression coverage for ENTITY-MIB community sanitization, full-walk warning semantics, registry status reconciliation, and 2960 uplink alias handling.

## 2.1.9

- Adds **Switch Vision Hub → Devices → Enable / Disable Devices** with a one-click state control for every saved switch.
- Adds **Enable / Disable Devices** as a bullet on the Hub Devices tile for at-a-glance discoverability.
- Saves quick-toggle changes through Home Assistant Supervisor's authoritative app-options API, keeping the native Configuration editor and Hub on the same persisted state.
- Keeps SNMP communities and unrelated settings server-side; the browser receives only safe switch identity/display fields.
- Blocks state changes while Discovery is running so every toggle has unambiguous next-run semantics.
- Retains the native Home Assistant Configuration field as a fallback and all v2.1.8 enabled/disabled generation safeguards.
- Adds regression coverage for Supervisor-backed Hub state changes, secret preservation, browser-safe output, and stale-row rejection.

## 2.1.8

- Adds persistent per-switch **Discovery State** with `enabled` / `disabled` choices.
- Enabled switches are walked, parsed, and included in generated SNMP2MQTT/dashboard output.
- Disabled switches remain saved but are excluded from Discovery source selection and generation; stored walk history is retained for easy re-enabling.
- Existing pre-v2.1.8 switch rows default to enabled and are migrated to an explicit enabled state on first v2.1.8 start.
- Prevents `parse_all_walks` from reintroducing disabled switches through stored per-switch walk folders.
- Prevents an all-disabled configured inventory from falling through to the legacy single `snmpwalk.txt` source.
- Preserves the legacy offline `parse_all_walks` directory workflow when no real switch rows are configured.
- Excludes stack-member mappings belonging to disabled parent switches.
- Rebuilds capability/generated output from the active source set so disabled switches do not survive through stale generated artifacts.
- Bumps portable Discovery configuration exports to `switch-vision-discovery-config-v2` while retaining import compatibility with v1; this prevents older Discovery releases from silently ignoring disabled-state semantics on downgrade/import.
- Adds CI/runtime packaging hygiene checks that reject Python bytecode/cache residue, unsafe archive paths, links, and special files before container build.
- Keeps all v2.1.7 Zyxel XS1930-10 support and prior privacy/Juniper fixes unchanged.

## 2.1.7

- Adds Experimental Zyxel XS1930-10 support from Support My Switch contribution `SV-2026-000004` with contributor credit to `jpedrot`.
- Detects exact `XS1930-10` hardware / sysObjectID `1.3.6.1.4.1.890.1.15` and maps `swp00`-`swp07` as eight RJ45 ports plus `swp08`-`swp09` as two 10G SFP+ uplinks.
- Generates standards-based IF-MIB link/speed and 64-bit RX/TX telemetry plus Q-BRIDGE PVID/native-VLAN sensors without inferring trunk/access mode.
- Adds contribution/MIB-proven Zyxel model, firmware, serial, CPU, memory, FAN1 RPM/status, and MAC/BOARD/PHY temperature telemetry.
- Keeps PoE and transceiver/DDMI telemetry unclaimed where the contribution does not prove them.
- Adds a curated Zyxel vendor/MIB pack and XS1930-10 regression coverage, including priority protection so proven sensor OIDs cannot be displaced by the generic enterprise candidate cap.
- Requires Switch Vision main/core v2.1.5 or later for the XS1930-10 model-aware 8-RJ45 + 2-SFP visual; older core versions can consume Discovery data but may render the generic fallback geometry.
- Keeps support status Experimental pending contributor runtime/dashboard validation; this model is not project-owner hardware validated.

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
