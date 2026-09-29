#!/usr/bin/env python3
"""Permanent contract for the extracted Hub Settings Back self-test module."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF_TEST = ROOT / "runtime_src/self-test.sh"
MODULE = ROOT / "runtime_src/self_test_hub_settings_back.sh"

HEADER = """# Switch Vision Discovery self-test Hub Settings Back module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

"""
EXTRACTED_BODY_SHA256 = "b5fbc8d6e986ff3fd9b2212aab0a4003679e168eafd4d042c8624ae0d51f2b60"
START_MARKER = "# Discovery 2.3.39 Hub Settings Back regression."
NEXT_MARKER = "# Manual dashboard export regression. Native generated YAML remains unchanged;"


def main() -> int:
    self_test = SELF_TEST.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    assert self_test.count('. "$BASE_DIR/self_test_hub_settings_back.sh"') == 1
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

    print("Discovery Hub Settings Back self-test module contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
