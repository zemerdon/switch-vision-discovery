#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTERFACE = ROOT / "runtime_src" / "opt" / "switch-vision" / "vendors" / "interface.sh"
DISCOVERY_JOB = ROOT / "runtime_src" / "discovery_job.sh"


def extract(value: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        walk = Path(td) / "walk.txt"
        walk.write_text(value + "\n", encoding="utf-8")
        result = subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; cv_cap_extract_bridge_mac "$2"',
                "bash",
                str(INTERFACE),
                str(walk),
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()


assert extract('.1.3.6.1.2.1.17.1.1.0 = Hex-STRING: 00 11 22 33 44 55') == "00:11:22:33:44:55"
assert extract('iso.3.6.1.2.1.17.1.1.0 = STRING: "AA:BB:CC:DD:EE:FF"') == "aa:bb:cc:dd:ee:ff"
assert extract('.1.3.6.1.2.1.17.1.1.0 = Hex-STRING: invalid') == ""

job = DISCOVERY_JOB.read_text(encoding="utf-8")
interface = INTERFACE.read_text(encoding="utf-8")
assert "1.3.6.1.2.1.17.1.1" in job
assert 'CV_CAP_DEVICE_MAC=$(cv_cap_extract_bridge_mac "$walk_file")' in interface
assert 'mac_address:(if ($mac_address|length)>0 then $mac_address else null end)' in interface

print("SNMP bridge-MAC reconciliation identity contract: PASS")
