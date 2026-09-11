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



def test_connection_test_local_remote_and_redaction() -> None:
    current = current_options()
    original_current = support_web._unifi2mqtt_current_options
    original_get = support_web._unifi_test_get_json
    support_web._unifi2mqtt_current_options = lambda: ("test-slug", current)
    calls: list[tuple[str, str, bool]] = []

    def fake_get(url: str, api_key: str, *, verify_ssl: bool, timeout: float = 12.0):
        calls.append((url, api_key, verify_ssl))
        if url.endswith("/v1/hosts?pageSize=100"):
            return {"data": [{"id": "console-1", "type": "console", "isBlocked": False}]}
        if url.endswith("/proxy/network/integration/v1/sites"):
            return {"data": [{"id": "site-1", "name": "default", "internalReference": "default"}]}
        if url.endswith("/proxy/network/integration/v1/sites/site-1/devices"):
            return {"data": [{"id": "dev-1"}, {"id": "dev-2"}]}
        raise AssertionError(url)

    support_web._unifi_test_get_json = fake_get
    try:
        local = support_web._test_unifi2mqtt_connection({
            "transport": "local",
            "controller_url": "https://10.0.0.1:11443",
            "site_id": "auto",
            "api_key": "",
            "verify_ssl": False,
            "allow_insecure_http": False,
        })
        assert local["ok"] is True, local
        assert local["device_count"] == 2, local
        assert local["site_id"] == "site-1", local
        assert calls[0][1] == "private-local-key", calls
        assert calls[0][2] is False, calls

        calls.clear()
        remote = support_web._test_unifi2mqtt_connection({
            "transport": "remote",
            "host_id": "auto",
            "site_id": "auto",
            "api_key": "",
        })
        assert remote["ok"] is True, remote
        assert remote["host_id"] == "console-1", remote
        assert remote["device_count"] == 2, remote
        assert calls[0][1] == "private-remote-key", calls
        assert all(call[2] is True for call in calls), calls

        secret = "typed-secret-value"
        def failing_get(url: str, api_key: str, *, verify_ssl: bool, timeout: float = 12.0):
            raise RuntimeError(f"authentication|HTTP 403 rejected credential {secret}")
        support_web._unifi_test_get_json = failing_get
        failed = support_web._test_unifi2mqtt_connection({
            "transport": "local",
            "controller_url": "https://10.0.0.1:11443",
            "site_id": "auto",
            "api_key": secret,
            "verify_ssl": True,
            "allow_insecure_http": False,
        })
        assert failed["ok"] is False, failed
        assert failed["stage"] == "authentication", failed
        serialized = repr(failed)
        assert secret not in serialized, serialized
        assert "[redacted]" in serialized, serialized
    finally:
        support_web._unifi2mqtt_current_options = original_current
        support_web._unifi_test_get_json = original_get


def test_connection_test_ui_contract() -> None:
    source = (RUNTIME / "support_web.py").read_text(encoding="utf-8")
    for marker in (
        'id="testUnifiLocalButton"',
        'id="testUnifiRemoteButton"',
        'id="unifiConnectionTestDebug"',
        'id="unifiConnectionTestDebugLog"',
        'id="clearUnifiConnectionTestDebugButton"',
        "function testUnifiConnection(transport)",
        "function appendUnifiConnectionTestDebug(result)",
        "endpoint('api/unifi2mqtt/test-connection')",
        'if path == "/api/unifi2mqtt/test-connection":',
        '.unifi-test-debug pre{display:block!important;max-height:280px;overflow:auto',
    ):
        assert marker in source, marker
    # Collapsed by default: the details element must not carry the open attribute.
    assert '<details id="unifiConnectionTestDebug" class="yaml-manager unifi-test-debug" open' not in source

def main() -> int:
    test_bridge_is_compatibility_only()
    test_browser_controller_rows_redact_nested_secrets()
    test_blank_top_level_secrets_preserve_both_profiles()
    test_browser_can_edit_controller_list_and_preserve_keys()
    test_connection_test_local_remote_and_redaction()
    test_connection_test_ui_contract()
    test_native_hub_contract_has_no_legacy_restriction()
    print("UniFi native Hub configuration regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
