#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "runtime_src/discovery_job.sh"
REGISTRY = ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"


def canonical(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def patch_hp_card_binding() -> None:
    text = JOB.read_text(encoding="utf-8")
    old_live = '''        case "${effective_model:-${detected_model:-}}" in
          *S5720-12TP-LI-AC*|*WS-C3750-48P*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_1g_{port}_status" ;;
          *) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_10g_{port}_status" ;;
        esac'''
    new_live = '''        case "${effective_model:-${detected_model:-}}" in
          *J8693A*|*3500yl-48G*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_uplink_{port}_status" ;;
          *S5720-12TP-LI-AC*|*WS-C3750-48P*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_1g_{port}_status" ;;
          *) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_10g_{port}_status" ;;
        esac'''
    old_fallback = '''      case "${exact_model:-}" in
        *S5720-12TP-LI-AC*|*WS-C3750-48P*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_1g_{port}_status" ;;
        *) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_10g_{port}_status" ;;
      esac'''
    new_fallback = '''      case "${exact_model:-}" in
        *J8693A*|*3500yl-48G*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_uplink_{port}_status" ;;
        *S5720-12TP-LI-AC*|*WS-C3750-48P*) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_1g_{port}_status" ;;
        *) echo "        sfp_status_entity_template: sensor.${safe_prefix}_sfp_10g_{port}_status" ;;
      esac'''
    if old_live in text:
        text = text.replace(old_live, new_live, 1)
    elif new_live not in text:
        raise SystemExit("live generated-card template block not found")
    if old_fallback in text:
        text = text.replace(old_fallback, new_fallback, 1)
    elif new_fallback not in text:
        raise SystemExit("fallback generated-card template block not found")
    JOB.write_text(text, encoding="utf-8")


def anonymous_contributor() -> dict:
    return {"display_name": "community contributor", "public_credit": False}


def contribution(cid: str, source_component: str, source_discovery_version: str, scope: str, dashboard: str) -> dict:
    return {
        "id": cid,
        "source_component": source_component,
        "source_discovery_version": source_discovery_version,
        "devices_observed": 1,
        "validation_scope": scope,
        "api_capabilities": {"port_detail": True, "per_port_traffic": False} if "UniFi2MQTT" in source_component else {},
        "dashboard_validation": dashboard,
        "contributor": anonymous_contributor(),
    }


def base_device(*, vendor: str, family: str, model: str, ports: dict, mapping: str,
                dashboard: bool = False, calibration: str = "", faceplate: str = "",
                stack: bool = False, notes: list[str], validation: dict,
                source: str = "support_my_switch_real_hardware_contribution") -> dict:
    return {
        "vendor": vendor,
        "family": family,
        "model": model,
        "status": "experimental",
        "confirmed_since": "2.3.24",
        "last_validated_version": "2.3.24",
        "evidence": source,
        "ports": ports,
        "stack_support": stack,
        "discovery_support": True,
        "dashboard_support": dashboard,
        "mapping_profile": mapping,
        "calibration_profile": calibration,
        "default_faceplate": faceplate,
        "optional_faceplates": [],
        "tested_firmware": [],
        "contributor": anonymous_contributor(),
        "notes": notes,
        "validation": validation,
        "visuals": {
            "status": "experimental" if dashboard else "pending",
            "recommended_faceplate": faceplate,
            "optional_faceplates": [],
            "calibration_profile": calibration,
            "canvas": {"width": 2048, "height": 448},
        },
    }


def ensure_note(device: dict, note: str) -> None:
    notes = device.setdefault("notes", [])
    if note not in notes:
        notes.append(note)


def ensure_firmware(device: dict, firmware: str) -> None:
    vals = device.setdefault("tested_firmware", [])
    if firmware and firmware not in vals:
        vals.append(firmware)


def ensure_contribution(device: dict, item: dict) -> None:
    vals = device.setdefault("contributions", [])
    if not any(str(x.get("id")) == item["id"] for x in vals if isinstance(x, dict)):
        vals.append(item)


def append_evidence(device: dict, token: str) -> None:
    current = str(device.get("evidence") or "")
    parts = [x.strip() for x in current.split(";") if x.strip()]
    if token not in parts:
        parts.append(token)
    device["evidence"] = "; ".join(parts)


def patch_registry() -> None:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    devices = data.setdefault("devices", [])
    by_model = {canonical(d.get("model", "")): d for d in devices if isinstance(d, dict)}

    additions = [
        base_device(
            vendor="Dell", family="PowerConnect 5500", model="PowerConnect 5548P",
            ports={"rj45": 48, "poe": True, "uplinks": 2, "uplink_type": "2x 10G SFP+", "gigabit_sfp": 0, "ten_gigabit_sfp_plus": 2},
            mapping="dell-powerconnect-5548p-48p-2x10g", dashboard=True,
            calibration="stock_48rj45_2sfp", faceplate="faceplates/48rj45-2sfp.png",
            notes=[
                "A sanitized real-hardware contribution exposes lowercase gi1/0/1..48 access interfaces and te1/0/1..2 uplinks.",
                "The exact-model classifier is intentionally narrow so lowercase Gi/Te names on unrelated devices remain excluded.",
                "Physical mapping is evidence-backed; PoE and environmental/system telemetry remain incomplete and therefore Experimental.",
            ],
            validation={"exact_model_detection": "contribution_confirmed", "rj45_mapping": "real_hardware_interface_map_confirmed", "poe": "pending_live_validation", "system_sensors": "pending", "uplinks": "real_hardware_interface_map_confirmed", "stack": "not_applicable"},
        ),
        base_device(
            vendor="Zyxel", family="GS1900", model="GS1900-24E",
            ports={"rj45": 24, "poe": False, "uplinks": 0, "uplink_type": "none", "gigabit_sfp": 0, "ten_gigabit_sfp_plus": 0},
            mapping="zyxel-gs1900-24e-24p", dashboard=False,
            notes=[
                "The contributed real-hardware walk already classifies all 24 RJ45 ports correctly with the generic interface parser.",
                "This entry adds exact identity/registry support without broadening the working interface classifier.",
                "Exact dashboard artwork remains pending.",
            ],
            validation={"exact_model_detection": "contribution_confirmed", "rj45_mapping": "real_hardware_24_ports_confirmed", "poe": "not_applicable", "system_sensors": "pending", "uplinks": "not_applicable", "stack": "not_applicable"},
        ),
        base_device(
            vendor="Cisco", family="Catalyst 3750X", model="WS-C3750X-48P",
            ports={"rj45": 48, "poe": True, "uplinks": 4, "uplink_type": "C3KX network-module SFP/SFP+", "gigabit_sfp": 2, "ten_gigabit_sfp_plus": 2},
            mapping="cisco-3750x-48p-c3kx", dashboard=True,
            calibration="default_cisco_48_port", faceplate="faceplates/48rj45-4sfp.png", stack=True,
            notes=[
                "A two-member sanitized real-hardware stack contribution proves 48 Gi access ports per member.",
                "C3KX network-module Gi aliases are de-duplicated when the same physical cages are also represented by Te interfaces; this prevents the previous 104-RJ45 overcount.",
                "The contributed module exposure corresponds to two 1G SFP plus two 10G SFP+ logical cage roles per member; other C3KX module variants remain outside this exact mapping until contributed.",
            ],
            validation={"exact_model_detection": "contribution_confirmed_two_member_stack", "rj45_mapping": "real_hardware_48_per_member_confirmed", "poe": "pending_live_dashboard_validation", "system_sensors": "pending", "uplinks": "real_hardware_alias_dedup_mapping_confirmed", "stack": "real_hardware_two_member_topology_confirmed"},
        ),
        base_device(
            vendor="Cisco", family="Cisco Small Business SG350", model="SG350-20",
            ports={"rj45": 16, "poe": False, "uplinks": 4, "uplink_type": "2 dual-personality copper/SFP + 2 SFP", "gigabit_sfp": 2, "ten_gigabit_sfp_plus": 0},
            mapping="cisco-sg350-20-16p-2combo-2sfp", dashboard=False,
            notes=[
                "The real-hardware IF-MIB exposes gi1..gi20 for the twenty front-panel logical positions.",
                "Ports 17-18 are kept as neutral uplink/combo positions because ifName alone cannot prove whether copper or SFP is populated.",
                "Ports 19-20 are SFP-only; exact combo-aware artwork remains pending.",
            ],
            validation={"exact_model_detection": "contribution_confirmed", "rj45_mapping": "real_hardware_fixed_ports_1_16_confirmed", "poe": "not_applicable", "system_sensors": "pending", "uplinks": "combo_semantics_conservative_pending_medium_validation", "stack": "not_applicable"},
        ),
        base_device(
            vendor="HP", family="3500yl", model="HP J8693A Switch 3500yl-48G",
            ports={"rj45": 44, "poe": True, "uplinks": 4, "uplink_type": "4 dual-personality 1G RJ45/SFP", "gigabit_sfp": 4, "ten_gigabit_sfp_plus": 0},
            mapping="hp-3500yl-j8693a-44p-4combo", dashboard=False,
            notes=[
                "The existing exact-model numeric-interface classifier maps ports 1-44 as RJ45 and 45-48 as neutral uplink positions.",
                "A community contribution confirmed that generated entities use uplink_1..uplink_4 names; Discovery 2.3.24 binds generated cards to those entities instead of incorrectly forcing sfp_10g names.",
                "The four front-panel positions are dual-personality RJ45/mini-GBIC; exact medium-specific rendered validation remains pending.",
            ],
            validation={"exact_model_detection": "contribution_confirmed", "rj45_mapping": "real_hardware_numeric_ports_1_44_confirmed", "poe": "platform_capability_confirmed_telemetry_pending", "system_sensors": "pending", "uplinks": "entity_binding_confirmed_medium_pending", "stack": "not_applicable"},
        ),
        base_device(
            vendor="Ubiquiti", family="UniFi Switch Pro HD", model="USW Pro HD 24 PoE",
            ports={"rj45": 24, "poe": True, "uplinks": 4, "uplink_type": "4x 10G SFP+", "gigabit_sfp": 0, "ten_gigabit_sfp_plus": 4},
            mapping="ubiquiti-usw-pro-hd-24-poe-snmp", dashboard=True,
            calibration="stock_24rj45_4sfp", faceplate="faceplates/24rj45-4sfp.png",
            notes=[
                "An anonymous sanitized real-hardware SNMP contribution exposes compact sysDescr USWProHD24PoE and ifName 0/1..0/28.",
                "Ports 0/1..0/24 are RJ45 and 0/25..0/28 are 10G SFP+; live link-state/speed evidence included active 10G optical links.",
                "PoE and environmental/system sensor telemetry were not validated by this SNMP contribution and remain pending.",
            ],
            validation={"exact_model_detection": "real_hardware_snmp_confirmed", "rj45_mapping": "real_hardware_snmp_ports_0_1_0_24_confirmed", "poe": "pending", "system_sensors": "pending", "uplinks": "real_hardware_snmp_ports_0_25_0_28_confirmed", "stack": "not_applicable"},
        ),
        base_device(
            vendor="Ubiquiti", family="UniFi Switch Aggregation", model="USW Aggregation",
            ports={"rj45": 0, "poe": False, "uplinks": 8, "uplink_type": "8x 10G SFP+", "gigabit_sfp": 0, "ten_gigabit_sfp_plus": 8},
            mapping="ubiquiti-usw-aggregation-api", dashboard=False,
            notes=[
                "An anonymous UniFi2MQTT 2.0.50 real-hardware snapshot confirms eight 10G SFP+ API ports with live link-state/speed detail.",
                "The contributed snapshot observed five active 10G optical links; per-port traffic counters were not available through this normalized API path.",
                "No existing generic faceplate can safely represent eight optical-only positions, so exact dashboard visuals remain pending.",
            ],
            validation={"exact_model_detection": "live_api_confirmed", "rj45_mapping": "not_applicable", "poe": "not_applicable", "system_sensors": "live_api_confirmed_cpu_memory_uptime", "uplinks": "live_api_confirmed_ports_1_8_10g_sfp_plus", "stack": "not_applicable"},
            source="support_my_switch_unifi2mqtt_2.0.50_real_hardware",
        ),
        base_device(
            vendor="Ubiquiti", family="UniFi Switch Enterprise", model="USW Enterprise 24 PoE",
            ports={"rj45": 24, "poe": True, "uplinks": 2, "uplink_type": "2x 10G SFP+", "gigabit_sfp": 0, "ten_gigabit_sfp_plus": 2},
            mapping="ubiquiti-usw-enterprise-24-poe-api", dashboard=True,
            calibration="unifi_24p_rj45_2sfp", faceplate="faceplates/unifi-24p-rj45-2sfp.png",
            notes=[
                "An anonymous UniFi2MQTT 2.0.50 real-hardware snapshot confirms 24 RJ45 plus two 10G SFP+ ports.",
                "API ports 1-12 are 1G-capable RJ45, ports 13-24 are 2.5G-capable RJ45, and ports 25-26 are 10G SFP+; live negotiated speeds included 2.5G and 10G links.",
                "Per-port traffic counters were not available through the normalized API path; Switch Vision must not synthesize them.",
            ],
            validation={"exact_model_detection": "live_api_confirmed", "rj45_mapping": "live_api_confirmed_ports_1_24", "poe": "live_api_output_capability_confirmed", "system_sensors": "live_api_confirmed_cpu_memory_uptime", "uplinks": "live_api_confirmed_ports_25_26_10g_sfp_plus", "stack": "not_applicable"},
            source="support_my_switch_unifi2mqtt_2.0.50_real_hardware",
        ),
        base_device(
            vendor="Ubiquiti", family="UniFi Switch Flex", model="USW Flex 2.5G 5",
            ports={"rj45": 5, "poe": False, "uplinks": 0, "uplink_type": "none", "gigabit_sfp": 0, "ten_gigabit_sfp_plus": 0},
            mapping="ubiquiti-usw-flex-2p5g-5-api", dashboard=False,
            notes=[
                "An anonymous UniFi2MQTT 2.0.50 real-hardware snapshot confirms five 2.5G-capable RJ45 API ports.",
                "The contributed snapshot observed live 1G and 2.5G negotiated links; the device does not expose PoE output capability.",
                "Exact five-port artwork remains pending; the UniFi card generator may use a safe oversized generic visual while preserving the true five-port count.",
            ],
            validation={"exact_model_detection": "live_api_confirmed", "rj45_mapping": "live_api_confirmed_ports_1_5_2p5g_capable", "poe": "live_api_confirmed_no_poe_output", "system_sensors": "live_api_confirmed_cpu_memory_uptime", "uplinks": "not_applicable", "stack": "not_applicable"},
            source="support_my_switch_unifi2mqtt_2.0.50_real_hardware",
        ),
        base_device(
            vendor="Ubiquiti", family="UniFi WAN Switch", model="USW WAN",
            ports={"rj45": 1, "poe": False, "uplinks": 3, "uplink_type": "3x 10G SFP+", "gigabit_sfp": 0, "ten_gigabit_sfp_plus": 3},
            mapping="ubiquiti-usw-wan-api", dashboard=False,
            notes=[
                "An anonymous UniFi2MQTT 2.0.50 real-hardware snapshot reports three 10G SFP+ ports followed by one 1G RJ45 port, all live in the contributed capture.",
                "That observed connector topology exactly matches the Ubiquiti USW-WAN product and distinguishes it from the separate USW-WAN-RJ45 variant.",
                "Exact four-position WAN-switch artwork remains pending.",
            ],
            validation={"exact_model_detection": "live_api_plus_official_topology_confirmed", "rj45_mapping": "live_api_confirmed_api_port_4", "poe": "not_applicable", "system_sensors": "live_api_confirmed_cpu_memory_uptime", "uplinks": "live_api_confirmed_api_ports_1_3_10g_sfp_plus", "stack": "not_applicable"},
            source="support_my_switch_unifi2mqtt_2.0.50_real_hardware",
        ),
    ]

    for device in additions:
        key = canonical(device["model"])
        if key not in by_model:
            devices.append(device)
            by_model[key] = device

    # Exact API port maps from Timothy's anonymous SV-2026-000028 bundle.
    for model, mapping in {
        "USW Aggregation": {"rj45": [], "sfp": list(range(1, 9))},
        "USW Enterprise 24 PoE": {"rj45": list(range(1, 25)), "sfp": [25, 26]},
        "USW Flex 2.5G 5": {"rj45": list(range(1, 6)), "sfp": []},
        "USW WAN": {"rj45": [4], "sfp": [1, 2, 3]},
    }.items():
        by_model[canonical(model)]["unifi_api_port_map"] = mapping

    # Timothy also supplied fresh evidence for two already-registered devices.
    enterprise8 = by_model.get(canonical("USW Enterprise 8 PoE"))
    if enterprise8:
        append_evidence(enterprise8, "support_my_switch_sv_2026_000028_unifi2mqtt_2.0.50")
        ensure_firmware(enterprise8, "7.5.10")
        ensure_contribution(enterprise8, contribution("sv-2026-000028-enterprise8", "UniFi2MQTT 2.0.50", "2.3.21", "additional_real_hardware_api_validation", "existing_registry_entry_revalidated"))
        ensure_note(enterprise8, "The anonymous SV-2026-000028 snapshot adds fresh live validation of the existing 8 RJ45 + 2 SFP+ topology, including active 1G copper and 10G optical links.")

    flexmini = by_model.get(canonical("USW Flex Mini"))
    if flexmini:
        append_evidence(flexmini, "support_my_switch_sv_2026_000028_unifi2mqtt_2.0.50")
        ensure_firmware(flexmini, "2.1.6")
        ensure_contribution(flexmini, contribution("sv-2026-000028-flexmini", "UniFi2MQTT 2.0.50", "2.3.21", "additional_api_topology_capture_device_offline", "existing_registry_entry_revalidated"))
        ensure_note(flexmini, "The anonymous SV-2026-000028 snapshot independently repeats the five-RJ45 API topology; this particular device was offline, so it does not add live link-state validation.")

    # Mark's anonymous SNMP bundle strengthens the already-existing Pro XG 8 PoE entry.
    xg8 = by_model.get(canonical("USW Pro XG 8 PoE"))
    if xg8:
        append_evidence(xg8, "support_my_switch_sv_2026_000006_real_hardware_snmp")
        ensure_contribution(xg8, {"id": "sv-2026-000006-snmp", "source_component": "Discovery SNMP", "source_discovery_version": "2.3.21", "devices_observed": 1, "validation_scope": "exact_compact_sysdescr_and_physical_ifname_mapping", "dashboard_validation": "pending_post_fix_user_validation", "contributor": anonymous_contributor()})
        ensure_note(xg8, "The anonymous SV-2026-000006 SNMP capture proves compact sysDescr USWProXG8PoE and physical ifName 0/1..0/10; ports 0/1..0/8 are RJ45 and 0/9..0/10 are 10G SFP+ with a live 10G optical link observed.")
        val = xg8.setdefault("validation", {})
        val["exact_model_detection"] = "real_hardware_snmp_confirmed"
        val["rj45_mapping"] = "real_hardware_snmp_ports_0_1_0_8_confirmed"
        val["uplinks"] = "real_hardware_snmp_ports_0_9_0_10_confirmed"

    # Attach contribution provenance to new exact entries without exposing contributor identity.
    for model, cid, component, source_version, scope in [
        ("PowerConnect 5548P", "sv-2026-000011-5548p", "Discovery SNMP", "2.3.21", "exact_model_and_physical_interface_mapping"),
        ("GS1900-24E", "sv-2026-000011-gs1900", "Discovery SNMP", "2.3.21", "exact_model_and_existing_24_port_mapping"),
        ("WS-C3750X-48P", "sv-2026-000008", "Discovery SNMP", "2.3.22", "two_member_stack_interface_alias_dedup"),
        ("SG350-20", "sv-2026-000048", "Discovery SNMP", "2.3.21", "exact_model_front_panel_mapping"),
        ("HP J8693A Switch 3500yl-48G", "sv-2026-000033", "Discovery SNMP", "2.3.23", "generated_card_uplink_entity_binding"),
        ("USW Pro HD 24 PoE", "sv-2026-000006-hd24", "Discovery SNMP", "2.3.21", "exact_compact_sysdescr_and_physical_ifname_mapping"),
        ("USW Aggregation", "sv-2026-000028-aggregation", "UniFi2MQTT 2.0.50", "2.3.21", "real_hardware_api_topology_and_live_links"),
        ("USW Enterprise 24 PoE", "sv-2026-000028-enterprise24", "UniFi2MQTT 2.0.50", "2.3.21", "real_hardware_api_topology_and_live_links"),
        ("USW Flex 2.5G 5", "sv-2026-000028-flex2p5g5", "UniFi2MQTT 2.0.50", "2.3.21", "real_hardware_api_topology_and_live_links"),
        ("USW WAN", "sv-2026-000028-wan", "UniFi2MQTT 2.0.50", "2.3.21", "real_hardware_api_topology_and_live_links"),
    ]:
        dev = by_model.get(canonical(model))
        if dev:
            ensure_contribution(dev, contribution(cid, component, source_version, scope, "pending_post_fix_user_validation"))

    for model, fw in {
        "USW Aggregation": "7.5.10",
        "USW Enterprise 24 PoE": "7.4.1",
        "USW Flex 2.5G 5": "2.1.8",
        "USW WAN": "7.3.109",
    }.items():
        ensure_firmware(by_model[canonical(model)], fw)

    REGISTRY.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    patch_hp_card_binding()
    patch_registry()
