#!/usr/bin/env python3
"""Executable backend contracts for Hub save/reset controls.

No live Supervisor, Home Assistant, MQTT, or user data is touched. The tests call
shipped backend functions with isolated in-memory Supervisor state and temp files.
"""
from __future__ import annotations

import copy
import re
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime_src"))

import support_web as hub  # noqa: E402

SOURCE_REGISTRY = ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"
SUPERVISOR_CONFIG = ROOT / "switch_vision_discovery/config.yaml"


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
        assert "WS-C3750X-48P-S" in safe["models"]
        assert "HP ProCurve 1810G-24" in safe["models"]
        assert "SG350-20" in safe["models"]
        assert "HP J8693A Switch 3500yl-48G" in safe["models"]

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
        assert state["options"]["autodiscover_networks"] == [], state["options"]
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


def test_saved_row_effective_config_is_canonical_fresh_and_secret_safe() -> None:
    legacy_row = {
        "switch_name": "SW7",
        "switch_host": "",
        "sensor_prefix": "",
        "snmp_community": "",
        "walk_mode": "",
        "switch_model": "",
        "display_name": "2960X",
        "host": " 192.168.1.103 ",
        "prefix": " sw7 ",
        "community": " private-community ",
        "enabled": "enabled",
        "mode": "targeted",
        "model_override": "WS-C2960X-48FPD-L",
        "card_header_title": "",
    }
    state = {
        "options": {
            "enable_switch_list": "true",
            "snmp_timeout": "3",
            "snmp_retries": "1",
            "switches": [legacy_row],
            "stack_member_prefixes": [],
        }
    }

    def get_options():
        return copy.deepcopy(state["options"])

    def supervisor(path, *, method="GET", timeout=12.0, payload=None):
        assert path == "/addons/self/options"
        assert method == "POST"
        state["options"] = copy.deepcopy(payload["options"])
        return {}

    with patched(
        DEFAULT_REGISTRY_FILE=SOURCE_REGISTRY,
        _self_addon_options=get_options,
        _supervisor_json=supervisor,
        create_pre_mutation_backup=lambda *_args, **_kwargs: None,
        enforce_retention=lambda _options: None,
    ):
        status = hub._discovery_settings_status()
        row = status["settings"]["switches"][0]
        assert row["switch_name"] == "SW7"
        assert row["switch_host"] == "192.168.1.103"
        assert row["sensor_prefix"] == "sw7"
        assert row["snmp_community"] == ""
        assert row["snmp_community_configured"] is True
        assert "community" not in row
        assert "host" not in row
        assert "prefix" not in row

        provenance = status["effective_config"]
        safe_row = provenance["switches"][0]
        assert provenance["source"] == "supervisor"
        assert len(provenance["revision"]) == 64
        assert safe_row["switch_name"] == "SW7"
        assert safe_row["switch_host"] == "192.168.1.103"
        assert safe_row["credential_configured"] is True
        assert "credential_fingerprint" not in safe_row
        assert provenance["revision_scope"] == "non_secret_effective_config"
        assert provenance["credential_evidence"] == "configured_state_only"
        assert "private-community" not in hub.json.dumps(provenance)

        # Reproduce a stale row with blank canonical keys plus populated aliases.
        with tempfile.TemporaryDirectory(prefix="sv-effective-config-legacy-") as temp:
            legacy_path = Path(temp) / "options.json"
            hub._write_authoritative_discovery_options_snapshot(
                destination=legacy_path,
                options=state["options"],
            )
            legacy_effective = hub.json.loads(
                legacy_path.read_text(encoding="utf-8")
            )["switches"][0]
            assert legacy_effective["switch_host"] == "192.168.1.103"
            assert legacy_effective["sensor_prefix"] == "sw7"
            assert legacy_effective["snmp_community"] == "private-community"
            assert not {
                "host", "manual_switch_host", "prefix", "entity_prefix",
                "community", "mode", "model_override",
            } & set(legacy_effective)

        ambiguous = copy.deepcopy(state["options"])
        ambiguous["switches"][0]["switch_host"] = "192.168.1.104"
        expect_value_error(
            lambda: hub._effective_discovery_options(ambiguous),
            "conflicting saved aliases",
        )

        # Saving the original row with a blank write-only field must preserve
        # its current effective community and migrate legacy aliases to the
        # canonical row schema instead of requiring a duplicate row.
        saved = hub._save_discovery_settings(
            {"settings": {"switches": [dict(row, snmp_community="")]}}
        )
        assert saved["saved"] is True
        persisted = state["options"]["switches"][0]
        assert persisted["switch_name"] == "SW7"
        assert persisted["switch_host"] == "192.168.1.103"
        assert persisted["sensor_prefix"] == "sw7"
        assert persisted["snmp_community"] == "private-community"
        assert "community" not in persisted
        assert "host" not in persisted
        assert "prefix" not in persisted

        with tempfile.TemporaryDirectory(prefix="sv-effective-config-") as temp:
            path = Path(temp) / "options.json"
            first = hub._write_authoritative_discovery_options_snapshot(
                destination=path,
                options=state["options"],
            )
            first_doc = hub.json.loads(first.read_text(encoding="utf-8"))
            first_provenance = hub._discovery_effective_config_provenance(
                state["options"]
            )
            assert first_doc["switches"][0]["switch_host"] == "192.168.1.103"
            assert first_doc["switches"][0]["snmp_community"] == "private-community"

            secret_only = copy.deepcopy(state["options"])
            secret_only["switches"][0]["snmp_community"] = " another-community "
            secret_only_provenance = hub._discovery_effective_config_provenance(
                secret_only
            )
            assert secret_only_provenance["revision"] == first_provenance["revision"]
            assert "credential_fingerprint" not in hub.json.dumps(secret_only_provenance)
            assert "another-community" not in hub.json.dumps(secret_only_provenance)

            # The next run must consume newly saved values rather than stale
            # per-row state from the previous snapshot.
            state["options"]["switches"][0]["switch_host"] = " 192.168.1.104 "
            state["options"]["switches"][0]["snmp_community"] = " changed-community "
            second = hub._write_authoritative_discovery_options_snapshot(
                destination=path,
                options=state["options"],
            )
            second_doc = hub.json.loads(second.read_text(encoding="utf-8"))
            second_provenance = hub._discovery_effective_config_provenance(
                state["options"]
            )
            assert second_doc["switches"][0]["switch_host"] == "192.168.1.104"
            assert second_doc["switches"][0]["snmp_community"] == "changed-community"
            assert first_provenance["revision"] != second_provenance["revision"]
            assert "credential_fingerprint" not in hub.json.dumps(second_provenance)
            assert "changed-community" not in hub.json.dumps(second_provenance)

        duplicate = copy.deepcopy(state["options"])
        duplicate["switches"].append(dict(duplicate["switches"][0]))
        expect_value_error(
            lambda: hub._effective_discovery_options(duplicate),
            "duplicates",
        )


def test_manual_model_fallback_is_complete() -> None:
    # If the runtime registry is temporarily unreadable, the fallback must still
    # accept every manual model allowed by the Supervisor schema, with no stale
    # hard-coded extras drifting outside that schema.
    with tempfile.TemporaryDirectory(prefix="sv-empty-registry-") as temp:
        missing = Path(temp) / "missing.json"
        with patched(DEFAULT_REGISTRY_FILE=missing):
            fallback = hub._manual_snmp_override_models()

    schema_text = SUPERVISOR_CONFIG.read_text(encoding="utf-8")
    match = re.search(
        r"(?m)^\s*switch_model:\s*list\(([^)]+)\)\?\s*$",
        schema_text,
    )
    assert match is not None, "Supervisor manual-model enum not found"
    schema_models = {value.strip() for value in match.group(1).split("|") if value.strip()}
    schema_models.discard("auto")
    assert fallback == schema_models, {
        "missing_from_fallback": sorted(schema_models - fallback),
        "stale_in_fallback": sorted(fallback - schema_models),
    }


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
            def __init__(self, return_code: int, result_marker: str = ""):
                self.pid = 4242
                self.stdout = [
                    "SV_STATUS|stage=Generating|switch=Audit|target=|command=synthetic|activity=running\n",
                    "synthetic discovery output\n",
                ]
                if result_marker:
                    self.stdout.append(result_marker.rstrip("\n") + "\n")
                self._return_code = return_code

            def wait(self):
                return self._return_code

            def poll(self):
                return self._return_code

        def run_case(return_code: int, result_marker: str = ""):
            bundle_calls: list[dict] = []
            handoff_calls: list[int] = []

            def fake_popen(*_args, **_kwargs):
                return FakeProcess(return_code, result_marker)

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
                    DEFAULT_CURRENT_DISCOVERY_DEBUG=root / "current-debug.log",
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

        api_only, api_only_handoff, api_only_bundle = run_case(
            0,
            "SV_RESULT|warnings=false|degraded=false|snmp2mqtt_required=false",
        )
        assert api_only["success"] is True
        assert api_only["phase"] == "complete"
        assert api_only["stage"] == "Complete"
        assert api_only["snmp2mqtt"]["status"] == "Not required"
        assert api_only["snmp2mqtt"]["action"] == "not_required"
        assert api_only_handoff == [], "API-only success must not start or restart SNMP2MQTT"
        assert api_only_bundle == [{
            "evidence_quality": "complete",
            "discovery_result": "success",
            "snmp2mqtt_handoff": "not_required",
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


def test_configured_device_http_dispatch_contract() -> None:
    """Check the real ingress-gated handler with isolated, reversible effects."""
    import io
    from types import SimpleNamespace

    events: list[str] = []

    @contextmanager
    def mutation(name: str):
        events.append("enter:" + name)
        try:
            yield
        finally:
            events.append("exit:" + name)

    def response(route: str, body: bytes = b"", *, allowed: bool = True,
                 declared_length: int | None = None):
        handler = hub.SupportHandler.__new__(hub.SupportHandler)
        handler.path = route
        handler.headers = {
            "Content-Length": str(len(body) if declared_length is None else declared_length)
        }
        handler.rfile = io.BytesIO(body)
        handler.server = SimpleNamespace(
            options_file=Path("/unused/options.json"),
            discovery_script=Path("/unused/discovery.sh"),
        )
        handler._allow_ingress_request = lambda: allowed
        results: list[tuple[int, object]] = []
        def emit(payload, status=200):
            events.append("response")
            results.append((int(status), payload))
        handler._json = emit
        hub.SupportHandler.do_POST(handler)
        return results

    with patched(
        _device_configuration_update=mutation,
        _set_configured_device_state=lambda _path, _data: (
            events.append("state") or {"updated": True}
        ),
        _move_configured_device=lambda _path, _data: (
            events.append("order") or {"ordered": True}
        ),
        _reset_configured_device_order=lambda _path: (
            events.append("reset") or {"reset": True}
        ),
        _record_device_dashboard_refresh=lambda result: events.append("dashboard"),
        _start_device_state_application=lambda _script: (
            events.append("queue") or {
                "started": True, "coalesced": True, "generation": 3
            }
        ),
    ):
        routes = (
            ("/api/configured-devices/state",
             b'{"device_key":"snmp:SW1","enabled":false}', "state", "Device configuration update"),
            ("/api/configured-devices/order",
             b'{"device_key":"snmp:SW1","direction":"up"}', "order", "Device order update"),
            ("/api/configured-devices/reset-order", b"", "reset", "Device order reset"),
        )
        for route, body, operation, label in routes:
            events.clear()
            replies = response(route, body)
            assert len(replies) == 1 and replies[0][0] == 200, replies
            expected = ["enter:" + label, operation, "dashboard"]
            if operation == "state":
                expected.append("queue")
                result = replies[0][1]
                assert result["polling_refresh_started"] is True
                assert result["polling_refresh_coalesced"] is True
                assert result["polling_refresh_generation"] == 3
            expected.extend(["response", "exit:" + label])
            assert events == expected, (route, events)

        events.clear()
        unifi = response("/api/configured-devices/state", b'{"device_key":"unifi:U1"}')
        assert unifi[0][1]["polling_refresh_pending"] is True
        assert unifi[0][1]["polling_refresh_started"] is False
        assert "queue" not in events

        for route in ("/api/configured-devices/state", "/api/configured-devices/order"):
            events.clear()
            assert response(route, b"{", declared_length=8193)[0][0] == 400
            assert response(route, b"broken-json")[0][0] == 400
            assert not any(item in events for item in ("state", "order", "dashboard", "queue"))
        events.clear()
        assert response("/api/configured-devices/reset-order", allowed=False) == []
        assert events == []

    @contextmanager
    def busy(_name: str):
        raise hub.OperationConflict("busy")
        yield

    with patched(_device_configuration_update=busy):
        for route in (
            "/api/configured-devices/state",
            "/api/configured-devices/order",
            "/api/configured-devices/reset-order",
        ):
            assert response(route, b'{"device_key":"snmp:SW1"}')[0] == (
                409, {"error": "busy"}
            )

    def broken_reset(_path: Path):
        raise OSError("unavailable")

    with patched(
        _device_configuration_update=mutation,
        _reset_configured_device_order=broken_reset,
    ):
        assert response("/api/configured-devices/reset-order") == [
            (400, {"error": "unavailable"})
        ]


def test_unifi_http_dispatch_contract() -> None:
    """Exercise actual Supervisor-gated UniFi POST routing without external effects."""
    import io
    from types import SimpleNamespace

    events: list[str] = []

    @contextmanager
    def operation(label: str):
        events.append("enter:" + label)
        try:
            yield
        finally:
            events.append("exit:" + label)

    def send(path: str, data: bytes = b"", *, length: int | None = None,
             ingress: bool = True) -> list[tuple[int, object]]:
        handler = hub.SupportHandler.__new__(hub.SupportHandler)
        handler.path = path
        handler.headers = {"Content-Length": str(len(data) if length is None else length)}
        handler.rfile = io.BytesIO(data)
        handler.server = SimpleNamespace()
        handler._allow_ingress_request = lambda: ingress
        responses: list[tuple[int, object]] = []

        def emit(value, status=200):
            events.append("response")
            responses.append((int(status), value))

        handler._json = emit
        hub.SupportHandler.do_POST(handler)
        return responses

    install = "/api/unifi2mqtt/install"
    connection = "/api/unifi2mqtt/test-connection"
    settings = "/api/unifi2mqtt/settings"

    with patched(
        _exclusive_operation=operation,
        _install_unifi2mqtt=lambda: events.append("install") or {"installed": True},
        _test_unifi2mqtt_connection=lambda data: (
            events.append("test") or {"tested": data["transport"]}
        ),
        _save_unifi2mqtt_settings=lambda data: (
            events.append("settings") or {"saved": data["enabled"]}
        ),
        _unifi_test_safe_reason=lambda _exc: "safe connection error",
    ):
        events.clear()
        assert send(install) == [(200, {"installed": True})]
        assert events == [
            "enter:UniFi2MQTT installation", "install", "response",
            "exit:UniFi2MQTT installation",
        ]
        events.clear()
        assert send(connection, b'{"transport":"local"}') == [
            (200, {"tested": "local"})
        ]
        assert events == ["test", "response"]

        events.clear()
        assert send(settings, b'{"enabled":true}') == [(200, {"saved": True})]
        assert events == [
            "enter:UniFi2MQTT settings update", "settings", "response",
            "exit:UniFi2MQTT settings update",
        ]

        events.clear()
        for route in (install, connection, settings):
            assert send(route, b'{}', ingress=False) == []
        assert events == [], "Denied Supervisor ingress must have no effect"

        for route, limit in ((connection, 16384), (settings, 32768)):
            events.clear()
            reply = send(route, b'{}', length=limit + 1)
            assert reply[0][0] == 400, (route, reply)
            assert "test" not in events and "settings" not in events
            events.clear()
            reply = send(route, b"{")
            assert reply[0][0] == 400, (route, reply)
            assert "test" not in events and "settings" not in events

    @contextmanager
    def busy(_label: str):
        raise hub.OperationConflict("busy")
        yield

    with patched(_exclusive_operation=busy):
        for route in (install, settings):
            assert send(route, b'{}') == [(409, {"error": "busy"})]

    def failed_install():
        raise RuntimeError("install unavailable")

    with patched(
        _exclusive_operation=operation,
        _install_unifi2mqtt=failed_install,
    ):
        assert send(install) == [(400, {"error": "install unavailable"})]

    def failed_connection(_data):
        raise RuntimeError("secret should be redacted")

    with patched(
        _test_unifi2mqtt_connection=failed_connection,
        _unifi_test_safe_reason=lambda _exc: "redacted",
    ):
        assert send(connection, b'{}') == [(400, {"error": "redacted"})]


def test_autodiscover_http_dispatch_contract() -> None:
    """Exercise actual AutoDiscover scan/add HTTP dispatch without scanning devices."""
    import io
    from types import SimpleNamespace

    events: list[str] = []

    @contextmanager
    def exclusive(label: str):
        events.append("exclusive:" + label)
        try:
            yield
        finally:
            events.append("exclusive-exit:" + label)

    @contextmanager
    def mutation(label: str):
        events.append("mutation:" + label)
        try:
            yield
        finally:
            events.append("mutation-exit:" + label)

    def send(path: str, body: bytes = b'{"source":"fixture"}',
             *, length: int | None = None, allowed: bool = True):
        handler = hub.SupportHandler.__new__(hub.SupportHandler)
        handler.path = path
        handler.headers = {"Content-Length": str(len(body) if length is None else length)}
        handler.rfile = io.BytesIO(body)
        handler.server = SimpleNamespace()
        handler._allow_ingress_request = lambda: allowed
        replies: list[tuple[int, object]] = []

        def emit(payload, status=200):
            events.append("reply")
            replies.append((int(status), payload))

        handler._json = emit
        hub.SupportHandler.do_POST(handler)
        return replies

    scan = "/api/autodiscover/scan"
    add = "/api/autodiscover/add"
    with patched(
        _exclusive_operation=exclusive,
        _device_configuration_update=mutation,
        _autodiscover_scan=lambda data: events.append("scan") or {"scanned": data["source"]},
        _autodiscover_add=lambda data: events.append("add") or {"added": data["source"]},
    ):
        events.clear()
        assert send(scan) == [(200, {"scanned": "fixture"})]
        assert events == [
            "exclusive:AutoDiscover scan", "scan", "reply",
            "exclusive-exit:AutoDiscover scan",
        ]
        events.clear()
        assert send(add + "/") == [(200, {"added": "fixture"})]
        assert events == [
            "mutation:AutoDiscover add devices", "add", "reply",
            "mutation-exit:AutoDiscover add devices",
        ]

        events.clear()
        assert send(scan, allowed=False) == []
        assert send(add, allowed=False) == []
        assert events == [], "Denied Supervisor ingress must not acquire locks or act"

        for route, limit, label in (
            (scan, 16384, "AutoDiscover scan"),
            (add, 65536, "AutoDiscover add devices"),
        ):
            for body, requested in (
                (b'{}', 0), (b'{}', limit + 1),
                (b'{bad', None),
            ):
                events.clear()
                answer = send(route, body, length=requested)
                assert len(answer) == 1 and answer[0][0] == 400, (route, answer)
                assert "scan" not in events and "add" not in events, events
                assert events[0].endswith(label), events
                assert events[1].endswith(label) and events[-1] == "reply", events

    @contextmanager
    def busy(_label):
        raise hub.OperationConflict("busy")
        yield

    with patched(_exclusive_operation=busy, _device_configuration_update=busy):
        assert send(scan) == [(409, {"error": "busy"})]
        assert send(add) == [(409, {"error": "busy"})]

    def broken_scan(_data):
        raise RuntimeError("scan error")

    def broken_add(_data):
        raise OSError("add failed")

    with patched(
        _exclusive_operation=exclusive,
        _device_configuration_update=mutation,
        _autodiscover_scan=broken_scan,
        _autodiscover_add=broken_add,
    ):
        assert send(scan) == [(400, {"error": "scan error"})]
        assert send(add) == [(400, {"error": "add failed"})]


def test_hub_settings_http_dispatch_contract() -> None:
    """Check actual Supervisor-gated settings POST dispatch without HAOS mutations."""
    import io
    from types import SimpleNamespace

    events: list[str] = []

    @contextmanager
    def operation(label: str):
        events.append("enter:" + label)
        try:
            yield
        finally:
            events.append("exit:" + label)

    def send(route: str, body: bytes = b'{"token":"fixture"}',
             *, declared_length: int | None = None, allowed: bool = True):
        handler = hub.SupportHandler.__new__(hub.SupportHandler)
        handler.path = route
        handler.headers = {
            "Content-Length": str(len(body) if declared_length is None else declared_length)
        }
        handler.rfile = io.BytesIO(body)
        handler.server = SimpleNamespace()
        handler._allow_ingress_request = lambda: allowed
        results: list[tuple[int, object]] = []

        def emit(payload, status=200):
            events.append("response")
            results.append((int(status), payload))

        handler._json = emit
        hub.SupportHandler.do_POST(handler)
        return results

    routes = (
        ("/api/settings/core", "core", None, 256 * 1024),
        ("/api/settings/snmp2mqtt", "snmp", "SNMP2MQTT settings update", 256 * 1024),
        ("/api/settings/discovery", "discovery", "Discovery settings update", 1024 * 1024),
    )
    with patched(
        _exclusive_operation=operation,
        _save_core_settings=lambda data: events.append("core") or {"core": data["token"]},
        _save_snmp2mqtt_settings=lambda data: events.append("snmp") or {"snmp": data["token"]},
        _save_discovery_settings=lambda data: events.append("discovery") or {"discovery": data["token"]},
    ):
        for route, action, lock, maximum in routes:
            events.clear()
            assert send(route + "/", b'{"token":"fixture"}') == [
                (200, {action: "fixture"})
            ]
            expected = ([f"enter:{lock}"] if lock else []) + [action, "response"]
            if lock:
                expected.append(f"exit:{lock}")
            assert events == expected, (route, events)
            events.clear()
            assert send(route, allowed=False) == []
            assert events == [], (route, events)

            for content, size in (
                (b'{}', 0),
                (b'{}', maximum + 1),
                (b'{not-json', None),
            ):
                events.clear()
                reply = send(route, content, declared_length=size)
                assert len(reply) == 1 and reply[0][0] == 400, (route, reply)
                assert action not in events, (route, events)
                assert events[-1] == "response", (route, events)
                assert events == ["response"], (route, events)

    @contextmanager
    def busy(_label):
        raise hub.OperationConflict("already running")
        yield

    with patched(_exclusive_operation=busy):
        for route in (routes[1][0], routes[2][0]):
            assert send(route) == [(409, {"error": "already running"})]

    def failed(_data):
        raise ValueError("invalid settings")

    with patched(
        _save_core_settings=failed,
        _save_snmp2mqtt_settings=failed,
        _save_discovery_settings=failed,
        _exclusive_operation=operation,
    ):
        for route, _action, lock, _max in routes:
            events.clear()
            assert send(route) == [(400, {"error": "invalid settings"})]
            if lock:
                assert events == [
                    f"enter:{lock}", f"exit:{lock}", "response"
                ], (route, events)
            else:
                assert events == ["response"], (route, events)


def test_hp_optics_http_dispatch_contract() -> None:
    """Verify the real Supervisor-gated optics handler without sending a HA command."""
    import io
    import json
    from types import SimpleNamespace

    route = "/api/optics/settings"
    safe_error = {"error": "HP optics settings could not be saved safely."}
    calls: list[dict] = []

    def ws(payload):
        calls.append(payload)
        return {"saved": True}

    def send(body: bytes, *, declared: str | None = None, allowed: bool = True):
        handler = hub.SupportHandler.__new__(hub.SupportHandler)
        handler.path = route + "/?source=test"
        handler.headers = {"Content-Length": str(len(body)) if declared is None else declared}
        handler.rfile = io.BytesIO(body)
        handler.server = SimpleNamespace()
        handler._allow_ingress_request = lambda: allowed
        replies: list[tuple[int, object]] = []
        handler._json = lambda obj, status=200: replies.append((int(status), obj))
        hub.SupportHandler.do_POST(handler)
        return replies

    with patched(_home_assistant_ws=ws):
        assert send(b'{"enabled":true,"write_community":"fixture"}') == [
            (200, {"saved": True})
        ]
        assert calls == [{
            "type": "switch_vision/set_hp_optics_settings",
            "enabled": True,
            "write_community": "fixture",
        }]
        calls.clear()
        assert send(b'{"enabled":false}') == [(200, {"saved": True})]
        assert calls == [{
            "type": "switch_vision/set_hp_optics_settings",
            "enabled": False,
            "write_community": "",
        }]
        calls.clear()

        assert send(b'{"enabled":true}', allowed=False) == []
        assert calls == [], "Ingress denial must not call Home Assistant"

        bad_payloads = (
            (b"{}", None),
            (b"{}", "0"),
            (b"{}", "8193"),
            (b"{}", "NaN"),
            (b"{", None),
            (b"\xff", None),
            (b"[]", None),
            (b"null", None),
            (b'{"enabled":"true"}', None),
            (b'{"enabled":1}', None),
            (b'{"enabled":true,"other":1}', None),
            (b'{"enabled":true,"write_community":null}', None),
            (b'{"enabled":true,"write_community":1}', None),
            (json.dumps({"enabled": True, "write_community": "x" * 257}).encode(), None),
        )
        for body, declared in bad_payloads:
            reply = send(body, declared=declared)
            assert reply == [(400, safe_error)], (body[:25], reply)
            assert calls == [], "Invalid request must not touch HA"

    def failed(_payload):
        raise RuntimeError("credential-sensitive backend details")

    with patched(_home_assistant_ws=failed):
        assert send(b'{"enabled":true,"write_community":"fixture"}') == [
            (400, safe_error)
        ]


def test_faceplate_upgrade_http_dispatch_contract() -> None:
    """Exercise actual Supervisor-gated stock faceplate action without touching Core."""
    import io
    from types import SimpleNamespace

    events: list[tuple[object, object]] = []
    options = Path("/nonexistent/sv-test-faceplate-options.json")

    def action(options_file, payload):
        events.append((options_file, payload))
        return {"ok": True, "action": payload["action"]}

    def send(body: bytes = b'{"action":"reset"}', *,
             size: str | None = None, allowed: bool = True):
        handler = hub.SupportHandler.__new__(hub.SupportHandler)
        handler.path = "/api/faceplate-upgrades/action/?from=test"
        handler.headers = {"Content-Length": str(len(body)) if size is None else size}
        handler.rfile = io.BytesIO(body)
        handler.server = SimpleNamespace(options_file=options)
        handler._allow_ingress_request = lambda: allowed
        replies: list[tuple[int, object]] = []
        handler._json = lambda response, status=200: replies.append((int(status), response))
        hub.SupportHandler.do_POST(handler)
        return replies

    with patched(_faceplate_upgrade_action=action):
        assert send() == [(200, {"ok": True, "action": "reset"})]
        assert events == [(options, {"action": "reset"})]
        events.clear()
        assert send(allowed=False) == []
        assert events == [], "Denied Supervisor ingress must cause no action"

        for body, length in (
            (b"{}", "0"), (b"{}", "4097"),
            (b"{}", "-1"), (b"{}", "not-a-number"),
            (b"{bad", None), (b"\xff", None),
        ):
            result = send(body, size=length)
            assert len(result) == 1 and result[0][0] == 400, (body, length, result)
            assert result[0][1]["ok"] is False
            assert events == [], "Rejected request must cause no action"

    def invalid(_options, _payload):
        raise ValueError("Invalid faceplate action")

    with patched(_faceplate_upgrade_action=invalid):
        assert send() == [(400, {"ok": False, "error": "Invalid faceplate action"})]

    for failure in (OSError, RuntimeError):
        def unavailable(_options, _payload):
            raise failure("Core faceplate reset unavailable")
        with patched(_faceplate_upgrade_action=unavailable):
            assert send() == [(503, {
                "ok": False, "error": "Core faceplate reset unavailable",
            })]


def test_ui_density_http_dispatch_contract() -> None:
    """Exercise Supervisor-gated UI density POST and its original HA service boundary."""
    import io
    from types import SimpleNamespace

    effects: list[tuple] = []

    def service(domain, name, data):
        effects.append(("service", domain, name, data))

    def preferences():
        effects.append(("preferences",))
        return {"density": "comfortable", "text_size": 14}

    def send(body: bytes = b'{"density":" COMPACT "}', *,
             length: str | None = None, allowed: bool = True):
        handler = hub.SupportHandler.__new__(hub.SupportHandler)
        handler.path = "/api/ui-density/?from=fixture"
        handler.headers = {"Content-Length": str(len(body)) if length is None else length}
        handler.rfile = io.BytesIO(body)
        handler.server = SimpleNamespace()
        handler._allow_ingress_request = lambda: allowed
        replies: list[tuple[int, object]] = []
        handler._json = lambda response, status=200: replies.append((int(status), response))
        hub.SupportHandler.do_POST(handler)
        return replies

    with patched(_home_assistant_service=service, _discovery_ui_preferences=preferences):
        assert send() == [(200, {
            "preferences": {"density": "compact", "text_size": 14}
        })]
        assert effects == [
            ("service", "switch_vision", "set_ui_density", {"density": "compact"}),
            ("preferences",),
        ], effects
        effects.clear()
        assert send(b'{"density":"ultra_dense"}') == [(200, {
            "preferences": {"density": "ultra_dense", "text_size": 14}
        })]
        assert effects[0][3] == {"density": "ultra_dense"}
        effects.clear()

        assert send(allowed=False) == []
        assert effects == [], "Denied ingress must not read preferences or call Core"

        invalid = (
            (b"{}", "0"),
            (b"{}", "-1"),
            (b"{}", "4097"),
            (b"{}", "not-a-number"),
            (b"{broken", None),
            (bytes([255]), None),
            (b"{}", None),
            (b'{"density":"nonsense"}', None),
        )
        for payload, length in invalid:
            replies = send(payload, length=length)
            assert len(replies) == 1 and replies[0][0] == 400, (payload, replies)
            assert effects == [], "Invalid UI density must not call Core"

    def unavailable(*_args):
        raise RuntimeError("UI density service unavailable")

    with patched(_home_assistant_service=unavailable, _discovery_ui_preferences=preferences):
        assert send() == [(400, {"error": "UI density service unavailable"})]
        assert effects == [], "Failed service must not read preferences"


def test_regenerate_yaml_http_dispatch_contract() -> None:
    """Exercise real ingress-gated YAML regeneration with isolated operation/thread effects."""
    import io
    from types import SimpleNamespace

    events: list[tuple] = []
    script = Path("/unused/discovery.sh")
    operation = "SNMP2MQTT YAML regeneration"

    def claim(name):
        events.append(("claim", name))

    def release(name):
        events.append(("release", name))

    def state(**fields):
        events.append(("state", fields))

    def start():
        events.append(("start",))

    def make_thread(*, target, args, daemon):
        assert target is hub._run_discovery
        events.append(("thread", args, daemon))
        return SimpleNamespace(start=start)

    def send(*, allowed: bool = True, path: str = "/api/discovery/regenerate-yaml/?origin=test"):
        handler = hub.SupportHandler.__new__(hub.SupportHandler)
        handler.path = path
        handler.headers = {"Content-Length": "0"}
        handler.rfile = io.BytesIO()
        handler.server = SimpleNamespace(discovery_script=script)
        handler._allow_ingress_request = lambda: allowed
        replies: list[tuple[int, object]] = []
        handler._json = lambda data, status=200: replies.append((int(status), data))
        hub.SupportHandler.do_POST(handler)
        return replies

    with patched(
        _claim_operation=claim, _release_operation=release,
        _DISCOVERY_STOP_REQUESTED=SimpleNamespace(clear=lambda: events.append(("clear",))),
        _set_discovery_state=state,
        threading=SimpleNamespace(Thread=make_thread),
    ):
        assert send(allowed=False) == []
        assert events == [], "Rejected Supervisor ingress must not touch regeneration state"
        assert send() == [(202, {"started": True, "mode": "regenerate_yaml"})]
        assert [item[0] for item in events] == ["claim", "clear", "state", "thread", "start"]
        assert events[0] == ("claim", operation)
        fields = events[2][1]
        assert fields["running"] is True and fields["mode"] == "regenerate_yaml"
        assert fields["phase"] == "preparing" and fields["success"] is None
        assert fields["snmp2mqtt"]["status"] == "Waiting"
        assert events[3] == ("thread", (script, "regenerate_yaml"), True)
        events.clear()

        def conflict(_name):
            raise hub.OperationConflict("Discovery is already running")

        with patched(_claim_operation=conflict):
            assert send() == [(409, {"error": "Discovery is already running"})]
        assert events == [], "Busy operation must not clear stop/state or start a thread"

        def failed_start():
            events.append(("start-failed",))
            raise RuntimeError("Thread could not start")

        with patched(threading=SimpleNamespace(Thread=lambda **kw: SimpleNamespace(start=failed_start))):
            try:
                send()
            except RuntimeError as exc:
                assert str(exc) == "Thread could not start"
            else:
                raise AssertionError("Failed thread.start must preserve the original exception")
        assert [item[0] for item in events] == [
            "claim", "clear", "state", "start-failed", "release"
        ], events
        assert events[-1] == ("release", operation)


def test_discovery_start_stop_http_dispatch_contract() -> None:
    """Exercise actual ingress, operation and worker lifecycle for run/stop routes."""
    import io
    from types import SimpleNamespace

    events: list[tuple] = []
    script = Path("/unused/discovery.sh")
    stop_allowed = [True]

    def claim(name):
        events.append(("claim", name))

    def release(name):
        events.append(("release", name))

    def state(**fields):
        events.append(("state", fields))

    def make_thread(*, target, args, daemon):
        assert target is hub._run_discovery
        events.append(("thread", args, daemon))
        return SimpleNamespace(start=lambda: events.append(("start-thread",)))

    def stop():
        events.append(("stop-request",))
        return stop_allowed[0]

    def send(route: str, *, allowed: bool = True):
        handler = hub.SupportHandler.__new__(hub.SupportHandler)
        handler.path = route + "/?from=fixture"
        handler.headers = {"Content-Length": "0"}
        handler.rfile = io.BytesIO()
        handler.server = SimpleNamespace(discovery_script=script)
        handler._allow_ingress_request = lambda: allowed
        replies: list[tuple[int, object]] = []
        handler._json = lambda body, status=200: replies.append((int(status), body))
        handler.send_error = lambda status: replies.append((int(status), "not found"))
        hub.SupportHandler.do_POST(handler)
        return replies

    with patched(
        _claim_operation=claim,
        _release_operation=release,
        _DISCOVERY_STOP_REQUESTED=SimpleNamespace(clear=lambda: events.append(("clear",))),
        _set_discovery_state=state,
        _request_discovery_stop=stop,
        threading=SimpleNamespace(Thread=make_thread),
    ):
        for route in ("/api/discovery/start", "/api/discovery/stop"):
            assert send(route, allowed=False) == []
            assert events == [], "Denied Supervisor ingress cannot start or stop Discovery"

        assert send("/api/discovery/start") == [(202, {"started": True})]
        assert [row[0] for row in events] == [
            "claim", "clear", "state", "thread", "start-thread"
        ], events
        assert events[0] == ("claim", "Discovery")
        fields = events[2][1]
        assert fields["running"] is True and fields["mode"] == "discovery"
        assert fields["phase"] == "preparing" and fields["success"] is None
        assert fields["activity"] == "Validating configured switches"
        assert fields["snmp2mqtt"]["status"] == "Waiting"
        assert events[3] == ("thread", (script,), True)
        assert not any(row[0] == "release" for row in events)
        events.clear()

        assert send("/api/discovery/stop") == [(202, {"stopping": True})]
        assert events == [("stop-request",)]
        events.clear()

        stop_allowed[0] = False
        assert send("/api/discovery/stop") == [(409, {"error": "Discovery is not running."})]
        assert events == [("stop-request",)]
        events.clear()

        def conflict(_name):
            raise hub.OperationConflict("Discovery busy")

        with patched(_claim_operation=conflict):
            assert send("/api/discovery/start") == [(409, {"error": "Discovery busy"})]
        assert events == [], "Conflicting start must not modify state or launch worker"

        def bad_start():
            events.append(("failed-thread",))
            raise RuntimeError("Worker start failed")

        with patched(threading=SimpleNamespace(Thread=lambda **kw: SimpleNamespace(start=bad_start))):
            try:
                send("/api/discovery/start")
            except RuntimeError as exc:
                assert str(exc) == "Worker start failed"
            else:
                raise AssertionError("Worker start failure must propagate")
        assert [row[0] for row in events] == [
            "claim", "clear", "state", "failed-thread", "release"
        ], events
        assert events[-1] == ("release", "Discovery")
        events.clear()

        assert send("/api/discovery/not-a-route") == [(404, "not found")]
        assert events == [], "Unknown Discovery action must be rejected"


def main() -> int:
    test_discovery_start_stop_http_dispatch_contract()
    print("PASS: Discovery start/stop ingress, state, worker, conflict and failure boundaries")
    test_regenerate_yaml_http_dispatch_contract()
    print("PASS: YAML regeneration ingress, operation lock, state, thread and error contracts")
    test_ui_density_http_dispatch_contract()
    print("PASS: UI density ingress, normalized service dispatch, size and error boundaries")
    test_faceplate_upgrade_http_dispatch_contract()
    print("PASS: faceplate action ingress, payload-size, dispatch and HTTP error boundaries")
    test_hp_optics_http_dispatch_contract()
    print("PASS: HP optics ingress, credential input validation and redacted errors")
    test_hub_settings_http_dispatch_contract()
    print("PASS: Hub settings ingress, route-specific locks, request limits and error semantics")
    test_autodiscover_http_dispatch_contract()
    print("PASS: AutoDiscover HTTP ingress, serialized locks, request limits and error contracts")
    test_unifi_http_dispatch_contract()
    print("PASS: UniFi2MQTT ingress, operations, payload limits and safe error contracts")
    test_configured_device_http_dispatch_contract()
    print("PASS: configured-device HTTP dispatch, serialization, ingress and error contracts")
    with tempfile.TemporaryDirectory(prefix="sv-hub-save-reset-contracts-") as temp:
        with patched(DEFAULT_DEVICE_CONTROL=Path(temp) / "device-control.json"):
            test_discovery_save_and_write_only_secrets()
            print("PASS: Discovery settings save, rename, manual-model and secret preservation contracts")
            test_saved_row_effective_config_is_canonical_fresh_and_secret_safe()
            print("PASS: Saved switch rows use fresh canonical effective config with secret-safe provenance")
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
