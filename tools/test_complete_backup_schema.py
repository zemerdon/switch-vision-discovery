#!/usr/bin/env python3
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
sys.path.insert(0, str(RUNTIME))

import complete_backup  # noqa: E402


def base_backup() -> dict:
    return {
        "format": complete_backup.COMPLETE_BACKUP_FORMAT,
        "schema_version": complete_backup.COMPLETE_BACKUP_SCHEMA_VERSION,
        "secrets_included": False,
        "components": {
            "core": {"settings": {}},
            "discovery": {
                "settings": {
                    "switches": [],
                    "stack_member_prefixes": [],
                }
            },
            "snmp2mqtt": {"settings": None},
            "unifi2mqtt": {"options": None},
            "installer": {"settings": {}},
        },
        "calibrations": {"profiles": [], "active_profiles": {}},
        "assets": [],
        "device_control": {},
    }


def validate(payload: dict, calls: list[str]) -> dict:
    return complete_backup.validate_complete_backup(
        payload,
        validate_stack_row=lambda _row, _index: calls.append("stack") or {},
        validate_inventory_identities=lambda _settings: calls.append("inventory"),
        calibration_profile_name=lambda value: str(value),
        unifi_secret_fields={"api_key", "mqtt_password"},
        validate_device_control=lambda _control: calls.append("control"),
    )


def main() -> int:
    source = Path(complete_backup.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "import support_web",
        "_supervisor_json",
        "_home_assistant_ws",
        "_home_assistant_service",
        "subprocess.",
    ):
        assert forbidden not in source, forbidden

    calls: list[str] = []
    payload = base_backup()
    result = validate(payload, calls)
    assert result == payload
    assert result is not payload
    assert calls == ["inventory", "control"], calls

    result["components"]["core"]["settings"]["changed"] = True
    assert "changed" not in payload["components"]["core"]["settings"]

    discovery = {
        "settings": {
            "switches": [
                {
                    "switch_name": "SW1",
                    "display_name": "Core",
                    "snmp_community_configured": True,
                }
            ],
            "support_contributor_value_configured": True,
        }
    }
    snmp2mqtt = {"password_configured": True}
    unifi2mqtt = {
        "local_api_key_configured": True,
        "remote_api_key_configured": True,
        "mqtt_password_configured": True,
        "options": {
            "controllers": [{"id": "site2", "api_key_configured": True}],
        },
    }
    requirements = complete_backup.backup_credential_requirements(
        discovery, snmp2mqtt, unifi2mqtt
    )
    kinds = {(row["component"], row["kind"]) for row in requirements}
    assert kinds == {
        ("discovery", "snmp_community"),
        ("discovery", "private_contributor_value"),
        ("snmp2mqtt", "mqtt_password"),
        ("unifi2mqtt", "api_key"),
        ("unifi2mqtt", "mqtt_password"),
        ("unifi2mqtt", "controller_api_key"),
    }, kinds

    bad = base_backup()
    bad["components"]["discovery"]["settings"]["switches"] = [
        {"snmp_community": "secret"}
    ]
    try:
        validate(bad, [])
    except ValueError:
        pass
    else:
        raise AssertionError("backup schema accepted an SNMP community")

    bad = base_backup()
    bad["components"]["unifi2mqtt"]["options"] = {"api_key": "secret"}
    try:
        validate(bad, [])
    except ValueError:
        pass
    else:
        raise AssertionError("backup schema accepted a UniFi API key")

    bad = base_backup()
    bad["secrets_included"] = True
    try:
        validate(bad, [])
    except ValueError:
        pass
    else:
        raise AssertionError("backup schema accepted secrets_included=true")

    print("Discovery complete-backup pure schema contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
