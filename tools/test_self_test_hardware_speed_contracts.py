#!/usr/bin/env python3
"""Permanent contract for the extracted hardware/status/speed self-test module."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF_TEST = ROOT / "runtime_src/self-test.sh"
MODULE = ROOT / "runtime_src/self_test_hardware_speed_contracts.sh"

HEADER = """# Switch Vision Discovery self-test hardware/status/speed contract module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

"""
EXTRACTED_BODY_SHA256 = "8dea51f22d0eea7c5b929f4670b28ae2759bc08dbb51d52341f670315d6cc9a2"
START_MARKER = "# v2.1.27 hardware-validation and speed-contract regressions."
NEXT_INCLUDE = '. "$BASE_DIR/self_test_generated_yaml_stage.sh"'


def main() -> int:
    self_test = SELF_TEST.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    assert self_test.count('. "$BASE_DIR/self_test_hardware_speed_contracts.sh"') == 1
    assert START_MARKER not in self_test
    assert module.startswith(HEADER)
    assert module.count(START_MARKER) == 1
    assert NEXT_INCLUDE not in module

    body = module[len(HEADER):].rstrip("\n")
    assert hashlib.sha256(body.encode()).hexdigest() == EXTRACTED_BODY_SHA256

    syntax = subprocess.run(
        ["sh", "-n", str(MODULE)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stdout

    print("Discovery hardware/status/speed self-test module contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
