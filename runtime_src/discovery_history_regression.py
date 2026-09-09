#!/usr/bin/env python3
"""Permanent bounded Discovery history regression."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from discovery_history import (
    DEBUG_LINE_LIMIT,
    HISTORY_LIMIT,
    append_discovery_history,
    discovery_history_snapshot,
)

BASE_DIR = Path(__file__).resolve().parent
SUPPORT_WEB = BASE_DIR / "support_web.py"

with tempfile.TemporaryDirectory(prefix="sv-discovery-history-") as tmp:
    history_path = Path(tmp) / "history.json"
    for index in range(HISTORY_LIMIT + 5):
        append_discovery_history(
            {
                "mode": "regenerate_card" if index % 2 else "discovery",
                "success": index % 3 != 0,
                "phase": "complete" if index % 3 else "failed",
                "started_at": f"2026-09-10T00:{index:02d}:00+1000",
                "finished_at": f"2026-09-10T00:{index:02d}:09+1000",
                "elapsed_seconds": 9,
                "message": f"operation {index} community=private-{index}",
                "stage": "Stored walk parse",
                "switch": f"LAB-{index}",
                "target": f"192.0.2.{index}",
                "activity": "Parsing saved walk",
                "command": f"snmpwalk -c private-{index} 192.0.2.{index}",
                "snmp2mqtt": {
                    "status": "Waiting",
                    "message": f"token=secret-{index}",
                },
                "log_tail": [
                    f"line {line} password=pw-{index}"
                    for line in range(DEBUG_LINE_LIMIT + 15)
                ],
            },
            history_path,
        )

    snapshot = discovery_history_snapshot(history_path)
    items = snapshot["items"]
    assert snapshot["limit"] == HISTORY_LIMIT
    assert snapshot["debug_line_limit"] == DEBUG_LINE_LIMIT
    assert len(items) == HISTORY_LIMIT
    assert items[0]["message"].startswith("operation 5 ")
    assert len(items[-1]["debug_tail"]) == DEBUG_LINE_LIMIT
    serialized = json.dumps(snapshot, sort_keys=True)
    for secret in ("private-24", "secret-24", "pw-24"):
        assert secret not in serialized
    assert "[REDACTED]" in serialized
    assert items[-1]["duration_seconds"] == 9
    assert items[-1]["mode"] == "discovery"
    assert items[-1]["status"] == "failed"
    assert os.stat(history_path).st_mode & 0o777 == 0o600

    history_path.write_text("{corrupt", encoding="utf-8")
    assert discovery_history_snapshot(history_path)["items"] == []

source = SUPPORT_WEB.read_text(encoding="utf-8")
for required in (
    "append_discovery_history(_discovery_state_snapshot())",
    '"discovery_history": discovery_history_snapshot()',
    'id="discoveryHistoryWrap"',
    'id="discoveryHistory"',
    "function renderDiscoveryHistory(history)",
    "renderDiscoveryHistory(d.discovery_history||{})",
):
    assert required in source, required

print("Switch Vision Discovery bounded structured history: PASS")
