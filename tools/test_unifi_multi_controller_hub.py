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


def _fake_module() -> SimpleNamespace:
    page = "\n".join(old for old, _new in bridge._PAGE_PATCHES)

    def status():
        return {
            "installed": True,
            "options": {
                "controller_url": "https://192.168.1.1",
                "site_id": "auto",
                "mqtt_host": "core-mosquitto",
                "controllers": [
                    {
                        "id": "branch-office",
                        "controller_url": "https://10.20.0.1",
                        "site_id": "Branch Office",
                        "api_key": "private-controller-key",
                    },
                    {
                        "id": "home",
                        "controller_url": "https://10.0.0.1",
                        "site_id": "auto",
                        "api_key": "private-home-key",
                    },
                ],
            },
            "api_key_configured": False,
        }

    def validate(data, current):
        result = dict(current)
        if not str(result.get("api_key") or "").strip():
            raise ValueError("legacy API key required")
        if isinstance(data, dict):
            for key in ("poll_interval", "mqtt_host", "api_key"):
                if key in data and data[key] not in (None, ""):
                    result[key] = data[key]
        return result

    return SimpleNamespace(
        _PAGE=page,
        _unifi2mqtt_settings_status=status,
        _validate_unifi2mqtt_options=validate,
    )


def test_page_patch_matches_current_hub() -> None:
    patched = bridge._patch_page(support_web._PAGE)
    assert "d?.multi_controller_enabled" in patched
    assert "Managed in Home Assistant App configuration" in patched
    assert "Multi-controller mode is active." in patched
    for old, _new in bridge._PAGE_PATCHES:
        assert old not in patched


def test_status_redacts_nested_controller_secrets() -> None:
    module = _fake_module()
    bridge.install(module)
    result = module._unifi2mqtt_settings_status()

    assert result["multi_controller_enabled"] is True
    assert result["controller_count"] == 2
    assert result["controller_credentials_configured"] is True
    assert result["api_key_configured"] is True
    assert result["legacy_api_key_configured"] is False
    assert "controllers" not in result["options"]

    serialized = repr(result)
    assert "private-controller-key" not in serialized
    assert "private-home-key" not in serialized
    assert "Branch Office" not in serialized
    assert "10.20.0.1" not in serialized


def test_global_save_preserves_multi_controller_credentials() -> None:
    module = _fake_module()
    bridge.install(module)
    current = {
        "controller_url": "https://192.168.1.1",
        "site_id": "auto",
        "api_key": "",
        "mqtt_host": "core-mosquitto",
        "poll_interval": "30",
        "controllers": [
            {
                "id": "home",
                "controller_url": "https://10.0.0.1",
                "site_id": "auto",
                "api_key": "private-home-key",
            }
        ],
    }

    result = module._validate_unifi2mqtt_options(
        {"poll_interval": "45"},
        current,
    )
    assert result["poll_interval"] == "45"
    assert result["controllers"] == current["controllers"]
    assert result.get("api_key", "") == ""
    assert bridge._SENTINEL_API_KEY not in repr(result)


def test_browser_cannot_replace_controller_list() -> None:
    module = _fake_module()
    bridge.install(module)
    current = {
        "api_key": "",
        "controllers": [
            {
                "id": "home",
                "controller_url": "https://10.0.0.1",
                "api_key": "private-home-key",
            }
        ],
    }
    try:
        module._validate_unifi2mqtt_options(
            {"controllers": []},
            current,
        )
    except ValueError as exc:
        assert "Home Assistant App configuration" in str(exc)
    else:
        raise AssertionError("Hub accepted a controller-list mutation")


def test_incomplete_multi_controller_config_fails_closed() -> None:
    module = _fake_module()
    bridge.install(module)
    current = {
        "api_key": "",
        "controllers": [
            {
                "id": "home",
                "controller_url": "https://10.0.0.1",
                "api_key": "",
            }
        ],
    }
    try:
        module._validate_unifi2mqtt_options(
            {"poll_interval": "45"},
            current,
        )
    except ValueError as exc:
        assert "incomplete" in str(exc).lower()
    else:
        raise AssertionError("incomplete controller credentials were accepted")


def main() -> int:
    test_page_patch_matches_current_hub()
    test_status_redacts_nested_controller_secrets()
    test_global_save_preserves_multi_controller_credentials()
    test_browser_cannot_replace_controller_list()
    test_incomplete_multi_controller_config_fails_closed()
    print("UniFi multi-controller Hub regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
