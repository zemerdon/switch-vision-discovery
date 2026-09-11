FROM ghcr.io/home-assistant/base:3.22@sha256:8f937e0b89e108f432d3cb140900f06e568f8f4fbdb7987472447f54d8b24495

ARG BUILD_VERSION
ARG BUILD_ARCH

RUN apk add --no-cache net-snmp-tools net-snmp libsmi jq zip python3 py3-yaml py3-websockets

# Keep the runtime self-contained for both current and future model work. Net-SNMP
# stays in numeric-output mode at runtime (-On); bundled MIB tooling is for
# translation, validation and future vendor/profile development, not a hidden
# dependency on host-installed packages.
RUN command -v snmpwalk \
    && command -v snmptranslate \
    && command -v smilint \
    && command -v smidump \
    && snmptranslate -On SNMPv2-MIB::sysDescr.0 | grep -Fqx '.1.3.6.1.2.1.1.1.0' \
    && test -f /usr/share/snmp/mibs/IF-MIB.txt \
    && test -f /usr/share/snmp/mibs/BRIDGE-MIB.txt \
    && test -f /usr/share/snmp/mibs/HOST-RESOURCES-MIB.txt \
    && test -f /usr/share/libsmi/mibs/ietf/Q-BRIDGE-MIB \
    && test -f /usr/share/libsmi/mibs/ietf/ENTITY-MIB \
    && test -f /usr/share/libsmi/mibs/ietf/ENTITY-SENSOR-MIB \
    && test -f /usr/share/libsmi/mibs/ietf/POWER-ETHERNET-MIB \
    && test -f /usr/share/libsmi/mibs/ietf/MAU-MIB


ADD runtime.tar.gz /

RUN chmod a+x \
    /run.sh \
    /discovery_job.sh \
    /discovery_contract_entrypoint.py \
    /physical_contract_prepare.sh \
    /support_my_switch.sh \
    /sanitize_support_bundle.py \
    /ha_entity_snapshot_sanitizer.py \
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
