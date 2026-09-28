#!/usr/bin/env python3
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
sys.path.insert(0, str(RUNTIME))

import complete_backup_restore as restore  # noqa: E402


def backup_fixture() -> dict:
    return {
        "format": "switch-vision-complete-backup-v1",
        "components": {
            "core": {"settings": {"sidebar": {"show_panel_in_sidebar": True}}},
            "installer": {
                "installed": True,
                "settings": {"backup_retention": 5},
            },
            "snmp2mqtt": {
                "installed": True,
                "settings": {
                    "mqtt": {"host": "mqtt.local", "password": "must-not-restore"},
                },
            },
            "unifi2mqtt": {
                "installed": True,
                "options": {
                    "poll_interval": "30",
                    "controllers": [
                        {
                            "id": "site2",
                            "name": "Second",
                            "api_key": "must-not-restore",
                            "api_key_configured": True,
                        }
                    ],
                },
            },
            "discovery": {
                "settings": {
                    "autodiscover_networks": ["192.168.10.0/24"],
                    "support_contributor_type": "named",
                    "support_contributor_value_configured": True,
                    "switches": [
                        {
                            "switch_name": "SW1",
                            "switch_host": "192.168.1.2",
                            "snmp_community": "must-not-restore",
                            "snmp_community_configured": True,
                            "original_switch_name": "Legacy",
                        }
                    ],
                    "stack_member_prefixes": [
                        {"switch_name": "SW1", "member": "1", "prefix": "Gi1/0/"}
                    ],
                }
            },
        },
        "assets": [{"filename": "one.png"}],
        "calibrations": {"profiles": [{"profile": "custom"}]},
        "device_control": {
            "schema_version": 2,
            "order": ["snmp:SW1"],
            "states": {"snmp:SW1": "enabled"},
            "added_at": {"snmp:SW1": "2026-09-17T00:00:00.000000Z"},
        },
        "credential_requirements": [
            {"component": "discovery", "kind": "snmp_community", "identifier": "SW1"}
        ],
    }


def main() -> int:
    backup = backup_fixture()
    calls: list[tuple[str, object]] = []
    pending = {
        "discovery_switches": [],
        "discovery_stack_member_prefixes": [],
        "unifi_controllers": [],
    }

    def validate(data):
        calls.append(("validate", data))
        return copy.deepcopy(backup)

    def ws(command, **_kwargs):
        calls.append(("preflight", copy.deepcopy(command)))
        return {"backup_api": 2}

    def save_core(payload):
        calls.append(("core", copy.deepcopy(payload)))

    def assets(_rows):
        calls.append(("assets", None))
        return 1

    def calibrations(_rows):
        calls.append(("calibrations", None))
        return 2

    def installer(payload):
        calls.append(("installer", copy.deepcopy(payload)))

    def snmp(payload):
        calls.append(("snmp2mqtt", copy.deepcopy(payload)))

    def load_pending():
        calls.append(("pending-load", None))
        return copy.deepcopy(pending)

    def unifi(options):
        calls.append(("unifi2mqtt", copy.deepcopy(options)))

    def discovery(payload):
        calls.append(("discovery", copy.deepcopy(payload)))

    saved_pending: list[dict] = []

    def save_pending(payload):
        calls.append(("pending-save", None))
        saved_pending.append(copy.deepcopy(payload))

    def load_control(payload):
        calls.append(("control-load", None))
        return copy.deepcopy(payload)

    saved_control: list[tuple[dict, object]] = []

    def save_control(payload, path):
        calls.append(("control-save", path))
        saved_control.append((copy.deepcopy(payload), path))

    result = restore.restore_complete_backup(
        {"incoming": True},
        backup_format="switch-vision-complete-backup-v1",
        validate_complete_backup=validate,
        home_assistant_ws=ws,
        save_core_settings=save_core,
        restore_core_assets=assets,
        restore_core_calibrations=calibrations,
        save_installer_settings=installer,
        save_snmp2mqtt_settings=snmp,
        load_configuration_restore_pending=load_pending,
        restore_unifi2mqtt_nonsecret=unifi,
        save_discovery_settings=discovery,
        save_configuration_restore_pending=save_pending,
        load_device_control_from_object=load_control,
        save_device_control=save_control,
        device_control_file="device-control.json",
    )

    assert [name for name, _ in calls] == [
        "validate",
        "preflight",
        "core",
        "assets",
        "calibrations",
        "installer",
        "snmp2mqtt",
        "pending-load",
        "unifi2mqtt",
        "discovery",
        "pending-save",
        "control-load",
        "control-save",
    ], calls

    snmp_payload = next(value for name, value in calls if name == "snmp2mqtt")
    assert snmp_payload["settings"]["mqtt"]["password"] == ""
    assert snmp_payload["settings"]["clear_password"] is False

    discovery_payload = next(value for name, value in calls if name == "discovery")
    assert "switches" not in discovery_payload["settings"]
    assert "stack_member_prefixes" not in discovery_payload["settings"]
    assert "support_contributor_type" not in discovery_payload["settings"]
    assert "support_contributor_value" not in discovery_payload["settings"]

    assert len(saved_pending) == 1
    assert saved_pending[0]["discovery_switches"] == [
        {
            "switch_name": "SW1",
            "switch_host": "192.168.1.2",
            "snmp_community": "",
            "snmp_community_configured": False,
            "restore_pending": True,
        }
    ]
    assert saved_pending[0]["discovery_stack_member_prefixes"] == [
        {"switch_name": "SW1", "member": "1", "prefix": "Gi1/0/"}
    ]
    assert saved_pending[0]["unifi_controllers"] == [
        {
            "id": "site2",
            "name": "Second",
            "api_key_configured": False,
            "restore_pending": True,
        }
    ]
    assert saved_control == [(backup["device_control"], "device-control.json")]

    assert result == {
        "imported": True,
        "format": "switch-vision-complete-backup-v1",
        "restored_components": [
            "core",
            "installer",
            "snmp2mqtt",
            "unifi2mqtt",
            "discovery",
        ],
        "asset_count": 1,
        "calibration_profile_count": 2,
        "credential_requirements": backup["credential_requirements"],
        "pending_discovery_switches": 1,
        "pending_discovery_stack_members": 1,
        "pending_unifi_controllers": 1,
        "warnings": [],
        "restart_required": False,
    }

    # Core backup-api preflight must fail before any mutation callback.
    fail_calls: list[str] = []
    try:
        restore.restore_complete_backup(
            backup,
            backup_format="switch-vision-complete-backup-v1",
            validate_complete_backup=lambda data: copy.deepcopy(data),
            home_assistant_ws=lambda _command, **_kwargs: {},
            save_core_settings=lambda _payload: fail_calls.append("core"),
            restore_core_assets=lambda _rows: fail_calls.append("assets") or 0,
            restore_core_calibrations=lambda _rows: fail_calls.append("calibrations") or 0,
            save_installer_settings=lambda _payload: fail_calls.append("installer"),
            save_snmp2mqtt_settings=lambda _payload: fail_calls.append("snmp"),
            load_configuration_restore_pending=lambda: pending,
            restore_unifi2mqtt_nonsecret=lambda _payload: fail_calls.append("unifi"),
            save_discovery_settings=lambda _payload: fail_calls.append("discovery"),
            save_configuration_restore_pending=lambda _payload: fail_calls.append("pending"),
            load_device_control_from_object=lambda payload: payload,
            save_device_control=lambda _payload, _path: fail_calls.append("control"),
            device_control_file="device-control.json",
        )
    except RuntimeError as exc:
        assert "too old" in str(exc).lower()
    else:
        raise AssertionError("restore coordinator did not fail closed on old Core")
    assert fail_calls == [], fail_calls

    # Optional component restore failures remain warnings and do not block the
    # required Discovery/device-control tail of the transaction.
    warning_result = restore.restore_complete_backup(
        backup,
        backup_format="switch-vision-complete-backup-v1",
        validate_complete_backup=lambda data: copy.deepcopy(data),
        home_assistant_ws=lambda _command, **_kwargs: {"backup_api": 2},
        save_core_settings=lambda _payload: None,
        restore_core_assets=lambda _rows: 0,
        restore_core_calibrations=lambda _rows: 0,
        save_installer_settings=lambda _payload: (_ for _ in ()).throw(RuntimeError("installer warning")),
        save_snmp2mqtt_settings=lambda _payload: (_ for _ in ()).throw(RuntimeError("snmp warning")),
        load_configuration_restore_pending=lambda: copy.deepcopy(pending),
        restore_unifi2mqtt_nonsecret=lambda _payload: (_ for _ in ()).throw(RuntimeError("unifi warning")),
        save_discovery_settings=lambda _payload: None,
        save_configuration_restore_pending=lambda _payload: None,
        load_device_control_from_object=lambda payload: copy.deepcopy(payload),
        save_device_control=lambda _payload, _path: None,
        device_control_file="device-control.json",
    )
    assert warning_result["warnings"] == [
        "installer warning",
        "snmp warning",
        "unifi warning",
    ]
    assert warning_result["restored_components"] == ["core", "discovery"]

    print("Discovery complete-backup restore coordinator: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
