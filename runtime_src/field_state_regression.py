#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile

import core_bridge
import dashboard_device_order
import discovery_contract_entrypoint as authority
import device_control
import support_diagnostics as diagnostics


# 1. A successful unchanged visible-dashboard projection must still advance the
# generation mtime consumed by the native Switch Vision panel.
with tempfile.TemporaryDirectory(prefix="sv-field-state-mtime-") as tmp:
    root = Path(tmp)
    dashboard = root / "generated-dashboard-card.yaml"
    dashboard.write_text(
        """views:
  - title: Switch Vision
    cards:
      - type: custom:switch-vision-3650
        title: API switch
        unifi_device_id: fixture-u1
""",
        encoding="utf-8",
    )
    control = root / "device-control.json"
    device_control.save(
        {
            "schema_version": 2,
            "order": ["unifi:fixture-u1"],
            "states": {"unifi:fixture-u1": "enabled"},
            "added_at": {},
        },
        control,
    )
    os.utime(dashboard, (1000, 1000))
    result = dashboard_device_order.apply_dashboard_order(
        dashboard,
        control,
        source_path=dashboard,
        snmp_states={},
    )
    assert result["visible_changed"] is False, result
    assert dashboard.stat().st_mtime > 1000, dashboard.stat().st_mtime


# 2. The physical-contract API/UniFi-only branch must replace stale report and
# last-run state, return clean success, and explicitly say SNMP2MQTT is not
# required.
originals = {}
for name in (
    "LEGACY", "PREPARE", "REGISTRY", "DEFAULT_OPTIONS", "DEVICE_CONTROL_PATH",
    "_read_options", "_stage_live_collection", "_stage_options", "_publish_contracts",
    "_append_unifi_dashboard_cards", "_append_display_fallbacks",
    "_project_generated_dashboard",
):
    originals[name] = getattr(authority, name)

try:
    with tempfile.TemporaryDirectory(prefix="sv-field-state-api-only-") as tmp:
        root = Path(tmp)
        for name in ("legacy.sh", "prepare.sh", "registry.json"):
            (root / name).write_text("{}\n", encoding="utf-8")
        report = root / "discovery-report.txt"
        last_run = root / "last-discovery-run.txt"
        card = root / "generated-dashboard-card.yaml"
        report.write_text("Status: live SNMP collection failed\n", encoding="utf-8")
        last_run.write_text("Result: FAILED\n", encoding="utf-8")
        options = {
            "report_path": str(report),
            "last_run_summary_path": str(last_run),
            "generated_card_path": str(card),
            "generated_yaml_path": str(root / "generated-snmp2mqtt.yaml"),
        }
        authority.LEGACY = root / "legacy.sh"
        authority.PREPARE = root / "prepare.sh"
        authority.REGISTRY = root / "registry.json"
        authority.DEFAULT_OPTIONS = root / "options.json"
        authority.DEVICE_CONTROL_PATH = root / "device-control.json"
        authority._read_options = lambda _path: dict(options)
        authority._stage_live_collection = lambda _options, _work: ([], False)
        authority._stage_options = lambda _options, _work, _run: (dict(options), [], [])
        authority._publish_contracts = lambda *_args, **_kwargs: None

        def add_unifi(path: Path):
            path.write_text(
                """views:
  - title: Switch Vision
    cards:
      - type: custom:switch-vision-3650
        title: API switch
        unifi_device_id: fixture-u1
""",
                encoding="utf-8",
            )
            return 1, 0

        authority._append_unifi_dashboard_cards = add_unifi
        authority._append_display_fallbacks = lambda *_args, **_kwargs: (0, 0)
        authority._project_generated_dashboard = (
            lambda output, _options, fresh_path=None:
            output.write_text(
                Path(fresh_path).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        )
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = authority.main()
        output = stream.getvalue()
        assert code == 0, output
        assert "SV_RESULT|warnings=false|degraded=false|snmp2mqtt_required=false" in output
        report_text = report.read_text(encoding="utf-8")
        last_text = last_run.read_text(encoding="utf-8")
        assert "Status: success" in report_text, report_text
        assert "live SNMP collection failed" not in report_text, report_text
        assert "Result: SUCCESS" in last_text, last_text
        assert "SNMP2MQTT handoff: not required" in last_text, last_text
finally:
    for name, value in originals.items():
        setattr(authority, name, value)


# 3. The installed Core bridge wrapper must preserve the large-message max_size
# keyword used by Complete Configuration backup/export and restore.
recorded = {}
original_execute = core_bridge.execute_home_assistant_ws
try:
    def fake_execute(command, *, read_token, websocket_connect, max_size=0):
        recorded["command"] = dict(command)
        recorded["token"] = read_token()
        recorded["max_size"] = max_size
        return {"ok": True}

    core_bridge.execute_home_assistant_ws = fake_execute
    fake_web = SimpleNamespace(
        _read_supervisor_token=lambda: "fixture-token",
        websocket_connect=lambda *_args, **_kwargs: None,
        _core_bridge_log_sink=lambda *_args, **_kwargs: None,
    )
    core_bridge.install(fake_web)
    response = fake_web._home_assistant_ws(
        {"type": "switch_vision/get_backup_asset"},
        max_size=64 * 1024 * 1024,
    )
    assert response == {"ok": True}
    assert recorded["max_size"] == 64 * 1024 * 1024, recorded
    assert recorded["token"] == "fixture-token"
finally:
    core_bridge.execute_home_assistant_ws = original_execute


# 4. UniFi connectivity diagnostics must be privacy-safe even when the private
# controller URL/key/site are used internally.
with tempfile.TemporaryDirectory(prefix="sv-field-state-unifi-diag-") as tmp:
    root = Path(tmp)
    original_info = diagnostics._unifi2mqtt_supervisor_info
    original_getaddrinfo = diagnostics.socket.getaddrinfo
    original_create_connection = diagnostics.socket.create_connection
    original_ssl_context = diagnostics.ssl.create_default_context

    class FakeSocket:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False

    class FakeTLS(FakeSocket):
        def version(self):
            return "TLSv1.3"

    class FakeContext:
        check_hostname = True
        verify_mode = diagnostics.ssl.CERT_REQUIRED
        def wrap_socket(self, _sock, server_hostname=None):
            assert server_hostname == "private-controller.invalid"
            return FakeTLS()

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload
            self.status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self, *_args):
            return json.dumps(self.payload).encode("utf-8")

    def fake_opener(request, **_kwargs):
        url = request.full_url
        if url.endswith("/sites"):
            return FakeResponse({"data": [{"id": "private-site-id", "name": "Private Site"}]})
        if url.endswith("/devices"):
            return FakeResponse({"data": [{"id": "private-device-id"}]})
        raise AssertionError(url)

    try:
        diagnostics._unifi2mqtt_supervisor_info = lambda *_args, **_kwargs: (
            "fixture_unifi2mqtt",
            {
                "options": {
                    "local_controller_url": "https://private-controller.invalid:11443",
                    "local_api_key": "private-api-key",
                    "local_site_id": "auto",
                    "local_verify_ssl": False,
                }
            },
        )
        diagnostics.socket.getaddrinfo = (
            lambda *_args, **_kwargs:
            [(diagnostics.socket.AF_INET, diagnostics.socket.SOCK_STREAM, 6, "", ("192.0.2.55", 11443))]
        )
        diagnostics.socket.create_connection = lambda *_args, **_kwargs: FakeSocket()
        diagnostics.ssl.create_default_context = lambda: FakeContext()

        result = diagnostics.capture_unifi_connectivity_diagnostics(
            root,
            opener=fake_opener,
            token_reader=lambda: "supervisor-token",
        )
        assert result["status"] == "ok", result
        assert [row["stage"] for row in result["stages"]] == [
            "dns", "tcp", "tls", "sites_api", "site_resolution", "devices_api"
        ], result
        serialized = json.dumps(result)
        for private in (
            "private-controller.invalid",
            "192.0.2.55",
            "private-api-key",
            "private-site-id",
            "Private Site",
            "private-device-id",
            "supervisor-token",
        ):
            assert private not in serialized, (private, serialized)
        assert result["privacy"]["controller_address_included"] is False
        assert result["privacy"]["api_key_included"] is False
    finally:
        diagnostics._unifi2mqtt_supervisor_info = original_info
        diagnostics.socket.getaddrinfo = original_getaddrinfo
        diagnostics.socket.create_connection = original_create_connection
        diagnostics.ssl.create_default_context = original_ssl_context

print("Field-state regression: PASS")
