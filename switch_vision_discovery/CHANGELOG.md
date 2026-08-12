# Changelog

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
