FROM ghcr.io/home-assistant/base:3.22

ARG BUILD_VERSION
ARG BUILD_ARCH

RUN apk add --no-cache net-snmp-tools jq zip python3 py3-yaml

ADD runtime.tar.gz /

RUN chmod a+x \
    /run.sh \
    /discovery_job.sh \
    /support_my_switch.sh \
    /sanitize_support_bundle.py \
    /make_support_email.py \
    /support_web.py \
    /registry_lookup.py \
    /standard_sensor_scan.py \
    /vendor_sensor_scan.py \
    /juniper_vlan_modes.py \
    /unifi_dashboard_cards.py

LABEL \
    org.opencontainers.image.title="Switch Vision Discovery" \
    org.opencontainers.image.description="Switch Vision multi-vendor discovery and Hub app for Home Assistant" \
    org.opencontainers.image.source="https://github.com/zemerdon/switch-vision-discovery"

CMD [ "/run.sh" ]
