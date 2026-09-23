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

print("Support My Switch add-on log capture: PASS")
