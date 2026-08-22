# Changelog

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
