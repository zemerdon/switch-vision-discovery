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
        "ideas, or bugs. If any faceplate geometry is not correct, can you please click Reset "
        "Faceplate in the Calibration tool, and if that doesn't work, let me know please."
    )
    assert hub.HUB_MOTD_DEFAULT == expected_default
    with motd_env(None):
        assert hub._hub_motd_text() == expected_default

    with motd_env("   Planned   maintenance\n tonight   "):
        assert hub._hub_motd_text() == "Planned maintenance tonight"

    with motd_env("x" * (hub.HUB_MOTD_MAX_CHARS + 50)):
        assert len(hub._hub_motd_text()) == hub.HUB_MOTD_MAX_CHARS


def test_motd_backend_is_preserved_but_not_displayed() -> None:
    with motd_env("<b>Notice</b> & check status"):
        assert hub._hub_motd_text() == "<b>Notice</b> & check status"
        page = hub._page_with_ui_preferences()
    assert "__SV_HUB_MOTD__" not in page
    assert "<b>Notice</b>" not in page
    assert "&lt;b&gt;Notice&lt;/b&gt; &amp; check status" not in page
    # Reintroducing the template placeholder must still render safely.
    original_page = hub._PAGE
    try:
        hub._PAGE = original_page.replace(
            '<div class="nav-grid">',
            '<p>__SV_HUB_MOTD__</p><div class="nav-grid">',
            1,
        )
        with motd_env("<b>Notice</b> & check status"):
            restored_page = hub._page_with_ui_preferences()
        assert "&lt;b&gt;Notice&lt;/b&gt; &amp; check status" in restored_page
        assert "<b>Notice</b>" not in restored_page
    finally:
        hub._PAGE = original_page


def test_motd_home_ui_is_fully_removed() -> None:
    page = hub._PAGE
    home = page.index('<section id="homeCard"')
    nav = page.index('<div class="nav-grid">', home)
    assert home < nav
    for removed in (
        'id="hubMotd"',
        'id="hubMotdToggle"',
        'id="hubMotdBody"',
        'id="hubMotdMessage"',
        "Message of the Day",
        "__SV_HUB_MOTD__",
        ".hub-motd{",
        "MOTD_VISIBILITY_STORAGE_KEY",
        "applyHubMotdVisibility",
        "initHubMotdVisibility",
        "toggleHubMotdVisibility",
        "switch-vision-hub-motd-visibility-v1",
    ):
        assert removed not in page, removed


def main() -> int:
    test_motd_default_and_bounded_normalisation()
    test_motd_backend_is_preserved_but_not_displayed()
    test_motd_home_ui_is_fully_removed()
    print("Hub MOTD contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
