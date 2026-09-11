#!/usr/bin/env python3
"""Compatibility shim for native UniFi Hub configuration support.

Multi-controller editing, Local/Remote priority/fallback, secret preservation and
privacy-safe status responses are now implemented directly by support_web.py.
This module remains only so existing container/entrypoint layouts keep working
while the obsolete migration-era restriction layer is retired.
"""
from __future__ import annotations

from typing import Any

_PAGE_PATCHES: tuple[tuple[str, str], ...] = ()


def install(module: Any) -> None:
    """Mark native UniFi Hub support active without monkey-patching behavior."""
    module._sv_unifi_multi_controller_bridge_installed = True
