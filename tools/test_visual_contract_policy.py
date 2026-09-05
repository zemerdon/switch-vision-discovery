#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "check_component_contracts.py"
spec = importlib.util.spec_from_file_location("sv_discovery_contracts", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

# No vendor gets implicit warning-only treatment anymore.
for model in (
    "WS-C3650-48PD",
    "EX3300-48P",
    "N2128PX-ON",
    "S5720-12TP-LI-AC",
    "S5735-L8P4X-A1",
    "USW-Pro-24-PoE",
):
    policy, reason = module.classify_visual_contract_drift(model)
    assert policy == "error", (model, policy, reason)
    assert reason is None

expected_exceptions = {
    "US 16 PoE 150W": (
        "Discovery owns the approved stock 24+2 visual fallback; the shared "
        "physical 16 RJ45 + 2 SFP topology remains identical to Core."
    ),
    "USW Pro Aggregation": (
        "Discovery consumes the exact Core 2.6.32 32-position optical canvas; "
        "the shared physical 28 SFP+ + 4 SFP28 topology remains identical to Core."
    ),
}
assert module.VISUAL_CONTRACT_EXCEPTIONS == expected_exceptions, module.VISUAL_CONTRACT_EXCEPTIONS

module.VISUAL_CONTRACT_EXCEPTIONS["INTENTIONAL-MODEL"] = "documented test divergence"
policy, reason = module.classify_visual_contract_drift("INTENTIONAL-MODEL")
assert policy == "warning"
assert reason == "documented test divergence"

module.VISUAL_CONTRACT_EXCEPTIONS["EMPTY-REASON"] = "   "
policy, reason = module.classify_visual_contract_drift("EMPTY-REASON")
assert policy == "invalid"
assert reason is None

source = MODULE_PATH.read_text(encoding="utf-8")
assert "strict_visual_models" not in source
assert "all shared exact-model visuals aligned or explicitly excepted" in source
print("Discovery strict visual-contract policy: PASS")
