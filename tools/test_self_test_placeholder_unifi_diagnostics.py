#!/usr/bin/env python3
"""Permanent contract for the extracted placeholder/UniFi diagnostics self-test module."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF_TEST = ROOT / "runtime_src/self-test.sh"
MODULE = ROOT / "runtime_src/self_test_placeholder_unifi_diagnostics.sh"

HEADER = """# Switch Vision Discovery self-test placeholder/UniFi diagnostics module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

"""
EXTRACTED_BODY_SHA256 = "2f0bd7c0cfa8ffc3bbe317c820a4ab66c7766ef1158a9c6ee1454793e76b8bef"
START_MARKER = "# v2.1.18 placeholder and UniFi diagnostics regressions."
NEXT_MARKER = "# v2.1.14 configuration/operation hardening regressions."


def main() -> int:
    self_test = SELF_TEST.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    assert self_test.count('. "$BASE_DIR/self_test_placeholder_unifi_diagnostics.sh"') == 1
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

    print("Discovery placeholder/UniFi diagnostics self-test module contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
