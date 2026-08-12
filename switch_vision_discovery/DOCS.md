# Switch Vision Discovery v2.1.1

Switch Vision Discovery is a read-only Home Assistant app that walks or imports SNMP data, identifies exact switch hardware, classifies interfaces, writes capability reports, and generates SNMP2MQTT and dashboard YAML.

## Requirements

- Home Assistant OS or Supervised with `/share` access
- SNMP v2c read-only access to each target
- UDP/161 reachability from Home Assistant
- Switch Vision custom integration and assets from the same release
- Separate Switch Vision SNMP2MQTT app for live entities

## Recommended operation

- Start on boot: enabled for persistent Web UI access
- Run Discovery manually when adding, validating, or re-walking switches
- Use targeted mode for known switches
- Use full mode when investigating new hardware

## Main outputs

```text
/share/switch_vision/snmpwalk.log
/share/switch_vision/discovery-report.txt
/share/switch_vision/last-discovery-run.txt
/share/switch_vision/generated-snmp2mqtt.yaml
/share/switch_vision/generated-dashboard-card.yaml
```

Per-switch walks are stored under a stable folder based on **Switch Name (Used internally only)**.

When Switch Vision UniFi2MQTT is installed, **Switch Vision Hub → UniFi2MQTT Settings** exposes its controller/MQTT configuration, install/running state, snapshot availability, and normalized device count. API keys and MQTT passwords are never read back into the browser; blank secret fields preserve the stored values. Home Assistant App configuration remains available as a fallback.

The Discovery Web UI presents **Generated Card YAML** above **Generated SNMP2MQTT YAML**. The card section validates the file and provides preview, copy, and download actions. Generated dashboard YAML remains review/copy only and is not installed automatically.

Discovery treats stored SNMP walks as explicit offline input only: they are parsed when `parse_all_walks` is enabled, not as an automatic fallback when a current run has no SNMP data. Dashboard-card generation is independent, so UniFi API-only installations can generate fresh cards without SNMP.

The **SNMP cleanup** action can retire the generated SNMP path completely. It stops Switch Vision SNMP2MQTT, clears identifiable retained Home Assistant MQTT Discovery entries using exact generated topic names recorded without credentials, removes saved SNMP walks/capability caches/generated SNMP files, and preserves UniFi2MQTT data/settings.

## Exact-model profiles

Discovery uses **Auto-detect** by default. A recognised exact SKU receives its registered interface mapping, calibration profile, and recommended visible faceplate automatically.

Unknown models receive a visible generic fallback and can be customised until a registered profile is available. A registered model can also be selected as an experimental compatibility override while the real detected model remains recorded.

Confirmed and Experimental status applies only to the exact models in the shipped supported-device registry.

## Display names and stack members

- `switch_name` is the stable internal target ID.
- `display_name` is optional friendly card text.
- Stack-member `display_name` becomes that member's generated card title.
- Member/profile identity remains based on the stable sensor prefix.

## Port activity

Dashboard activity is derived from RX/TX byte-counter changes. Separate `_last_change` MQTT entities are not required.

## Configuration export and import

The Configuration page exports the switch list, stack mappings, and Discovery settings to portable JSON. Store exports securely because they may contain management addresses and SNMP community strings.

Import validates the JSON, path roots, numeric limits, switch rows, and stack rows before writing anything. It creates `/data/options.before-import.json` and preserves current Support My Switch privacy and recognition preferences.

## Support My Switch

Support My Switch creates a privacy-processed bundle from a temporary copy of `/share/switch_vision/`. The live folder is not modified.

Clean, fully inspected bundles can include:

- contribution ZIP;
- prepared `.eml` addressed to `switch-vision@zemerdon.com`;
- local Actions HTML page.

Unsupported binary, oversized, unreadable, unwritable, symlink, or special files are excluded and force **REVIEW REQUIRED**. Blocked bundles provide the ZIP and privacy reports but withhold prepared send actions. Nothing is sent automatically.

If the experimental UniFi2MQTT snapshot exists at `/share/switch_vision/unifi/devices.json`, Support My Switch always masks stable UniFi device IDs and, when hostname masking is enabled, masks the user-assigned UniFi device names.

## Diagnostics

The persistent Web UI includes read-only Diagnostics for:

- running app version;
- device registry state;
- generated YAML files;
- per-device capability data;
- support contribution readiness;
- installed related-app links.

## Updating

Switch Vision Installer manages Discovery installation and updates through this public Home Assistant app repository. Home Assistant Supervisor tracks the repository version and pulls the matching published container image.

## Home Assistant app compatibility

Discovery uses only the shared `/share` data mapping; it does not request direct Home Assistant `/config` access. The Dockerfile is the single build source and uses the supported Home Assistant Alpine 3.22 base. On startup, Discovery removes the retired `show_card_header` option from older saved app options so current Supervisor schema validation stays clean after the first migrated start.
