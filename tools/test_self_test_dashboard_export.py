#!/usr/bin/env python3
"""Permanent contract for the extracted manual dashboard-export self-test module."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF_TEST = ROOT / "runtime_src/self-test.sh"
MODULE = ROOT / "runtime_src/self_test_dashboard_export.sh"

HEADER = """# Switch Vision Discovery self-test manual dashboard-export module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

"""
EXTRACTED_BODY_SHA256 = "d3e716047e29cd301b68ec0a1abd533b1d9eb118e51e5e33e13c7ac000f522fe"
START_MARKER = "# Manual dashboard export regression. Native generated YAML remains unchanged;"
INCLUDE = '. "$BASE_DIR/self_test_dashboard_export.sh"'


def main() -> int:
    self_test = SELF_TEST.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    assert self_test.count(INCLUDE) == 1
    assert self_test.rstrip().endswith(INCLUDE)
    assert START_MARKER not in self_test
    assert module.startswith(HEADER)
    assert module.count(START_MARKER) == 1

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

    print("Discovery manual dashboard-export self-test module contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
