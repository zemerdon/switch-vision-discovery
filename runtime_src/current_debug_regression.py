#!/usr/bin/env python3
"""Regression for complete current Discovery debug-session retention."""
from __future__ import annotations

import tempfile
from pathlib import Path

import support_web as web


with tempfile.TemporaryDirectory(prefix="sv-current-debug-") as tmp:
    original_path = web.DEFAULT_CURRENT_DISCOVERY_DEBUG
    web.DEFAULT_CURRENT_DISCOVERY_DEBUG = Path(tmp) / "current-debug.log"
    try:
        web._reset_current_discovery_debug()
        for index in range(350):
            value = f"debug line {index}"
            if index == 173:
                value += " api_key=super-secret-value"
            web._append_current_discovery_debug(value)

        snapshot = web._current_discovery_debug_snapshot()
        lines = snapshot["text"].splitlines()
        assert snapshot["line_count"] == 350, snapshot["line_count"]
        assert lines[0] == "debug line 0", lines[0]
        assert lines[-1] == "debug line 349", lines[-1]
        assert "super-secret-value" not in snapshot["text"]
        assert "api_key=[REDACTED]" in snapshot["text"]
        assert web.DEFAULT_CURRENT_DISCOVERY_DEBUG.stat().st_mode & 0o777 == 0o600

        web._reset_current_discovery_debug()
        reset = web._current_discovery_debug_snapshot()
        assert reset["line_count"] == 0, reset
        assert reset["text"] == "", reset
    finally:
        web.DEFAULT_CURRENT_DISCOVERY_DEBUG = original_path

source = Path(web.__file__).read_text(encoding="utf-8")
for marker in (
    'elif path == "/api/discovery/debug":',
    "async function fetchCurrentDiscoveryDebug()",
    "const d=await fetchCurrentDiscoveryDebug();",
    "Complete current-session debug copied",
    "if(debugVisible)await refreshCurrentDiscoveryDebug()",
    "expandedDiscoveryHistoryEntries",
    "entry.open=expandedDiscoveryHistoryEntries.has(key)",
    "<summary><strong>Recent Discovery activity</strong></summary>",
):
    assert marker in source, marker

assert "lines = lines[-300:]" not in source
assert "_set_discovery_state(log_tail=lines[-300:])" in source

print("Switch Vision complete current Discovery debug session: PASS")
