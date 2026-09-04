#!/usr/bin/env python3
"""Executable backend contracts for Hub save/reset controls.

No live Supervisor, Home Assistant, MQTT, or user data is touched. The tests call
shipped backend functions with isolated in-memory Supervisor state and temp files.
"""
from __future__ import annotations

import copy
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime_src"))

import support_web as hub  # noqa: E402

SOURCE_REGISTRY = ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"


@contextmanager
def patched(**values):
    original = {name: getattr(hub, name) for name in values}
    try:
        for name, value in values.items():
            setattr(hub, name, value)
        yield
    finally:
        for name, value in original.items():
            setattr(hub, name, value)


def expect_value_error(fn, contains: str) -> None:
    try:
        fn()
    except ValueError as exc:
        assert contains.casefold() in str(exc).casefold(), (contains, str(exc))
    else:
        raise AssertionError(f"Expected ValueError containing {contains!r}")


def expect_runtime_error(fn, contains: str) -> None:
    try:
        fn()
    except RuntimeError as exc:
        assert contains.casefold() in str(exc).casefold(), (contains, str(exc))
    else:
        raise AssertionError(f"Expected RuntimeError containing {contains!r}")


def base_switch(*, name: str = "SW1", community: str = "private-community", model: str = "auto") -> dict:
    return {
        "switch_name": name,
        "display_name": "Audit Switch",
        "switch_host": "10.10.10.10",
        "sensor_prefix": name.casefold(),
        "snmp_community": community,
        "enabled": "enabled",
        "walk_mode": "targeted",
        "switch_model": model,
        "card_header_title": "",
    }


def test_discovery_save_and_write_only_secrets() -> None:
    state = {
        "options": {
            "switches": [base_switch()],
            "stack_member_prefixes": [],
            "support_contributor_type": "github",
            "support_contributor_value": "saved-handle",
        }
    }
    backups: list[str] = []

    def get_options():
        return copy.deepcopy(state["options"])

    def supervisor(path, *, method="GET", timeout=12.0, payload=None):
        assert path == "/addons/self/options"
        assert method == "POST"
        assert isinstance(payload, dict) and isinstance(payload.get("options"), dict)
        state["options"] = copy.deepcopy(payload["options"])
        return {}

    with patched(
        DEFAULT_REGISTRY_FILE=SOURCE_REGISTRY,
        _self_addon_options=get_options,
        _supervisor_json=supervisor,
        create_pre_mutation_backup=lambda _options, *, reason: backups.append(reason),
        enforce_retention=lambda _options: None,
    ):
        safe = hub._discovery_settings_status()
        row = safe["settings"]["switches"][0]
        assert row["snmp_community"] == ""
        assert row["snmp_community_configured"] is True
        assert row["original_switch_name"] == "SW1"
        assert safe["settings"]["support_contributor_value"] == ""
        assert safe["settings"]["support_contributor_value_configured"] is True
        assert "PowerConnect 5548P" in safe["models"]
        assert "WS-C3750X-48P" in safe["models"]

        # Rename the switch while leaving the write-only community blank. The
        # original name is the stable lookup key that must preserve the secret.
        renamed = dict(row)
        renamed.update({
            "switch_name": "SW2",
            "sensor_prefix": "sw2",
            "switch_model": "PowerConnect 5548P",
            "snmp_community": "",
        })
        saved = hub._save_discovery_settings({"settings": {"switches": [renamed]}})
        assert saved["saved"] is True and saved["changed"] is True
        persisted = state["options"]["switches"][0]
        assert persisted["switch_name"] == "SW2"
        assert persisted["switch_model"] == "PowerConnect 5548P"
        assert persisted["snmp_community"] == "private-community"
        assert backups == ["hub_settings_update"]

        # A brand-new switch cannot silently inherit or invent a community.
        new_row = base_switch(name="SW3", community="", model="PowerConnect 5548P")
        new_row["original_switch_name"] = ""
        expect_value_error(
            lambda: hub._save_discovery_settings({"settings": {"switches": [new_row]}}),
            "requires an SNMP community",
        )

        # Contributor recognition is also write-only; blank preserves it only
        # when the recognition type is unchanged.
        result = hub._save_discovery_settings({
            "settings": {
                "support_contributor_type": "github",
                "support_contributor_value": "",
            }
        })
        assert result["saved"] is True
        assert state["options"]["support_contributor_value"] == "saved-handle"
        expect_value_error(
            lambda: hub._save_discovery_settings({
                "settings": {
                    "support_contributor_type": "forum",
                    "support_contributor_value": "",
                }
            }),
            "Enter the name or username",
        )


def test_manual_model_fallback_is_complete() -> None:
    # If the runtime registry is temporarily unreadable, the fallback must still
    # accept every manual model allowed by the Supervisor schema.
    with tempfile.TemporaryDirectory(prefix="sv-empty-registry-") as temp:
        missing = Path(temp) / "missing.json"
        with patched(DEFAULT_REGISTRY_FILE=missing):
            fallback = hub._manual_snmp_override_models()
    required = {
        "WS-C3750X-48P",
        "CRS328-24P-4S+RM",
        "XS1930-10",
        "N2128PX-ON",
        "PowerConnect 5548P",
    }
    assert required <= fallback, sorted(required - fallback)


def test_core_reset_contract() -> None:
    commands: list[dict] = []

    def ws(command):
        commands.append(copy.deepcopy(command))
        return {"settings": {"factory": True}}

    with patched(_home_assistant_ws=ws):
        result = hub._save_core_settings({"reset_to_defaults": True})
    assert result == {"settings": {"factory": True}}
    assert commands == [{"type": "switch_vision/set_settings", "reset_to_defaults": True}]


def test_snmp2mqtt_save_password_preservation_and_restart() -> None:
    state = {
        "options": {
            "mqtt": {
                "host": "mqtt-old",
                "port": 1883,
                "username": "switchvision",
                "password": "broker-secret",
                "base_topic": "snmp2mqtt",
            },
            "targets_path": "/config/app_configs/switch_vision_snmp2mqtt/targets.yaml",
            "use_switch_vision_generated_yaml": True,
            "switch_vision_generated_yaml_path": "/share/switch_vision/generated-snmp2mqtt.yaml",
            "imported_targets_path": "/config/app_configs/switch_vision_snmp2mqtt/imported/generated-snmp2mqtt.yaml",
            "backup_existing_config": False,
            "homeassistant": {"discovery": True, "prefix": "homeassistant"},
        }
    }
    supervisor_calls: list[tuple[str, str]] = []

    def addon_options():
        return "local_switch_vision_snmp2mqtt", "started", copy.deepcopy(state["options"])

    def supervisor(path, *, method="GET", timeout=12.0, payload=None):
        supervisor_calls.append((path, method))
        if path.endswith("/options"):
            state["options"] = copy.deepcopy(payload["options"])
        return {}

    request = {
        "mqtt": {
            "host": "mqtt-new",
            "port": 1883,
            "username": "switchvision",
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

    with patched(_snmp2mqtt_addon_options=addon_options, _supervisor_json=supervisor):
        result = hub._save_snmp2mqtt_settings({"settings": request})

    assert result["saved"] is True and result["changed"] is True
    assert result["restart_requested"] is True
    assert state["options"]["mqtt"]["host"] == "mqtt-new"
    assert state["options"]["mqtt"]["password"] == "broker-secret"
    assert any(path.endswith("/options") for path, _ in supervisor_calls)
    assert any(path.endswith("/restart") for path, _ in supervisor_calls)


def test_snmp_reset_boundary() -> None:
    with patched(_discovery_state_snapshot=lambda: {"running": True}):
        expect_runtime_error(hub._reset_snmp_discovery_data, "Stop Discovery")

    with tempfile.TemporaryDirectory(prefix="sv-functional-audit-") as temp:
        root = Path(temp)
        walks = root / "snmpwalks"
        caps = root / "capabilities"
        walks.mkdir()
        caps.mkdir()
        (walks / "walk.txt").write_text("walk\n", encoding="utf-8")
        (caps / "cap.json").write_text("{}\n", encoding="utf-8")
        generated = root / "generated-snmp2mqtt.yaml"
        card = root / "generated-dashboard-card.yaml"
        report = root / "report.txt"
        generated.write_text("targets: []\n", encoding="utf-8")
        card.write_text("type: custom:test\n", encoding="utf-8")
        report.write_text("report\n", encoding="utf-8")
        unifi = root / "unifi-snapshot.json"
        unifi.write_text('{"devices": []}\n', encoding="utf-8")

        runtime_info = {
            "installed": False,
            "slug": None,
            "state": "not_installed",
            "options_readable": False,
            "homeassistant_prefix": None,
        }

        with patched(
            _discovery_state_snapshot=lambda: {"running": False},
            _snmp2mqtt_runtime_info=lambda: copy.deepcopy(runtime_info),
            _load_snmp2mqtt_retirement_topics=lambda: [],
            _stop_snmp2mqtt_for_reset=lambda _info: False,
            DEFAULT_SNMPWALKS_DIR=walks,
            DEFAULT_CAPABILITIES_DIR=caps,
            DEFAULT_GENERATED_SNMP2MQTT=generated,
            DEFAULT_UNIFI_SNAPSHOT=unifi,
            SNMP_RESET_FILES=(generated, card, report),
        ):
            result = hub._reset_snmp_discovery_data()

        assert result["reset"] is True
        assert result["walk_entries_removed"] == 1
        assert result["capability_entries_removed"] == 1
        assert result["unifi_snapshot_preserved"] is True
        assert unifi.is_file(), "SNMP reset must preserve UniFi API snapshot"
        assert not generated.exists() and not card.exists() and not report.exists()
        assert list(walks.iterdir()) == [] and list(caps.iterdir()) == []


def test_discovery_exit10_warning_and_handoff_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="sv-discovery-warning-") as temp:
        root = Path(temp)
        log_path = root / "discovery.log"
        options_path = root / "options.json"
        generated_yaml = root / "generated-snmp2mqtt.yaml"
        options_path.write_text("{}\n", encoding="utf-8")

        class FakeProcess:
            def __init__(self, return_code: int):
                self.pid = 4242
                self.stdout = [
                    "SV_STATUS|stage=Generating|switch=Audit|target=|command=synthetic|activity=running\n",
                    "synthetic discovery output\n",
                ]
                self._return_code = return_code

            def wait(self):
                return self._return_code

            def poll(self):
                return self._return_code

        def run_case(return_code: int):
            bundle_calls: list[dict] = []
            handoff_calls: list[int] = []

            def fake_popen(*_args, **_kwargs):
                return FakeProcess(return_code)

            def fake_handoff(*_args, **_kwargs):
                handoff_calls.append(return_code)
                return {
                    "status": "Running",
                    "action": "verified",
                    "slug": "local_switch_vision_snmp2mqtt",
                    "state": "started",
                    "activation_verified": True,
                    "handoff_failed": False,
                    "message": "SNMP2MQTT activation verified",
                }

            def fake_bundle(_settings, _lines, **kwargs):
                bundle_calls.append(copy.deepcopy(kwargs))
                return True

            original_popen = hub.subprocess.Popen
            hub.subprocess.Popen = fake_popen
            hub._DISCOVERY_STOP_REQUESTED.clear()
            try:
                with patched(
                    DEFAULT_DISCOVERY_LOG=log_path,
                    DEFAULT_GENERATED_SNMP2MQTT=generated_yaml,
                    _ensure_runtime_paths=lambda: None,
                    _self_addon_options=lambda: {"generate_support_my_switch_bundle": True},
                    _write_authoritative_discovery_options_snapshot=lambda **_kwargs: options_path,
                    _load_snmp2mqtt_retirement_topics=lambda: [],
                    _ensure_snmp2mqtt_running=fake_handoff,
                    _generate_automatic_support_bundle=fake_bundle,
                ):
                    hub._run_discovery(root / "synthetic-discovery")
                    state = hub._discovery_state_snapshot()
            finally:
                hub.subprocess.Popen = original_popen
                hub._DISCOVERY_STOP_REQUESTED.clear()
            return state, handoff_calls, bundle_calls

        degraded, degraded_handoff, degraded_bundle = run_case(10)
        assert degraded["success"] is True
        assert degraded["phase"] == "complete"
        assert degraded["stage"] == "Complete with warnings"
        assert degraded["snmp2mqtt"]["action"] == "blocked_degraded"
        assert degraded["snmp2mqtt"]["activation_verified"] is False
        assert degraded_handoff == [], "exit 10 must never start or restart SNMP2MQTT"
        assert degraded_bundle == [{
            "evidence_quality": "degraded",
            "discovery_result": "complete_with_warnings",
            "snmp2mqtt_handoff": "blocked_degraded",
        }]

        normal, normal_handoff, normal_bundle = run_case(0)
        assert normal["success"] is True
        assert normal["phase"] == "complete"
        assert normal["stage"] == "Complete"
        assert normal_handoff == [0], "exit 0 must retain the normal SNMP2MQTT handoff"
        assert normal_bundle == [{
            "evidence_quality": "complete",
            "discovery_result": "success",
            "snmp2mqtt_handoff": "verified",
        }]


def test_latest_contribution_exposes_evidence_metadata() -> None:
    with tempfile.TemporaryDirectory(prefix="sv-evidence-metadata-") as temp:
        root = Path(temp)
        archive = root / "Switch_Vision_Contribution_SV-2026-000001_20260904-000000.zip"
        evidence = {
            "quality": "degraded",
            "discovery_result": "complete_with_warnings",
            "snmp2mqtt_handoff": "blocked_degraded",
        }
        with hub.zipfile.ZipFile(archive, "w") as zf:
            zf.writestr(
                "Support_My_Switch_SV-2026-000001/MANIFEST.json",
                hub.json.dumps({
                    "contribution_id": "SV-2026-000001",
                    "switch_vision_version": "2.3.40",
                    "bundle_quality": "PASS",
                    "ready_to_send": True,
                    "evidence": evidence,
                }),
            )
            zf.writestr(
                "Support_My_Switch_SV-2026-000001/DEVICE_SUMMARY.json",
                "[]",
            )
        latest = hub._latest_contribution(root)
        assert latest is not None
        assert latest["ready_to_send"] is True
        assert latest["quality"] == "PASS"
        assert latest["evidence"] == evidence


def main() -> int:
    test_discovery_save_and_write_only_secrets()
    print("PASS: Discovery settings save, rename, manual-model and secret preservation contracts")
    test_manual_model_fallback_is_complete()
    print("PASS: Degraded registry fallback accepts current manual model set")
    test_core_reset_contract()
    print("PASS: Core Reset button backend contract")
    test_snmp2mqtt_save_password_preservation_and_restart()
    print("PASS: SNMP2MQTT save preserves blank password and requests restart")
    test_snmp_reset_boundary()
    print("PASS: SNMP Discovery reset stop guard, cleanup and UniFi preservation boundary")
    test_discovery_exit10_warning_and_handoff_contract()
    print("PASS: Discovery exit 10 is warning-only, blocks SNMP2MQTT and preserves exit-0 handoff")
    test_latest_contribution_exposes_evidence_metadata()
    print("PASS: Support My Switch contribution status exposes structured evidence metadata")
    print("Switch Vision Hub executable save/reset contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
