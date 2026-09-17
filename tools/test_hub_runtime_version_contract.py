#!/usr/bin/env python3
"""Regression contract for stale-open Hub/runtime version synchronization."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime_src"))

import support_web as hub  # noqa: E402


def main() -> int:
    page = hub._page_with_ui_preferences("2.4.35-test")
    assert 'data-sv-discovery-version="2.4.35-test"' in page
    assert "const HUB_DOCUMENT_VERSION=String(document.body.dataset.svDiscoveryVersion||'unknown').trim()" in page
    assert "const HUB_VERSION_RELOAD_KEY='switch-vision-hub-runtime-version-reload-v1'" in page
    assert "function syncHubRuntimeVersion(runtimeVersion)" in page
    assert "sessionStorage.getItem(HUB_VERSION_RELOAD_KEY)" in page
    assert "sessionStorage.setItem(HUB_VERSION_RELOAD_KEY,token)" in page
    assert "if(previous===token)return false" in page
    assert "window.location.reload();return true" in page
    assert "if(syncHubRuntimeVersion(d.version))return" in page

    source = (ROOT / "runtime_src/support_web.py").read_text(encoding="utf-8")
    status_marker = 'elif path == "/api/status":'
    health_marker = 'elif path == "/api/discovery/debug":'
    status_block = source[source.index(status_marker):source.index(health_marker)]
    assert '"version": self.app.version' in status_block
    assert '_page_with_ui_preferences(self.app.version)' in source

    print("Hub runtime-version synchronization contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
