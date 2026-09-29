#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
PREPARE = RUNTIME / "physical_contract_prepare.sh"
REGISTRY = RUNTIME / "opt/switch-vision/devices/supported_devices.json"
REGISTRY_LOOKUP = RUNTIME / "registry_lookup.py"
PROFILE = RUNTIME / "profiles/switch-vision-profiles.yaml"
LEGACY = RUNTIME / "discovery_job.sh"
REPORT_STAGE = RUNTIME / "discovery_report_stage.sh"
YAML_STAGE = RUNTIME / "discovery_yaml_stage.sh"


def run(args, *, env=None):
    proc = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
        timeout=120,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"command failed rc={proc.returncode}: {' '.join(str(x) for x in args)}\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    return proc


registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
models = {row["model"]: row for row in registry["devices"]}
device = models["HP J9774A 2530-8G-PoEP"]
ports = device["ports"]
assert device["status"] == "experimental"
assert device["mapping_profile"] == "hp-2530-8g-poep-8p-2dual"
assert device["dashboard_support"] is True
assert device["calibration_profile"] == "stock_24rj45_2sfp"
assert device["default_faceplate"] == "faceplates/24rj45-2sfp.png"
assert ports["rj45"] == 8
assert ports["combo_ports"] == 2
assert ports["combo_logical_ports"] == [9, 10]
assert ports["uplinks"] == 2
assert ports["gigabit_sfp"] == 2
assert ports["rj45"] + ports["combo_ports"] == 10

with tempfile.TemporaryDirectory(prefix="sv-hp-j9774a-") as td:
    work = Path(td)
    walk = work / "j9774a.walk"
    normalized = work / "normalized.walk"
    capabilities = work / "capabilities.json"
    contract = work / "contract.json"

    lines = [
        '.1.3.6.1.2.1.1.1.0 = STRING: "HP J9774A 2530-8G-PoEP Switch, revision YA.16.11.0031, ROM YA.15.20"',
        ".1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.11.2.3.7.11.138",
        '.1.3.6.1.2.1.47.1.1.1.1.13.1 = STRING: "J9774A"',
        '.1.3.6.1.2.1.47.1.1.1.1.2.1 = STRING: "HP J9774A 2530-8G-PoEP Switch"',
    ]
    for idx in range(1, 11):
        lines.extend(
            [
                f'.1.3.6.1.2.1.2.2.1.2.{idx} = STRING: Port {idx}',
                f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: {idx}',
                f'.1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 1000',
                f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: {"up(1)" if idx in (1, 2, 9, 10) else "down(2)"}',
                f'.1.3.6.1.2.1.31.1.1.1.6.{idx} = Counter64: {idx * 100}',
                f'.1.3.6.1.2.1.31.1.1.1.10.{idx} = Counter64: {idx * 200}',
            ]
        )
    lines.extend(
        [
            '.1.3.6.1.2.1.2.2.1.2.100 = STRING: CPU',
            '.1.3.6.1.2.1.31.1.1.1.1.100 = STRING: CPU',
            '.1.3.6.1.2.1.2.2.1.2.101 = STRING: DEFAULT_VLAN',
            '.1.3.6.1.2.1.31.1.1.1.1.101 = STRING: DEFAULT_VLAN',
            '.1.3.6.1.2.1.105.1.3.1.1.2.1 = Gauge32: 67',
        ]
    )
    for port in range(1, 9):
        lines.append(f".1.3.6.1.2.1.105.1.1.1.6.1.{port} = INTEGER: off(2)")
    walk.write_text("\n".join(lines) + "\n", encoding="utf-8")

    config = (ROOT / "switch_vision_discovery/config.yaml").read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"([^"]+)"', config, re.MULTILINE)
    assert match is not None
    env = os.environ.copy()
    env["SWITCH_VISION_DISCOVERY_VERSION"] = match.group(1)

    run([str(PREPARE), str(walk), str(normalized), str(capabilities), str(contract)], env=env)
    cap = json.loads(capabilities.read_text(encoding="utf-8"))
    con = json.loads(contract.read_text(encoding="utf-8"))

    assert cap["device"]["vendor"] == "hp_aruba", cap["device"]
    assert cap["device"]["model_text"] == "HP J9774A 2530-8G-PoEP", cap["device"]
    assert cap["device"]["sys_object_id"] == "1.3.6.1.4.1.11.2.3.7.11.138"
    assert cap["device"]["support_status"] == "experimental"
    assert cap["summary"]["physical_count"] == 10, cap["summary"]
    assert cap["summary"]["rj45_count"] == 8, cap["summary"]
    assert cap["summary"]["uplink_count"] == 2, cap["summary"]
    assert all(not row["physical"] for row in cap["interfaces"] if row["name"] in {"CPU", "DEFAULT_VLAN"})

    assert con["status"] == "resolved", con
    assert con["errors"] == []
    assert con["device"]["exact_registry_match"] is True
    assert con["device"]["mapping_profile"] == "hp-2530-8g-poep-8p-2dual"
    assert con["expected"]["physical"] == 10
    assert con["observed"]["physical"] == 10
    assert con["observed"]["rj45"] == 8
    assert con["observed"]["uplinks"] == 2
    assert [p["source"]["if_name"] for p in con["ports"] if p["media"] == "uplink"] == ["9", "10"]

    normalized_text = normalized.read_text(encoding="utf-8")
    assert 'STRING: "1"' in normalized_text
    assert 'STRING: "10"' in normalized_text
    assert "CPU" in normalized_text and "DEFAULT_VLAN" in normalized_text

    selected = work / "HP2530-capabilities.json"
    selected.write_text(capabilities.read_text(encoding="utf-8"), encoding="utf-8")
    run(
        [
            "python3",
            str(REGISTRY_LOOKUP),
            "--registry",
            str(REGISTRY),
            "--model",
            "HP J9774A 2530-8G-PoEP",
            "--enrich",
            str(selected),
        ],
        env=env,
    )
    enriched = json.loads(selected.read_text(encoding="utf-8"))
    reg_ports = enriched["registry"]["ports"]
    assert reg_ports["rj45"] + reg_ports["combo_ports"] == 10
    assert reg_ports["combo_logical_ports"] == [9, 10]

    walks_root = work / "walks"
    staged = walks_root / "HP2530"
    staged.mkdir(parents=True)
    staged_walk = staged / "live-full-snmpwalk.txt"
    staged_walk.write_text(normalized_text, encoding="utf-8")
    targets = work / "targets.csv"
    targets.write_text(f"HP2530,192.0.2.74,HP2530,readonly,{staged},HP2530\n", encoding="utf-8")
    options = work / "options.json"
    options.write_text(
        json.dumps(
            {
                "input_path": str(staged_walk),
                "snmpwalks_dir": str(walks_root),
                "report_path": str(work / "report.txt"),
                "run_snmp_walks": "false",
                "enable_switch_list": "true",
                "switches": [
                    {
                        "switch_name": "HP2530",
                        "display_name": "HP 2530",
                        "switch_host": "192.0.2.74",
                        "sensor_prefix": "HP2530",
                        "enabled": True,
                    }
                ],
                "parse_all_walks": "true",
                "generate_snmp2mqtt": "true",
                "targets_csv": str(targets),
                "last_run_summary_path": str(work / "summary.txt"),
                "generated_yaml_path": str(work / "generated.yaml"),
                "generated_card_path": str(work / "card.yaml"),
                "snmp_log_path": str(work / "discovery.log"),
                "live_output_dir": str(work / "live"),
                "live_output_path": str(work / "live/live-targeted-snmpwalk.txt"),
                "generate_support_my_switch_bundle": "false",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    legacy_env = env.copy()
    legacy_env.update(
        {
            "SWITCH_VISION_OPTIONS_FILE": str(options),
            "SWITCH_VISION_CAPABILITIES_DIR": str(work),
            "SWITCH_VISION_DEVICE_REGISTRY": str(REGISTRY),
            "SWITCH_VISION_REGISTRY_LOOKUP": str(REGISTRY_LOOKUP),
            "SWITCH_VISION_RUNTIME_DIR": str(RUNTIME),
        }
    )
    run([str(LEGACY)], env=legacy_env)
    generated = (work / "generated.yaml").read_text(encoding="utf-8")
    card = (work / "card.yaml").read_text(encoding="utf-8")
    assert "# Detected model: HP J9774A 2530-8G-PoEP" in generated
    assert generated.count("1.3.6.1.2.1.2.2.1.8.") == 10
    assert "HP2530 Port 1 Status" in generated
    assert "HP2530 Port 10 Status" in generated
    assert 'switch_model: "HP J9774A 2530-8G-PoEP"' in card
    assert "        port_count: 10" in card
    assert "        sfp_port_count: 2" in card
    assert "sfp_logical_port_map:[9,10]" in card.replace(" ", ""), card
    assert 'calibration_profile: "stock_24rj45_2sfp"' in card

profiles = PROFILE.read_text(encoding="utf-8")
assert "hp-2530-8g-poep-8p-2dual:" in profiles
legacy = LEGACY.read_text(encoding="utf-8")
report_stage = REPORT_STAGE.read_text(encoding="utf-8")
yaml_stage = YAML_STAGE.read_text(encoding="utf-8")
assert report_stage.count('hp_2530_model = "HP J9774A 2530-8G-PoEP"') == 1
assert (legacy + yaml_stage).count('hp_2530_model="HP J9774A 2530-8G-PoEP"') == 1
assert 'model == "HP J9774A 2530-8G-PoEP" && name ~ /^([1-9]|10)$/' in yaml_stage

print("HP J9774A 2530-8G-PoEP exact-model physical/card contract: PASS")
