#!/usr/bin/env python3
"""Registry metadata contracts that belong to Discovery authority, not Core."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"

WALK_BACKED_MODELS = {
    "HP 1810-24G",
    "GS1900-8",
    "SR-S25G3420F",
    "US-8-150W",
    "US-24-250W",
    "PowerConnect 5548P",
    "GS1900-24E",
    "WS-C3750X-48P",
    "SG350-20",
    "SG200-26",
    "HP J8693A Switch 3500yl-48G",
    "3524GT-PWR+",
    "N4032F",
    "USW Pro HD 24 PoE",
    "USW Aggregation",
    "USW Enterprise 24 PoE",
    "USW Flex 2.5G 5",
    "USW WAN",
    "GS1915-24EP",
}


def notes_text(device: dict) -> str:
    return json.dumps(device.get("notes") or [], ensure_ascii=False)


def contribution(device: dict, *, units: int) -> dict:
    rows = [
        row
        for row in device.get("contributions") or []
        if isinstance(row, dict)
        and row.get("source_component") == "UniFi2MQTT 2.0.47"
        and row.get("devices_observed") == units
    ]
    assert len(rows) == 1, (device.get("model"), rows)
    return rows[0]


def main() -> int:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    models = {
        str(item.get("model")): item
        for item in payload.get("devices", [])
        if isinstance(item, dict)
    }

    for model in WALK_BACKED_MODELS:
        device = models[model]
        assert device.get("evidence"), model
        contributor = device.get("contributor") or {}
        assert contributor.get("public_credit") is False, model

    hp_notes = notes_text(models["HP J8693A Switch 3500yl-48G"])
    assert "A1-A4" in hp_notes
    assert "does not add them to the current card geometry" in hp_notes

    n4032_optional = models["N4032F"].get("discovery_optional_interfaces") or []
    assert n4032_optional[0]["faceplate_positions"] == [25, 26]
    assert n4032_optional[0]["telemetry_only"] is False

    assert "zero-uplink" in notes_text(models["GS1915-24EP"]).lower()

    n2128 = models["N2128PX-ON"]
    assert n2128.get("evidence") == "community_hardware_validation"
    n2128_notes = notes_text(n2128)
    lowered_n2128 = n2128_notes.casefold()
    assert "contribution id" not in lowered_n2128
    assert "bundle received" not in lowered_n2128
    assert "current-build field feedback confirms" in lowered_n2128
    assert "faceplate alignment" in lowered_n2128
    assert "port-description presentation" in lowered_n2128
    assert "detailed per-port poe card/presentation" in lowered_n2128
    assert "system-sensor applicability" in lowered_n2128
    assert "vlan/trunk semantics" in lowered_n2128

    n4032_optional = models["N4032F"].get("discovery_optional_interfaces") or []
    assert n4032_optional[0]["interface_names"] == ["Fo1/1/1", "Fo1/1/2"]
    assert n4032_optional[0]["faceplate_positions"] == [25, 26]
    assert n4032_optional[0]["telemetry_only"] is False

    for model in ("UCG Ultra", "US 16 PoE 150W", "USW Pro Max 24", "USW Ultra"):
        device = models[model]
        assert device.get("evidence") == "multiple_real_hardware_unifi_api_contributions", model
        contributions = device.get("contributions") or []
        assert contributions, model
        for row in contributions:
            contributor = row.get("contributor") or {}
            assert str(contributor.get("display_name") or "").casefold() == "community contributor", model
            assert contributor.get("public_credit") is False, model
            assert row["api_capabilities"]["per_port_traffic"] is False, model

    assert "ports 17-24 are 2.5G-capable RJ45" in notes_text(models["USW Pro Max 24"])

    c3750 = models["WS-C3750-48P"]
    c3750_notes = notes_text(c3750)
    assert "10/100 FastEthernet" in c3750_notes
    assert "must not be advertised as Gigabit-capable" in c3750_notes
    assert "does not include the retail software-feature suffix" in c3750_notes
    c3750_contributor = c3750.get("contributor") or {}
    assert str(c3750_contributor.get("display_name") or "").casefold() == "community contributor"
    assert c3750_contributor.get("public_credit") is False
    serialized_c3750 = json.dumps(c3750)
    assert "SV-2026-" not in serialized_c3750
    assert '"public_credit": true' not in serialized_c3750

    assert "15.2(4)E10" in (models["WS-C3750X-48P-S"].get("tested_firmware") or [])

    sg200 = models["SG200-26"]
    assert sg200["status"] == "experimental"
    assert sg200["ports"]["rj45"] == 24
    assert sg200["ports"]["uplinks"] == 2
    assert sg200["ports"]["combo_ports"] == 2
    assert sg200["ports"]["combo_logical_ports"] == [25, 26]
    assert sg200["mapping_profile"] == "cisco-sg200-26-24p-2dual"
    assert sg200["default_faceplate"] == "faceplates/48rj45-2sfp.png"
    assert "1.3.6.1.4.1.9.6.1.88.26.1" in notes_text(sg200)

    usw24g2 = models["USW-24-G2"]
    assert usw24g2["status"] == "experimental"
    assert usw24g2["ports"]["rj45"] == 24
    assert usw24g2["ports"]["gigabit_sfp"] == 2
    assert usw24g2["ports"]["poe"] is False
    assert usw24g2["mapping_profile"] == "ubiquiti-usw-24-g2-api"
    assert usw24g2["default_faceplate"] == "faceplates/unifi-24-rj45-2sfp-inline.png"
    assert "7.5.15" in usw24g2["tested_firmware"]
    assert "per-port RX/TX counters" in notes_text(usw24g2)

    for model in ("USW-16-PoE", "US 8 60W", "USW Flex Mini"):
        device = models[model]
        assert device["last_validated_version"] == "3.0.18", model
        assert "per-port RX/TX traffic" in notes_text(device), model
    assert models["USW Flex Mini"]["status"] == "community_validated"

    for model in ("SG500X-24", "S5720-12TP-LI-AC", "S5735-L8P4X-A1"):
        device = models[model]
        assert device.get("status") == "community_validated", model
        notes = notes_text(device)
        assert "link/activity" in notes, model
        assert "rendered alignment" in notes, model

    mikrotik = models["CRS328-24P-4S+RM"]
    contributor = mikrotik.get("contributor") or {}
    assert contributor.get("display_name") == "community contributor"
    assert contributor.get("public_credit") is False
    mikrotik_notes = notes_text(mikrotik)
    assert "local RouterOS model string" in mikrotik_notes
    assert "four SFP+ cage positions" in mikrotik_notes
    assert "rendered alignment" in mikrotik_notes

    c3560 = models["WS-C3560CG-8PC-S"]
    c3560_notes = notes_text(c3560)
    assert "Gi0/9" in c3560_notes
    assert "Gi0/10" in c3560_notes
    assert "dual-purpose" in c3560_notes.lower()

    for model in ("WS-C2960X-24TS-L", "WS-C3560CG-8PC-S"):
        assert models[model].get("status") == "experimental", model
        assert "Remains Experimental" in notes_text(models[model]), model

    expected_contributions = {
        "US 8 60W": (1, "experimental"),
        "USW Flex Mini": (2, "community_validated"),
        "US 48 PoE 500W": (2, "experimental"),
    }
    for model, (units, status) in expected_contributions.items():
        device = models[model]
        assert device.get("status") == status, model
        row = contribution(device, units=units)
        assert row.get("dashboard_validation") == "pending", model
        assert row.get("api_capabilities") == {
            "port_detail": True,
            "per_port_traffic": False,
        }, model
        row_contributor = row.get("contributor") or {}
        assert str(row_contributor.get("display_name") or "").casefold() == "community contributor", model
        assert row_contributor.get("public_credit") is False, model

    udm = models["UDM Pro Max"]
    assert udm.get("tested_firmware") == ["5.1.31"]
    udm_contributor = udm.get("contributor") or {}
    assert str(udm_contributor.get("display_name") or "").casefold() == "community contributor"
    assert udm_contributor.get("public_credit") is False
    udm_notes = notes_text(udm)
    assert "2.5G-capable RJ45" in udm_notes
    assert "must not synthesize per-port traffic" in udm_notes

    xg = models["USW Pro XG 24 PoE"]
    assert xg.get("tested_firmware") == ["7.5.10"]
    xg_contributor = xg.get("contributor") or {}
    assert str(xg_contributor.get("display_name") or "").casefold() == "community contributor"
    assert xg_contributor.get("public_credit") is False
    xg_notes = notes_text(xg)
    assert "ports 1-8 are 2.5G-capable RJ45" in xg_notes
    assert "ports 9-24 are 10G-capable RJ45" in xg_notes
    assert "ports 25-26 are 25G SFP28" in xg_notes
    assert "802.3bt Type 4" in xg_notes
    assert "100M, 1G and 10G" in xg_notes
    assert "both 10G and 25G" in xg_notes

    aggregation = models["USW Pro Aggregation"]
    aggregation_notes = notes_text(aggregation)
    assert "Ports 29 and 30" in aggregation_notes
    assert "negotiating at 10G" in aggregation_notes
    assert "25G" in aggregation_notes

    print("Discovery registry authority metadata contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
