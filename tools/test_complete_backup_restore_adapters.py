#!/usr/bin/env python3
from __future__ import annotations

import ast
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
sys.path.insert(0, str(RUNTIME))

import complete_backup_restore as restore  # noqa: E402


def main() -> int:
    source = Path(restore.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert "support_web" not in imported_modules, imported_modules

    service_calls: list[tuple[str, str, dict]] = []

    def service(domain, service_name, payload):
        service_calls.append((domain, service_name, copy.deepcopy(payload)))

    profile = "WS-C2960X-24PS-L__faceplate__custom"
    calibrations = {
        "profiles": [
            {"profile": profile, "calibration": {"model": "fixture", "left": 12}}
        ],
        "active_profiles": {"WS-C2960X-24PS-L": profile},
    }
    restored = restore.restore_core_calibrations(
        calibrations,
        calibration_profile_name=lambda value: str(value).strip(),
        home_assistant_service=service,
    )
    assert restored == 1
    assert len(service_calls) == 2
    assert service_calls[0][0:2] == ("switch_vision", "save_calibration")
    assert service_calls[0][2]["profile"] == profile
    assert service_calls[0][2]["mirror_to_base"] is False
    assert service_calls[1][2]["profile"] == profile
    assert service_calls[1][2]["mirror_to_base"] is True

    invalid = copy.deepcopy(calibrations)
    invalid["active_profiles"] = {"WRONG-BASE": profile}
    try:
        restore.restore_core_calibrations(
            invalid,
            calibration_profile_name=lambda value: str(value).strip(),
            home_assistant_service=lambda *_args, **_kwargs: None,
        )
    except ValueError as exc:
        assert "base profile" in str(exc)
    else:
        raise AssertionError("restore accepted a mismatched active calibration base")

    assets = [
        {
            "kind": "logos",
            "filename": "custom.png",
            "sha256": "a" * 64,
            "content_base64": "YWJj",
        }
    ]
    asset_calls: list[tuple[dict, dict]] = []

    def asset_ws(command, **kwargs):
        asset_calls.append((copy.deepcopy(command), dict(kwargs)))
        return {"sha256": command["sha256"]}

    assert restore.restore_core_assets(assets, home_assistant_ws=asset_ws) == 1
    assert asset_calls == [
        (
            {
                "type": "switch_vision/put_backup_asset",
                "kind": "logos",
                "filename": "custom.png",
                "sha256": "a" * 64,
                "content_base64": "YWJj",
            },
            {"max_size": 32 * 1024 * 1024},
        )
    ]

    try:
        restore.restore_core_assets(
            assets,
            home_assistant_ws=lambda *_args, **_kwargs: {"sha256": "b" * 64},
        )
    except RuntimeError as exc:
        assert "did not confirm restored asset" in str(exc)
    else:
        raise AssertionError("restore accepted a mismatched Core asset digest")

    supervisor_calls: list[tuple[str, dict]] = []
    stored = {
        "poll_interval": "10",
        "mqtt_password": "live-secret",
        "controllers": [{"id": "live", "api_key": "live-key"}],
    }

    def supervisor(path, **kwargs):
        supervisor_calls.append((path, copy.deepcopy(kwargs)))
        if path.endswith("/info"):
            return {"data": {"options": copy.deepcopy(stored)}}
        assert path.endswith("/options")
        return {"result": "ok"}

    validate_calls: list[tuple[dict, dict]] = []

    def validate_options(safe, existing):
        validate_calls.append((copy.deepcopy(safe), copy.deepcopy(existing)))
        updated = copy.deepcopy(existing)
        updated.update(copy.deepcopy(safe))
        return updated

    restore.restore_unifi2mqtt_nonsecret(
        {
            "poll_interval": "30",
            "mqtt_password": "backup-secret-must-not-pass",
            "controllers": [{"id": "backup", "api_key": "backup-key"}],
        },
        unifi2mqtt_settings_status=lambda: {
            "installed": True,
            "slug": "repo/addon",
        },
        supervisor_json=supervisor,
        validate_unifi2mqtt_options=validate_options,
        unifi_secret_fields={"api_key", "local_api_key", "remote_api_key", "mqtt_password"},
    )
    safe, existing = validate_calls[0]
    assert safe == {"poll_interval": "30"}
    assert existing == stored
    assert supervisor_calls[0][0] == "/addons/repo%2Faddon/info"
    assert supervisor_calls[1][0] == "/addons/repo%2Faddon/options"
    posted = supervisor_calls[1][1]["payload"]["options"]
    assert posted["poll_interval"] == "30"
    assert posted["mqtt_password"] == "live-secret"
    assert posted["controllers"] == stored["controllers"]
    assert "backup-secret-must-not-pass" not in repr(posted)
    assert "backup-key" not in repr(posted)

    no_op_calls: list[str] = []

    def no_op_supervisor(path, **_kwargs):
        no_op_calls.append(path)
        if path.endswith("/info"):
            return {"data": {"options": copy.deepcopy(stored)}}
        raise AssertionError("no-op restore unexpectedly POSTed options")

    restore.restore_unifi2mqtt_nonsecret(
        {"poll_interval": "10", "mqtt_password": "ignored", "controllers": []},
        unifi2mqtt_settings_status=lambda: {"installed": True, "slug": "addon"},
        supervisor_json=no_op_supervisor,
        validate_unifi2mqtt_options=lambda _safe, existing: existing,
        unifi_secret_fields={"mqtt_password"},
    )
    assert no_op_calls == ["/addons/addon/info"]

    print("Discovery complete-backup restore adapters: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
