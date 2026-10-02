#!/usr/bin/env python3
"""Permanent contract for the extracted UniFi community-validation self-test module."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF_TEST = ROOT / "runtime_src/self-test.sh"
MODULE = ROOT / "runtime_src/self_test_unifi_community_validation.sh"

HEADER = """# Switch Vision Discovery self-test UniFi community-validation module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

"""
EXTRACTED_BODY_SHA256 = "44738bc4b2bb62ff02640dc915f9bb25c66e27a8f5373a35e14d8ea6510000a3"
START_MARKER = "# v2.1.19 community-validation UniFi profile regression."
NEXT_MARKER = "# v2.1.20 Dell EMC Networking N2128PX-ON contribution regression."


def main() -> int:
    self_test = SELF_TEST.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    assert self_test.count('. "$BASE_DIR/self_test_unifi_community_validation.sh"') == 1
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

    print("Discovery UniFi community-validation self-test module contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
