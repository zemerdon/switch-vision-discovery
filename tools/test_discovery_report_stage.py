#!/usr/bin/env python3
"""Permanent contract for the extracted Discovery report stage."""
from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "runtime_src/discovery_job.sh"
STAGE = ROOT / "runtime_src/discovery_report_stage.sh"
DOCKERFILE = ROOT / "runtime_src/Dockerfile"

EXTRACTED_BODY_SHA256 = "ab0acda2a75900c336f5e2e86b8caa34fb9ad246c177e39e6b1948bcfb3da7e6"
HEADER = """# Switch Vision Discovery report-stage module.
# Sourced by discovery_job.sh after shared walk/CSV helpers are defined.
# Keep report/parser behavior shell-native; this module is an extraction boundary.

"""


def main() -> int:
    job = JOB.read_text(encoding="utf-8")
    stage = STAGE.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert job.count('. "$RUNTIME_DIR/discovery_report_stage.sh"') == 1
    assert "parser_report() {" not in job
    assert "write_walk_section() {" not in job
    assert stage.startswith(HEADER)
    assert stage.count("parser_report() {") == 1
    assert stage.count("write_walk_section() {") == 1

    body = stage[len(HEADER):].rstrip("\n")
    assert hashlib.sha256(body.encode()).hexdigest() == EXTRACTED_BODY_SHA256

    assert "COPY discovery_report_stage.sh /discovery_report_stage.sh" in dockerfile

    syntax = subprocess.run(
        ["sh", "-n", str(STAGE)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stdout

    with tempfile.TemporaryDirectory(prefix="sv-discovery-report-stage-") as tmp:
        walk = Path(tmp) / "synthetic-walk.txt"
        walk.write_text(
            """.1.3.6.1.2.1.1.5.0 = STRING: report-test-switch
.1.3.6.1.2.1.1.1.0 = STRING: Cisco IOS Software, WS-C2960X-24PS-L, Version 15.2(7)E
.1.3.6.1.2.1.31.1.1.1.1.1 = STRING: Gi1/0/1
.1.3.6.1.2.1.2.2.1.8.1 = INTEGER: up(1)
""",
            encoding="utf-8",
        )
        harness = (
            'GENERATE_SNMP2MQTT=false; '
            'REGISTRY_LOOKUP=/nonexistent-registry-lookup.py; '
            'DEVICE_REGISTRY=/nonexistent-supported-devices.json; '
            f'. "{STAGE}"; '
            'parser_report "$1" "192.0.2.10"'
        )
        result = subprocess.run(
            ["sh", "-c", harness, "sv-report-stage-test", str(walk)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert result.returncode == 0, result.stdout
        output = result.stdout
        required = (
            "Discovery parser summary",
            "Hostname: report-test-switch",
            "Model/platform: WS-C2960X-24PS-L",
            "management target provided: 192.0.2.10",
            "Parser notes:",
        )
        for marker in required:
            assert marker in output, (marker, output)

    print("Discovery report-stage extraction contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
