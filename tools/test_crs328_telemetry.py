from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sv-crs328-telemetry-") as td:
        work = Path(td)
        walk_root = work / "snmpwalks"
        walk_dir = walk_root / "CRS328"
        walk_dir.mkdir(parents=True)
        walk = walk_dir / "live-targeted-snmpwalk.txt"
        report = work / "report.txt"
        generated = work / "generated.yaml"
        card = work / "card.yaml"
        targets = work / "targets.csv"
        last_run = work / "last-run.txt"
        caps = work / "capabilities"
        options = work / "options.json"

        lines = [
            '.1.3.6.1.2.1.1.1.0 = STRING: "RouterOS CRS328-24P-4S+"',
            '.1.3.6.1.2.1.1.5.0 = STRING: "crs328-test"',
        ]
        for port in range(1, 25):
            lines.extend([
                f'.1.3.6.1.2.1.31.1.1.1.1.{port} = STRING: "ether{port}"',
                f'.1.3.6.1.2.1.2.2.1.8.{port} = INTEGER: 1',
                f'.1.3.6.1.2.1.31.1.1.1.15.{port} = Gauge32: 1000',
            ])
        for cage in range(1, 5):
            idx = 24 + cage
            lines.extend([
                f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: "sfp-sfpplus{cage}"',
                f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: 2',
                f'.1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 10000',
            ])

        # Neutral synthetic values model the public numeric MIKROTIK-MIB contract.
        # No private contribution payload is committed into this regression.
        lines.extend([
            '.1.3.6.1.2.1.25.3.3.1.2.1 = INTEGER: 7',
            '.1.3.6.1.4.1.14988.1.1.3.100.1.2.16 = STRING: "poe-out-consumption"',
            '.1.3.6.1.4.1.14988.1.1.3.100.1.3.16 = INTEGER: 153',
            '.1.3.6.1.4.1.14988.1.1.3.100.1.4.16 = INTEGER: 5',
            '.1.3.6.1.4.1.14988.1.1.3.100.1.2.17 = STRING: "cpu-temperature"',
            '.1.3.6.1.4.1.14988.1.1.3.100.1.3.17 = INTEGER: 52',
            '.1.3.6.1.4.1.14988.1.1.3.100.1.4.17 = INTEGER: 1',
            '.1.3.6.1.4.1.14988.1.1.3.100.1.2.7001 = STRING: "fan1-speed"',
            '.1.3.6.1.4.1.14988.1.1.3.100.1.3.7001 = INTEGER: 1350',
            '.1.3.6.1.4.1.14988.1.1.3.100.1.4.7001 = INTEGER: 2',
            '.1.3.6.1.4.1.14988.1.1.15.1.1.2.4 = STRING: "ether4"',
            '.1.3.6.1.4.1.14988.1.1.15.1.1.3.4 = INTEGER: 3',
            '.1.3.6.1.4.1.14988.1.1.15.1.1.4.4 = INTEGER: 522',
            '.1.3.6.1.4.1.14988.1.1.15.1.1.5.4 = INTEGER: 170',
            '.1.3.6.1.4.1.14988.1.1.15.1.1.6.4 = INTEGER: 43',
        ])
        walk.write_text("\n".join(lines) + "\n", encoding="utf-8")
        targets.write_text(
            f"switch name,switch host,sensor prefix,switch snmp community,output_dir,display name\n"
            f"{walk.name},192.0.2.44,CRS,public,{work},CRS328\n",
            encoding="utf-8",
        )
        options.write_text(
            json.dumps({
                "input_path": str(walk),
                "snmpwalks_dir": str(walk_root),
                "report_path": str(report),
                "parse_all_walks": True,
                "generate_snmp2mqtt": True,
                "targets_csv": str(targets),
                "generated_yaml_path": str(generated),
                "generated_card_path": str(card),
                "last_run_summary_path": str(last_run),
                "run_snmp_walks": False,
                "enable_switch_list": True,
                "switches": [{
                    "switch_name": "CRS328",
                    "display_name": "CRS328 Test",
                    "switch_host": "192.0.2.44",
                    "sensor_prefix": "CRS",
                    "snmp_community": "public",
                    "enabled": "enabled",
                    "walk_mode": "targeted",
                    "switch_model": "auto",
                    "card_header_title": "",
                }],
                "stack_member_prefixes": [],
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
        assert "Model/platform: CRS328-24P-4S+" in report_text, report_text
        assert "- Physical switch interfaces detected: 28" in report_text, report_text
        assert "- RJ45 ether1-ether24 ports: 24" in report_text, report_text
        assert "- 10G SFP+ sfp-sfpplus1-sfp-sfpplus4 uplinks: 4" in report_text, report_text

        yaml_text = generated.read_text(encoding="utf-8")
        required = [
            "name: CRS CPU",
            'unit_of_measurement: "%"',
            "name: CRS Temperature",
            'unit_of_measurement: "°C"',
            "name: CRS PoE Used",
            "name: CRS Fan 1 RPM",
            "name: CRS Port 4 PoE Power",
            "name: CRS Port 4 PoE Voltage",
            "name: CRS Port 4 PoE Current",
            "name: CRS Port 4 PoE Status Code",
            "transform: value / 10",
        ]
        for marker in required:
            assert marker in yaml_text, marker
        assert "name: CRS Port 5 PoE Power" not in yaml_text, "absent PoE rows must not be invented"
        assert "CRS PoE Budget" not in yaml_text, "PoE budget must not be invented"

        card_text = card.read_text(encoding="utf-8")
        assert "cpu_entity: sensor.crs_cpu" in card_text, card_text
        assert "temperature_entity: sensor.crs_temperature" in card_text, card_text
        assert "poe_used_entity: sensor.crs_poe_used" in card_text, card_text
        assert "fans_entity: sensor.crs_fan_1_rpm" in card_text, card_text

    print("Switch Vision Discovery CRS328 telemetry regression: PASS")


if __name__ == "__main__":
    main()
