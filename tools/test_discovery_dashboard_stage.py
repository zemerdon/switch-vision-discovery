#!/usr/bin/env python3
"""Permanent contract for the extracted Discovery generated-dashboard-card stage."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "runtime_src/discovery_job.sh"
STAGE = ROOT / "runtime_src/discovery_dashboard_stage.sh"
DOCKERFILE = ROOT / "runtime_src/Dockerfile"

EXTRACTED_BODY_SHA256 = "9fa1bd1f9ff8929bfb1cde9ee9dbfbd431a7f72a1050f17c800f4a71f87fd235"
HEADER = """# Switch Vision Discovery generated-dashboard-card stage module.
# Sourced by discovery_job.sh after shared model/registry/card helpers are defined.
# Keep dashboard-card behavior shell-native; this module is an extraction boundary.

"""

EXTRACTED_FUNCTIONS = (
    "emit_generated_port_metadata",
    "yaml_quote",
    "write_generated_dashboard_card",
)


def main() -> int:
    job = JOB.read_text(encoding="utf-8")
    stage = STAGE.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert job.count('. "$RUNTIME_DIR/discovery_dashboard_stage.sh"') == 1
    assert stage.startswith(HEADER)

    for name in EXTRACTED_FUNCTIONS:
        marker = f"{name}() {{"
        assert marker not in job, name
        assert stage.count(marker) == 1, name

    body = stage[len(HEADER):].rstrip("\n")
    assert hashlib.sha256(body.encode()).hexdigest() == EXTRACTED_BODY_SHA256
    assert "COPY discovery_dashboard_stage.sh /discovery_dashboard_stage.sh" in dockerfile

    syntax = subprocess.run(
        ["sh", "-n", str(STAGE)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stdout

    print("Discovery generated-dashboard-card stage extraction contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
