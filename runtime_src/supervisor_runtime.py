#!/usr/bin/env python3
"""Shared Supervisor/Home Assistant runtime authentication helpers."""
from __future__ import annotations

import os
from pathlib import Path

TOKEN_ENV_NAMES = ("SUPERVISOR_TOKEN", "HASSIO_TOKEN")
TOKEN_FILES = (
    Path("/run/s6/container_environment/SUPERVISOR_TOKEN"),
    Path("/var/run/s6/container_environment/SUPERVISOR_TOKEN"),
    Path("/run/s6/container_environment/HASSIO_TOKEN"),
    Path("/var/run/s6/container_environment/HASSIO_TOKEN"),
)


def read_supervisor_token() -> str:
    """Return the Supervisor token without logging or exposing its value."""
    for name in TOKEN_ENV_NAMES:
        token = os.environ.get(name, "").strip()
        if token:
            return token
    for path in TOKEN_FILES:
        try:
            token = path.read_text(encoding="utf-8").strip().strip("\x00")
        except OSError:
            continue
        if token:
            return token
    return ""
