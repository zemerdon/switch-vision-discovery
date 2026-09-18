#!/usr/bin/env python3
"""Regression for whole-stack, explicitly non-secret configuration backup."""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import device_control
import support_web as web

SECRET_VALUES = {
    "private-community",
    "snmp-mqtt-password",
    "local-api-key",
    "remote-api-key",
    "controller-api-key",
    "unifi-mqtt-password",
    "private-contributor",
}

originals = {}
for name in (
    "_core_settings_status", "_discovery_settings_status", "_snmp2mqtt_settings_status",
    "_unifi2mqtt_settings_status", "_installer_settings_status", "_configured_devices_snapshot",
    "_core_calibration_backup", "_core_asset_backup", "_home_assistant_ws",
    "_save_core_settings", "_restore_core_assets", "_restore_core_calibrations",
    "_save_installer_settings", "_save_snmp2mqtt_settings", "_restore_unifi2mqtt_nonsecret",
    "_save_discovery_settings",
):
    originals[name] = getattr(web, name)
original_control = web.DEFAULT_DEVICE_CONTROL
original_pending = web.DEFAULT_CONFIGURATION_RESTORE_PENDING

try:
    with tempfile.TemporaryDirectory(prefix="sv-complete-backup-") as tmp:
        web.DEFAULT_DEVICE_CONTROL = Path(tmp) / "device-control.json"
        web.DEFAULT_CONFIGURATION_RESTORE_PENDING = Path(tmp) / "configuration-restore-pending.json"
        device_control.save({
            "schema_version": 2,
            "order": ["snmp:SW1", "unifi:u1"],
            "states": {"snmp:SW1": "enabled", "unifi:u1": "disabled"},
            "added_at": {
                "snmp:SW1": "2026-09-17T00:00:00.000000Z",
                "unifi:u1": "2026-09-17T00:00:01.000000Z",
            },
        }, web.DEFAULT_DEVICE_CONTROL)
        web._core_settings_status = lambda: {"settings": {"sidebar": {"show_panel_in_sidebar": True}}}
        web._discovery_settings_status = lambda: {"settings": {
            "run_snmp_walks": "true",
            "enable_switch_list": "true",
            "switches": [{
                "switch_name": "SW1", "display_name": "Core", "switch_host": "192.0.2.10",
                "sensor_prefix": "sw1", "snmp_community": "", "snmp_community_configured": True,
                "enabled": "enabled", "walk_mode": "targeted", "switch_model": "auto",
                "original_switch_name": "SW1",
            }],
            "stack_member_prefixes": [{
                "switch_name": "SW1", "member": "1", "display_name": "Core member 1",
                "sensor_prefix": "sw1", "card_header_title": "Core",
            }],
            "support_contributor_type": "forum",
            "support_contributor_value": "",
            "support_contributor_value_configured": True,
        }}
        web._snmp2mqtt_settings_status = lambda: {
            "installed": True, "password_configured": True,
            "settings": {"mqtt": {"host": "core-mosquitto", "port": 1883, "username": "u", "password": ""},
                         "targets_path": "/config/app_configs/switch_vision_snmp2mqtt/targets.yaml",
                         "use_switch_vision_generated_yaml": True,
                         "switch_vision_generated_yaml_path": "/share/switch_vision/generated-snmp2mqtt.yaml",
                         "imported_targets_path": "/config/app_configs/switch_vision_snmp2mqtt/imported/generated-snmp2mqtt.yaml",
                         "backup_existing_config": False, "homeassistant": {"discovery": True, "prefix": "homeassistant"},
                         "clear_password": False},
        }
        web._unifi2mqtt_settings_status = lambda: {
            "installed": True,
            "local_api_key_configured": True,
            "remote_api_key_configured": True,
            "mqtt_password_configured": True,
            "options": {
                "priority_transport": "local", "fallback_transport": "remote",
                "local_controller_url": "https://192.0.2.20:11443", "local_site_id": "auto",
                "local_verify_ssl": False, "local_allow_insecure_http": False,
                "remote_host_id": "host", "remote_site_id": "auto",
                "controllers": [{"id": "site2", "transport": "remote", "host_id": "host2", "site_id": "auto",
                                 "controller_url": "", "verify_ssl": True, "allow_insecure_http": False,
                                 "api_key_configured": True}],
                "poll_interval": "30", "mqtt_host": "core-mosquitto", "mqtt_port": "1883",
                "mqtt_username": "u", "mqtt_tls": "false", "mqtt_verify_ssl": "true", "mqtt_ca": "",
                "mqtt_topic_prefix": "switch_vision/unifi", "mqtt_discovery_prefix": "homeassistant",
            },
        }
        web._installer_settings_status = lambda: {"installed": True, "settings": {"preserve_custom_assets": True, "backup_retention": 5}}
        web._configured_devices_snapshot = lambda _path: {"ok": True}
        web._core_calibration_backup = lambda: {"profiles": [{"profile": "custom_lab", "calibration": {"model": "fixture"}}], "active_profiles": {}}

        # Core owns the stock/custom distinction. Discovery must fetch only files
        # Core marks custom; stock release assets are recreated by Core install.
        asset_calls = []
        def asset_ws(command, **_kwargs):
            asset_calls.append(copy.deepcopy(command))
            if command["type"] == "switch_vision/list_assets":
                return {
                    "backup_api": 2,
                    "logos": ["sv-logo.png", "logo.png"],
                    "faceplates": ["24rj45-4sfp.png", "custom-faceplate.png"],
                    "custom_logos": ["logo.png"],
                    "custom_faceplates": ["custom-faceplate.png"],
                }
            name = command["filename"]
            raw = b"abc" if name == "logo.png" else b"xyz"
            import base64, hashlib
            return {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "content_base64": base64.b64encode(raw).decode("ascii")}
        web._home_assistant_ws = asset_ws
        custom_assets = web._core_asset_backup()
        assert [row["filename"] for row in custom_assets] == ["logo.png", "custom-faceplate.png"], custom_assets
        requested_assets = [row["filename"] for row in asset_calls if row.get("type") == "switch_vision/get_backup_asset"]
        assert requested_assets == ["logo.png", "custom-faceplate.png"], requested_assets
        assert "sv-logo.png" not in requested_assets
        assert "24rj45-4sfp.png" not in requested_assets

        web._core_asset_backup = lambda: [{"kind": "logos", "filename": "logo.png", "size": 3,
                                            "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", "content_base64": "YWJj"}]

        backup = web._switch_vision_backup_export("2.4.31")
        encoded = json.dumps(backup, sort_keys=True)
        assert backup["format"] == web.COMPLETE_BACKUP_FORMAT
        assert backup["secrets_included"] is False
        assert set(backup["components"]) == {"core", "discovery", "snmp2mqtt", "unifi2mqtt", "installer"}
        assert backup["device_control"]["added_at"]["snmp:SW1"].startswith("2026-09-17")
        assert backup["calibrations"]["profiles"][0]["profile"] == "custom_lab"
        assert backup["assets"][0]["filename"] == "logo.png"
        for secret in SECRET_VALUES:
            assert secret not in encoded
        kinds = {(r["component"], r["kind"]) for r in backup["credential_requirements"]}
        assert ("discovery", "snmp_community") in kinds
        assert ("snmp2mqtt", "mqtt_password") in kinds
        assert ("unifi2mqtt", "api_key") in kinds
        assert ("unifi2mqtt", "controller_api_key") in kinds
        assert ("discovery", "private_contributor_value") in kinds

        # Fail closed if a future change accidentally places a secret in the portable bundle.
        bad = copy.deepcopy(backup)
        bad["components"]["discovery"]["settings"]["switches"][0]["snmp_community"] = "private-community"
        try:
            web._validate_complete_backup(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("backup validator accepted an SNMP community")

        bad = copy.deepcopy(backup)
        bad["components"]["snmp2mqtt"]["settings"]["mqtt"]["password"] = "snmp-mqtt-password"
        try:
            web._validate_complete_backup(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("backup validator accepted an MQTT password")

        bad = copy.deepcopy(backup)
        bad["assets"][0]["content_base64"] = "ZGVm"
        try:
            web._validate_complete_backup(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("backup validator accepted asset content with the wrong SHA-256")

        # Restore is preflighted against the coordinated Core API before any
        # component mutation and recreates secret-dependent structures as
        # pending rows rather than smuggling credentials into the backup.
        calls: list[tuple[str, object]] = []
        web._home_assistant_ws = lambda command, **_kwargs: (
            calls.append(("core-preflight", copy.deepcopy(command)))
            or {"backup_api": 2}
        )
        web._save_core_settings = lambda payload: calls.append(("core", copy.deepcopy(payload))) or {}
        web._restore_core_assets = lambda assets: calls.append(("assets", copy.deepcopy(assets))) or len(assets)
        web._restore_core_calibrations = lambda data: calls.append(("calibrations", copy.deepcopy(data))) or len(data["profiles"])
        web._save_installer_settings = lambda settings: calls.append(("installer", copy.deepcopy(settings))) or {}
        web._save_snmp2mqtt_settings = lambda payload: calls.append(("snmp2mqtt", copy.deepcopy(payload))) or {}
        web._restore_unifi2mqtt_nonsecret = lambda options: calls.append(("unifi2mqtt", copy.deepcopy(options)))
        web._save_discovery_settings = lambda payload: calls.append(("discovery", copy.deepcopy(payload))) or {}
        restored = web._restore_complete_backup(backup)
        assert restored["imported"] is True
        assert calls[0][0] == "core-preflight", calls
        pending = web._load_configuration_restore_pending()
        assert len(pending["discovery_switches"]) == 1, pending
        assert pending["discovery_switches"][0]["switch_name"] == "SW1"
        assert pending["discovery_switches"][0]["snmp_community"] == ""
        assert pending["discovery_switches"][0]["restore_pending"] is True
        assert len(pending["discovery_stack_member_prefixes"]) == 1, pending
        assert pending["discovery_stack_member_prefixes"][0]["switch_name"] == "SW1"
        assert pending["discovery_stack_member_prefixes"][0]["member"] == "1"
        assert restored["pending_discovery_stack_members"] == 1
        assert len(pending["unifi_controllers"]) == 1, pending
        assert "api_key" not in pending["unifi_controllers"][0]
        assert pending["unifi_controllers"][0]["restore_pending"] is True
        snmp_payload = next(value for name, value in calls if name == "snmp2mqtt")
        assert snmp_payload["settings"]["mqtt"]["password"] == ""
        discovery_payload = next(value for name, value in calls if name == "discovery")
        assert "switches" not in discovery_payload["settings"]
        assert "stack_member_prefixes" not in discovery_payload["settings"]
        assert "support_contributor_value" not in discovery_payload["settings"]
        restored_control = device_control.load(web.DEFAULT_DEVICE_CONTROL)
        assert restored_control["added_at"] == backup["device_control"]["added_at"]

        # Switches-only transfer is deliberately narrow and non-secret.
        switch_export = web._switches_export("2.4.38")
        assert switch_export["format"] == web.SWITCHES_EXPORT_FORMAT
        assert switch_export["secrets_included"] is False
        assert len(switch_export["switches"]) == 1
        assert len(switch_export["stack_member_prefixes"]) == 1
        assert switch_export["switches"][0]["switch_name"] == "SW1"
        assert switch_export["stack_member_prefixes"][0]["switch_name"] == "SW1"
        switch_encoded = json.dumps(switch_export, sort_keys=True)
        assert "snmp_community" not in switch_encoded
        assert "private-community" not in switch_encoded
        assert "run_snmp_walks" not in switch_encoded
        web.DEFAULT_CONFIGURATION_RESTORE_PENDING.unlink(missing_ok=True)
        imported_switches = web._import_switches_only(switch_export)
        assert imported_switches["switch_count"] == 1
        assert imported_switches["stack_member_count"] == 1
        pending = web._load_configuration_restore_pending()
        assert pending["discovery_switches"][0]["restore_pending"] is True
        assert pending["discovery_switches"][0]["snmp_community"] == ""
        assert pending["discovery_stack_member_prefixes"][0]["member"] == "1"

        # An old Core aborts before any restore side effect.
        side_effects: list[str] = []
        web._home_assistant_ws = lambda _command, **_kwargs: {}
        web._save_core_settings = lambda _payload: side_effects.append("core") or {}
        try:
            web._restore_complete_backup(backup)
        except RuntimeError as exc:
            assert "too old" in str(exc).lower()
        else:
            raise AssertionError("complete restore did not fail closed against old Core")
        assert side_effects == []
finally:
    for name, value in originals.items():
        setattr(web, name, value)
    web.DEFAULT_DEVICE_CONTROL = original_control
    web.DEFAULT_CONFIGURATION_RESTORE_PENDING = original_pending

source = Path(web.__file__).read_text(encoding="utf-8")
for marker in (
    'COMPLETE_BACKUP_FORMAT = "switch-vision-complete-backup-v1"',
    '/download/switch-vision-backup.json',
    'Export Complete Backup',
    'Credentials are deliberately excluded.',
    'pending_discovery_switches',
    'pending_discovery_stack_members',
    'pending_unifi_controllers',
    'switch_vision/get_backup_asset',
    'switch_vision/put_backup_asset',
    'listing.get(f"custom_{kind}")',
    'int(listing.get("backup_api") or 0) < 2',
    'SWITCHES_EXPORT_FORMAT = "switch-vision-switch-configuration-v1"',
    '/download/switch-vision-switch-configuration.json',
    '/api/switches/import',
    'async function importSwitchesConfiguration()',
    "$('importSwitchesButton').addEventListener('click',importSwitchesConfiguration)",
    'data-maintenance-tab="configuration"',
    'data-maintenance-tab="calibrations"',
    'Configuration Import / Export',
    'id="calibrationProfilesRoot"',
    'id="hubDeviceConfiguration"',
    'Add / Remove Devices',
):
    assert marker in source, marker

assert 'id="openConfigurationButton"' not in source
assert 'id="openCalibrationProfilesButton"' not in source

print("Switch Vision complete non-secret configuration backup regression: PASS")
