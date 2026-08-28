#!/usr/bin/env python3
"""Typed, sanitized Discovery -> Home Assistant Core WebSocket bridge.

The Discovery Hub historically collapsed every WebSocket failure into a generic
RuntimeError and HTTP 502. This module preserves the existing external route
contract while making the failure stage observable and safe to log or include
in Support My Switch diagnostics.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
from typing import Any, Callable


_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(\bbearer\s+)[^\s,;]+"),
    re.compile(r'(?i)(["\']?access_token["\']?\s*[:=]\s*["\']?)[^"\'\s,}]+'),
    re.compile(r'(?i)(["\']?token["\']?\s*[:=]\s*["\']?)[^"\'\s,}]+'),
)

_DIAGNOSTIC_SCHEMA = "switch-vision.core-bridge-diagnostic.v1"


def sanitize_bridge_text(value: Any, *, max_length: int = 240) -> str:
    """Return one-line diagnostic text with credential-shaped values removed."""
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(r"\1[redacted]", text)
    text = " ".join(text.split())
    if len(text) > max_length:
        text = text[: max_length - 1] + "…"
    return text


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_diagnostic_id() -> str:
    return f"SV-CB-{secrets.token_hex(6).upper()}"


class HomeAssistantWebSocketError(RuntimeError):
    """A classified, credential-safe Home Assistant WebSocket failure."""

    def __init__(
        self,
        message: str,
        *,
        kind: str,
        ha_error_code: str | None = None,
        cause_type: str | None = None,
        stage: str = "unknown",
        diagnostic_id: str | None = None,
        error_class: str | None = None,
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
        self.stage = sanitize_bridge_text(stage, max_length=64) or "unknown"
        self.diagnostic_id = (
            sanitize_bridge_text(diagnostic_id, max_length=64)
            if diagnostic_id
            else None
        )
        self.error_class = (
            sanitize_bridge_text(error_class, max_length=96)
            if error_class
            else None
        )


def _stable_error_class(exc: HomeAssistantWebSocketError) -> str:
    if exc.kind == "token_unavailable":
        return "TOKEN_MISSING"
    if exc.kind == "authentication":
        return "WS_AUTH_FAILED"
    if exc.kind == "transport":
        return "WS_TRANSPORT_FAILED"
    if exc.kind == "protocol":
        return "WS_PROTOCOL_FAILED"
    if exc.kind == "core_command" and exc.ha_error_code == "unknown_command":
        return "CORE_COMMAND_UNAVAILABLE"
    if exc.kind == "core_command":
        return "CORE_COMMAND_FAILED"
    return "CORE_BRIDGE_FAILED"


def core_bridge_error_payload(
    exc: HomeAssistantWebSocketError,
    *,
    operation: str,
) -> dict[str, Any]:
    """Build a browser-safe diagnostic payload for the failing route."""
    payload: dict[str, Any] = {
        "error": sanitize_bridge_text(str(exc)),
        "error_type": exc.kind,
        "operation": sanitize_bridge_text(operation, max_length=96),
    }
    if exc.ha_error_code:
        payload["ha_error_code"] = exc.ha_error_code
    if exc.cause_type:
        payload["cause_type"] = exc.cause_type
    if exc.stage and exc.stage != "unknown":
        payload["stage"] = exc.stage
    if exc.error_class:
        payload["error_class"] = exc.error_class
    if exc.diagnostic_id:
        payload["diagnostic_id"] = exc.diagnostic_id
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
    if exc.stage and exc.stage != "unknown":
        fields.append(f"stage={exc.stage}")
    if exc.error_class:
        fields.append(f"error_class={exc.error_class}")
    if exc.diagnostic_id:
        fields.append(f"diagnostic_id={exc.diagnostic_id}")
    if exc.ha_error_code:
        fields.append(f"ha_error_code={exc.ha_error_code}")
    if exc.cause_type:
        fields.append(f"cause={exc.cause_type}")
    fields.append(f"detail={sanitize_bridge_text(str(exc))}")
    sink(" ".join(fields))


def _recv_json(
    connection: Any,
    *,
    stage: str,
    error_stage: str,
) -> dict[str, Any]:
    try:
        raw = connection.recv(timeout=12)
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HomeAssistantWebSocketError(
            f"Home Assistant WebSocket returned invalid JSON during {stage}.",
            kind="protocol",
            cause_type=type(exc).__name__,
            stage=error_stage,
        ) from exc
    except HomeAssistantWebSocketError:
        raise
    except Exception as exc:
        raise HomeAssistantWebSocketError(
            "Home Assistant WebSocket transport failed.",
            kind="transport",
            cause_type=type(exc).__name__,
            stage=error_stage,
        ) from exc

    if not isinstance(payload, dict):
        raise HomeAssistantWebSocketError(
            f"Home Assistant WebSocket returned an invalid {stage} payload.",
            kind="protocol",
            stage=error_stage,
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

    try:
        token = str(read_token() or "").strip()
    except Exception as exc:
        raise HomeAssistantWebSocketError(
            "Home Assistant API token could not be read.",
            kind="token_unavailable",
            cause_type=type(exc).__name__,
            stage="token",
        ) from exc
    if not token:
        raise HomeAssistantWebSocketError(
            "Home Assistant API token is unavailable.",
            kind="token_unavailable",
            stage="token",
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
            stage="websocket_connect",
        ) from exc

    try:
        with connection_context as connection:
            required = _recv_json(
                connection,
                stage="authentication request",
                error_stage="auth",
            )
            if required.get("type") != "auth_required":
                raise HomeAssistantWebSocketError(
                    "Home Assistant WebSocket did not request authentication.",
                    kind="protocol",
                    stage="auth",
                )

            try:
                connection.send(json.dumps({"type": "auth", "access_token": token}))
            except Exception as exc:
                raise HomeAssistantWebSocketError(
                    "Home Assistant WebSocket transport failed while authenticating.",
                    kind="transport",
                    cause_type=type(exc).__name__,
                    stage="auth",
                ) from exc

            authenticated = _recv_json(
                connection,
                stage="authentication response",
                error_stage="auth",
            )
            if authenticated.get("type") != "auth_ok":
                raise HomeAssistantWebSocketError(
                    "Home Assistant WebSocket authentication failed.",
                    kind="authentication",
                    stage="auth",
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
                    stage="command",
                ) from exc

            while True:
                response = _recv_json(
                    connection,
                    stage="command response",
                    error_stage="response",
                )
                if response.get("id") != 1:
                    continue

                if response.get("type") != "result":
                    raise HomeAssistantWebSocketError(
                        "Home Assistant WebSocket returned an unexpected command response.",
                        kind="protocol",
                        stage="response",
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
                        stage="response",
                    )

                return response.get("result")

    except HomeAssistantWebSocketError:
        raise
    except Exception as exc:
        raise HomeAssistantWebSocketError(
            "Home Assistant WebSocket transport failed.",
            kind="transport",
            cause_type=type(exc).__name__,
            stage="websocket_connect",
        ) from exc


def _operation_name(command: dict[str, Any]) -> str:
    command_type = str(command.get("type") or "").strip()
    if command_type == "switch_vision/list_calibrations":
        return "calibration_profiles"
    return command_type or "unknown"


def _core_command_registered(
    *,
    status: str,
    exc: HomeAssistantWebSocketError | None,
) -> bool | None:
    if status == "ok":
        return True
    if exc is None:
        return None
    if exc.kind == "core_command":
        return exc.ha_error_code != "unknown_command"
    return None


def _diagnostic_snapshot(
    *,
    command_type: str,
    route_operation: str,
    status: str,
    token_present: bool,
    diagnostic_id: str,
    discovery_version: str,
    exc: HomeAssistantWebSocketError | None = None,
) -> dict[str, Any]:
    error_class = _stable_error_class(exc) if exc is not None else None
    stage = exc.stage if exc is not None else "response"
    message = (
        sanitize_bridge_text(str(exc))
        if exc is not None
        else "Switch Vision Core calibration command completed successfully."
    )
    return {
        "schema": _DIAGNOSTIC_SCHEMA,
        "timestamp": _utc_timestamp(),
        "diagnostic_id": diagnostic_id,
        "operation": sanitize_bridge_text(command_type, max_length=128),
        "route_operation": sanitize_bridge_text(route_operation, max_length=96),
        "status": status,
        "stage": stage,
        "error_class": error_class,
        "error_type": exc.kind if exc is not None else None,
        "ha_error_code": exc.ha_error_code if exc is not None else None,
        "cause_type": exc.cause_type if exc is not None else None,
        "token_present": bool(token_present),
        "supervisor_auth_available": bool(token_present),
        "discovery_version": sanitize_bridge_text(discovery_version, max_length=64) or "unknown",
        "core_version": None,
        "core_command_registered": _core_command_registered(status=status, exc=exc),
        "message": message,
    }


def _write_diagnostic_snapshot(path: Path, payload: dict[str, Any]) -> None:
    """Atomically persist one already-sanitized diagnostic document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def install(support_web_module: Any) -> None:
    """Install the typed bridge into the existing Hub module at startup/tests."""
    support_web_module.HomeAssistantWebSocketError = HomeAssistantWebSocketError
    support_web_module._core_bridge_error_payload = core_bridge_error_payload

    if not hasattr(support_web_module, "_core_bridge_log_sink"):
        support_web_module._core_bridge_log_sink = print

    if not hasattr(support_web_module, "_core_bridge_diagnostic_path"):
        switch_vision_root = Path(os.environ.get("SWITCH_VISION_ROOT", "/share/switch_vision"))
        support_web_module._core_bridge_diagnostic_path = (
            switch_vision_root / "diagnostics" / "calibration-core-bridge.json"
        )

    def _log(operation: str, exc: HomeAssistantWebSocketError) -> None:
        log_core_bridge_failure(
            operation,
            exc,
            sink=support_web_module._core_bridge_log_sink,
        )

    support_web_module._log_core_bridge_failure = _log

    def _persist_calibration_diagnostic(
        *,
        command_type: str,
        operation: str,
        status: str,
        token_present: bool,
        diagnostic_id: str,
        exc: HomeAssistantWebSocketError | None = None,
    ) -> None:
        if operation != "calibration_profiles":
            return
        payload = _diagnostic_snapshot(
            command_type=command_type,
            route_operation=operation,
            status=status,
            token_present=token_present,
            diagnostic_id=diagnostic_id,
            discovery_version=os.environ.get("SWITCH_VISION_DISCOVERY_VERSION", "unknown"),
            exc=exc,
        )
        try:
            _write_diagnostic_snapshot(
                Path(support_web_module._core_bridge_diagnostic_path),
                payload,
            )
        except OSError as write_exc:
            support_web_module._core_bridge_log_sink(
                "[Switch Vision Core Bridge] "
                f"diagnostic_id={diagnostic_id} "
                f"diagnostic_write_failed cause={type(write_exc).__name__}"
            )

    support_web_module._persist_calibration_core_bridge_diagnostic = (
        _persist_calibration_diagnostic
    )

    def _home_assistant_ws(command: dict[str, Any]) -> Any:
        operation = _operation_name(command)
        command_type = str(command.get("type") or "").strip() or "unknown"

        try:
            cached_token = str(support_web_module._read_supervisor_token() or "")
        except Exception:
            cached_token = ""
        token_present = bool(cached_token.strip())

        diagnostic_id = _new_diagnostic_id()

        try:
            result = execute_home_assistant_ws(
                command,
                read_token=lambda: cached_token,
                websocket_connect=support_web_module.websocket_connect,
            )
        except HomeAssistantWebSocketError as exc:
            exc.error_class = _stable_error_class(exc)
            exc.diagnostic_id = diagnostic_id
            _persist_calibration_diagnostic(
                command_type=command_type,
                operation=operation,
                status="error",
                token_present=token_present,
                diagnostic_id=diagnostic_id,
                exc=exc,
            )
            _log(operation, exc)
            raise

        _persist_calibration_diagnostic(
            command_type=command_type,
            operation=operation,
            status="ok",
            token_present=token_present,
            diagnostic_id=diagnostic_id,
        )
        return result

    support_web_module._home_assistant_ws = _home_assistant_ws
