#!/usr/bin/env python3
"""Permanent stack-aware reporting/native handoff wording regression."""
from pathlib import Path
import discovery_contract_entrypoint as contract

ROOT = Path(__file__).resolve().parent
ENTRY = (ROOT / "discovery_contract_entrypoint.py").read_text(encoding="utf-8")
JOB = (ROOT / "discovery_job.sh").read_text(encoding="utf-8")

ordered = [
    {"contract": {"status": "resolved", "observed": {"members": 2}}},
    *[{"contract": {"status": "resolved", "observed": {"members": 1}}} for _ in range(8)],
]
assert len(ordered) == 9
assert contract._expected_generated_snmp_cards(ordered) == 10
assert contract._physical_member_summary(ordered) == (10, 1, 2)
assert "accepted SNMP targets=" in ENTRY
assert "exact target contracts=" in ENTRY
assert "physical switch members=" in ENTRY
assert "stack targets=" in ENTRY
assert "stack members=" in ENTRY
assert "generated SNMP dashboard cards=" in ENTRY
assert "resolved exact models=" not in ENTRY

for stale in (
    "Review/copy only; it has not been installed.",
    "Review/copy only. This file is not installed automatically.",
    "Review-only output; it has not been installed.",
    "SNMP2MQTT YAML generation is review-only. The generated file is not installed automatically.",
):
    assert stale not in JOB, stale
assert "Native panel source: automatically consumed by Switch Vision" in JOB
assert "Native Switch Vision dashboard source. The native panel reads this file automatically" in JOB
assert "Authoritative Discovery handoff. Switch Vision SNMP2MQTT imports this file" in JOB
assert "Handoff source: Switch Vision SNMP2MQTT imports this generated file" in JOB
print("Discovery stack-aware reporting/native handoff wording contract: PASS")
