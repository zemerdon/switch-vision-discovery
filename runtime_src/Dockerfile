FROM ghcr.io/home-assistant/base:3.22

ARG BUILD_VERSION
ARG BUILD_ARCH

RUN apk add --no-cache net-snmp-tools jq zip python3 py3-yaml

COPY run.sh /run.sh
COPY discovery_job.sh /discovery_job.sh
COPY discovery_contract_entrypoint.py /discovery_contract_entrypoint.py
COPY physical_contract.py /physical_contract.py
COPY physical_contract_prepare.sh /physical_contract_prepare.sh
COPY support_my_switch.sh /support_my_switch.sh
COPY sanitize_support_bundle.py /sanitize_support_bundle.py
COPY ha_entity_snapshot_sanitizer.py /ha_entity_snapshot_sanitizer.py
COPY support_diagnostics.py /support_diagnostics.py
COPY walk_correlation.py /walk_correlation.py
COPY make_support_email.py /make_support_email.py
COPY support_web.py /support_web.py
COPY core_bridge.py /core_bridge.py
COPY support_web_entry.py /support_web_entry.py
COPY mqtt_maintenance.py /mqtt_maintenance.py
COPY mqtt_maintenance_runtime.py /mqtt_maintenance_runtime.py
COPY supervisor_runtime.py /supervisor_runtime.py
COPY maintenance.js /maintenance.js
COPY credits_v25.css /credits_v25.css
COPY credits_v25.js /credits_v25.js
COPY migrate_options.py /migrate_options.py
COPY registry_lookup.py /registry_lookup.py
COPY standard_sensor_scan.py /standard_sensor_scan.py
COPY vendor_sensor_scan.py /vendor_sensor_scan.py
COPY juniper_vlan_modes.py /juniper_vlan_modes.py
COPY unifi_dashboard_cards.py /unifi_dashboard_cards.py
COPY devices /opt/switch-vision/devices
COPY mib_database /opt/switch-vision/mib_database
COPY vendors /opt/switch-vision/vendors

# Home Assistant's builder passes the app version as BUILD_VERSION. Stamp the
# two runtime entrypoints from that single authoritative release value so the
# published image cannot drift from config.yaml while keeping tracked source
# deterministic between releases.
RUN test -n "$BUILD_VERSION" \
    && sed -i "s/^SWITCH_VISION_DISCOVERY_VERSION=\"[^\"]*\"$/SWITCH_VISION_DISCOVERY_VERSION=\"$BUILD_VERSION\"/" /run.sh /discovery_job.sh \
    && grep -Fqx "SWITCH_VISION_DISCOVERY_VERSION=\"$BUILD_VERSION\"" /run.sh \
    && grep -Fqx "SWITCH_VISION_DISCOVERY_VERSION=\"$BUILD_VERSION\"" /discovery_job.sh

RUN chmod a+x /run.sh /discovery_job.sh /discovery_contract_entrypoint.py /physical_contract.py /physical_contract_prepare.sh /support_my_switch.sh /sanitize_support_bundle.py /ha_entity_snapshot_sanitizer.py /make_support_email.py /support_web.py /support_web_entry.py /migrate_options.py /registry_lookup.py /standard_sensor_scan.py /vendor_sensor_scan.py /juniper_vlan_modes.py /unifi_dashboard_cards.py

CMD [ "/run.sh" ]
