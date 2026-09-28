#!/usr/bin/env python3
"""Permanent contracts for extracted Hub diagnostics orchestration."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import hub_diagnostics


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def file_info(path: Path):
    return {
        "found": path.is_file(),
        "path": str(path),
        "size": path.stat().st_size if path.is_file() else 0,
        "modified": None,
    }


def main() -> int:
    source = (RUNTIME / "hub_diagnostics.py").read_text(encoding="utf-8")
    assert re.search(r"(?m)^\s*import\s+support_web\b", source) is None
    assert re.search(r"(?m)^\s*from\s+support_web\b", source) is None

    assert hub_diagnostics.normalized_device_mac("02-11-22-33-44-55") == "02:11:22:33:44:55"
    assert hub_diagnostics.normalized_device_mac("invalid") == ""
    assert hub_diagnostics.normalized_device_ip("192.0.2.10") == "192.0.2.10"
    assert hub_diagnostics.normalized_device_ip("not-an-ip") == ""

    with tempfile.TemporaryDirectory(prefix="sv-hub-diagnostics-") as tmp_name:
        root = Path(tmp_name)
        share = root / "share"
        caps = share / "capabilities"
        walks = share / "snmpwalks" / "SW1"
        unifi = share / "unifi"
        caps.mkdir(parents=True)
        walks.mkdir(parents=True)
        unifi.mkdir(parents=True)

        walk = walks / "live-targeted-snmpwalk.txt"
        walk.write_text(
            '# Switch IP: 192.0.2.10\n.1.3.6.1.2.1.1.1.0 = STRING: "switch"\n',
            encoding="utf-8",
        )
        capability = {
            "source_walk": str(walk),
            "generated_at": "2026-09-29T00:00:00+00:00",
            "device": {
                "model_text": "Test Switch",
                "support_status": "experimental",
                "mac_address": "02:11:22:33:44:55",
            },
            "interfaces": [
                {"physical": True, "media": "rj45"},
                {"physical": True, "media": "sfp"},
            ],
        }
        (caps / "SW1-capabilities.json").write_text(
            json.dumps(capability), encoding="utf-8"
        )
        (unifi / "devices.json").write_text(
            json.dumps({
                "generated_at": "2026-09-29T00:00:00+00:00",
                "devices": [{
                    "id": "unifi-same",
                    "name": "UniFi observation",
                    "model": "Test Switch",
                    "ip_address": "198.51.100.10",
                    "mac_address": "02-11-22-33-44-55",
                    "state": "ONLINE",
                    "firmware": "test",
                    "ports": [],
                }],
            }),
            encoding="utf-8",
        )
        registry = root / "registry.json"
        registry.write_text('{"devices":[]}', encoding="utf-8")
        options = {
            "switches": [{
                "switch_name": "SW1",
                "switch_host": "192.0.2.10",
                "sensor_prefix": "sw1",
            }]
        }

        runtime = hub_diagnostics.HubDiagnosticsRuntime(
            read_json=read_json,
            registry_lookup=lambda _registry, _model: None,
            switch_name_identity=lambda value: str(value).strip().casefold(),
            self_addon_options=lambda: options,
            load_options=lambda _path: options,
            unifi2mqtt_diagnostics_status=lambda: {"found": False},
            file_info=file_info,
            snmp2mqtt_applicability=lambda: {"applicable": True},
            discovery_state_snapshot=lambda: {"message": "Complete"},
            default_share_dir=share,
            default_registry_file=registry,
            default_unifi_snapshot=unifi / "devices.json",
            default_support_script=root / "support_my_switch.sh",
            default_contributions_dir=root / "contributions",
        )

        snapshot = hub_diagnostics.diagnostics_snapshot(
            "test",
            root / "options.json",
            runtime=runtime,
        )
        assert len(snapshot["devices"]) == 1, snapshot["devices"]
        device = snapshot["devices"][0]
        assert device["name"] == "SW1"
        assert device["data_source"] == "SNMP + UniFi API"
        assert device["unifi_match_basis"] == "hardware_mac"
        assert device["unifi_device_id"] == "unifi-same"
        assert "_identity_mac" not in device
        assert "_identity_ip" not in device
        assert device["physical_interfaces"] == 2
        assert device["rj45_interfaces"] == 1
        assert device["uplink_interfaces"] == 1

        text = hub_diagnostics.diagnostics_text(snapshot)
        assert "Switch Vision Diagnostics" in text
        assert "Data source: SNMP + UniFi API" in text
        assert "02:11:22:33:44:55" not in text

    print("Switch Vision Hub diagnostics module contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
