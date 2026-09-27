#!/usr/bin/env python3
"""Regression contract for the externalized Switch Vision Hub page asset."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
sys.path.insert(0, str(RUNTIME))

import support_web as hub  # noqa: E402


def main() -> int:
    asset = RUNTIME / "support_web.html"
    source = (RUNTIME / "support_web.py").read_text(encoding="utf-8")
    dockerfile = (RUNTIME / "Dockerfile").read_text(encoding="utf-8")

    assert asset.is_file()
    page = asset.read_text(encoding="utf-8")
    assert len(page) > 200_000
    assert page.startswith("<!doctype html>")
    assert page.endswith("</body></html>")
    assert hub.HUB_PAGE_PATH == asset
    assert hub._PAGE == page
    assert '_PAGE = r"""<!doctype html>' not in source
    assert 'HUB_PAGE_PATH = Path(__file__).with_name("support_web.html")' in source
    assert '_PAGE = HUB_PAGE_PATH.read_text(encoding="utf-8")' in source
    assert "COPY support_web.html /support_web.html" in dockerfile

    print(f"Discovery Hub page asset contract: PASS ({len(page)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
