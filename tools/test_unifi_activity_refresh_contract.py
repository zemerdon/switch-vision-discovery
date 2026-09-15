#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "runtime_src" / "unifi_dashboard_cards.py"


def load_module():
    spec = importlib.util.spec_from_file_location("sv_unifi_dashboard_cards", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load UniFi dashboard card generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    module = load_module()
    snapshot = {
        "devices": [
            {
                "id": "fixture-device",
                "model": "Fixture UniFi Switch",
                "ip_address": "192.0.2.10",
                "ports": [
                    {"idx": 1, "connector": "RJ45", "state": "UP", "speed_mbps": 1000},
                ],
                "api_capabilities": {
                    "port_detail": True,
                    "per_port_traffic": True,
                },
            }
        ]
    }
    registry = {"devices": []}

    binding = module.binding_card_fields(snapshot, registry, "192.0.2.10")
    assert binding is not None
    assert binding["unifi_refresh_seconds"] == 10, binding
    assert binding["unifi_per_port_traffic"] is True, binding

    rendered, emitted, *_ = module.render(snapshot, registry, indent=0)
    assert emitted == 1, rendered
    assert "unifi_refresh_seconds: 10" in rendered, rendered
    assert "activity_hold_seconds: 12" in rendered, rendered
    assert "unifi_refresh_seconds: 30" not in rendered, rendered

    print("Discovery UniFi activity refresh contract: PASS (10s refresh / 12s hold)")


if __name__ == "__main__":
    main()
