#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
sys.path.insert(0, str(RUNTIME))

import support_web  # noqa: E402
import unifi_multi_controller_bridge as bridge  # noqa: E402


def current_options() -> dict:
    return {
        **support_web.UNIFI2MQTT_DEFAULT_OPTIONS,
        "local_api_key": "private-local-key",
        "remote_api_key": "private-remote-key",
        "mqtt_password": "private-mqtt-password",
        "controllers": [
            {
                "id": "home",
                "transport": "local",
                "controller_url": "https://10.0.0.1:11443",
                "host_id": "auto",
                "site_id": "auto",
                "api_key": "private-home-key",
                "verify_ssl": "false",
                "allow_insecure_http": "false",
            },
            {
                "id": "cloud",
                "transport": "remote",
                "controller_url": "",
                "host_id": "console-1",
                "site_id": "auto",
                "api_key": "private-cloud-key",
                "verify_ssl": "true",
                "allow_insecure_http": "false",
            },
        ],
    }


def test_bridge_is_compatibility_only() -> None:
    module = SimpleNamespace()
    bridge.install(module)
    assert module._sv_unifi_multi_controller_bridge_installed is True
    assert bridge._PAGE_PATCHES == ()


def test_browser_controller_rows_redact_nested_secrets() -> None:
    rows = support_web._unifi_controller_browser_rows(current_options())
    assert len(rows) == 2
    assert rows[0]["api_key_configured"] is True
    assert rows[1]["transport"] == "remote"
    serialized = repr(rows)
    for secret in ("private-home-key", "private-cloud-key"):
        assert secret not in serialized


def test_blank_top_level_secrets_preserve_both_profiles() -> None:
    current = current_options()
    result = support_web._validate_unifi2mqtt_options(
        {
            "priority_transport": "local",
            "fallback_transport": "remote",
            "local_controller_url": "https://10.0.0.2:11443",
            "local_site_id": "auto",
            "local_api_key": "",
            "remote_host_id": "console-2",
            "remote_site_id": "auto",
            "remote_api_key": "",
            "mqtt_password": "",
            "mqtt_host": "core-mosquitto",
            "mqtt_port": "1883",
            "mqtt_topic_prefix": "switch_vision/unifi",
            "mqtt_discovery_prefix": "homeassistant",
        },
        current,
    )
    assert result["local_api_key"] == "private-local-key"
    assert result["remote_api_key"] == "private-remote-key"
    assert result["mqtt_password"] == "private-mqtt-password"
    assert result["priority_transport"] == "local"
    assert result["fallback_transport"] == "remote"
    assert result["local_controller_url"].endswith(":11443")


def test_browser_can_edit_controller_list_and_preserve_keys() -> None:
    current = current_options()
    result = support_web._validate_unifi2mqtt_options(
        {
            "controllers": [
                {
                    "id": "home",
                    "transport": "local",
                    "controller_url": "https://10.0.0.9:11443",
                    "site_id": "auto",
                    "api_key": "",
                    "verify_ssl": False,
                    "allow_insecure_http": False,
                },
                {
                    "id": "cloud",
                    "transport": "remote",
                    "host_id": "console-9",
                    "site_id": "auto",
                    "api_key": "",
                },
            ],
            "mqtt_host": "core-mosquitto",
            "mqtt_port": "1883",
            "mqtt_topic_prefix": "switch_vision/unifi",
            "mqtt_discovery_prefix": "homeassistant",
        },
        current,
    )
    assert result["controllers"][0]["api_key"] == "private-home-key"
    assert result["controllers"][1]["api_key"] == "private-cloud-key"
    assert result["controllers"][0]["controller_url"] == "https://10.0.0.9:11443"
    assert result["controllers"][1]["host_id"] == "console-9"

    removed = support_web._validate_unifi2mqtt_options(
        {
            "controllers": [
                {
                    "id": "home",
                    "transport": "local",
                    "controller_url": "https://10.0.0.9:11443",
                    "site_id": "auto",
                    "api_key": "",
                    "verify_ssl": False,
                    "allow_insecure_http": False,
                }
            ],
            "mqtt_host": "core-mosquitto",
            "mqtt_port": "1883",
            "mqtt_topic_prefix": "switch_vision/unifi",
            "mqtt_discovery_prefix": "homeassistant",
        },
        current,
    )
    assert [row["id"] for row in removed["controllers"]] == ["home"]


def test_native_hub_contract_has_no_legacy_restriction() -> None:
    source = (RUNTIME / "support_web.py").read_text(encoding="utf-8")
    assert "Controller lists and per-controller API keys must be managed" not in source
    assert '"local_api_key_configured"' in source
    assert '"remote_api_key_configured"' in source
    assert '"controller_credentials_configured"' in source
    assert "https://192.168.1.1:11443" in source


def main() -> int:
    test_bridge_is_compatibility_only()
    test_browser_controller_rows_redact_nested_secrets()
    test_blank_top_level_secrets_preserve_both_profiles()
    test_browser_can_edit_controller_list_and_preserve_keys()
    test_native_hub_contract_has_no_legacy_restriction()
    print("UniFi native Hub configuration regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
