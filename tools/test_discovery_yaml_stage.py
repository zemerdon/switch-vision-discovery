#!/usr/bin/env python3
"""Permanent contract for the extracted Discovery generated-YAML stage."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "runtime_src/discovery_job.sh"
STAGE = ROOT / "runtime_src/discovery_yaml_stage.sh"
DOCKERFILE = ROOT / "runtime_src/Dockerfile"

EXTRACTED_BODY_SHA256 = "903f6d60aac746e8ea8bf677ec98959b92670bc3b6bc0df60569b7b22af2f366"
HEADER = """# Switch Vision Discovery generated-YAML stage module.
# Sourced by discovery_job.sh after shared walk/target helpers are defined.
# Keep generated-YAML behavior shell-native; this module is an extraction boundary.

"""

EXTRACTED_FUNCTIONS = (
    "write_generated_yaml_for_walk",
    "generator_has_unknown_targets",
    "quarantine_invalid_generated_live_yaml",
    "report_generated_yaml_failure_state",
    "new_generated_yaml_id",
    "write_generated_yaml",
)


def main() -> int:
    job = JOB.read_text(encoding="utf-8")
    stage = STAGE.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert job.count('. "$RUNTIME_DIR/discovery_yaml_stage.sh"') == 1
    assert stage.startswith(HEADER)

    for name in EXTRACTED_FUNCTIONS:
        marker = f"{name}() {{"
        assert marker not in job, name
        assert stage.count(marker) == 1, name

    body = stage[len(HEADER):].rstrip("\n")
    assert hashlib.sha256(body.encode()).hexdigest() == EXTRACTED_BODY_SHA256
    assert "COPY discovery_yaml_stage.sh /discovery_yaml_stage.sh" in dockerfile

    syntax = subprocess.run(
        ["sh", "-n", str(STAGE)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stdout

    print("Discovery generated-YAML stage extraction contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
