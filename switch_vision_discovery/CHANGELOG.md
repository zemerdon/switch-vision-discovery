# Changelog

## 2.1.38

- Prefer the existing UniFi 24 RJ45 + 2 SFP generic faceplate and `unifi_24p_rj45_2sfp` calibration profile for unknown/pending UniFi devices whose observed topology fits that layout.
- Keep neutral stock generic faceplates for larger/different UniFi topologies where no UniFi-specific generic exists yet.
- Preserve real observed RJ45/SFP counts, link-state/speed/PoE UniFi API telemetry, exact-model mappings, and the v2.1.37 unsupported-model card-generation fallback unchanged.
- Extend Brendan's four-device regression so UCG Ultra, US 16 PoE 150W, USW Pro Max 24, and USW Ultra must all select the UniFi generic faceplate rather than the neutral stock 24+2 visual.

## 2.1.37

- Generate a Switch Vision dashboard card for positively detected UniFi switching devices even when no exact model registry entry exists yet.
- Use the smallest suitable existing stock/generic faceplate (24+2, 24+4, 48+2, or 48+4) while preserving the real observed RJ45/SFP counts and live UniFi port data.
- Apply the same generic fallback to registered UniFi models whose exact dashboard visuals are still pending, so artwork no longer gates dashboard availability.
- Keep exact registered/model-specific faceplates and API port maps unchanged when their verified geometry matches the observed device.
- Make malformed UniFi snapshot/registry inputs visible with YAML-safe diagnostics instead of silently returning zero cards.
- Add permanent regression coverage for Brendan's unsupported-model case: UCG Ultra, US 16 PoE 150W, USW Pro Max 24, and USW Ultra must produce four generic cards rather than an empty dashboard.

## 2.1.36

- Treat generated SNMP2MQTT YAML as **Not applicable** when no enabled SNMP switch targets are configured, including UniFi2MQTT-only installations.
- Remove the false missing-YAML warning from diagnostics when the SNMP data path is not in use.
- Hide SNMP2MQTT YAML regeneration/preview/download controls when they are irrelevant, while keeping SNMP cleanup available for users retiring old SNMP state.
- Show the live SNMP2MQTT state as **Not in use** instead of **Waiting** on UniFi-only installations.
- Preserve strict missing/invalid generated-YAML validation whenever at least one enabled SNMP target is actually configured.
- Add a packaged regression covering UniFi-only, active-SNMP, and generator-disabled status behavior.

## 2.1.35

- Synchronize the reviewed Core exact-model registry for Support My Switch contribution `SV-2026-000002` and preserve the validated Zyxel XS1930-10 contributor evidence.
- Add UniFi API profiles for `US 48`, optical-first `US XG 16`, and 32-port optical `USW Pro Aggregation`.
- Keep `US 48` on the existing legacy sequential 48-RJ45 + four-optical dashboard path as backward-compatibility coverage.
- Recognize `US XG 16` and `USW Pro Aggregation` without generating fake dashboard cards while their exact faceplates remain unverified; generated output records that they are waiting for visuals.
- Recognize SFP28 as an optical connector class and preserve 25G maximum capability separately from current negotiated link speed.
- Forward explicit `unifi_api_port_map` metadata into generated cards when a future exact model is dashboard-enabled, while retaining `unifi_sfp_port_offset` compatibility.
- Add packaged runtime regressions for the contribution registry, API profiles, pending-visual behavior, and generated-card contracts.

## 2.1.34

- Make Core/Discovery visual defaults a hard contract for every shared exact model, regardless of vendor.
- Remove the previous warning-only path for non-Ubiquiti/non-Huawei shared visual drift.
- Add an explicit model-to-reason exception table for rare intentional visual divergence; empty, unknown, or stale exceptions are rejected.
- Add a permanent synthetic regression proving Cisco, Juniper, Dell, Huawei and Ubiquiti models are all strict by default.
- Preserve hardware contracts, Huawei exact-model safeguards, SNMP2MQTT path checks, saved-walk YAML regeneration, and runtime behavior unchanged.

## 2.1.33

- Add **Regenerate SNMP2MQTT YAML** beside Run Discovery in Switch Vision Hub.
- Regeneration performs no new SNMP walks; it reuses the authoritative saved switch inventory and existing saved walk files.
- Enabled switch folders remain authoritative, so disabled saved devices are not silently resurrected.
- Reuse the normal v2.1.31 parser/generator, candidate validation and atomic publication path instead of introducing a second YAML generator.
- Redirect regeneration-only report, capability and dashboard-card outputs to temporary files; only the configured SNMP2MQTT YAML may publish.
- Apply/restart Switch Vision SNMP2MQTT only when a valid changed YAML is successfully published, preserving the previous known-good YAML on failure.

## 2.1.32

- Rename the Home Assistant ingress/sidebar panel from **Support My Switch** to **Switch Vision Hub**.
- Keep the app itself named **Switch Vision Discovery** in Settings → Apps.
- Keep Support My Switch as a feature inside the Hub rather than the identity of the entire management interface.
- Preserve v2.1.31 authoritative generated-YAML handoff hardening, v2.1.30 structured progress highlighting, v2.1.29 Huawei defaults, mappings, telemetry and generated-card behavior.

## 2.1.31

- Fix the v2.1.27 S5720 speed-template shell/AWK quoting regression that could abort every SNMP2MQTT generator run, leaving a target-less YAML file; the generator now emits shell-safe quoted templates and surfaces parser-stage failures explicitly.
- Correct the S5720 physical 1G SFP speed-cap matcher for prefixed labels (for example `SW1 SFP 1G 1`), so implausible IF-MIB speeds are actually capped at 1000 Mbps.
- Make current-run walk metadata authoritative for SNMP2MQTT generation: each successful/warning walk is paired with its exact switch name, management host, prefix, and community at collection time instead of rediscovering those values later from filenames or directories.
- Add the embedded `# Switch IP:` walk header as a diagnostic host fallback while keeping current-run metadata and explicit mappings preferred.
- Exclude failed live walks from the current-run parser/generator set.
- Split the YAML generator parser/formatter pipeline into explicit checked stages so an internal AWK failure can no longer collapse silently into a `targets:`-only candidate.
- Quarantine an already-invalid live `generated-snmp2mqtt.yaml` when a new candidate also fails, while continuing to preserve a previously valid live handoff.
- Add permanent regressions for authoritative current-run metadata, failed-walk exclusion, generator-stage failure visibility, and invalid-live quarantine.

## 2.1.30

- Keep the active blue Discovery progress highlight on `Generating SNMP2MQTT YAML` until the structured current stage actually advances to dashboard-card generation.
- Prioritize the live structured `stage` value over stale historical log-tail text when selecting the progress step.
- Limit log-tail fallback matching to the most recent lines and preserve all Discovery generation, Huawei visual defaults, atomic YAML publication, mappings, and telemetry unchanged.

## 2.1.29

- Restore `S5720-12TP-LI-AC` and `S5735-L8P4X-A1` to the neutral `stock_24rj45_4sfp` calibration profile and `faceplates/24rj45-4sfp.png` visual recommendation.
- Keep Discovery-generated cards aligned with Core factory/reset defaults for both Huawei 8 RJ45 + 4 SFP models.
- Upgrade Huawei visual drift from a warning to a permanent cross-component contract failure.
- Preserve S5720 physical 1G SFP speed capping, interface-name fallback, generated-YAML atomic publication, device mappings, and telemetry behavior unchanged.

## v2.1.28 — Atomic generated-YAML handoff

- Write SNMP2MQTT output to a candidate file and publish it atomically only after the candidate passes the Switch Vision header and non-empty target-list contract.
- Preserve the previous live `generated-snmp2mqtt.yaml` unchanged when a generation attempt produces an empty, target-less, malformed, or otherwise invalid candidate.
- Add a standalone generated-YAML semantic guard plus a permanent regression proving an invalid candidate cannot clobber a known-good live handoff.
- Keep the Huawei S5720-12TP-LI-AC 8 RJ45 + 4 physical 1G SFP mapping and 1000 Mbps physical-cage speed cap from v2.1.27 unchanged.
- Update Discovery UI guidance to reflect automatic SNMP2MQTT application of valid changed YAML.

## v2.1.27 — Hardware validation safeguards

- Promote WS-C2960X-24TS-L, WS-C3560CG-8PC-S, SG500X-24, Huawei S5735-L8P4X-A1, and Huawei S5720-12TP-LI-AC to Community Validated from existing real-hardware evidence.
- Preserve WS-C3560CG-8PC-S Gi0/9 and Gi0/10 dual-purpose combo-uplink semantics.
- Keep Huawei S5720-12TP-LI-AC at 8 RJ45 + 4 physical 1G SFP positions and cap generated speed telemetry for those cages at 1000 Mbps when IF-MIB reports an implausible higher value.
- Strengthen Dell N2128PX-ON regressions for physical 10G uplinks 29/30, exclusion of non-present 31/32, and ifHighSpeed preference over legacy ifSpeed.
- Add a permanent UniFi registry regression requiring explicit model faceplate/profile assignments and rejecting Cisco-specific visual fallbacks.
- Preserve existing MQTT topics, saved calibrations, Support My Switch privacy behavior, and unrelated device mappings.

## v2.1.26 — Cross-component contract audit fixes

- Correct the packaged Discovery runtime version identifier so runtime status, logs, and support metadata report v2.1.26 consistently with the Home Assistant app version.
- Synchronize the five Ubiquiti models shared with Switch Vision Core v2.4.0 to the dedicated `unifi-24p-rj45-2sfp.png` faceplate and `unifi_24p_rj45_2sfp` calibration profile.
- Preserve Discovery's additional exact-model hardware knowledge, including Dell N2128PX-ON and newer UniFi models that are not yet present in the Core supported-device index.
- Add a cross-component CI contract check covering Discovery app/runtime version parity, Core-model presence, shared hardware mappings, shared Ubiquiti visual defaults, and the Discovery → SNMP2MQTT generated-YAML path.
- Keep existing SNMP walks, device mappings, UniFi API port geometry, Support My Switch behavior, calibration profile management, and generated entity contracts unchanged.

## v2.1.25 — Calibration Profile Manager in Discovery Hub

- Moves Calibration Profile management into the Switch Vision Discovery Hub.
- Uses the existing Switch Vision Core calibration WebSocket and service backend.
- Adds profile listing, stale and duplicate indicators, protected deletion, copy, import, export, and bulk stale cleanup.
- Does not directly read or modify Home Assistant calibration storage files.

## v2.1.24 — Cisco trunk-status diagnostic correctness

- Update Discovery runtime and Home Assistant app version identifiers to v2.1.24.
- Tighten the early Cisco trunk-status diagnostic so it only reports a match for the same indexed `INTEGER` rows accepted by the Discovery parser.
- Prevent stray base-OID text, unindexed rows, or rows with the wrong SNMP value type from being reported as valid Cisco trunk-status evidence.
- Add regression coverage for numeric and `iso.` SNMP walk forms.
- Preserve existing device mappings, VLAN/PVID handling, generated telemetry behavior, and Juniper EX3300 behavior.

## v2.1.23 — Reviewable Discovery runtime source

- Add the complete packaged Discovery runtime as normal Git-tracked source under `runtime_src/` for line-by-line review, history, blame, and external auditing.
- Add a strict source/archive parity checker covering runtime file paths, SHA-256 file contents, and executable-bit semantics.
- Add CI enforcement so `runtime_src/` and the shipped `runtime.tar.gz` cannot diverge unnoticed.
- Reject links, special files, Python bytecode, and `__pycache__` material from the tracked runtime-source contract.
- Keep the existing `runtime.tar.gz` byte-for-byte unchanged from v2.1.22; this release changes source transparency and packaging assurance only.
- Preserve all Discovery runtime behavior, device profiles, Support My Switch privacy defaults, UniFi diagnostics, SNMP2MQTT generation, and validated Juniper EX3300 live-interface behavior unchanged.

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
