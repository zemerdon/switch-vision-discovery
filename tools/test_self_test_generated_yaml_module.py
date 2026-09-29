#!/usr/bin/env python3
"""Permanent contract for the extracted generated-YAML self-test module."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF_TEST = ROOT / "runtime_src/self-test.sh"
MODULE = ROOT / "runtime_src/self_test_generated_yaml_stage.sh"

HEADER = """# Switch Vision Discovery self-test generated-YAML regression module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

"""
EXTRACTED_BODY_SHA256 = "7c7673ea1801d64b5f07b82c19ff2572c70ac64f8bf498b576a01239818621ee"
START_MARKER = "# v2.1.28 generated SNMP2MQTT YAML publication regression."
END_MARKER = "# community-validation UniFi exact-model/API mapping regression."


def main() -> int:
    self_test = SELF_TEST.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    assert self_test.count('. "$BASE_DIR/self_test_generated_yaml_stage.sh"') == 1
    assert START_MARKER not in self_test
    assert module.startswith(HEADER)
    assert module.count(START_MARKER) == 1
    assert END_MARKER not in module

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

    print("Discovery generated-YAML self-test module contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
