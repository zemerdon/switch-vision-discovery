#!/usr/bin/env python3
"""Regression for walk-backed GS1915-24EP registered support.

A real-hardware walk is sufficient evidence to add the exact model. Visual
alignment remains a separate Experimental validation dimension. The captured
GS1915 physical contract is swp00..swp23 as 24 copper interfaces, zero optical
uplinks, with standard POWER-ETHERNET-MIB evidence present.
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
        '.1.3.6.1.2.1.105.1.3.1.1.2.1 = Gauge32: 1300',
        '.1.3.6.1.2.1.105.1.3.1.1.4.1 = Gauge32: 0',
    ]
    for idx in range(1, 25):
        name = f"swp{idx - 1:02d}"
        rows.extend(
            [
                f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: "{name}"',
                f'.1.3.6.1.2.1.2.2.1.2.{idx} = STRING: "{name}"',
                f'.1.3.6.1.2.1.2.2.1.7.{idx} = INTEGER: up(1)',
                f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: up(1)',
                f'.1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 1000',
            ]
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    config_text = (ROOT / "switch_vision_discovery" / "config.yaml").read_text(encoding="utf-8")
    assert "|GS1915-24EP|" in config_text, "GS1915 must remain selectable in the Supervisor manual-model enum"

    device = next(row for row in registry["devices"] if row.get("model") == "GS1915-24EP")
    assert device["status"] == "experimental"
    assert device["ports"]["rj45"] == 24
    assert device["ports"]["uplinks"] == 0
    assert device["ports"]["poe"] is True
    assert device["mapping_profile"] == "zyxel-gs1915-24ep"
    assert device["dashboard_support"] is True

    entry = load_entrypoint()
    old_env = {key: os.environ.get(key) for key in (
        "SWITCH_VISION_RUNTIME_DIR", "SWITCH_VISION_DEVICE_REGISTRY", "SWITCH_VISION_DISCOVERY_VERSION"
    )}
    try:
        os.environ["SWITCH_VISION_RUNTIME_DIR"] = str(RUNTIME)
        os.environ["SWITCH_VISION_DEVICE_REGISTRY"] = str(REGISTRY)
        os.environ["SWITCH_VISION_DISCOVERY_VERSION"] = "2.4.2"
        with tempfile.TemporaryDirectory(prefix="sv-gs1915-registered-") as tmp_name:
            tmp = Path(tmp_name)
            source_dir = tmp / "GS1915-fixture"
            source_dir.mkdir()
            walk = source_dir / "live-targeted-snmpwalk.txt"
            make_walk(walk)
            options = {
                "switches": [{
                    "switch_name": "GS1915-fixture",
                    "switch_host": "192.0.2.191",
                    "sensor_prefix": "gs1915fixture",
                    "snmp_community": "fixture-readonly",
                    "enabled": "enabled",
                    "walk_mode": "targeted",
                    "switch_model": "auto",
                    "output_dir": str(source_dir),
                }],
                "stack_member_prefixes": [],
                "input_path": str(walk),
                "snmpwalks_dir": str(tmp / "walks"),
                "parse_all_walks": "false",
            }
            records = [{
                "walk": str(walk), "switch": "GS1915-fixture", "host": "192.0.2.191",
                "prefix": "gs1915fixture", "community": "fixture-readonly",
            }]
            work = tmp / "work"
            work.mkdir()
            staged, ordered, accepted = entry._stage_options(options, work, records)
            assert len(accepted) == 1, accepted
            assert len(ordered) == 1, ordered
            assert len(staged["switches"]) == 1, staged["switches"]
            assert list((work / "snmpwalks").rglob("*.txt")), "registered GS1915 walk was not staged"

            info = accepted[0]
            capability = json.loads(Path(info["capability"]).read_text(encoding="utf-8"))
            contract = json.loads(Path(info["contract_path"]).read_text(encoding="utf-8"))
            assert capability["device"]["vendor"] == "zyxel"
            assert capability["device"]["family"] == "GS1915"
            assert capability["device"]["model_text"] == "GS1915-24EP"
            assert capability["device"]["support_status"] == "experimental"
            assert capability["device"]["sys_object_id"] == "1.3.6.1.4.1.890.1.15.3.139.1"
            assert capability["summary"]["interface_count"] == 24
            assert capability["summary"]["physical_count"] == 24
            assert capability["summary"]["rj45_count"] == 24
            assert capability["summary"]["uplink_count"] == 0
            assert contract["status"] == "resolved"
            assert contract["device"]["registry_match"] is True
            assert contract["device"]["model"] == "GS1915-24EP"
            assert contract["expected"]["rj45"] == 24
            assert contract["expected"]["uplinks"] == 0
            assert contract["observed"]["rj45"] == 24
            assert contract["observed"]["uplinks"] == 0
            assert entry._expected_generated_snmp_cards(ordered) == 1

            published = tmp / "published-capabilities"
            entry._publish_contracts(accepted, published)
            cap_out = published / "GS1915-fixture-capabilities.json"
            contract_out = published / "GS1915-fixture-physical-contract.json"
            assert cap_out.is_file() and contract_out.is_file()
            assert json.loads(cap_out.read_text(encoding="utf-8"))["device"]["model_text"] == "GS1915-24EP"
            assert json.loads(contract_out.read_text(encoding="utf-8"))["status"] == "resolved"
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    print("Discovery GS1915-24EP walk-backed registered support regression: PASS")


if __name__ == "__main__":
    main()
