#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
PREPARE = RUNTIME / "physical_contract_prepare.sh"
REGISTRY = RUNTIME / "opt/switch-vision/devices/supported_devices.json"
LOOKUP = RUNTIME / "registry_lookup.py"
PROFILE = RUNTIME / "profiles/switch-vision-profiles.yaml"
STANDARD_SENSOR_SCAN = RUNTIME / "standard_sensor_scan.py"


def run(args, *, env=None):
    proc = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
        timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"command failed rc={proc.returncode}: {' '.join(str(x) for x in args)}\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    return proc


with tempfile.TemporaryDirectory(prefix="sv-avaya-3524-") as td:
    work = Path(td)
    walk = work / "3524gt-pwrplus.walk"
    normalized = work / "normalized.walk"
    capabilities = work / "capabilities.json"
    contract = work / "contract.json"

    lines = [
        ".1.3.6.1.2.1.1.1.0 = STRING: Ethernet Routing Switch 3524GT-PWR+   HW:17       FW:1.0.0.15  SW:v5.1.0.007 BN:07 (c) Avaya Networks",
        ".1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.45.3.80.4",
    ]
    for idx in range(1, 25):
        lines.append(f".1.3.6.1.2.1.2.2.1.2.{idx} = STRING: Slot 1 / Port {idx}")
        lines.append(f".1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: {idx}")
    lines.extend(
        [
            ".1.3.6.1.2.1.2.2.1.2.25 = STRING: VLAN 1",
            ".1.3.6.1.2.1.31.1.1.1.1.25 = STRING: Vlan 1",
            ".1.3.6.1.2.1.105.1.3.1.1.2.1 = Gauge32: 370",
            ".1.3.6.1.2.1.105.1.3.1.1.4.1 = Gauge32: 7",
        ]
    )
    for port in range(1, 25):
        lines.append(f".1.3.6.1.2.1.105.1.1.1.6.1.{port} = INTEGER: off(2)")
    walk.write_text("\n".join(lines) + "\n", encoding="utf-8")

    env = os.environ.copy()
    env["SWITCH_VISION_DISCOVERY_VERSION"] = "3.0.4"
    run([str(PREPARE), str(walk), str(normalized), str(capabilities), str(contract)], env=env)

    cap = json.loads(capabilities.read_text(encoding="utf-8"))
    con = json.loads(contract.read_text(encoding="utf-8"))

    assert cap["device"]["vendor"] == "avaya"
    assert cap["device"]["vendor_name"] == "Avaya"
    assert cap["device"]["model_text"] == "3524GT-PWR+"
    assert cap["device"]["sys_object_id"] == "1.3.6.1.4.1.45.3.80.4"
    assert cap["device"]["support_status"] == "experimental"
    assert cap["summary"]["physical_count"] == 24
    assert cap["summary"]["rj45_count"] == 20
    assert cap["summary"]["uplink_count"] == 4

    assert con["status"] == "resolved", con
    assert con["errors"] == []
    assert con["device"]["registry_match"] is True
    assert con["device"]["exact_registry_match"] is True
    assert con["device"]["mapping_profile"] == "avaya-ers3524gt-pwrplus-20p-4dual"
    assert con["expected"] == {
        "members": 1,
        "rj45_per_member": 20,
        "uplinks_per_member": 4,
        "rj45": 20,
        "uplinks": 4,
        "physical": 24,
    }
    assert con["observed"]["rj45"] == 20
    assert con["observed"]["uplinks"] == 4
    assert [p["source"]["if_index"] for p in con["ports"] if p["media"] == "uplink"] == [21, 22, 23, 24]

    run(
        [
            "python3",
            str(LOOKUP),
            "--registry",
            str(REGISTRY),
            "--model",
            "3524GT-PWR+",
            "--enrich",
            str(capabilities),
            "--enrich-key",
            "registry",
        ]
    )
    enriched = json.loads(capabilities.read_text(encoding="utf-8"))
    ports = enriched["registry"]["ports"]
    assert ports["rj45"] == 20
    assert ports["combo_ports"] == 4
    assert ports["uplinks"] == 4
    assert ports["combo_logical_ports"] == [21, 22, 23, 24]

    # These are the exact values consumed by Discovery card generation.
    assert ports["rj45"] + ports["combo_ports"] == 24
    assert ports["uplinks"] == 4
    assert enriched["registry"]["calibration_profile"] == "stock_24rj45_4sfp"
    assert enriched["registry"]["default_faceplate"] == "faceplates/24rj45-4sfp.png"

    sensor_output = work / "standard-sensors.json"
    run([
        "python3",
        str(STANDARD_SENSOR_SCAN),
        "--walk",
        str(walk),
        "--output",
        str(sensor_output),
    ])
    standard = json.loads(sensor_output.read_text(encoding="utf-8"))
    poe = [item for item in standard["candidates"] if item["category"] == "poe"]
    assert standard["counts_by_category"]["poe"] == 2
    assert any(item["sensor_type"] == "watts" and item["raw_value"] == "370" for item in poe)

profiles = PROFILE.read_text(encoding="utf-8")
assert "avaya-ers3524gt-pwrplus-20p-4dual:" in profiles
assert "1.3.6.1.4.1.45.3.80.4" in profiles
assert "combo_logical_ports:" in profiles

print("Avaya ERS 3524GT-PWR+ exact-model physical/card contract: PASS")
