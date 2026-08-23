# Changelog

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
