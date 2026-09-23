#!/usr/bin/env python3
"""Regression contract for Devices -> AutoDiscover."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest import mock

import autodiscover
import support_web as web

HERE = Path(__file__).resolve().parent
WEB_SOURCE = (HERE / "support_web.py").read_text(encoding="utf-8")


def fake_runner(command, **kwargs):
    host = command[-4] if command[0] == "snmpget" else command[-2]
    if host != "192.168.50.2":
        return subprocess.CompletedProcess(command, 1, "", "timeout")
    if command[0] == "snmpget":
        return subprocess.CompletedProcess(
            command,
            0,
            '"Cisco IOS Software, test"\n.1.3.6.1.4.1.9.1.1\n"switch-two"\n',
            "",
        )
    return subprocess.CompletedProcess(command, 0, '"WS-C2960X-24PS-L"\n', "")


registry = {
    "devices": [
        {
            "model": "WS-C2960X-24PS-L",
            "vendor": "Cisco",
            "status": "Experimental",
            "dashboard_support": True,
        },
        {
            "model": "USW Pro 24",
            "vendor": "Ubiquiti",
            "status": "Supported",
            "dashboard_support": True,
        },
    ]
}

options = {
    "switches": [
        {
            "switch_name": "",
            "switch_host": "",
            "snmp_community": "readonly",
        },
        {
            "switch_name": "Existing",
            "switch_host": "192.168.50.9",
            "snmp_community": "private-secret",
        },
        {
            "switch_name": "Duplicate Secret",
            "switch_host": "192.168.50.10",
            "snmp_community": "private-secret",
        },
    ]
}

assert str(autodiscover.validate_subnet("192.168.50.1/30")) == "192.168.50.0/30"
try:
    autodiscover.validate_subnet("192.168.0.0/21")
except ValueError as exc:
    assert "limited" in str(exc)
else:
    raise AssertionError("oversized subnet should fail")
try:
    autodiscover.validate_subnet("2001:db8::/120")
except ValueError as exc:
    assert "IPv4" in str(exc)
else:
    raise AssertionError("IPv6 should fail in v1")

creds = autodiscover.credential_specs(options, use_saved=True, manual_community="one-time-secret")
assert [item["ref"] for item in creds] == ["saved:Existing", "manual"], creds
assert all(item["community"] != "readonly" for item in creds)
assert autodiscover.resolve_credential(options, "saved:Existing") == "private-secret"
assert autodiscover.resolve_credential(options, "manual", manual_community="one-time-secret") == "one-time-secret"

result = autodiscover.scan(
    "192.168.50.0/30",
    options=options,
    manual_community="one-time-secret",
    use_saved=True,
    registry_data=registry,
    unifi_snapshot={
        "devices": [
            {
                "id": "unifi-1",
                "name": "UniFi switch",
                "model": "USW Pro 24",
                "ip_address": "192.168.50.3",
                "state": "ONLINE",
            }
        ]
    },
    timeout=0.2,
    workers=2,
    runner=fake_runner,
)
assert result["network"] == "192.168.50.0/30"
assert result["network_hosts"] == 2
assert result["snmp_probe_hosts"] == 2
assert result["scanned_hosts"] == 2
assert result["credential_count"] == 2
assert result["snmp_devices"] == 1
assert result["unifi_devices"] == 1
snmp = [row for row in result["devices"] if row["host"] == "192.168.50.2"][0]
assert snmp["registry_match"] is True, snmp
assert snmp["model"] == "WS-C2960X-24PS-L", snmp
assert snmp["suggested_switch_name"] == "switch-two"
assert snmp["ready_to_add"] is True
unifi = [row for row in result["devices"] if row["host"] == "192.168.50.3"][0]
assert unifi["already_managed"] is True
assert unifi["ready_to_add"] is False
assert unifi["model"] == "USW Pro 24"
encoded = json.dumps(result)
for secret in ("private-secret", "one-time-secret", "readonly"):
    assert secret not in encoded, secret

# With no selected SNMP credential source, AutoDiscover still returns UniFi/API
# inventory but must not pretend the IPv4 range was probed.
def no_probe_runner(*args, **kwargs):
    raise AssertionError("SNMP runner must not execute without credentials")

no_creds = autodiscover.scan(
    "192.168.50.0/30",
    options={"switches": []},
    use_saved=False,
    registry_data=registry,
    unifi_snapshot={"devices": []},
    runner=no_probe_runner,
)
assert no_creds["network_hosts"] == 2, no_creds
assert no_creds["snmp_probe_hosts"] == 0, no_creds
assert no_creds["scanned_hosts"] == 0, no_creds
assert no_creds["credential_count"] == 0, no_creds

for marker in (
    'data-devices-tab="autodiscover">AutoDiscover</button>',
    'id="devicesPanel-autodiscover"',
    "function loadAutoDiscoverStatus()",
    "async function scanAutoDiscover()",
    "async function addAutoDiscoverDevices(",
    "'api/autodiscover/status'",
    "'api/autodiscover/scan'",
    "'api/autodiscover/add'",
    'path == "/api/autodiscover/status"',
    'path == "/api/autodiscover/scan"',
    'path == "/api/autodiscover/add"',
    "const ids=['configure','autodiscover','overview']",
    "if(item.addable){const actions=document.createElement('div')",
    "filter(item=>item?.addable===true)",
):
    assert marker in WEB_SOURCE, marker

assert WEB_SOURCE.index('id="devicesTab-configure"') < WEB_SOURCE.index('id="devicesTab-autodiscover"') < WEB_SOURCE.index('id="devicesTab-overview"')
assert "guess" in WEB_SOURCE.lower()
assert "brute" not in WEB_SOURCE.lower()
assert "autodiscoverCommunity').value=''" not in WEB_SOURCE
# Hub status never reveals saved credential values.
with mock.patch.object(web, "_self_addon_options", return_value=options), mock.patch.object(
    web, "_effective_discovery_options", side_effect=lambda value: value
), mock.patch.object(
    web,
    "_autodiscover_unifi_snapshot",
    return_value={"devices": [{"id": "u1", "ip_address": "192.168.50.3"}]},
):
    status = web._autodiscover_status()
assert status["saved_credential_count"] == 1, status
assert status["unifi_device_count"] == 1, status
assert status["suggested_network"] == "192.168.50.0/24", status
status_json = json.dumps(status)
assert "private-secret" not in status_json
assert "readonly" not in status_json

# A scan payload is fail-closed if any credential material somehow enters its result.
with mock.patch.object(web, "_self_addon_options", return_value=options), mock.patch.object(
    web, "_effective_discovery_options", side_effect=lambda value: value
), mock.patch.object(
    web.autodiscover, "scan", return_value={"devices": [], "leak": "private-secret"}
):
    try:
        web._autodiscover_scan(
            {"network": "192.168.50.0/30", "use_saved": True, "manual_community": ""}
        )
    except RuntimeError as exc:
        assert "credential material" in str(exc)
    else:
        raise AssertionError("credential-bearing AutoDiscover response should fail closed")

# Add revalidates the candidate, keeps exact model ownership with normal Discovery,
# removes only the factory placeholder, and saves all requested additions atomically.
captured = []
verified_candidate = {
    "host": "192.168.50.2",
    "sys_name": "switch-two",
    "model": "WS-C2960X-24PS-L",
    "model_hint": "WS-C2960X-24PS-L",
}
with mock.patch.object(web, "_self_addon_options", return_value=options), mock.patch.object(
    web, "_effective_discovery_options", side_effect=lambda value: value
), mock.patch.object(
    web, "_autodiscover_registry", return_value=registry
), mock.patch.object(
    web.autodiscover, "probe_host", return_value=verified_candidate
), mock.patch.object(
    web,
    "_save_discovery_settings",
    side_effect=lambda payload: captured.append(payload) or {"saved": True, "settings": {}},
):
    added = web._autodiscover_add(
        {
            "network": "192.168.50.0/24",
            "manual_community": "",
            "devices": [{"host": "192.168.50.2", "credential_ref": "saved:Existing"}],
        }
    )
assert added["added_count"] == 1, added
assert "settings" not in added, added
assert len(captured) == 1, captured
saved_rows = captured[0]["settings"]["switches"]
assert len(saved_rows) == 3, saved_rows
new_row = [row for row in saved_rows if row["switch_host"] == "192.168.50.2"][0]
assert new_row["switch_model"] == "auto", new_row
assert new_row["snmp_community"] == "private-secret", new_row
assert not any(not row.get("switch_name") and not row.get("switch_host") for row in saved_rows)
assert "private-secret" not in json.dumps(added)

# If any member of an Add All request fails revalidation, nothing is persisted.
save_attempts = []
def selective_probe(host, *args, **kwargs):
    if host == "192.168.50.2":
        return verified_candidate
    return None

with mock.patch.object(web, "_self_addon_options", return_value=options), mock.patch.object(
    web, "_effective_discovery_options", side_effect=lambda value: value
), mock.patch.object(
    web, "_autodiscover_registry", return_value=registry
), mock.patch.object(
    web.autodiscover, "probe_host", side_effect=selective_probe
), mock.patch.object(
    web, "_save_discovery_settings", side_effect=lambda payload: save_attempts.append(payload)
):
    try:
        web._autodiscover_add(
            {
                "network": "192.168.50.0/24",
                "manual_community": "",
                "devices": [
                    {"host": "192.168.50.2", "credential_ref": "saved:Existing"},
                    {"host": "192.168.50.3", "credential_ref": "saved:Existing"},
                ],
            }
        )
    except ValueError as exc:
        assert "no longer responds" in str(exc)
    else:
        raise AssertionError("stale Add All candidate should fail")
assert save_attempts == [], save_attempts

print("Switch Vision Devices AutoDiscover regression: PASS")
