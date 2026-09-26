#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
LEGACY = RUNTIME / "discovery_job.sh"
REGISTRY = RUNTIME / "opt/switch-vision/devices/supported_devices.json"


def run(args, *, env):
    proc = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=90,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"command failed rc={proc.returncode}: {' '.join(str(x) for x in args)}\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    return proc


with tempfile.TemporaryDirectory(prefix="sv-dell-n2128-optics-") as td:
    work = Path(td)
    walks_root = work / "walks"
    switch_dir = walks_root / "N2128"
    switch_dir.mkdir(parents=True)
    walk = switch_dir / "live-full-snmpwalk.txt"

    lines = [
        '.1.3.6.1.2.1.1.1.0 = STRING: "Dell EMC Networking N2128PX-ON, 6.7.1.27, Linux 4.14.174, v1.0.9"',
        ".1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.674.10895.3077",
    ]
    for idx in range(1, 29):
        lines.extend([
            f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: Gi1/0/{idx}',
            f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: down(2)',
        ])
    for port, idx in ((1, 29), (2, 30)):
        lines.extend([
            f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: Te1/0/{port}',
            f'.1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 10000',
            f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: up(1)',
            f'.1.3.6.1.2.1.31.1.1.1.6.{idx} = Counter64: {1000 * idx}',
            f'.1.3.6.1.2.1.31.1.1.1.10.{idx} = Counter64: {2000 * idx}',
        ])

    base = "1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43"
    for row, temp, volt, current, tx, rx, vendor, part, media in [
        (29, 337, 3277, 258, -2827, -1999, "FINISAR", "FTLX8571D3BCL", "10GBase-LR"),
        (30, 411, 3356, 58, -2180, -12479, "JDSU", "PLRXPLSCS433H", "10GBase-SR"),
    ]:
        lines.extend([
            f".{base}.1.18.1.1.{row} = Gauge32: {row}",
            f".{base}.1.18.1.2.{row} = INTEGER: {temp}",
            f".{base}.1.18.1.3.{row} = INTEGER: {volt}",
            f".{base}.1.18.1.4.{row} = INTEGER: {current}",
            f".{base}.1.18.1.5.{row} = INTEGER: {tx}",
            f".{base}.1.18.1.6.{row} = INTEGER: {rx}",
            f'.{base}.1.18.1.9.{row} = STRING: "No Fault"',
            f".{base}.1.19.1.1.{row} = Gauge32: {row}",
            f'.{base}.1.19.1.2.{row} = STRING: "{vendor}"',
            f'.{base}.1.19.1.6.{row} = STRING: "{part}"',
            f'.{base}.1.19.1.9.{row} = STRING: "{media}"',
        ])
    walk.write_text("\n".join(lines) + "\n", encoding="utf-8")

    options = work / "options.json"
    targets = work / "targets.csv"
    targets.write_text(f"N2128,192.0.2.28,N2128,readonly,{switch_dir},N2128\n", encoding="utf-8")
    options.write_text(json.dumps({
        "input_path": str(walk),
        "snmpwalks_dir": str(walks_root),
        "report_path": str(work / "report.txt"),
        "run_snmp_walks": "false",
        "enable_switch_list": "false",
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

    env = os.environ.copy()
    env.update({
        "SWITCH_VISION_DISCOVERY_VERSION": "3.0.8",
        "SWITCH_VISION_OPTIONS_FILE": str(options),
        "SWITCH_VISION_CAPABILITIES_DIR": str(work),
        "SWITCH_VISION_DEVICE_REGISTRY": str(REGISTRY),
        "SWITCH_VISION_REGISTRY_LOOKUP": str(RUNTIME / "registry_lookup.py"),
        "SWITCH_VISION_RUNTIME_DIR": str(RUNTIME),
    })
    run([str(LEGACY)], env=env)

    generated = (work / "generated.yaml").read_text(encoding="utf-8")
    assert "# Detected model: N2128PX-ON" in generated
    assert "N2128 SFP 10G 1 Temperature" in generated
    assert "N2128 SFP 10G 2 Temperature" in generated
    assert "transform: value / 10" in generated
    assert "transform: value / 1000" in generated
    assert "N2128 SFP 10G 1 TX Optical Power" in generated
    assert "N2128 SFP 10G 1 RX Optical Power" in generated
    assert "N2128 SFP 10G 1 Optical Status" in generated
    assert "N2128 SFP 10G 1 Transceiver Vendor" in generated
    assert "N2128 SFP 10G 1 Transceiver Part" in generated
    assert "N2128 SFP 10G 1 Media Type" in generated
    assert "Optic Row" not in generated

source = LEGACY.read_text(encoding="utf-8")
assert "Dell N2128PX-ON optical supplemental walks" in source
assert "1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.18" in source
assert "1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.19" in source

print("Dell N2128PX-ON DDMI/transceiver binding contract: PASS")
