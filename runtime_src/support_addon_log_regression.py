#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import support_diagnostics as diag


class Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.payload


seen = {}


def opener(request, timeout=0):
    seen["url"] = request.full_url
    seen["authorization"] = request.headers.get("Authorization")
    seen["timeout"] = timeout
    return Response(b"startup line\nwarning line\nready line\n")


with tempfile.TemporaryDirectory(prefix="sv-addon-log-") as tmp:
    root = Path(tmp)
    status = diag.capture_discovery_addon_log(
        root,
        opener=opener,
        token_reader=lambda: "private-supervisor-token",
    )
    assert status["status"] == "captured", status
    assert status["line_count"] == 3, status
    assert "/addons/self/logs/latest?lines=400&no_colors" in seen["url"], seen
    assert seen["authorization"] == "Bearer private-supervisor-token", seen
    log_text = (root / diag.DISCOVERY_ADDON_LOG).read_text(encoding="utf-8")
    assert log_text == "startup line\nwarning line\nready line\n", log_text
    assert "private-supervisor-token" not in log_text
    status_doc = json.loads((root / diag.DISCOVERY_ADDON_LOG_STATUS).read_text(encoding="utf-8"))
    assert status_doc["sanitization_required"] is True, status_doc

with tempfile.TemporaryDirectory(prefix="sv-addon-log-missing-token-") as tmp:
    root = Path(tmp)
    status = diag.capture_discovery_addon_log(root, token_reader=lambda: "")
    assert status["status"] == "unavailable", status
    assert status["reason"] == "supervisor_token_unavailable", status
    assert not (root / diag.DISCOVERY_ADDON_LOG).exists()

original_info = diag._unifi2mqtt_supervisor_info
try:
    diag._unifi2mqtt_supervisor_info = lambda *_args, **_kwargs: (
        "fixture_switch_vision_unifi2mqtt",
        {},
    )
    unifi_seen = {}

    def unifi_opener(request, timeout=0):
        unifi_seen["url"] = request.full_url
        unifi_seen["authorization"] = request.headers.get("Authorization")
        return Response(b"unifi startup https://private-controller.invalid:11443\nnetwork timeout\n")

    with tempfile.TemporaryDirectory(prefix="sv-unifi-addon-log-") as tmp:
        root = Path(tmp)
        status = diag.capture_unifi2mqtt_addon_log(
            root,
            opener=unifi_opener,
            token_reader=lambda: "private-supervisor-token",
        )
        assert status["status"] == "captured", status
        assert status["line_count"] == 2, status
        assert (
            "/addons/fixture_switch_vision_unifi2mqtt/logs/latest?lines=400&no_colors"
            in unifi_seen["url"]
        ), unifi_seen
        assert unifi_seen["authorization"] == "Bearer private-supervisor-token"
        log_text = (root / diag.UNIFI2MQTT_ADDON_LOG).read_text(encoding="utf-8")
        assert log_text == "unifi startup https://[redacted-controller]\nnetwork timeout\n", log_text
        assert "private-controller.invalid" not in log_text
        assert "private-supervisor-token" not in log_text
        status_doc = json.loads(
            (root / diag.UNIFI2MQTT_ADDON_LOG_STATUS).read_text(encoding="utf-8")
        )
        assert status_doc["sanitization_required"] is True, status_doc
finally:
    diag._unifi2mqtt_supervisor_info = original_info

print("Support My Switch add-on log capture: PASS")
