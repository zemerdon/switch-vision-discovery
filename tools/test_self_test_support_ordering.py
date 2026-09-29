#!/usr/bin/env python3
"""Permanent contract for the extracted Support My Switch ordering self-test module."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF_TEST = ROOT / "runtime_src/self-test.sh"
MODULE = ROOT / "runtime_src/self_test_support_ordering.sh"

HEADER = """# Switch Vision Discovery self-test Support My Switch ordering module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

"""
EXTRACTED_BODY_SHA256 = "fff24185dccface822e51953847570da63dcbda17908fdc3a74516439094b8a0"
START_MARKER = "# v2.2.5 automatic Support My Switch ordering regression. The shell Discovery"
NEXT_MARKER = "# Discovery 2.3.39 Hub Settings Back regression."


def main() -> int:
    self_test = SELF_TEST.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    assert self_test.count('. "$BASE_DIR/self_test_support_ordering.sh"') == 1
    assert START_MARKER not in self_test
    assert module.startswith(HEADER)
    assert module.count(START_MARKER) == 1
    assert NEXT_MARKER not in module

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

    print("Discovery Support My Switch ordering self-test module contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
