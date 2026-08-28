#!/usr/bin/env python3
"""Executable contracts for the Discovery -> Switch Vision Core calibration bridge.

No live Home Assistant, Supervisor, calibration data, or user data is touched.
The tests exercise the WebSocket bridge with scripted in-memory connections so
transport/auth/Core-command failures cannot collapse into an anonymous HTTP 502.
"""
from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime_src"))

import core_bridge  # noqa: E402
import support_web as hub  # noqa: E402

core_bridge.install(hub)


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


class ScriptedConnection:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def recv(self, timeout=None):
        del timeout
        if not self.messages:
            raise AssertionError("scripted WebSocket response queue exhausted")
        message = self.messages.pop(0)
        if isinstance(message, BaseException):
            raise message
        return json.dumps(message)

    def send(self, payload):
        self.sent.append(json.loads(payload))


def expect_bridge_error(fn, *, kind: str, ha_error_code: str | None = None):
    try:
        fn()
    except hub.HomeAssistantWebSocketError as exc:
        assert exc.kind == kind, (kind, exc.kind, str(exc))
        assert exc.ha_error_code == ha_error_code, (
            ha_error_code,
            exc.ha_error_code,
            str(exc),
        )
        return exc
    except Exception as exc:  # noqa: BLE001 - make legacy/generic failure obvious
        raise AssertionError(
            f"Expected HomeAssistantWebSocketError(kind={kind!r}), "
            f"got {type(exc).__name__}: {exc}"
        ) from exc
    raise AssertionError(f"Expected HomeAssistantWebSocketError(kind={kind!r})")


def ws_factory(connection):
    def connect(_url, **_kwargs):
        return connection
    return connect


def test_successful_calibration_list_round_trip() -> None:
    connection = ScriptedConnection([
        {"type": "auth_required"},
        {"type": "auth_ok"},
        {
            "id": 1,
            "type": "result",
            "success": True,
            "result": {"items": [{"profile": "factory-demo"}]},
        },
    ])
    with patched(
        _read_supervisor_token=lambda: "test-token",
        websocket_connect=ws_factory(connection),
    ):
        result = hub._home_assistant_ws(
            {"type": "switch_vision/list_calibrations"}
        )
    assert result == {"items": [{"profile": "factory-demo"}]}
    assert connection.sent[0] == {"type": "auth", "access_token": "test-token"}
    assert connection.sent[1] == {
        "type": "switch_vision/list_calibrations",
        "id": 1,
    }


def test_missing_token_is_classified() -> None:
    with patched(_read_supervisor_token=lambda: ""):
        exc = expect_bridge_error(
            lambda: hub._home_assistant_ws(
                {"type": "switch_vision/list_calibrations"}
            ),
            kind="token_unavailable",
        )
    assert "token" in str(exc).casefold()


def test_auth_rejection_is_classified() -> None:
    connection = ScriptedConnection([
        {"type": "auth_required"},
        {"type": "auth_invalid", "message": "Invalid access token"},
    ])
    with patched(
        _read_supervisor_token=lambda: "test-token",
        websocket_connect=ws_factory(connection),
    ):
        exc = expect_bridge_error(
            lambda: hub._home_assistant_ws(
                {"type": "switch_vision/list_calibrations"}
            ),
            kind="authentication",
        )
    assert "authentication" in str(exc).casefold()


def test_transport_failure_is_classified_without_secret() -> None:
    def connect(_url, **_kwargs):
        raise TimeoutError("Authorization: Bearer SHOULD_NOT_APPEAR")

    with patched(
        _read_supervisor_token=lambda: "test-token",
        websocket_connect=connect,
    ):
        exc = expect_bridge_error(
            lambda: hub._home_assistant_ws(
                {"type": "switch_vision/list_calibrations"}
            ),
            kind="transport",
        )
    assert exc.cause_type == "TimeoutError"
    assert "SHOULD_NOT_APPEAR" not in str(exc)


def test_core_command_error_preserves_home_assistant_code() -> None:
    connection = ScriptedConnection([
        {"type": "auth_required"},
        {"type": "auth_ok"},
        {
            "id": 1,
            "type": "result",
            "success": False,
            "error": {
                "code": "unknown_command",
                "message": "Unknown command.",
            },
        },
    ])
    with patched(
        _read_supervisor_token=lambda: "test-token",
        websocket_connect=ws_factory(connection),
    ):
        exc = expect_bridge_error(
            lambda: hub._home_assistant_ws(
                {"type": "switch_vision/list_calibrations"}
            ),
            kind="core_command",
            ha_error_code="unknown_command",
        )
    assert "Unknown command" in str(exc)


def test_calibration_error_payload_and_log_are_safe() -> None:
    exc = hub.HomeAssistantWebSocketError(
        "Switch Vision Core command failed: Authorization: Bearer SECRET_VALUE",
        kind="core_command",
        ha_error_code="unknown_command",
        cause_type=None,
    )
    payload = hub._core_bridge_error_payload(
        exc,
        operation="calibration_profiles",
    )
    assert payload["error_type"] == "core_command"
    assert payload["ha_error_code"] == "unknown_command"
    assert "SECRET_VALUE" not in json.dumps(payload)

    lines: list[str] = []
    with patched(_core_bridge_log_sink=lines.append):
        hub._log_core_bridge_failure(
            "calibration_profiles",
            exc,
        )
    assert len(lines) == 1
    assert "operation=calibration_profiles" in lines[0]
    assert "kind=core_command" in lines[0]
    assert "ha_error_code=unknown_command" in lines[0]
    assert "SECRET_VALUE" not in lines[0]


def main() -> int:
    test_successful_calibration_list_round_trip()
    print("PASS: Calibration/Core WebSocket success round trip")
    test_missing_token_is_classified()
    print("PASS: Missing Supervisor token is classified")
    test_auth_rejection_is_classified()
    print("PASS: Home Assistant authentication rejection is classified")
    test_transport_failure_is_classified_without_secret()
    print("PASS: WebSocket transport failure is classified without leaking detail")
    test_core_command_error_preserves_home_assistant_code()
    print("PASS: Core command failure preserves Home Assistant error code")
    test_calibration_error_payload_and_log_are_safe()
    print("PASS: Calibration bridge browser/log diagnostics are structured and sanitized")
    print("Switch Vision Calibration/Core bridge contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
