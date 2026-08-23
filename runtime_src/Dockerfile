FROM ghcr.io/home-assistant/base:3.22

ARG BUILD_VERSION
ARG BUILD_ARCH

RUN apk add --no-cache net-snmp-tools jq zip python3 py3-yaml

COPY run.sh /run.sh
COPY discovery_job.sh /discovery_job.sh
COPY support_my_switch.sh /support_my_switch.sh
COPY sanitize_support_bundle.py /sanitize_support_bundle_base.py
COPY ha_entity_snapshot_sanitizer.py /sanitize_support_bundle.py
COPY support_diagnostics.py /support_diagnostics.py
COPY make_support_email.py /make_support_email.py
COPY support_web.py /support_web.py
COPY mqtt_maintenance.py /mqtt_maintenance.py
COPY mqtt_maintenance_runtime.py /mqtt_maintenance_runtime.py
COPY maintenance.js /maintenance.js
COPY migrate_options.py /migrate_options.py
COPY registry_lookup.py /registry_lookup.py
COPY standard_sensor_scan.py /standard_sensor_scan.py
COPY vendor_sensor_scan.py /vendor_sensor_scan.py
COPY juniper_vlan_modes.py /juniper_vlan_modes.py
COPY unifi_dashboard_cards.py /unifi_dashboard_cards.py
COPY devices /opt/switch-vision/devices
COPY mib_database /opt/switch-vision/mib_database
COPY vendors /opt/switch-vision/vendors
RUN chmod a+x /run.sh /discovery_job.sh /support_my_switch.sh /sanitize_support_bundle.py /sanitize_support_bundle_base.py /make_support_email.py /support_web.py /migrate_options.py /registry_lookup.py /standard_sensor_scan.py /vendor_sensor_scan.py /juniper_vlan_modes.py /unifi_dashboard_cards.py

CMD [ "/run.sh" ]
