#!/usr/bin/env python3
"""Regression for explicit one-at-a-time Hub credential reveal."""
from __future__ import annotations

import json
from pathlib import Path

import support_web as web

DISCOVERY_VALUE = "fixture-community-001"
SNMP_VALUE = "fixture-mqtt-002"
LOCAL_VALUE = "fixture-local-003"
REMOTE_VALUE = "fixture-remote-004"
CONTROLLER_VALUE = "fixture-controller-005"
UNIFI_MQTT_VALUE = "fixture-unifi-mqtt-006"


discovery_options = {
    "switches": [
        {
            "switch_name": "saved_switch",
            "display_name": "Saved Switch",
            "switch_host": "192.0.2.10",
            "sensor_prefix": "saved_switch",
            "snmp_community": DISCOVERY_VALUE,
            "enabled": "enabled",
            "walk_mode": "targeted",
            "switch_model": "auto",
            "card_header_title": "",
        }
    ]
}

snmp_options = {
    "mqtt": {
        "host": "broker.example.invalid",
        "port": 1883,
        "username": "fixture-user",
        "password": SNMP_VALUE,
    }
}

unifi_options = {
    "transport": "local",
    "api_key": "",
    "local_api_key": LOCAL_VALUE,
    "remote_api_key": REMOTE_VALUE,
    "mqtt_password": UNIFI_MQTT_VALUE,
    "controllers": [
        {
            "id": "branch_one",
            "transport": "local",
            "controller_url": "https://192.0.2.20:11443",
            "site_id": "auto",
            "api_key": CONTROLLER_VALUE,
            "verify_ssl": "true",
            "allow_insecure_http": "false",
        }
    ],
}

web._self_addon_options = lambda: dict(discovery_options)
web._snmp2mqtt_addon_options = lambda: ("fixture_snmp", "started", dict(snmp_options))
web._find_unifi2mqtt_addon = lambda include_store=True: {
    "slug": "fixture_unifi",
    "name": "Switch Vision UniFi2MQTT",
    "installed": True,
    "state": "started",
    "_source": "addons",
}


def fake_supervisor(path: str, **_kwargs):
    if path == "/addons/fixture_unifi/info":
        return {"data": {"state": "started", "options": dict(unifi_options)}}
    raise AssertionError(f"unexpected Supervisor request: {path}")


web._supervisor_json = fake_supervisor

assert web._reveal_hub_secret(
    {"scope": "discovery", "kind": "snmp_community", "identifier": "saved_switch"}
)["secret"] == DISCOVERY_VALUE
assert web._reveal_hub_secret(
    {"scope": "snmp2mqtt", "kind": "mqtt_password"}
)["secret"] == SNMP_VALUE
assert web._reveal_hub_secret(
    {"scope": "unifi2mqtt", "kind": "local_api_key"}
)["secret"] == LOCAL_VALUE
assert web._reveal_hub_secret(
    {"scope": "unifi2mqtt", "kind": "remote_api_key"}
)["secret"] == REMOTE_VALUE
assert web._reveal_hub_secret(
    {"scope": "unifi2mqtt", "kind": "controller_api_key", "identifier": "branch_one"}
)["secret"] == CONTROLLER_VALUE
assert web._reveal_hub_secret(
    {"scope": "unifi2mqtt", "kind": "mqtt_password"}
)["secret"] == UNIFI_MQTT_VALUE

# Normal settings/status payloads stay redacted even though reveal is supported.
discovery_status = json.dumps(web._discovery_settings_status(), sort_keys=True)
snmp_status = json.dumps(web._snmp2mqtt_settings_status(), sort_keys=True)
unifi_status = json.dumps(web._unifi2mqtt_settings_status(), sort_keys=True)
for value in (
    DISCOVERY_VALUE,
    SNMP_VALUE,
    LOCAL_VALUE,
    REMOTE_VALUE,
    CONTROLLER_VALUE,
    UNIFI_MQTT_VALUE,
):
    assert value not in discovery_status
    assert value not in snmp_status
    assert value not in unifi_status

assert web._discovery_settings_status()["secret_policy"]["snmp_community"] == (
    "redacted_default_reveal_on_demand_blank_preserves"
)

for bad in (
    {"scope": "discovery", "kind": "snmp_community", "identifier": "missing"},
    {"scope": "unifi2mqtt", "kind": "controller_api_key", "identifier": "missing"},
    {"scope": "unknown", "kind": "value"},
):
    try:
        web._reveal_hub_secret(bad)
    except (ValueError, RuntimeError):
        pass
    else:
        raise AssertionError(f"invalid reveal request was accepted: {bad}")

source = Path(web.__file__).read_text(encoding="utf-8")
for marker in (
    'if path == "/api/secrets/reveal":',
    "async function fetchSavedSecret(ref)",
    "function secretControl(input,refProvider,configured=false)",
    "className='secret-eye'",
    "function secretInp(v,fn,refProvider,configured,a={})",
    "scope:'discovery',kind:'snmp_community'",
    "scope:'snmp2mqtt',kind:'mqtt_password'",
    "scope:'unifi2mqtt',kind:'local_api_key'",
    "scope:'unifi2mqtt',kind:'remote_api_key'",
    "scope:'unifi2mqtt',kind:'controller_api_key'",
):
    assert marker in source, marker

print("Switch Vision Hub explicit credential reveal/redaction regression: PASS")
