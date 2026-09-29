#!/usr/bin/env python3
"""Permanent contracts for extracted Hub AutoDiscover orchestration."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import hub_autodiscover


def plain_text(value, field, *, max_length, allow_empty=True):
    text = str(value if value is not None else "")
    if len(text) > max_length:
        raise ValueError(f"{field} is too long.")
    if not allow_empty and not text:
        raise ValueError(f"{field} cannot be empty.")
    return text


def validate_switch_row(row, _index):
    return dict(row)


def main() -> int:
    source = (RUNTIME / "hub_autodiscover.py").read_text(encoding="utf-8")
    assert re.search(r"(?m)^\s*import\s+support_web\b", source) is None
    assert re.search(r"(?m)^\s*from\s+support_web\b", source) is None

    options = {
        "switches": [
            {
                "switch_name": "Existing",
                "switch_host": "192.168.50.9",
                "snmp_community": "private-secret",
            }
        ],
        "autodiscover_networks": ["192.168.50.0/24"],
        "snmp_timeout": 1,
    }
    saved = []
    runtime = hub_autodiscover.HubAutoDiscoverRuntime(
        self_addon_options=lambda: dict(options),
        effective_discovery_options=lambda value: value,
        plain_text=plain_text,
        validate_switch_row=validate_switch_row,
        save_discovery_settings=lambda payload: saved.append(payload) or {"saved": True},
        registry_loader=lambda: {"devices": []},
        unifi_snapshot_loader=lambda: {
            "devices": [{"id": "u1", "ip_address": "192.168.50.3"}]
        },
    )

    status = hub_autodiscover.status(runtime=runtime)
    assert status["saved_switch_count"] == 1
    assert status["saved_credential_count"] == 1
    assert status["unifi_device_count"] == 1
    assert status["saved_networks"] == ["192.168.50.0/24"]
    assert status["suggested_network"] == "192.168.50.0/24"
    assert "private-secret" not in json.dumps(status, sort_keys=True)

    clean = {
        "networks": ["192.168.50.0/30"],
        "devices": [],
        "credential_count": 1,
    }
    with mock.patch.object(hub_autodiscover.autodiscover, "scan", return_value=clean):
        returned = hub_autodiscover.scan(
            {
                "networks": ["192.168.50.1/30"],
                "use_saved": True,
                "manual_community": "",
            },
            runtime=runtime,
        )
    assert returned is clean
    assert saved == [
        {"settings": {"autodiscover_networks": ["192.168.50.0/30"]}}
    ]

    saved.clear()
    leaked = {"devices": [], "leak": "private-secret"}
    with mock.patch.object(hub_autodiscover.autodiscover, "scan", return_value=leaked):
        try:
            hub_autodiscover.scan(
                {
                    "networks": ["192.168.50.0/30"],
                    "use_saved": True,
                    "manual_community": "",
                },
                runtime=runtime,
            )
        except RuntimeError as exc:
            assert "credential material" in str(exc)
        else:
            raise AssertionError("credential-bearing response must fail closed")
    assert saved == []

    assert hub_autodiscover.validated_networks(
        ["192.168.50.1/30", "192.168.60.1/30"]
    ) == ["192.168.50.0/30", "192.168.60.0/30"]

    print("Switch Vision Hub AutoDiscover module contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
