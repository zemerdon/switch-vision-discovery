# Changelog

## 2.3.8

- Compact Calibration Profiles cards into one visual block by placing the action controls inline with the Internal profile row on desktop and wrapping them beneath it on narrow screens.
- Remove the visible Base profile, Faceplate exists and SHA-256 detail rows; base-profile compatibility, faceplate-existence state and integrity/duplicate metadata remain available to backend/runtime logic.
- Remove the old separator/details band and excess action-row margin while preserving the shared Hub control/button geometry and tightening only the spacing between profile actions.
- Compact Settings checkbox/toggle groups into left-anchored content-width columns instead of two half-card columns, reducing wasted horizontal space while preserving one-column mobile stacking.
- Reduce the sticky Save/Reload footer to a slim command bar by removing excess outer padding/margins while keeping the same shared 38px button geometry.
- Add a packaged regression protecting the compact card structure, all profile actions, hidden-only technical metadata, duplicate-state behavior, compact toggle columns and slim Save bar.
- No settings ownership, switch mapping, physical geometry, connector, PoE, telemetry, maximum-capability, support-status or privacy contracts change.

## 2.3.7

- Introduce one shared Hub component geometry contract across Core, SNMP2MQTT and Discovery settings: common 38px controls, radii, padding, field/helper spacing, toggle alignment, subsection rows, buttons, grid gaps and responsive behavior.
- Align checkbox/toggle rows even when neighboring labels wrap, and reduce selectable option labels to normal weight so themed section headings and field labels carry the visual hierarchy.
- Put Native header Shortcut order beside its toggle group on desktop as a compact single vertical sequence instead of stretching an empty full-width panel below the options.
- Pack Activity LED controls into a denser responsive four-column desktop grid while retaining the same shared control geometry and mobile stacking.
- Consume Core 2.6.3's explicit **10–20 px** Discovery/Installer body-font choices, preserving legacy `normal` as 16 px and `small` as 14 px.
- Apply the same 38px control geometry to ordinary Hub fields/buttons outside Settings so Support My Switch, UniFi2MQTT and other Hub forms no longer drift in box size.
- Keep SHA-256 as a private/backend integrity primitive but do not expose it as a normal Support My Switch/Last-bundle summary field.
- Add permanent packaged regressions for font migration, shared geometry, normal-weight selectable options, compact shortcut layout, dense Activity LED layout and hidden-only integrity hashing.
- No settings ownership, secret handling, switch mapping, physical geometry, connector, PoE, telemetry, maximum-capability or support-status changes.

## 2.3.6

- Give all four Hub management themes their own accessible heading palette so section hierarchy is visually distinct from ordinary body text: Switch Vision electric sky, Cisco Classic cyan, Cisco Nexus ice-cyan and UniFi deep blue.
- Add theme-owned heading/title/line/soft/glow tokens rather than hard-coding one colour across every theme.
- Improve Hub visual hierarchy with themed page and section headings, subtle section rails, softly tinted component summaries, restrained card depth, navigation-card accent strips, stronger input focus states and a more deliberate sticky Save bar.
- Keep body text neutral and preserve existing status/warning/success/error semantics so accent colour communicates hierarchy rather than replacing state colours.
- Preserve the 2.3.5 compact 38px Hub form-control sizing and alignment contract.
- Add permanent packaged regressions for every theme heading palette and the major hierarchy/focus styling hooks.
- No settings ownership, saved values, secret handling, switch mapping, physical geometry, connector, PoE, telemetry or support-status changes.

## 2.3.5

- Tighten the new Hub settings form controls to a consistent 38px height with smaller vertical padding instead of inheriting the larger general Discovery form sizing.
- Prevent CSS grid row stretching from shifting controls when a neighboring field has helper text, keeping MQTT password/community and ordinary text/number/select controls on the same top baseline.
- Reduce Hub-only settings grid gaps while leaving the established Discovery, Support My Switch and other non-settings form layouts unchanged.
- Add a packaged regression protecting the Hub-specific alignment and control-size contract.
- No settings ownership, saved values, secret handling, switch mapping, geometry, connector, PoE, telemetry or support-status changes.

## 2.3.4

- Make Switch Vision Hub the normal settings centre for Switch Vision Core, SNMP2MQTT and Discovery, while each component keeps its existing authoritative settings store.
- Add one Hub Save changes workflow with dirty-state tracking and explicit partial-save/error reporting instead of pretending cross-component writes are atomic.
- Keep Home Assistant Integration/App configuration pages available as fallback and recovery surfaces.
- Keep SNMP2MQTT MQTT passwords, Discovery SNMP communities and optional contributor identity write-only in the Hub; blank secret fields preserve existing stored values.
- Keep SNMP2MQTT Home Assistant MQTT Discovery enabled with the canonical `homeassistant` prefix, matching the existing effective runtime contract.
- Add complete Discovery controls for saved switches, stack display mappings, walk/generation controls, paths/timing, Discovery backup retention and Support My Switch privacy/recognition options.
- Label Discovery/Installer Core text-size choices with their actual current body sizes: Normal (~15.7 px) and Small (14.4 px).
- Explicitly require administrator access to the Hub ingress panel with `panel_admin: true`.
- Add packaged regressions for authoritative ownership, secret non-disclosure/preservation, enforced SNMP2MQTT discovery settings and Hub settings wiring, plus a permanent cross-component guard that fails if Core's public Hub settings groups, keys or admin-only WebSocket contract drift.
- No switch hardware mapping, physical geometry, connector, PoE, telemetry, maximum-capability or support-status changes.

## 2.3.3

- Move Installer recovery backup management into Switch Vision → Maintenance while keeping Installer recovery backups physically private under `/data/switch-vision-backups`.
- Use Home Assistant Supervisor's app STDIN control path instead of relaxing Installer's Supervisor-ingress-only HTTP boundary or adding direct app-to-app privileged HTTP.
- Start the manual-boot Installer on demand through Supervisor before sending a Maintenance command, and fail closed if it does not reach a running state.
- Add Maintenance controls for automatic retention on/off, a strict retained-backup count of 1–10, create, validate, restore, delete and manual retention.
- Keep Installer full recovery backups clearly separate from Discovery retained configuration backups under `/share/switch_vision/backups/discovery/`.
- Return only sanitized Installer backup metadata and operation state to Discovery; backup paths, saved option payloads, credentials and file contents are not exposed through the bridge.
- Add permanent packaged-runtime regressions for the bridge contract, retention bounds, approved action allowlist and Maintenance UI wiring.
- No switch mapping, physical geometry, connector type, PoE, polling, telemetry, maximum-capability or support-status changes.

## 2.3.2

- Expand private Support My Switch diagnostics with a privacy-safe configuration snapshot covering the operational Discovery, SNMP2MQTT, UniFi2MQTT and Installer options needed to eliminate user misconfiguration during support diagnosis.
- Record configured/not-configured flags and default/custom modes instead of credentials, SNMP communities, API keys, management addresses, private names or raw custom paths/topics.
- Include the credential-free effective SNMP2MQTT runtime handoff state when available, including generated/manual configuration source, generated target/sensor counts and effective Home Assistant discovery state.
- Bump the private Support My Switch bundle schema to version 12 and add permanent privacy and packaged-ZIP regressions.
- No switch mapping, physical geometry, connector type, PoE, polling, telemetry, maximum-capability or support-status changes.

## 2.3.1

- Restrict the Discovery Hub HTTP server to requests originating from the Home Assistant Supervisor ingress proxy.
- Reject all other internal app-network sources with HTTP 403 before route dispatch or request-body handling.
- Add a packaged-runtime regression proving Supervisor ingress remains allowed while direct GET and POST requests are denied.
- No switch mapping, geometry, connector, PoE, polling, telemetry or support-status changes.

## 2.3.0

# Discovery 2.3.0

- Add private retained backups for Switch Vision Discovery configuration mutations made through the Hub.
- Store owned backups only under `/share/switch_vision/backups/discovery/`, with the directory forced to `0700` and backup files to `0600`.
- Create the backup atomically before Hub configuration import and saved-device enable/disable changes.
- Add automatic retention control with a retained-count range of 1–10 and a default of 5; pruning is oldest-first and matches strict Switch Vision Discovery backup filenames only.
- Keep unrelated files and Support My Switch contributions outside the retention/removal scope.
- Add Maintenance metadata and manual removal controls that expose only backup name, time, size and count; saved configuration and secrets are never returned by the Maintenance API.
- Keep manual removal available when automatic retention is disabled, while invalid counts and backup names fail closed.
- Add permanent regressions for retention ordering, permissions, atomic cleanup, disabled retention, malicious/hand-edited names, metadata privacy, unrelated-file preservation and Support My Switch isolation.
- These backups cover persistent configuration mutations owned by the Switch Vision Hub. Discovery does not claim to intercept changes made independently through Home Assistant's add-on Configuration page.
- No switch mapping, physical geometry, connector type, PoE, polling, telemetry, maximum-capability or support-status changes.

## 2.2.5

# Discovery 2.2.5

- Verify the Discovery → SNMP2MQTT handoff instead of treating a Supervisor restart request as proof that the newly generated configuration became active.
- Detect an explicit SNMP2MQTT manual-target configuration and stop with a clear warning rather than reporting generated-YAML application success or silently overriding the user's deliberate mode.
- Verify the current generated MQTT Discovery identity set appears after SNMP2MQTT starts/restarts; if activation cannot be proven, keep the previous retained identities intact and report the handoff as unverified.
- Retire previous generated MQTT Discovery identities only after the replacement identity set has been observed live.
- Defer automatic Support My Switch bundle creation until after the SNMP2MQTT handoff check, so a normal Discovery contribution captures the post-restart runtime rather than an unavoidable pre-handoff snapshot. Failed handoffs are captured after the failed verification with previous retained identities preserved.
- Make Support My Switch walk freshness aware of the current Discovery transaction window so a long multi-switch run cannot make its own newly captured walks stale before the contribution bundle is created.
- Preserve the ordinary 15-minute freshness rule for stored/offline walks outside the current Discovery run.
- Add permanent regressions for manual-target mode, successful and failed post-restart activation verification, delayed MQTT publication, safe retirement ordering, post-handoff bundle ordering, same-run walk freshness, old-walk staleness, and malformed run metadata fallback.
- No switch mapping, physical geometry, connector type, PoE, polling, telemetry, maximum capability, support status, Core or privacy contract changes.

## 2.2.4

# Discovery 2.2.4

- Fix Support My Switch port-pipeline correlation so standard IF-MIB OIDs are never merged across different switches. Each generated sensor prefix is now bound to the correct Discovery-selected switch and its own captured walk source.
- Add explicit walk provenance/freshness to port diagnostics, including source, capture time and age. Historical/stale walk evidence is preserved for support analysis but is never treated as a current Home Assistant mismatch.
- Report fresh/stale/unmapped walk row counts separately and only compute `walk up but HA not up` anomalies from fresh, correctly-bound walk evidence.
- Harden Maintenance retained-MQTT scanning against a startup/busy-Home-Assistant race by allowing a longer grace period before the first retained event, while retaining the shorter idle-completion timeout after retained delivery starts.
- Fail safely instead of returning a partial retained scan if the hard completion limit is reached while retained events are still arriving.
- Add permanent regressions proving two switches with the same IF-MIB status OID remain isolated, stale walks cannot generate current HA anomalies, and MQTT first-event/idle timeout semantics stay distinct.
- Preserve Support My Switch schema 11, all Maintenance repair ownership/deletion safeguards, switch mapping, geometry, connector type, PoE, polling, telemetry, maximum capability, support status and Core contracts.

## 2.2.3

- Fix Support My Switch Home Assistant/runtime diagnostics so they use the same Supervisor-token discovery semantics already proven by Maintenance, including the Home Assistant s6 container-environment fallback.
- Restore real Home Assistant entity-resolution snapshots and installed runtime/component version reporting when the Supervisor token is mounted outside the normal process environment.
- Make port-pipeline diagnostics explicitly availability-aware: if Home Assistant state capture is unavailable, retain walk evidence but report HA correlation as unavailable instead of generating false `walk up but HA not up` mismatches or zero suffix counts.
- Add permanent regressions for environment-token priority, s6 token-file fallback, unavailable-HA port-pipeline semantics, and continued exclusion of Home Assistant attributes/unrelated entities.
- Preserve Support My Switch schema 11, MQTT Maintenance repair behavior, switch mapping, geometry, connector type, PoE, polling, telemetry, maximum capability, support status, and Core contracts.

## 2.2.2

- Fix Support My Switch schema-11 packaging so the Home Assistant entity snapshot and extended cross-layer diagnostics are actually generated in real contribution archives before sanitization.
- Align the packaged sanitizer paths with the materialized `runtime.tar.gz` layout: the diagnostic wrapper is invoked explicitly and delegates to the base sanitizer by its real packaged name.
- Keep the final whole-bundle privacy pass on the base sanitizer so diagnostics are captured once, then sanitized/audited with the rest of the contribution without creating duplicate diagnostic trees.
- Add an end-to-end packaged regression that runs the real Support My Switch script with Supervisor access unavailable, opens the resulting ZIP, and requires exactly one copy of every schema-11 diagnostic report.
- Preserve fail-safe diagnostic behavior: Home Assistant, Supervisor, or MQTT diagnostic unavailability records safe unavailable/partial results instead of blocking contribution creation.
- Preserve all switch mapping, port geometry, connector type, PoE, polling, telemetry, maximum-capability, support-status, Maintenance repair, and Core custom-component contracts.

## 2.2.1

- Improve the **Maintenance → Repair MQTT Entities** results view so large stale-entity lists are collapsed by default while the important scan totals remain visible.
- Add **Export Results** to Maintenance. The exported JSON contains the safe scan summary and stale Switch Vision entity IDs only; it excludes repair plan tokens, raw retained MQTT discovery payloads and credentials.
- Expand private **Support My Switch** diagnostics so a single contribution can correlate Discovery output, generated SNMP2MQTT targets, Home Assistant entity resolution and card bindings when diagnosing stale, suffixed, missing or mis-bound entities.
- Add private runtime/component version reporting for Home Assistant and installed Switch Vision add-ons when Supervisor information is available, with fail-safe partial output when it is not.
- Add generated-file provenance using path, size, SHA-256 and modification time only, allowing support analysis to identify stale or mismatched generated artifacts without copying additional sensitive file contents.
- Add model provenance from sanitized capability reports so local detected/effective model identity and registry-match evidence can be compared across devices without exposing management addresses, credentials or unrelated device metadata.
- Add generated card-to-target/entity binding diagnostics to help distinguish incorrect card selection/binding from correct SNMP discovery and polling.
- Add per-port correlation between generated status entities, captured `ifOperStatus` walk evidence, exact Home Assistant entity IDs and numeric-suffix alternatives such as `_2`/`_3`, making cases where the switch reports an active link but the exact card entity is missing or stale directly visible.
- Add a private MQTT-maintenance snapshot using the existing strict Switch Vision ownership classifier so Support My Switch can report current expected, retained and stale Switch Vision discovery entities without including raw MQTT payloads or unrelated integrations.
- Add a compact diagnostic anomaly summary covering missing exact entities, numeric-suffix alternatives, stale owned MQTT discovery and walk-up/HA-not-up mismatches.
- Bump the private Support My Switch contribution schema from bundle version 10 to **11** for the expanded diagnostic set.
- Keep contribution sanitization authoritative and fail-safe: extended diagnostics cannot block sanitization or submission if Home Assistant, Supervisor or MQTT diagnostic collection is unavailable.
- Add permanent privacy regression coverage that injects a fake secret into Home Assistant entity attributes and proves it cannot appear in the new diagnostic output.
- Preserve all existing switch mapping, port geometry, connector type, PoE, polling, telemetry, maximum-capability, support-status and Core custom-component contracts; this release is diagnostic/maintenance UX only.

## 2.2.0

- Add a first-class **Maintenance** section to Switch Vision Hub.
- Add **Repair MQTT Entities** with a read-only scan/preview followed by explicit confirmation before any retained MQTT discovery entry is removed.
- Restrict historical MQTT cleanup to retained discovery configs whose topic, origin, unique ID, entity ID and state-topic contract prove they are owned by Switch Vision SNMP2MQTT; unrelated MQTT integrations are ignored.
- Re-scan immediately before repair and reject stale plans if MQTT state changed after preview.
- Republish current SNMP2MQTT discovery after repair when the app was already running, preserve a stopped app as stopped, and verify the remaining stale count after repair.
- Move the existing stronger **Reset SNMP Discovery Data** action into Maintenance while preserving its separate explicit warning and confirmation path.
- Keep existing automatic generated-YAML retirement/reconciliation behaviour and all switch mapping, polling, telemetry, geometry, privacy and support-status contracts unchanged.

## 2.1.48

- Fixes the Support My Switch detected-hardware email summary so adjacent detected-name/model values that are identical after case/whitespace normalization are rendered once.
- Preserves both identity fields when they genuinely differ, and preserves the existing family description suffix.
- Adds a permanent SMTP/MIME regression covering UniFi duplicate-name examples plus a distinct vendor/model case.
- Synchronizes the shared UCG Ultra and USW Ultra dashboard visual metadata with Core 2.4.18, including their exact five-RJ45 and eight-RJ45 UniFi faceplates/calibration profiles; rendered community alignment remains pending.
- No hardware detection, port mapping, connector geometry, polling, telemetry, privacy policy, or support-status change is introduced.

## 2.1.47

- Extends the read-only targeted SNMP walk with standard DOT3-MAU-MIB (`1.3.6.1.2.1.26`) so Support My Switch evidence can identify the active media exposed by devices with dual-personality copper/SFP interfaces.
- Adds a packaged runtime regression that the DOT3-MAU subtree remains in the targeted `LIVE_OIDS` capture set.
- This is diagnostic evidence only: no HP port classification, connector rendering, SNMP2MQTT entity generation, telemetry synthesis, or support-status change is introduced.

## 2.1.46

- Adds a private Support My Switch diagnostic snapshot that compares generated Switch Vision port status, RX/TX byte-counter, and speed entity IDs with the entities Home Assistant actually exposes at bundle-creation time.
- Records only expected entity IDs, exact-presence state, safe numeric/enumerated values, update timestamps, and numeric-suffix alternatives such as `_2`; Home Assistant attributes and unrelated entities are excluded.
- Keeps the existing Support My Switch sanitizer authoritative and makes diagnostic capture fail-safe so Home Assistant API errors cannot block bundle sanitization.
- Makes no switch mapping, polling, port geometry, telemetry synthesis, or support-status changes.

## 2.1.45

- Prevents remote LLDP/CDP neighbour model strings from contaminating local switch model detection by restricting exact-model extraction to local sysDescr and ENTITY-MIB identity fields.
- Detects HP J8693A / 3500yl-48G local identity as Detected from real-hardware evidence without claiming unresolved combo-port geometry or broader HP family support.
- Adds a permanent CI regression covering HP-with-Dell-neighbour contamination plus existing local ENTITY-MIB exact-SKU precedence.

## 2.1.44

- Sanitizes public Discovery profile evidence so private Support My Switch submission identifiers never ship in source or runtime metadata.
- Promotes UCG Ultra, US 16 PoE 150W, and USW Ultra from Detected to Experimental after corroborating real-hardware UniFi API evidence; USW Pro Max 24 remains Experimental.
- Preserves every existing port count, connector type, PoE mask, physical ordering, and maximum-speed contract; this release does not change hardware geometry.
- Adds a permanent CI privacy regression covering public profile source in addition to generated registries and release text.

## 2.1.43

- Add Experimental exact-model Discovery profiles for `UDM Pro Max` and `USW Pro XG 24 PoE` from privacy-processed community real-hardware UniFi API validation.
- Preserve the UDM Pro Max contract as 8 × 1G RJ45 + 1 × 2.5G-capable RJ45 + 2 × 10G SFP+ with no PoE output.
- Preserve the USW Pro XG 24 PoE contract as 8 × 2.5G RJ45 + 16 × 10G RJ45 + 2 × 25G SFP28 with 802.3bt Type 4 PoE capability on all 24 copper ports.
- Teach Support My Switch UniFi summaries to distinguish 1G SFP, 10G SFP+ and 25G SFP28 while retaining a combined `uplink_count`, fixing SFP28 devices being reported with zero optical uplinks.
- Preserve established UniFi contribution fingerprints while adding the connector split: the legacy fingerprint optical value remains 1G SFP + SFP+ only, SFP28 remains excluded as before, and the two models first registered in this release retain their prior generic `UniFi` fingerprint family.
- Merge only the two reviewed Core 2.4.14 model records into Discovery's existing registry so stricter Discovery public-contribution metadata for previously supported models is preserved.
- Keep maximum connector capability separate from negotiated speed; 25G SFP28 ports may legitimately report a current 10G link and 10G-capable copper may negotiate at 100M/1G.
- Synchronize the reviewed Core exact-model registry and add permanent regressions for SFP28 contribution summaries, dashboard generation, model profiles, registry matching and attribution privacy.

## 2.1.42

- Correct live Cisco `WS-C3750-48P` interface classification to the stock 48-RJ45 + 4-SFP layout: 48 × 10/100 FastEthernet access ports plus four physical 1G SFP uplinks.
- Prevent `Gi<member>/0/1-4` on this exact model from falling through the generic Catalyst RJ45 classifier.
- Generate the four uplinks as 1G SFP entities, cap FastEthernet capability at 100 Mbps and SFP capability at 1000 Mbps, and keep SFP+ disabled for this model.
- Add a synthetic end-to-end 3750 walk regression proving 52 physical interfaces, 48 RJ45, four 1G SFP uplinks, correct generated YAML labels, and the stock `48rj45-4sfp.png` visual contract.
- Add generic registry-to-profile referential-integrity validation so any exact device that names a missing mapping profile fails CI.
- Repair the pre-existing `US 48 PoE 500W` registry/profile reference by adding its declared 48-RJ45 + 2-SFP+ + 2-SFP API mapping profile.

## 2.1.41

- Add Experimental exact-model Discovery handling for the community-observed Cisco `WS-C3750-48P` platform string.
- Map 48 × 10/100 FastEthernet access ports and four 1G SFP uplinks using stack-aware Catalyst 3750 interface names while keeping live overlay/uplink/stack validation pending.
- Generate Support My Switch `.eml` files with the SMTP email policy and RFC-compliant CRLF line endings so MIME headers and ZIP attachments remain structurally valid in strict mail clients.
- Add permanent regressions that parse the generated `.eml`, verify the ZIP is a real `application/zip` attachment, and prevent MIME headers from leaking into the Subject/body.
- Preserve anonymous public contribution metadata and omit private submission identifiers and filenames.

## 2.1.40

- Apply a general public-attribution privacy policy to Discovery release history and structured public contributor metadata.
- Remove contributor and tester identities unless explicitly approved by the project owner.
- Remove submission identifiers, contribution package names, and submission filenames from public release/history text.
- Preserve technical validation facts using neutral **Community contributor** wording.
- Add permanent regression coverage preventing non-approved attribution or private submission references from returning.
- No device mapping, generated YAML, telemetry, dashboard-card, or runtime behaviour changes.

## 2.1.39

- Add exact UniFi API hardware contracts for `UCG Ultra`, `US 16 PoE 150W`, `USW Pro Max 24`, and `USW Ultra` from community-provided real-hardware validation.
- Give `USW Pro Max 24` exact 24-RJ45 + 2-SFP+ dashboard geometry while preserving its verified 16 × 1G / 8 × 2.5G-capable copper split and 2 × 10G SFP+ uplinks.
- Keep UCG Ultra, US 16 PoE 150W and USW Ultra exact visuals pending while rendering them through the safe UniFi generic fallback with true observed port counts.
- Preserve verified PoE semantics and the contributed API capability boundary (`port_detail: true`, `per_port_traffic: false`) without synthesizing unsupported traffic data.
- Public release history intentionally omits contributor/tester identities, submission identifiers, contribution package names, and submission filenames.

## 2.1.38

- Prefer the existing UniFi 24 RJ45 + 2 SFP generic faceplate for unknown/pending UniFi devices whose observed topology fits that layout.
- Preserve real observed port counts, link-state, speed and PoE telemetry while keeping larger/different topologies on neutral stock fallbacks.

## 2.1.37

- Generate dashboard cards for positively detected UniFi switching devices even when no exact visual is available yet.
- Use the smallest suitable safe generic faceplate while preserving real observed RJ45/SFP counts and live UniFi data.
- Make malformed snapshot/registry inputs visible with YAML-safe diagnostics instead of silently returning zero cards.

## 2.1.36

- Treat generated SNMP2MQTT YAML as **Not applicable** when no enabled SNMP switch targets are configured, including UniFi-only installations.
- Hide irrelevant SNMP2MQTT controls and warnings while preserving strict validation whenever SNMP is actually configured.

## 2.1.35

- Synchronize reviewed Core exact-model UniFi hardware contracts into Discovery.
- Add API profiles for `US 48`, optical-first `US XG 16`, and `USW Pro Aggregation`.
- Keep optical-heavy models dashboard-disabled until truthful exact visuals exist.
- Preserve maximum capability separately from negotiated link speed.

## 2.1.34

- Make Core/Discovery visual defaults a strict contract for every shared exact model, regardless of vendor.
- Add a permanent cross-vendor regression for visual-contract drift.

## 2.1.33

- Add **Regenerate SNMP2MQTT YAML** using authoritative saved switch inventory and existing saved walk files.
- Reuse the normal parser/generator and atomic publication path rather than introducing a second YAML generator.

## 2.1.32

- Rename the Home Assistant ingress/sidebar panel to **Switch Vision Hub** while keeping Support My Switch as a feature inside the Hub.

## 2.1.31

- Fix the S5720 speed-template shell/AWK quoting regression that could abort SNMP2MQTT generation.
- Correct the physical 1G SFP speed-cap matcher for prefixed labels.
- Make current-run walk metadata authoritative for generation and quarantine invalid live YAML safely.

## 2.1.30

- Keep structured Discovery progress highlighting aligned with the actual current generation stage.

## 2.1.29

- Restore Huawei S5720/S5735 neutral 24 RJ45 / 4 SFP visual recommendations and keep Core/Discovery defaults aligned.

## 2.1.28 — Atomic generated-YAML handoff

- Generate SNMP2MQTT YAML to a candidate file, validate it semantically, and publish atomically only when valid.
- Preserve the previous known-good live YAML when a new candidate is invalid.

## 2.1.27 — Hardware validation safeguards

- Promote real-hardware-tested exact models while preserving model-specific physical semantics.
- Preserve Huawei S5720 8 RJ45 + 4 physical 1G SFP mapping and physical-cage speed limits.
- Strengthen Dell N2128PX-ON physical-uplink and speed regressions.

## 2.1.26 — Cross-component contract audit fixes

- Synchronize shared Core/Discovery model and visual contracts and enforce runtime/app version parity.

## 2.1.25 — Calibration Profile Manager in Discovery Hub

- Move calibration-profile management into Switch Vision Discovery Hub while retaining Core as the storage/service backend.

## 2.1.24 — Cisco trunk-status diagnostic correctness

- Tighten Cisco trunk-status diagnostics so only parser-valid indexed integer rows are accepted.

## 2.1.23 — Reviewable Discovery runtime source

- Add the complete packaged Discovery runtime as normal Git-tracked source and enforce source/archive parity.

## 2.1.22 — Immutable Home Assistant base image

- Pin the Discovery container base image to an immutable multi-architecture digest.

## 2.1.21 — Support My Switch privacy-safe defaults

- Enable VLAN-name and interface-description masking by default for new contribution configurations.
- Keep management IP, MAC-address and hostname masking enabled by default.

## 2.1.20 — Dell EMC Networking N2128PX-ON experimental support

- Add Experimental Dell EMC Networking N2128PX-ON support from community-provided real-hardware validation.
- Map 28 RJ45 ports and two 10G SFP+ uplinks per member while keeping presentation/visual work conservative.

## Earlier releases

Earlier detailed changelog entries have been consolidated from the public changelog as part of the Switch Vision public-attribution privacy policy. Public changelog and release-note text must not contain contributor/tester identities, submission identifiers, contribution package names, or submission filenames unless explicitly approved by the project owner.
