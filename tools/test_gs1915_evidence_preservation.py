#!/usr/bin/env python3
"""Regression for contributed GS1915-24EP current-run evidence preservation.

The contribution proves exact local identity and at least swp1..swp24 IF-MIB
interfaces. It does not prove a complete front-panel media/PoE/uplink contract,
so this test deliberately requires evidence preservation without topology/card
invention.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
REGISTRY = RUNTIME / "opt/switch-vision/devices/supported_devices.json"
ENTRYPOINT = RUNTIME / "discovery_contract_entrypoint.py"
PREPARE = RUNTIME / "physical_contract_prepare.sh"


def load_entrypoint():
    spec = importlib.util.spec_from_file_location("gs1915_entrypoint", ENTRYPOINT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.PREPARE = PREPARE
    module.REGISTRY = REGISTRY
    return module


def make_walk(path: Path) -> None:
    rows = [
        '.1.3.6.1.2.1.1.1.0 = STRING: "Zyxel GS1915-24EP Managed Switch"',
        '.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.890.1.15.3.139.1',
        '.1.3.6.1.2.1.1.5.0 = STRING: "privacy-safe-fixture"',
    ]
    for idx in range(1, 25):
        rows.extend(
            [
                f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: "swp{idx}"',
                f'.1.3.6.1.2.1.2.2.1.2.{idx} = STRING: "swp{idx}"',
                f'.1.3.6.1.2.1.2.2.1.7.{idx} = INTEGER: up(1)',
                f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: up(1)',
            ]
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert not any(
        isinstance(row, dict) and row.get("model") == "GS1915-24EP"
        for row in registry.get("devices", [])
    ), "Regression fixture must remain unregistered until physical truth is proven"

    entry = load_entrypoint()
    old_env = {
        key: os.environ.get(key)
        for key in (
            "SWITCH_VISION_RUNTIME_DIR",
            "SWITCH_VISION_DEVICE_REGISTRY",
            "SWITCH_VISION_DISCOVERY_VERSION",
        )
    }
    try:
        os.environ["SWITCH_VISION_RUNTIME_DIR"] = str(RUNTIME)
        os.environ["SWITCH_VISION_DEVICE_REGISTRY"] = str(REGISTRY)
        os.environ["SWITCH_VISION_DISCOVERY_VERSION"] = "2.4.1"

        with tempfile.TemporaryDirectory(prefix="sv-gs1915-preservation-") as tmp_name:
            tmp = Path(tmp_name)
            source_dir = tmp / "GS1915-carry"
            source_dir.mkdir()
            walk = source_dir / "live-targeted-snmpwalk.txt"
            make_walk(walk)

            options = {
                "switches": [
                    {
                        "switch_name": "GS1915-carry",
                        "switch_host": "192.0.2.191",
                        "sensor_prefix": "gs1915fixture",
                        "snmp_community": "fixture-readonly",
                        "enabled": "enabled",
                        "walk_mode": "targeted",
                        "switch_model": "auto",
                        "output_dir": str(source_dir),
                    }
                ],
                "stack_member_prefixes": [],
                "input_path": str(walk),
                "snmpwalks_dir": str(tmp / "walks"),
                "parse_all_walks": "false",
            }
            records = [
                {
                    "walk": str(walk),
                    "switch": "GS1915-carry",
                    "host": "192.0.2.191",
                    "prefix": "gs1915fixture",
                    "community": "fixture-readonly",
                }
            ]
            work = tmp / "work"
            work.mkdir()
            staged, ordered, accepted = entry._stage_options(options, work, records)

            assert len(accepted) == 1, accepted
            assert ordered == [], ordered
            assert staged["switches"] == [], staged["switches"]
            assert not list((work / "snmpwalks").rglob("*.txt")), (
                "Unregistered GS1915 walk entered generated-topology tree"
            )

            info = accepted[0]
            capability = json.loads(Path(info["capability"]).read_text(encoding="utf-8"))
            contract = json.loads(Path(info["contract_path"]).read_text(encoding="utf-8"))

            assert capability["device"]["vendor"] == "zyxel"
            assert capability["device"]["family"] == "GS1915"
            assert capability["device"]["model_text"] == "GS1915-24EP"
            assert capability["device"]["support_status"] == "detected"
            assert capability["device"]["sys_object_id"] == "1.3.6.1.4.1.890.1.15.3.139.1"
            assert capability["summary"]["interface_count"] >= 24
            # Do not promote swp naming into physical media truth without evidence.
            assert capability["summary"]["physical_count"] == 0
            assert contract["status"] == "unregistered"
            assert contract["device"]["registry_match"] is False
            assert contract["device"]["model"] == "GS1915-24EP"
            assert entry._expected_generated_snmp_cards(ordered) == 0

            published = tmp / "published-capabilities"
            entry._publish_contracts(accepted, published)
            cap_out = published / "GS1915-carry-capabilities.json"
            contract_out = published / "GS1915-carry-physical-contract.json"
            assert cap_out.is_file()
            assert contract_out.is_file()
            assert json.loads(cap_out.read_text(encoding="utf-8"))["device"]["model_text"] == "GS1915-24EP"
            assert json.loads(contract_out.read_text(encoding="utf-8"))["status"] == "unregistered"
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    print("Discovery GS1915-24EP accepted-evidence preservation regression: PASS")


if __name__ == "__main__":
    main()
