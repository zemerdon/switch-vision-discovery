#!/usr/bin/env python3
"""Retained UniFi cards are not evidence of a recent controller API poll."""
import json
import tempfile
import time
from pathlib import Path

import discovery_contract_entrypoint as discovery

now = int(time.time())
fresh = {"last_success_at": now, "stale": False, "reason": ""}
stale = {"last_success_at": now, "stale": True, "reason": "all_transports_failed"}
expired = {"last_success_at": now - 3600, "stale": False, "reason": ""}
future = {"last_success_at": now + 600, "stale": False, "reason": ""}

with tempfile.TemporaryDirectory(prefix="sv-unifi-freshness-") as tmp:
    original = discovery.UNIFI_SNAPSHOT
    path = Path(tmp) / "devices.json"
    discovery.UNIFI_SNAPSHOT = path
    try:
        assert not discovery._unifi_snapshot_has_fresh_telemetry(), "missing snapshot must not prove live API success"
        cases = [
            ([], False),
            ([{"freshness": dict(fresh)}], True),
            ([{"freshness": dict(fresh)}, {"freshness": dict(fresh)}], True),
            ([{"freshness": dict(stale)}], False),
            ([{"freshness": dict(fresh)}, {"freshness": dict(stale)}], False),
            ([{"freshness": dict(expired)}], False),
            ([{"freshness": dict(future)}], False),
            ([{"id": "legacy-no-freshness"}], False),
            ([{"freshness": {"stale": False}}], False),
            ([{"freshness": {"last_success_at": now, "stale": "false"}}], False),
            ([{"freshness": {"last_success_at": True, "stale": False}}], False),
            ([{"freshness": {"last_success_at": now, "stale": False}}, None], False),
        ]
        for devices, expected in cases:
            path.write_text(json.dumps({
                "devices": devices,
                "generated_at": now,
                "stale_after_seconds": 180,
            }), encoding="utf-8")
            actual = discovery._unifi_snapshot_has_fresh_telemetry()
            assert actual is expected, (devices, expected, actual)
        for payload in ("not valid json", "null", '{"devices":{}}',
                        '{"devices":[{}],"stale_after_seconds":-1}',
                        '{"devices":[{}],"stale_after_seconds":"infinite"}'):
            path.write_text(payload, encoding="utf-8")
            assert not discovery._unifi_snapshot_has_fresh_telemetry(), payload
    finally:
        discovery.UNIFI_SNAPSHOT = original

print("UniFi snapshot live-freshness vs cached-presentation regression: PASS")
