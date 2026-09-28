#!/usr/bin/env python3
"""Permanent contract tests for extracted Core/SNMP2MQTT Hub settings logic."""
from __future__ import annotations

import copy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

import hub_component_settings as settings


def plain_text(value, field, *, max_length, allow_empty=True):
    text = str(value if value is not None else "")
    if "\x00" in text or "\r" in text or "\n" in text:
        raise ValueError(f"{field} contains invalid control characters.")
    if len(text) > max_length:
        raise ValueError(f"{field} is too long.")
    if not allow_empty and not text:
        raise ValueError(f"{field} cannot be empty.")
    return text


def test_core_settings_contract() -> None:
    calls = []

    def ws(command):
        calls.append(copy.deepcopy(command))
        if command["type"] == "switch_vision/get_settings":
            return {"settings": {"sidebar": {"show_panel_in_sidebar": True}}}
        return {"settings": {"sidebar": {"show_panel_in_sidebar": False}}}

    assert settings.core_settings_status(home_assistant_ws=ws)["settings"]
    result = settings.save_core_settings(
        {"settings": {"sidebar": {"show_panel_in_sidebar": False}}},
        home_assistant_ws=ws,
    )
    assert result["settings"]["sidebar"]["show_panel_in_sidebar"] is False
    assert calls[-1] == {
        "type": "switch_vision/set_settings",
        "reset_to_defaults": False,
        "settings": {"sidebar": {"show_panel_in_sidebar": False}},
    }


def test_snmp2mqtt_status_redacts_secret() -> None:
    secret = "never-return-this"
    status = settings.snmp2mqtt_settings_status(
        snmp2mqtt_addon_options=lambda: (
            "switch_vision_snmp2mqtt",
            "started",
            {
                "mqtt": {
                    "host": "core-mosquitto",
                    "port": 1883,
                    "username": "user",
                    "password": secret,
                }
            },
        )
    )
    assert status["password_configured"] is True
    assert status["settings"]["mqtt"]["password"] == ""
    assert secret not in repr(status)


def test_snmp2mqtt_save_preserves_secret_and_future_options() -> None:
    state = {
        "options": {
            "mqtt": {
                "host": "mqtt-old",
                "port": 1883,
                "username": "user",
                "password": "broker-secret",
                "base_topic": "snmp2mqtt",
            },
            "targets_path": "/config/app_configs/switch_vision_snmp2mqtt/targets.yaml",
            "use_switch_vision_generated_yaml": True,
            "switch_vision_generated_yaml_path": "/share/switch_vision/generated-snmp2mqtt.yaml",
            "imported_targets_path": "/config/app_configs/switch_vision_snmp2mqtt/imported/generated-snmp2mqtt.yaml",
            "backup_existing_config": False,
            "homeassistant": {"discovery": False, "prefix": "legacy"},
            "future_option": {"keep": True},
        }
    }
    calls = []

    def addon_options():
        return "switch_vision_snmp2mqtt", "started", copy.deepcopy(state["options"])

    def supervisor(path, *, method="GET", timeout=12.0, payload=None):
        calls.append((path, method))
        if path.endswith("/options"):
            state["options"] = copy.deepcopy(payload["options"])
        return {}

    request = {
        "mqtt": {
            "host": "mqtt-new",
            "port": 1883,
            "username": "user",
            "password": "",
        },
        "targets_path": "/config/app_configs/switch_vision_snmp2mqtt/targets.yaml",
        "use_switch_vision_generated_yaml": True,
        "switch_vision_generated_yaml_path": "/share/switch_vision/generated-snmp2mqtt.yaml",
        "imported_targets_path": "/config/app_configs/switch_vision_snmp2mqtt/imported/generated-snmp2mqtt.yaml",
        "backup_existing_config": False,
        "homeassistant": {"discovery": True, "prefix": "homeassistant"},
        "clear_password": False,
    }

    result = settings.save_snmp2mqtt_settings(
        {"settings": request},
        snmp2mqtt_addon_options=addon_options,
        supervisor_json=supervisor,
        plain_text=plain_text,
        settings_status=lambda: settings.snmp2mqtt_settings_status(
            snmp2mqtt_addon_options=addon_options
        ),
    )
    assert result["saved"] is True
    assert result["changed"] is True
    assert result["restart_requested"] is True
    assert state["options"]["mqtt"]["password"] == "broker-secret"
    assert state["options"]["future_option"] == {"keep": True}
    assert state["options"]["homeassistant"] == {
        "discovery": True,
        "prefix": "homeassistant",
    }
    assert any(path.endswith("/options") for path, _ in calls)
    assert any(path.endswith("/restart") for path, _ in calls)


def test_path_and_discovery_policy_fail_closed() -> None:
    assert settings.hub_app_path(
        "/share/switch_vision/generated-snmp2mqtt.yaml",
        "generated",
        plain_text=plain_text,
    ).startswith("/share/")
    for bad in ("/etc/passwd", "/share/switch_vision/../escape", "relative/path"):
        try:
            settings.hub_app_path(bad, "generated", plain_text=plain_text)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe Hub app path accepted: {bad}")

    current = {
        "mqtt": {"host": "", "port": 1883, "username": "", "password": ""},
        "targets_path": "/config/app_configs/switch_vision_snmp2mqtt/targets.yaml",
        "use_switch_vision_generated_yaml": True,
        "switch_vision_generated_yaml_path": "/share/switch_vision/generated-snmp2mqtt.yaml",
        "imported_targets_path": "/config/app_configs/switch_vision_snmp2mqtt/imported/generated-snmp2mqtt.yaml",
        "backup_existing_config": False,
        "homeassistant": {"discovery": True, "prefix": "homeassistant"},
    }
    request = {
        "settings": {
            "mqtt": {"host": "", "port": 1883, "username": "", "password": ""},
            "targets_path": current["targets_path"],
            "use_switch_vision_generated_yaml": True,
            "switch_vision_generated_yaml_path": current["switch_vision_generated_yaml_path"],
            "imported_targets_path": current["imported_targets_path"],
            "backup_existing_config": False,
            "homeassistant": {"discovery": False, "prefix": "wrong"},
            "clear_password": False,
        }
    }
    try:
        settings.save_snmp2mqtt_settings(
            request,
            snmp2mqtt_addon_options=lambda: ("slug", "started", copy.deepcopy(current)),
            supervisor_json=lambda *_args, **_kwargs: {},
            plain_text=plain_text,
            settings_status=lambda: {},
        )
    except ValueError:
        pass
    else:
        raise AssertionError("noncanonical Home Assistant discovery settings were accepted")


def test_module_boundary() -> None:
    source = (RUNTIME / "hub_component_settings.py").read_text(encoding="utf-8")
    import re

    assert re.search(r"(?m)^\s*import\s+support_web\b", source) is None
    assert re.search(r"(?m)^\s*from\s+support_web\b", source) is None


def main() -> int:
    test_core_settings_contract()
    test_snmp2mqtt_status_redacts_secret()
    test_snmp2mqtt_save_preserves_secret_and_future_options()
    test_path_and_discovery_policy_fail_closed()
    test_module_boundary()
    print("Switch Vision Hub component settings module contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
