from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

with tempfile.TemporaryDirectory(prefix="sv-c3750-") as td:
    work = Path(td)
    walk = work / "c3750.txt"
    report = work / "report.txt"
    generated = work / "generated.yaml"
    card = work / "card.yaml"
    targets = work / "targets.csv"
    last_run = work / "last-run.txt"
    caps = work / "capabilities"
    options = work / "options.json"

    lines = [
        '.1.3.6.1.2.1.1.1.0 = STRING: "Cisco IOS Software, WS-C3750-48P"',
        '.1.3.6.1.2.1.1.5.0 = STRING: "c3750-test"',
    ]
    idx = 1
    for port in range(1, 49):
        lines.append(f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: "Fa1/0/{port}"')
        lines.append(f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: up(1)')
        lines.append(f'.1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 100')
        idx += 1
    for port in range(1, 5):
        lines.append(f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: "Gi1/0/{port}"')
        lines.append(f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: up(1)')
        lines.append(f'.1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 1000')
        idx += 1
    walk.write_text("\n".join(lines) + "\n", encoding="utf-8")
    targets.write_text(
        f"switch name,switch host,sensor prefix,switch snmp community,output_dir,display name\n{walk.name},192.0.2.10,C3750,public,{work},C3750\n",
        encoding="utf-8",
    )
    options.write_text(
        json.dumps({
            "input_path": str(walk),
            "snmpwalks_dir": str(work),
            "report_path": str(report),
            "parse_all_walks": True,
            "generate_snmp2mqtt": True,
            "targets_csv": str(targets),
            "generated_yaml_path": str(generated),
            "generated_card_path": str(card),
            "last_run_summary_path": str(last_run),
            "run_snmp_walks": False,
            "enable_switch_list": False,
            "live_output_dir": str(work / "live"),
            "live_output_path": str(work / "live" / "live-targeted-snmpwalk.txt"),
            "live_log_path": str(work / "live-snmpwalk.log"),
            "live_output_dir": str(work / "live"),
            "live_output_path": str(work / "live" / "live-targeted-snmpwalk.txt"),
            "live_log_path": str(work / "live-snmpwalk.log"),
            "live_output_dir": str(work / "live"),
            "live_output_path": str(work / "live" / "live-targeted-snmpwalk.txt"),
            "live_log_path": str(work / "live-snmpwalk.log"),
        }),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update({
        "SWITCH_VISION_OPTIONS_FILE": str(options),
        "CV_VENDOR_DIR": str(ROOT / "runtime_src/opt/switch-vision/vendors"),
        "CV_MIB_DATABASE_DIR": str(ROOT / "runtime_src/opt/switch-vision/mib_database"),
        "SWITCH_VISION_CAPABILITIES_DIR": str(caps),
        "SWITCH_VISION_SHARE_DIR": str(work / "share"),
        "SWITCH_VISION_SHARE_DIR": str(work / "share"),
        "SWITCH_VISION_SHARE_DIR": str(work / "share"),
    })
    result = subprocess.run(
        ["sh", str(ROOT / "runtime_src/discovery_job.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout

    report_text = report.read_text(encoding="utf-8")
    assert "Model/platform: WS-C3750-48P" in report_text, report_text
    assert "- Physical switch interfaces detected: 52" in report_text, report_text
    assert "- RJ45 FastEthernet <member>/0/1-48 ports: 48" in report_text, report_text
    assert "- 1G SFP GigabitEthernet <member>/0/1-4 uplinks: 4" in report_text, report_text
    assert "- Matched profile: cisco-3750-48p-48fe-4sfp" in report_text, report_text

    cap_files = list(caps.glob("*-capabilities.json"))
    assert cap_files, "normalized capabilities JSON was not generated"
    cap = json.loads(cap_files[0].read_text(encoding="utf-8"))
    summary = cap["summary"]
    assert summary["physical_count"] == 52, summary
    assert summary["rj45_count"] == 48, summary
    assert summary["sfp_count"] == 4, summary
    assert summary["sfp_plus_count"] == 0, summary
    assert summary["uplink_count"] == 4, summary

    yaml_text = generated.read_text(encoding="utf-8")
    assert "C3750 Port 48 Status" in yaml_text, yaml_text
    assert "C3750 SFP 1G 4 Status" in yaml_text, yaml_text
    assert "C3750 Port 49 Status" not in yaml_text, yaml_text
    assert "C3750 SFP 10G" not in yaml_text, yaml_text
    assert "[value | int, 100] | min" in yaml_text, "FastEthernet speed cap missing"
    assert "[value | int, 1000] | min" in yaml_text, "1G SFP speed cap missing"

print("Switch Vision Discovery Catalyst 3750 live mapping: PASS")
