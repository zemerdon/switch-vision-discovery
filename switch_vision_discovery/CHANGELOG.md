# Changelog

## 2.3.24

## Discovery 2.3.24

- Add evidence-backed exact detection and physical-interface handling for Dell PowerConnect 5548P, Cisco WS-C3750X-48P, Cisco SG350-20, Zyxel GS1900-24E, HP J8693A Switch 3500yl-48G, and Ubiquiti USW Pro HD 24 PoE.
- Recognize compact Ubiquiti model identities used by USW Pro HD 24 PoE and USW Pro XG 8 PoE SNMP data without broadening generic `0/N` interface handling.
- Fix Catalyst 3750X C3KX network-module alias handling so Gi/Te aliases for the same physical cages are not double-counted as access ports.
- Fix HP J8693A generated dashboard cards to bind the four dual-personality positions to the emitted `uplink_*_status` entities instead of the generic `sfp_10g_*_status` template.
- Add Experimental UniFi API topology/profile metadata for USW Aggregation, USW Enterprise 24 PoE, USW Flex 2.5G 5, and USW WAN while preserving true observed port counts and connector types.
- Add synthetic contributor regressions and privacy-safe public evidence identifiers; raw contribution artifacts and private submission identifiers remain outside the public repository.
- No newly added model is promoted beyond Experimental by this release.

## 2.3.23

## Discovery 2.3.23

- Remove public contributor attribution from the MikroTik CRS328 Experimental registry entry; retain neutral `community contributor` provenance only.
- No hardware detection, mapping, telemetry, Q-BRIDGE, manufacturer, or support-status behaviour changes from 2.3.22.

## 2.3.22

# Switch Vision Discovery 2.3.22

- Adds Experimental MikroTik CRS328-24P-4S+RM discovery from privacy-processed real-hardware evidence, including exact 24 x `ether` RJ45 and 4 x `sfp-sfpplus` SFP+ front-panel classification.
- Preserves the locally observed RouterOS model string `CRS328-24P-4S+` and normalizes it only for exact registry lookup against the marketed `CRS328-24P-4S+RM` SKU.
- Corrects BRIDGE/Q-BRIDGE targeted acquisition and generated PVID OIDs from the incorrect `.1.3.6.1.2.1.18` tree to the standard `.1.3.6.1.2.1.17` tree.
- Fixes generated SNMP2MQTT YAML so an unknown/non-Cisco device can no longer inherit `device_manufacturer: Cisco`; known vendors are assigned explicitly and unknown devices remain `Unknown`.
- Adds narrow, read-only MikroTik supplemental collection for HOST-RESOURCES CPU, ENTITY-SENSOR, MikroTik health, and MikroTik PoE-Out candidates. These candidates remain walk-aware/review-only and are not installed unless returned and subsequently validated.

## 2.3.21

# Switch Vision Discovery 2.3.21

- Moves the Hub Credits navigation card to the final position, after Switch Vision Settings and UniFi2MQTT Settings.
- Keeps the Credits page, animation, fake test entries, privacy boundary, and all Discovery behaviour unchanged.
- Presentation/navigation-order change only.

## 2.3.20

# Switch Vision Discovery 2.3.20

- Adds a Matrix-inspired Credits-page construction animation that resolves into the normal Switch Vision cyan visual language.
- Adds a settled animated cyan edge glow, periodic energy sweep, faint circuit/particle drift, breathing Credits heading, staggered contributor reveal, and hover shimmer/lift effects.
- Adds clearly labelled fake test credit rows only; no real contributor identity is published in this release.
- Respects `prefers-reduced-motion` by skipping the construction sequence and disabling continuous motion.
- Changes presentation only; Discovery, device support, telemetry, configuration, privacy, contribution evidence, and generated output behaviour are unchanged.

## 2.3.19

# Switch Vision Discovery 2.3.19

- Adds a new **Credits** card to Switch Vision Hub.
- The Credits card displays the project thank-you message and is ready for future opt-in contributor acknowledgements in the form `Alias — Component(s)`.
- No contributor names or aliases are included in this release.
- Credits remains presentation-only and does not read contributor evidence, email, Evidence Vault data, or private recognition records.
- No Discovery workflow, device mapping, telemetry, settings, generated YAML, or hardware-support behaviour changes.

## 2.3.18

- Fix Hub settings saves being stopped by the Discovery backup validator with `Discovery backup reason is invalid.`.
- Allow the existing `hub_settings_update` pre-mutation backup reason used by the Hub Save workflow while keeping unknown backup reasons fail-closed.
- Add permanent regression coverage for the exact Hub settings-save backup reason and verify the recorded backup metadata.
- Preserve Supervisor as the authoritative configuration store and keep pre-save backup retention, privacy, device mappings, telemetry, generated configuration and hardware-support behavior unchanged.

## 2.3.17

- Reorganize Calibration Profiles into grouped Active and Unused sections, with active profiles split into Custom and Native groups.
- Move profile operations into one top manager toolbar; per-profile rows become action-free and row selection drives the toolbar.
- Keep context actions grey/disabled until the current selection makes them valid, while preserving active/factory deletion protection and existing import/export/copy/delete rules.
- Keep hardware/faceplate summaries single-line with aggressive ellipsis, desktop hover text, and a tap-accessible full-summary tooltip for touch devices.
- Preserve the approved Hub header, Calibration Profiles card framing, Hub Settings layout, device mappings, privacy behavior, and generated configuration semantics.

## 2.3.16

## 2.3.16 — Keep Calibration Profile summaries on one line

- Keep each profile model / RJ45 / SFP / faceplate summary on one line.
- Ellipsis-truncate the summary when horizontal space is constrained instead of wrapping it onto a second line.
- Preserve profile badges, names, actions, protection semantics and the 2.3.15 card organization.

## 2.3.15

- Move each Calibration Profiles scope/state badge and hardware/faceplate summary onto the top-right row opposite the selection/protection state.
- Keep the profile name on the next row and keep only real profile actions aligned at the right.
- Remove the redundant disabled Active/Factory protected pseudo-action buttons; protection remains represented by the selection/protection text and state badge.
- Preserve profile protection semantics, import/export/copy/delete behavior, hidden internal profile IDs, Hub framing and the compact five-action management toolbar.

## 2.3.14

- Restore the shared Hub header to the pre-2.3.13 structure, keeping Back/title/theme/sponsor in the top bar and returning contextual page text to its own line below.
- Return Calibration Profiles to a normal Hub card with its section heading and description while keeping the compact profile content inside the card.
- Keep the five Calibration Profiles management actions on one horizontal line at the right, with horizontal scrolling rather than wrapping on narrow screens.
- Keep per-profile actions right-aligned at narrow widths and tighten only Calibration Profiles button padding so the controls remain compact without changing button sizing elsewhere in the Hub.
- Preserve the 2.3.13 settings-card cleanup, hidden internal profile IDs, settings ownership, privacy handling, device mappings and generated configuration behavior.

## 2.3.13

- Compact the Hub page header so Back, title, contextual description, Theme and Sponsor share the top bar instead of consuming separate vertical rows.
- Rework Calibration Profiles into one compact toolbar showing saved/active/selected state with management actions, remove the duplicate inner page heading and visible internal profile IDs, and align per-profile actions with the profile protection/selection row.
- Give Core Hub settings clearly bounded section cards for sidebar/navigation, native dashboard header, dashboard presentation and Activity LEDs while preserving the compact shortcut-order layout and shared control geometry.
- Restyle the sticky Save/Reload/status area as a compact bordered action bar and reduce unnecessary section/component whitespace.
- Add permanent Hub UI regressions protecting the compact header/profile/settings contracts. This is presentation-only: settings ownership, secret handling, switch mappings, generated configuration, support status and privacy behavior are unchanged.

## 2.3.12

- Synchronize Discovery's embedded device registry with the authoritative Core 2.6.7 support-status evidence for WS-C2960X-24TS-L and WS-C3560CG-8PC-S.
- Return both models to Experimental while their recorded live dashboard, interface/activity, uplink/media, PoE/sensor or stack checks remain pending/candidate; preserve their existing hardware mapping, geometry, connector semantics and polling contracts.
- Synchronize Dell N2128PX-ON public evidence wording with Core's privacy-neutral community-hardware metadata; Dell remains Experimental and its hardware contract is unchanged.
- Extend the permanent Core/Discovery registry contract so shared support status, evidence and validation must remain synchronized; also pin Dell's privacy-neutral leading evidence note while preserving legitimate Discovery-specific runtime notes for other models.
- Update the packaged support-status regression so evidence-backed Community Validated models stay promoted while WS-C2960X-24TS-L and WS-C3560CG-8PC-S remain Experimental until their pending live checks are completed.

## 2.3.11

- Restore interface discovery for the exact HP J8693A / 3500yl-48G when IF-MIB exposes the 48 physical logical ports as numeric names.
- Preserve the hardware contract as 44 fixed 1G copper ports plus four dual-personality 1G copper/mini-GBIC logical uplinks; do not infer this layout for other HP/Aruba devices.
- Include all 48 logical physical ports in normalized capabilities and generated SNMP2MQTT status, traffic, speed, VLAN/alias polling.
- Add a packaged regression covering the exact numeric-interface contract. Support status remains Detected pending live rendered validation.
- Synchronize the Dell N2128PX-ON visual registry with Core's dedicated 28-RJ45 / 2-SFP+ faceplate and calibration defaults; Dell remains Experimental.

## 2.3.10

- Apply a Hub-wide option/field-label hierarchy using theme-owned muted blue-grey label colours while preserving brighter section headings, dimmer helper text and normal input/value text.
- Consolidate Maintenance backup management into the Installer Recovery Backups section: replace the checkbox/policy form with one Automatic retention toggle button, remove the visible retained-limit control, remove the Installer version summary tile, and remove the duplicate Discovery Configuration Backups UI.
- Render the retained-backup count directly from the same backup array used to render rows so the visible count cannot disagree with the visible list in one render pass.
- Compact retained Installer backups into single-line desktop rows with responsive wrapping on narrow screens, keeping Validate, Restore and Delete actions.
- Preserve the existing private Installer backup transport, internal retention policy value, Discovery pre-mutation backup backend, restore validation, secret handling and privacy boundaries.
- Add permanent packaged regressions for the four-theme label palette, consolidated backup manager, toggle wiring, count/list source-of-truth and hidden duplicate Discovery backup UI.
- No switch mapping, physical geometry, connector, PoE, telemetry, maximum-capability, support-status or Core source contract changes.

## 2.3.9

- Consolidate the Hub landing page around one Switch Vision Settings card: remove the redundant Discovery Settings and SNMP2MQTT Settings homepage cards while keeping both settings sections fully available inside Switch Vision Settings.
- Give the Switch Vision Settings homepage card exactly three concise bullets: UI Settings, Discovery Settings and SNMP2MQTT Settings.
- Tighten Hub settings option rows vertically by reducing toggle minimum height, internal padding and checkbox-to-label spacing without changing the shared 38px input/select/button geometry.
- Tighten the two-column option layout horizontally, reduce subsection/header spacing, and compact Shortcut order row spacing while preserving responsive one-column mobile behavior.
- Add permanent packaged regressions protecting the consolidated homepage navigation and the tighter Hub settings spacing contract.
- No settings ownership, secret handling, switch mapping, physical geometry, connector, PoE, telemetry, maximum-capability, support-status or privacy contracts change.

## 2.3.8

- Compact Calibration Profiles cards into one visual block by placing the action controls inline with the Internal profile row on desktop and wrapping them beneath it on narrow screens.
- Remove the visible Base profile, Faceplate exists and SHA-256 detail rows; base-profile compatibility, faceplate-existence state and integrity/duplicate metadata remain available to backend/runtime logic.
- Remove the old separator/details band and excess action-row margin while preserving the shared Hub control/button geometry and tightening only the spacing between profile actions.
- Compact Settings checkbox/toggle groups into left-anchored content-width columns instead of two half-card columns, reducing wasted horizontal space while preserving one-column mobile stacking.
- Reduce the sticky Save/Reload footer to a slim command bar by removing excess outer padding/margins while keeping the same shared 38px button geometry.
- Compact detected-device facts into one responsive line (`Registry · Validated · Physical · RJ45`) instead of a four-row definition block.
- Compact Installer recovery-backup rows into one responsive line containing backup name, timestamp and Switch Vision version, with actions alongside; remove the visible component inventory while preserving it in private backup metadata and restore validation.
- Tighten detected-device validation status cells by reducing their grid gap, top margin and internal padding while preserving status colour/readability.
- Start all collapsible Hub sections closed by default, including Core Settings and both generated-YAML managers; direct settings shortcuts still expand the requested component programmatically.
- Add a packaged regression protecting the compact card structure, all profile actions, hidden-only technical metadata, duplicate-state behavior, compact toggle columns, slim Save bar, compact device facts/backups, compact validation cells and collapsed defaults.
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
