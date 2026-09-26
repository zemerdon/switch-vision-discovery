#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import support_web as web

original_options = web._self_addon_options
original_pending = web.DEFAULT_CONFIGURATION_RESTORE_PENDING

try:
    with tempfile.TemporaryDirectory(prefix="sv-restore-pending-") as tmp:
        web.DEFAULT_CONFIGURATION_RESTORE_PENDING = Path(tmp) / "configuration-restore-pending.json"
        web.DEFAULT_CONFIGURATION_RESTORE_PENDING.write_text(
            json.dumps({
                "schema_version": 1,
                "discovery_switches": [{
                    "switch_name": "SW1",
                    "display_name": "Old name",
                    "switch_host": "192.0.2.10",
                    "sensor_prefix": "sw1",
                    "enabled": "disabled",
                    "walk_mode": "targeted",
                    "switch_model": "auto",
                    "card_header_title": "",
                    "snmp_community": "",
                    "snmp_community_configured": False,
                    "restore_pending": True,
                }],
                "discovery_stack_member_prefixes": [],
                "unifi_controllers": [],
            }),
            encoding="utf-8",
        )
        live_options = {
            "switches": [{
                "switch_name": "SW1",
                "display_name": "Current name",
                "switch_host": "192.0.2.10",
                "sensor_prefix": "sw1",
                "snmp_community": "configured-community",
                "enabled": "enabled",
                "walk_mode": "targeted",
                "switch_model": "auto",
                "card_header_title": "",
            }],
            "stack_member_prefixes": [],
            "autodiscover_networks": [],
        }
        web._self_addon_options = lambda: live_options
        result = web._discovery_settings_status()
        rows = result["settings"]["switches"]
        assert len(rows) == 1, rows
        assert rows[0]["switch_name"] == "SW1", rows
        assert rows[0]["display_name"] == "Current name", rows
        assert rows[0]["enabled"] == "enabled", rows
        assert rows[0]["snmp_community"] == "", rows
        assert rows[0]["snmp_community_configured"] is True, rows
        assert not rows[0].get("restore_pending"), rows
        pending = web._load_configuration_restore_pending()
        assert pending["discovery_switches"] == [], pending

    class FailingPendingPath:
        def unlink(self, *, missing_ok: bool = False) -> None:
            assert missing_ok is True
            raise OSError("injected pending-state delete failure")

    web.DEFAULT_CONFIGURATION_RESTORE_PENDING = FailingPendingPath()
    try:
        web._save_configuration_restore_pending({
            "discovery_switches": [],
            "discovery_stack_member_prefixes": [],
            "unifi_controllers": [],
        })
    except RuntimeError as exc:
        assert "Could not clear pending configuration restore state" in str(exc), exc
        assert "injected pending-state delete failure" in str(exc), exc
    else:
        raise AssertionError("pending-state delete failure must be surfaced")

    print("Discovery stale restore-pending reconciliation: PASS")
finally:
    web._self_addon_options = original_options
    web.DEFAULT_CONFIGURATION_RESTORE_PENDING = original_pending
