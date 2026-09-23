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


expected_support_exceptions = {
    "WS-C2960X-24PS-L": {
        "fields": ("status", "validation"),
        "reason": (
            "Discovery is the support-confidence authority and promotes the exact 24PS-L "
            "contract to Community Validated after the established real-hardware evidence "
            "plus current owner field/render validation; Core's derivative registry may lag "
            "the status and older uplink-validation marker."
        ),
    },
    "USW Flex Mini": {
        "fields": ("status",),
        "reason": (
            "Discovery is the support-confidence authority and promotes Flex Mini to "
            "Community Validated after independent API corroboration plus current owner "
            "dashboard/faceplate field validation; Core's derivative registry may lag status."
        ),
    },
    "USW Pro Aggregation": {
        "fields": ("status",),
        "reason": (
            "Discovery is the support-confidence authority and promotes this complete "
            "32-port API/card contract to Experimental under the dashboard-first policy; "
            "Core's derivative registry may lag this support-status-only change."
        ),
    },
}
assert module.SUPPORT_CONTRACT_EXCEPTIONS == expected_support_exceptions, module.SUPPORT_CONTRACT_EXCEPTIONS
assert set(module.SUPPORT_CONTRACT_EXCEPTIONS["WS-C2960X-24PS-L"]["fields"]) == {"status", "validation"}
assert set(module.SUPPORT_CONTRACT_EXCEPTIONS["USW Flex Mini"]["fields"]) == {"status"}
assert "evidence" not in module.SUPPORT_CONTRACT_EXCEPTIONS["WS-C2960X-24PS-L"]["fields"]
assert "evidence" not in module.SUPPORT_CONTRACT_EXCEPTIONS["USW Flex Mini"]["fields"]

source = MODULE_PATH.read_text(encoding="utf-8")
assert "strict_visual_models" not in source
assert "all shared exact-model visuals aligned or explicitly excepted" in source
print("Discovery strict visual-contract policy: PASS")
