#!/usr/bin/env python3
"""Regression contract for the Switch Vision Hub Message of the Day."""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime_src"))

import support_web as hub  # noqa: E402


@contextmanager
def motd_env(value: str | None):
    old = os.environ.get(hub.HUB_MOTD_ENV_VAR)
    try:
        if value is None:
            os.environ.pop(hub.HUB_MOTD_ENV_VAR, None)
        else:
            os.environ[hub.HUB_MOTD_ENV_VAR] = value
        yield
    finally:
        if old is None:
            os.environ.pop(hub.HUB_MOTD_ENV_VAR, None)
        else:
            os.environ[hub.HUB_MOTD_ENV_VAR] = old


def test_motd_default_and_bounded_normalisation() -> None:
    expected_default = (
        "Thank you for your continued support. Please use Support My Switch and submit your "
        "contribution package to switch-vision@zemerdon.com. Even if nothing is wrong, a "
        "contribution package validates correctness. Also feel free to express any feedback, "
        "ideas, or bugs."
    )
    assert hub.HUB_MOTD_DEFAULT == expected_default
    with motd_env(None):
        assert hub._hub_motd_text() == expected_default

    with motd_env("   Planned   maintenance\n tonight   "):
        assert hub._hub_motd_text() == "Planned maintenance tonight"

    with motd_env("x" * (hub.HUB_MOTD_MAX_CHARS + 50)):
        assert len(hub._hub_motd_text()) == hub.HUB_MOTD_MAX_CHARS


def test_motd_is_html_escaped_before_rendering() -> None:
    with motd_env("<b>Notice</b> & check status"):
        page = hub._page_with_ui_preferences()
    assert "<b>Notice</b>" not in page
    assert "&lt;b&gt;Notice&lt;/b&gt; &amp; check status" in page
    assert "__SV_HUB_MOTD__" not in page


def test_motd_home_layout_accessibility_and_persistence_contract() -> None:
    page = hub._PAGE
    home = page.index('<section id="homeCard"')
    motd = page.index('id="hubMotd"')
    nav = page.index('<div class="nav-grid">', motd)
    assert home < motd < nav

    assert 'role="region" aria-labelledby="hubMotdTitle"' in page
    assert 'id="hubMotdToggle"' in page
    assert 'type="button" data-action="toggle-motd-visibility"' in page
    assert 'aria-expanded="true"' in page
    assert 'aria-controls="hubMotdBody"' in page
    assert 'id="hubMotdBody"' in page
    assert 'id="hubMotdMessage">__SV_HUB_MOTD__' in page

    assert "switch-vision-hub-motd-visibility-v1" in page
    assert "localStorage.getItem(MOTD_VISIBILITY_STORAGE_KEY)" in page
    assert "localStorage.setItem(MOTD_VISIBILITY_STORAGE_KEY,shown?'shown':'hidden')" in page
    assert "body.hidden=!shown" in page
    assert "button.setAttribute('aria-expanded',String(shown))" in page
    assert "button.textContent=shown?'Hide':'Show'" in page
    assert "$('hubMotdToggle').addEventListener('click',toggleHubMotdVisibility)" in page
    assert "initHubMotdVisibility()" in page

    css = page[page.index('.hub-motd{'):page.index('#creditsCard{')]
    assert "position:fixed" not in css
    assert "position:sticky" not in css


def main() -> int:
    test_motd_default_and_bounded_normalisation()
    test_motd_is_html_escaped_before_rendering()
    test_motd_home_layout_accessibility_and_persistence_contract()
    print("Hub MOTD contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
