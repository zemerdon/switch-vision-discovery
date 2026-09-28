#!/usr/bin/env python3
from __future__ import annotations

import ast
import copy
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
sys.path.insert(0, str(RUNTIME))

import complete_backup_runtime as runtime  # noqa: E402


def main() -> int:
    source = Path(runtime.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert "support_web" not in imported_modules, imported_modules
    for forbidden in ("_supervisor_json", "_home_assistant_service"):
        assert forbidden not in source, forbidden

    calibration_calls: list[dict] = []

    def calibration_ws(command, **_kwargs):
        calibration_calls.append(copy.deepcopy(command))
        if command["type"] == "switch_vision/list_calibrations":
            return {
                "items": [
                    {"profile": "factory", "scope": "factory"},
                    {
                        "profile": "custom_lab",
                        "scope": "custom",
                        "active": True,
                        "base_profile": "WS-C2960X-24PS-L",
                    },
                ]
            }
        assert command == {
            "type": "switch_vision/get_calibration",
            "profile": "custom_lab",
            "exact": True,
        }
        return {"exists": True, "calibration": {"model": "fixture"}}

    calibrations = runtime.core_calibration_backup(
        home_assistant_ws=calibration_ws,
        calibration_profile_name=lambda value: str(value).strip(),
    )
    assert calibrations == {
        "profiles": [
            {"profile": "custom_lab", "calibration": {"model": "fixture"}}
        ],
        "active_profiles": {"WS-C2960X-24PS-L": "custom_lab"},
    }
    assert [row["type"] for row in calibration_calls] == [
        "switch_vision/list_calibrations",
        "switch_vision/get_calibration",
    ]

    asset_calls: list[dict] = []

    def asset_ws(command, **kwargs):
        asset_calls.append({"command": copy.deepcopy(command), "kwargs": dict(kwargs)})
        if command["type"] == "switch_vision/list_assets":
            return {
                "backup_api": 2,
                "custom_logos": ["logo.png"],
                "custom_faceplates": ["custom-faceplate.png"],
            }
        raw = b"abc" if command["filename"] == "logo.png" else b"xyz"
        import base64

        return {
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "content_base64": base64.b64encode(raw).decode("ascii"),
        }

    assets = runtime.core_asset_backup(home_assistant_ws=asset_ws)
    assert [row["filename"] for row in assets] == [
        "logo.png",
        "custom-faceplate.png",
    ]
    assert all(
        call["kwargs"].get("max_size") == 32 * 1024 * 1024
        for call in asset_calls
        if call["command"]["type"] == "switch_vision/get_backup_asset"
    )

    calls: list[str] = []
    core = {"settings": {"sidebar": {"show_panel_in_sidebar": True}}}
    discovery = {
        "settings": {
            "switches": [],
            "stack_member_prefixes": [],
            "support_contributor_value": "",
        }
    }
    snmp = {"installed": True, "settings": {"mqtt": {"password": ""}}}
    unifi = {"installed": True, "options": {"controllers": []}}
    installer = {"installed": True, "settings": {"backup_retention": 5}}
    control = {
        "schema_version": 2,
        "order": ["snmp:SW1"],
        "states": {"snmp:SW1": "enabled"},
        "added_at": {"snmp:SW1": "2026-09-17T00:00:00.000000Z"},
    }

    def status(name, payload):
        def inner():
            calls.append(name)
            return payload

        return inner

    def snapshot(path):
        calls.append(f"snapshot:{path}")
        return {"ok": True}

    def load_control(path):
        calls.append(f"control:{path}")
        return control

    def calibration_backup():
        calls.append("calibrations")
        return calibrations

    def asset_backup():
        calls.append("assets")
        return assets

    def requirements(_discovery, _snmp, _unifi):
        calls.append("requirements")
        return [{"component": "snmp2mqtt", "kind": "mqtt_password", "identifier": "MQTT"}]

    def validate(payload):
        calls.append("validate")
        assert payload["secrets_included"] is False
        assert payload["format"] == "switch-vision-complete-backup-v1"
        return copy.deepcopy(payload)

    payload = runtime.export_complete_backup(
        "3.0.9",
        backup_format="switch-vision-complete-backup-v1",
        schema_version=1,
        core_settings_status=status("core", core),
        discovery_settings_status=status("discovery", discovery),
        snmp2mqtt_settings_status=status("snmp2mqtt", snmp),
        unifi2mqtt_settings_status=status("unifi2mqtt", unifi),
        installer_settings_status=status("installer", installer),
        configured_devices_snapshot=snapshot,
        options_file="options.json",
        load_device_control=load_control,
        device_control_file="device-control.json",
        core_calibration_backup=calibration_backup,
        core_asset_backup=asset_backup,
        credential_requirements=requirements,
        validate_complete_backup=validate,
        exported_at="2026-09-28T00:00:00+0000",
    )
    assert calls == [
        "core",
        "discovery",
        "snmp2mqtt",
        "unifi2mqtt",
        "installer",
        "snapshot:options.json",
        "control:device-control.json",
        "calibrations",
        "assets",
        "requirements",
        "validate",
    ], calls
    assert payload["exported_at"] == "2026-09-28T00:00:00+0000"
    assert payload["switch_vision_discovery_version"] == "3.0.9"
    assert payload["components"]["core"]["settings"] == core["settings"]
    assert payload["components"]["discovery"]["settings"] == discovery["settings"]
    assert payload["device_control"] == control
    assert payload["calibrations"] == calibrations
    assert payload["assets"] == assets

    payload["components"]["core"]["settings"]["sidebar"]["show_panel_in_sidebar"] = False
    assert core["settings"]["sidebar"]["show_panel_in_sidebar"] is True
    payload["device_control"]["states"]["snmp:SW1"] = "disabled"
    assert control["states"]["snmp:SW1"] == "enabled"

    print("Discovery complete-backup runtime export service: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
