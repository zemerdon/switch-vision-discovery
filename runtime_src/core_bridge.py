#!/usr/bin/env python3
"""Typed, sanitized Discovery -> Home Assistant Core WebSocket bridge.

The Discovery Hub historically collapsed every WebSocket failure into a generic
RuntimeError and HTTP 502.  This module preserves the existing external route
contract while making the failure stage observable and safe to log.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable


_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(\bbearer\s+)[^\s,;]+"),
    re.compile(r'(?i)(["\']?access_token["\']?\s*[:=]\s*["\']?)[^"\'\s,}]+'),
    re.compile(r'(?i)(["\']?token["\']?\s*[:=]\s*["\']?)[^"\'\s,}]+'),
)


def sanitize_bridge_text(value: Any, *, max_length: int = 240) -> str:
    """Return one-line diagnostic text with credential-shaped values removed."""
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(r"\1[redacted]", text)
    text = " ".join(text.split())
    if len(text) > max_length:
        text = text[: max_length - 1] + "…"
    return text


class HomeAssistantWebSocketError(RuntimeError):
    """A classified, credential-safe Home Assistant WebSocket failure."""

    def __init__(
        self,
        message: str,
        *,
        kind: str,
        ha_error_code: str | None = None,
        cause_type: str | None = None,
    ) -> None:
        super().__init__(sanitize_bridge_text(message))
        self.kind = str(kind or "unknown").strip() or "unknown"
        self.ha_error_code = (
            sanitize_bridge_text(ha_error_code, max_length=96)
            if ha_error_code
            else None
        )
        self.cause_type = (
            sanitize_bridge_text(cause_type, max_length=96)
            if cause_type
            else None
        )


def core_bridge_error_payload(
    exc: HomeAssistantWebSocketError,
    *,
    operation: str,
) -> dict[str, Any]:
    """Build a browser-safe diagnostic payload for future/alternate routes."""
    payload: dict[str, Any] = {
        "error": sanitize_bridge_text(str(exc)),
        "error_type": exc.kind,
        "operation": sanitize_bridge_text(operation, max_length=96),
    }
    if exc.ha_error_code:
        payload["ha_error_code"] = exc.ha_error_code
    if exc.cause_type:
        payload["cause_type"] = exc.cause_type
    return payload


def log_core_bridge_failure(
    operation: str,
    exc: HomeAssistantWebSocketError,
    *,
    sink: Callable[[str], None] = print,
) -> None:
    """Emit one structured, sanitized line without traceback locals/secrets."""
    fields = [
        "[Switch Vision Core Bridge]",
        f"operation={sanitize_bridge_text(operation, max_length=96) or 'unknown'}",
        f"kind={exc.kind}",
    ]
    if exc.ha_error_code:
        fields.append(f"ha_error_code={exc.ha_error_code}")
    if exc.cause_type:
        fields.append(f"cause={exc.cause_type}")
    fields.append(f"detail={sanitize_bridge_text(str(exc))}")
    sink(" ".join(fields))


def _recv_json(connection: Any, *, stage: str) -> dict[str, Any]:
    try:
        raw = connection.recv(timeout=12)
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HomeAssistantWebSocketError(
            f"Home Assistant WebSocket returned invalid JSON during {stage}.",
            kind="protocol",
            cause_type=type(exc).__name__,
        ) from exc
    except HomeAssistantWebSocketError:
        raise
    except Exception as exc:  # transport/timeout/socket library failures
        raise HomeAssistantWebSocketError(
            "Home Assistant WebSocket transport failed.",
            kind="transport",
            cause_type=type(exc).__name__,
        ) from exc

    if not isinstance(payload, dict):
        raise HomeAssistantWebSocketError(
            f"Home Assistant WebSocket returned an invalid {stage} payload.",
            kind="protocol",
        )
    return payload


def execute_home_assistant_ws(
    command: dict[str, Any],
    *,
    read_token: Callable[[], str],
    websocket_connect: Callable[..., Any],
) -> Any:
    """Execute one Switch Vision Home Assistant WebSocket command."""
    command_type = str(command.get("type") or "").strip()
    if not command_type.startswith("switch_vision/"):
        raise ValueError("Unsupported Home Assistant WebSocket command.")

    token = str(read_token() or "").strip()
    if not token:
        raise HomeAssistantWebSocketError(
            "Home Assistant API token is unavailable.",
            kind="token_unavailable",
        )

    try:
        connection_context = websocket_connect(
            "ws://supervisor/core/websocket",
            open_timeout=12,
            close_timeout=5,
            max_size=4 * 1024 * 1024,
        )
    except Exception as exc:
        raise HomeAssistantWebSocketError(
            "Home Assistant WebSocket transport failed.",
            kind="transport",
            cause_type=type(exc).__name__,
        ) from exc

    try:
        with connection_context as connection:
            required = _recv_json(connection, stage="authentication request")
            if required.get("type") != "auth_required":
                raise HomeAssistantWebSocketError(
                    "Home Assistant WebSocket did not request authentication.",
                    kind="protocol",
                )

            try:
                connection.send(
                    json.dumps({"type": "auth", "access_token": token})
                )
            except Exception as exc:
                raise HomeAssistantWebSocketError(
                    "Home Assistant WebSocket transport failed while authenticating.",
                    kind="transport",
                    cause_type=type(exc).__name__,
                ) from exc

            authenticated = _recv_json(connection, stage="authentication response")
            if authenticated.get("type") != "auth_ok":
                raise HomeAssistantWebSocketError(
                    "Home Assistant WebSocket authentication failed.",
                    kind="authentication",
                )

            payload = dict(command)
            payload["id"] = 1
            try:
                connection.send(json.dumps(payload))
            except Exception as exc:
                raise HomeAssistantWebSocketError(
                    "Home Assistant WebSocket transport failed while sending the Core command.",
                    kind="transport",
                    cause_type=type(exc).__name__,
                ) from exc

            while True:
                response = _recv_json(connection, stage="command response")
                if response.get("id") != 1:
                    continue

                if response.get("type") != "result":
                    raise HomeAssistantWebSocketError(
                        "Home Assistant WebSocket returned an unexpected command response.",
                        kind="protocol",
                    )

                if response.get("success") is not True:
                    error = response.get("error")
                    if isinstance(error, dict):
                        code = str(error.get("code") or "").strip() or None
                        detail = str(error.get("message") or "").strip()
                    else:
                        code = None
                        detail = str(error or "").strip()

                    safe_detail = sanitize_bridge_text(detail)
                    if code and safe_detail:
                        message = (
                            f"Switch Vision Core command failed [{sanitize_bridge_text(code, max_length=96)}]: "
                            f"{safe_detail}"
                        )
                    elif code:
                        message = (
                            "Switch Vision Core command failed "
                            f"[{sanitize_bridge_text(code, max_length=96)}]."
                        )
                    elif safe_detail:
                        message = f"Switch Vision Core command failed: {safe_detail}"
                    else:
                        message = "Switch Vision Core command failed."

                    raise HomeAssistantWebSocketError(
                        message,
                        kind="core_command",
                        ha_error_code=code,
                    )

                return response.get("result")

    except HomeAssistantWebSocketError:
        raise
    except Exception as exc:
        raise HomeAssistantWebSocketError(
            "Home Assistant WebSocket transport failed.",
            kind="transport",
            cause_type=type(exc).__name__,
        ) from exc


def _operation_name(command: dict[str, Any]) -> str:
    command_type = str(command.get("type") or "").strip()
    if command_type == "switch_vision/list_calibrations":
        return "calibration_profiles"
    return command_type or "unknown"


def install(support_web_module: Any) -> None:
    """Install the typed bridge into the existing Hub module at startup/tests."""
    support_web_module.HomeAssistantWebSocketError = HomeAssistantWebSocketError
    support_web_module._core_bridge_error_payload = core_bridge_error_payload

    if not hasattr(support_web_module, "_core_bridge_log_sink"):
        support_web_module._core_bridge_log_sink = print

    def _log(operation: str, exc: HomeAssistantWebSocketError) -> None:
        log_core_bridge_failure(
            operation,
            exc,
            sink=support_web_module._core_bridge_log_sink,
        )

    support_web_module._log_core_bridge_failure = _log

    def _home_assistant_ws(command: dict[str, Any]) -> Any:
        operation = _operation_name(command)
        try:
            return execute_home_assistant_ws(
                command,
                read_token=support_web_module._read_supervisor_token,
                websocket_connect=support_web_module.websocket_connect,
            )
        except HomeAssistantWebSocketError as exc:
            _log(operation, exc)
            raise

    support_web_module._home_assistant_ws = _home_assistant_ws
