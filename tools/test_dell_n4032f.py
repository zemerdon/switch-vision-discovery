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
REGISTRY_LOOKUP = RUNTIME / "registry_lookup.py"
PROFILE = RUNTIME / "profiles/switch-vision-profiles.yaml"
LEGACY = RUNTIME / "discovery_job.sh"


def run(args, *, env=None):
    proc = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
        timeout=90,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"command failed rc={proc.returncode}: {' '.join(str(x) for x in args)}\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    return proc


with tempfile.TemporaryDirectory(prefix="sv-dell-n4032f-") as td:
    work = Path(td)
    walk = work / "n4032f.walk"
    normalized = work / "normalized.walk"
    capabilities = work / "capabilities.json"
    contract = work / "contract.json"

    lines = [
        '.1.3.6.1.2.1.1.1.0 = STRING: "Dell Networking N4032F, 6.5.4.23, Linux 3.7.10-77c011e4"',
        ".1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.674.10895.3044",
        '.1.3.6.1.2.1.47.1.1.1.1.2.28 = STRING: "Dell 2 Port QSFP Expansion Card"',
    ]
    for idx in range(1, 25):
        lines.extend([
            f'.1.3.6.1.2.1.2.2.1.2.{idx} = STRING: Unit: 1 Slot: 0 Port: {idx} 10G - Level',
            f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: Te1/0/{idx}',
            f'.1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 10000',
            f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: down(2)',
            f'.1.3.6.1.2.1.31.1.1.1.6.{idx} = Counter64: {idx * 100}',
            f'.1.3.6.1.2.1.31.1.1.1.10.{idx} = Counter64: {idx * 200}',
        ])
    for offset, idx in enumerate((59, 60), start=1):
        lines.extend([
            f'.1.3.6.1.2.1.2.2.1.2.{idx} = STRING: Unit: 1 Slot: 1 Port: {offset} 40G - Level',
            f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: Fo1/1/{offset}',
            f'.1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 40000',
            f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: down(2)',
            f'.1.3.6.1.2.1.31.1.1.1.6.{idx} = Counter64: 0',
            f'.1.3.6.1.2.1.31.1.1.1.10.{idx} = Counter64: 0',
        ])
    for lane, idx in enumerate(range(61, 69), start=1):
        lines.extend([
            f'.1.3.6.1.2.1.2.2.1.2.{idx} = STRING: Unit: 1 Slot: 1 Port: {lane} 10G - Level',
            f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: Te1/1/{lane}',
            f'.1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 10000',
            f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: notPresent(6)',
        ])

    walk.write_text("\n".join(lines) + "\n", encoding="utf-8")

    env = os.environ.copy()
    env["SWITCH_VISION_DISCOVERY_VERSION"] = "3.0.8"
    run([str(PREPARE), str(walk), str(normalized), str(capabilities), str(contract)], env=env)

    cap = json.loads(capabilities.read_text(encoding="utf-8"))
    con = json.loads(contract.read_text(encoding="utf-8"))
    assert cap["device"]["model_text"] == "N4032F"
    assert cap["device"]["sys_object_id"] == "1.3.6.1.4.1.674.10895.3044"
    assert cap["summary"]["physical_count"] == 26, cap["summary"]
    assert cap["summary"]["rj45_count"] == 0
    assert cap["summary"]["sfp_plus_count"] == 24
    assert cap["summary"]["uplink_count"] == 26
    lane_rows = [x for x in cap["interfaces"] if x["name"].startswith("Te1/1/")]
    assert len(lane_rows) == 8
    assert all(not x["physical"] for x in lane_rows)

    assert con["status"] == "resolved", con
    assert con["errors"] == []
    assert con["expected"]["physical"] == 24
    assert con["observed"]["physical"] == 26
    assert con["observed_base"]["physical"] == 24
    assert con["optional_observed"]["count"] == 2
    assert con["device"]["dashboard_support"] is True
    assert con["device"]["frontend_hold"] is False
    assert len(con["ports"]) == 26
    assert [p["source"]["if_name"] for p in con["optional_observed"]["ports"]] == ["Fo1/1/1", "Fo1/1/2"]

    normalized_text = normalized.read_text(encoding="utf-8")
    assert 'STRING: "Te1/0/1"' in normalized_text
    assert 'STRING: "Te1/0/24"' in normalized_text
    assert 'STRING: "Fo1/1/1"' in normalized_text
    assert "SwitchVisionNonPhysical" in normalized_text
    (work / "N4032-capabilities.json").write_text(
        capabilities.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    walks_root = work / "walks"
    staged_dir = walks_root / "N4032"
    staged_dir.mkdir(parents=True)
    staged_walk = staged_dir / "live-full-snmpwalk.txt"
    staged_walk.write_text(normalized_text, encoding="utf-8")
    options = work / "options.json"
    targets = work / "targets.csv"
    targets.write_text(f"N4032,192.0.2.40,N4032,readonly,{staged_dir},N4032\n", encoding="utf-8")
    options.write_text(json.dumps({
        "input_path": str(staged_walk),
        "snmpwalks_dir": str(walks_root),
        "report_path": str(work / "report.txt"),
        "run_snmp_walks": "false",
        "enable_switch_list": "true",
        "switches": [{
            "switch_name": "N4032",
            "display_name": "SGC-10gig",
            "switch_host": "192.0.2.40",
            "sensor_prefix": "N4032",
            "enabled": True,
        }],
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
    }, indent=2) + "\n", encoding="utf-8")
    cap_for_card = work / "N4032-capabilities.json"
    run([
        "python3",
        str(REGISTRY_LOOKUP),
        "--registry",
        str(REGISTRY),
        "--model",
        "N4032F",
        "--enrich",
        str(cap_for_card),
    ], env=env)

    legacy_env = env.copy()
    legacy_env.update({
        "SWITCH_VISION_OPTIONS_FILE": str(options),
        "SWITCH_VISION_CAPABILITIES_DIR": str(work),
        "SWITCH_VISION_DEVICE_REGISTRY": str(REGISTRY),
        "SWITCH_VISION_REGISTRY_LOOKUP": str(RUNTIME / "registry_lookup.py"),
        "SWITCH_VISION_RUNTIME_DIR": str(RUNTIME),
    })
    legacy_run = run([str(LEGACY)], env=legacy_env)
    generated_path = work / "generated.yaml"
    assert generated_path.is_file(), legacy_run.stdout + "\n" + legacy_run.stderr
    generated = generated_path.read_text(encoding="utf-8")
    assert "# Detected model: N4032F" in generated
    assert generated.count("1.3.6.1.2.1.2.2.1.8.") == 26
    assert "N4032 SFP 10G 1 Status" in generated
    assert "N4032 SFP 10G 24 Status" in generated
    assert "N4032 Rear QSFP 40G 1 Status" in generated
    assert "N4032 Rear QSFP 40G 2 Status" in generated
    assert "Optic Row" not in generated

    card = (work / "card.yaml").read_text(encoding="utf-8")
    assert "type: custom:switch-vision-3650" in card, card
    assert 'switch_model: "N4032F"' in card, card
    assert "        port_count: 0" in card, card
    assert "        sfp_port_count: 26" in card, card
    assert 'calibration_profile: "unifi_32sfp"' in card, card
    assert "discovered and telemetry-capable" not in card, card
    assert "intentionally not bound to a faceplate yet" not in card, card

    # The rear expansion is optional. A base N4032F without Fo1/1/1-2 must
    # use only the 24 front optical positions rather than inheriting phantom
    # rear sockets from the exact-model registry.
    base_only = "\n".join(
        line for line in normalized_text.splitlines()
        if "Fo1/1/" not in line and "FortyGigabitEthernet1/1/" not in line
        and "Te1/1/" not in line and "TenGigabitEthernet1/1/" not in line
    ) + "\n"
    staged_walk.write_text(base_only, encoding="utf-8")
    for output in (work / "generated.yaml", work / "card.yaml"):
        output.unlink(missing_ok=True)
    base_run = run([str(LEGACY)], env=legacy_env)
    base_card = (work / "card.yaml").read_text(encoding="utf-8")
    assert "type: custom:switch-vision-3650" in base_card, base_run.stdout + "\n" + base_run.stderr
    assert 'switch_model: "N4032F"' in base_card, base_card
    assert "        sfp_port_count: 24" in base_card, base_card
    assert "        sfp_port_count: 26" not in base_card, base_card
    base_yaml = (work / "generated.yaml").read_text(encoding="utf-8")
    assert "Rear QSFP 40G" not in base_yaml

registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
device = next(row for row in registry["devices"] if row.get("model") == "N4032F")
assert device["dashboard_support"] is True
assert device.get("frontend_hold") is not True
assert device["default_faceplate"] == "faceplates/unifi-32sfp.png"
assert device["calibration_profile"] == "unifi_32sfp"
assert device["ports"]["uplinks"] == 24
assert [item["interface_names"] for item in device["discovery_optional_interfaces"]] == [["Fo1/1/1", "Fo1/1/2"]]
assert device["discovery_optional_interfaces"][0]["telemetry_only"] is False
assert device["discovery_optional_interfaces"][0]["faceplate_positions"] == [25, 26]

profiles = PROFILE.read_text(encoding="utf-8")
assert "dell-n4032f-24sfp2qsfp:" in profiles
assert "qsfp_40g_ports: 2" not in profiles
assert "bind to faceplate optical positions 25-26 when observed" in profiles

print("Dell N4032F registered + 26-position faceplate binding contract: PASS")
