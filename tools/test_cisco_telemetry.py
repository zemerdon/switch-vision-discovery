from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    source = (ROOT / "runtime_src/discovery_job.sh").read_text(encoding="utf-8")
    for oid_root in (
        "1.3.6.1.2.1.105.1.1.1",
        "1.3.6.1.4.1.9.9.13.1.4.1",
        "1.3.6.1.4.1.9.9.13.1.5.1",
        "1.3.6.1.4.1.9.9.402.1.2.1",
    ):
        assert oid_root in source, oid_root

    with tempfile.TemporaryDirectory(prefix="sv-cisco-telemetry-") as td:
        work = Path(td)
        walk_root = work / "snmpwalks"
        walk_dir = walk_root / "CISCO"
        walk_dir.mkdir(parents=True)
        walk = walk_dir / "live-targeted-snmpwalk.txt"
        report = work / "report.txt"
        generated = work / "generated.yaml"
        card = work / "card.yaml"
        targets = work / "targets.csv"
        caps = work / "capabilities"
        options = work / "options.json"

        lines = [
            '.1.3.6.1.2.1.1.1.0 = STRING: "Cisco IOS Software, C2960XR Software"',
            '.1.3.6.1.2.1.47.1.1.1.1.13.1000 = STRING: "WS-C2960XR-48LPS-I"',
            '.1.3.6.1.2.1.47.1.1.1.1.11.1000 = STRING: "TESTSERIAL"',
            '.1.3.6.1.2.1.31.1.1.1.1.10101 = STRING: "GigabitEthernet1/0/1"',
            '.1.3.6.1.2.1.31.1.1.1.1.10102 = STRING: "GigabitEthernet1/0/2"',
            '.1.3.6.1.2.1.2.2.1.8.10101 = INTEGER: 1',
            '.1.3.6.1.2.1.2.2.1.8.10102 = INTEGER: 1',
            '.1.3.6.1.2.1.31.1.1.1.15.10101 = Gauge32: 1000',
            '.1.3.6.1.2.1.31.1.1.1.15.10102 = Gauge32: 1000',

            # ENTITY-MIB is the authoritative Cisco PoE physical-port join.
            '.1.3.6.1.2.1.47.1.1.1.1.7.5001 = STRING: "GigabitEthernet1/0/1"',
            '.1.3.6.1.2.1.47.1.1.1.1.2.5001 = STRING: "GigabitEthernet1/0/1"',
            '.1.3.6.1.2.1.47.1.1.1.1.7.5002 = STRING: "Power Supply 1"',

            # Standard POWER-ETHERNET-MIB state/class rows.
            '.1.3.6.1.2.1.105.1.1.1.3.1.1 = INTEGER: 1',
            '.1.3.6.1.2.1.105.1.1.1.6.1.1 = INTEGER: 3',
            '.1.3.6.1.2.1.105.1.1.1.10.1.1 = INTEGER: 4',
            '.1.3.6.1.2.1.105.1.1.1.6.1.2 = INTEGER: 3',
            '.1.3.6.1.2.1.105.1.1.1.10.1.2 = INTEGER: 4',

            # Cisco extension ties group.port 1.1 to ENTITY-MIB port 5001.
            '.1.3.6.1.4.1.9.9.402.1.2.1.9.1.1 = Gauge32: 6300',
            '.1.3.6.1.4.1.9.9.402.1.2.1.11.1.1 = INTEGER: 5001',

            # A second power row without a valid ENTITY-MIB port join must not leak.
            '.1.3.6.1.4.1.9.9.402.1.2.1.9.1.2 = Gauge32: 7100',
            '.1.3.6.1.4.1.9.9.402.1.2.1.11.1.2 = INTEGER: 0',

            # Cisco ENVMON state tables.
            '.1.3.6.1.4.1.9.9.13.1.4.1.2.1 = STRING: "Fan 1"',
            '.1.3.6.1.4.1.9.9.13.1.4.1.3.1 = INTEGER: 1',
            '.1.3.6.1.4.1.9.9.13.1.5.1.2.1 = STRING: "Power Supply 1"',
            '.1.3.6.1.4.1.9.9.13.1.5.1.3.1 = INTEGER: 1',

            # Existing aggregate telemetry remains intact.
            '.1.3.6.1.2.1.105.1.3.1.1.2.1 = Gauge32: 370',
            '.1.3.6.1.2.1.105.1.3.1.1.4.1 = Gauge32: 6',
        ]
        walk.write_text("\n".join(lines) + "\n", encoding="utf-8")
        targets.write_text(
            "switch name,switch host,sensor prefix,switch snmp community,output_dir,display name\n"
            f"{walk.name},192.0.2.70,CISCO,public,{work},Cisco Test\n",
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
                "last_run_summary_path": str(work / "last-run.txt"),
                "run_snmp_walks": False,
                "enable_switch_list": True,
                "switches": [{
                    "switch_name": "CISCO",
                    "display_name": "Cisco Test",
                    "switch_host": "192.0.2.70",
                    "sensor_prefix": "CISCO",
                    "snmp_community": "public",
                    "enabled": "enabled",
                    "walk_mode": "targeted",
                    "switch_model": "auto",
                    "card_header_title": "",
                }],
                "stack_member_prefixes": [],
                "live_output_dir": str(work / "live"),
                "live_output_path": str(work / "live/live-targeted-snmpwalk.txt"),
                "live_log_path": str(work / "live-snmpwalk.log"),
            }),
            encoding="utf-8",
        )

        env = os.environ.copy()
        env.update({
            "PYTHONDONTWRITEBYTECODE": "1",
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

        yaml_text = generated.read_text(encoding="utf-8")
        required = (
            "name: CISCO Fan 1 State",
            "oid: 1.3.6.1.4.1.9.9.13.1.4.1.3.1",
            "name: CISCO PSU 1 State",
            "oid: 1.3.6.1.4.1.9.9.13.1.5.1.3.1",
            "name: CISCO Port 1 PoE Status Code",
            "oid: 1.3.6.1.2.1.105.1.1.1.6.1.1",
            "name: CISCO Port 1 PoE Class Code",
            "oid: 1.3.6.1.2.1.105.1.1.1.10.1.1",
            "name: CISCO Port 1 PoE Power",
            "oid: 1.3.6.1.4.1.9.9.402.1.2.1.9.1.1",
            "transform: value / 1000",
            'unit_of_measurement: "W"',
        )
        for marker in required:
            assert marker in yaml_text, marker

        assert "CISCO Port 2 PoE Status Code" not in yaml_text
        assert "CISCO Port 2 PoE Class Code" not in yaml_text
        assert "CISCO Port 2 PoE Power" not in yaml_text

    print("Switch Vision Discovery Cisco fan/PSU/per-port PoE regression: PASS")


if __name__ == "__main__":
    main()
