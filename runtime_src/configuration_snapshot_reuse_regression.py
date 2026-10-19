#!/usr/bin/env python3
"""Source-bound contract for shared private Discovery configuration snapshots."""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix="sv-discovery-snapshot-contract-") as td:
    root = Path(td)
    os.environ["SV_CURRENT_DISCOVERY_DEBUG_PATH"] = str(root / "current-debug.txt")
    spec = importlib.util.spec_from_file_location("sv_discovery_snapshot_contract", ROOT / "support_web.py")
    assert spec and spec.loader
    web = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(web)

    source = {
        "switches": [{
            "switch_name": "LAB1",
            "switch_host": "192.0.2.18",
            "sensor_prefix": "LAB1",
            "snmp_community": "private-fixture-value",
            "enabled": "enabled",
        }],
        "enable_switch_list": False,
        "run_snmp_walks": True,
        "run_live_snmpwalk": True,
        "parse_all_walks": False,
        "generate_support_my_switch_bundle": True,
        "snmp_community": "private-fixture-value",
    }
    web._self_addon_options = lambda: dict(source)
    web._validate_inventory_identities = lambda _options: None
    web.DEFAULT_GENERATED_SNMP2MQTT = root / "real-snmp-output.yaml"
    web.DEFAULT_GENERATED_CARD = root / "real-dashboard.yaml"

    cases = (
        ("authoritative", lambda path: web._write_authoritative_discovery_options_snapshot(path, options=source),
         "Could not prepare the authoritative Discovery configuration snapshot"),
        ("snmp", web._write_snmp2mqtt_regeneration_options_snapshot,
         "Could not prepare SNMP2MQTT regeneration configuration"),
        ("device", web._write_device_state_application_options_snapshot,
         "Could not prepare device-state application configuration"),
        ("card", web._write_dashboard_card_regeneration_options_snapshot,
         "Could not prepare Dashboard Card regeneration configuration"),
    )
    for name, writer, failure in cases:
        path = root / f"{name}.json"
        assert writer(path) == path
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert path.read_bytes().endswith(b"\n")
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert payload["switches"][0]["switch_name"] == "LAB1"
        assert payload["snmp_community"] == "private-fixture-value"
        assert payload["generate_support_my_switch_bundle"] is False
        if name != "authoritative":
            assert payload["run_snmp_walks"] is False
            assert payload["run_live_snmpwalk"] is False
            assert payload["clean_output_before_walk"] is False
            assert payload["parse_all_walks"] is True
            assert payload["enable_switch_list"] is True
            assert payload["generate_snmp2mqtt"] is (name != "card")
        if name == "card":
            assert payload["generated_card_path"] == str(web.DEFAULT_GENERATED_CARD)
            assert payload["generated_yaml_path"].startswith("/tmp/")
        elif name == "device":
            assert payload["generated_card_path"] == str(web.DEFAULT_GENERATED_CARD)
            assert payload["generated_yaml_path"] == str(web.DEFAULT_GENERATED_SNMP2MQTT)

        # Force the atomic rename to fail: the destination is a directory.
        # The old destination must remain untouched and temp must be removed.
        blocked = root / f"{name}-blocked"
        blocked.mkdir()
        temporary = blocked.with_name(f".{blocked.name}.{os.getpid()}.tmp")
        try:
            writer(blocked)
        except RuntimeError as exc:
            assert str(exc).startswith(failure + ": "), (name, exc)
        else:
            raise AssertionError(f"expected atomic-write failure: {name}")
        assert blocked.is_dir()
        assert not temporary.exists()
        assert path.exists()

print("Discovery shared private configuration snapshots and failure cleanup: PASS")
