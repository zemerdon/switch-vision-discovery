#!/usr/bin/env python3
"""Permanent Discovery 2.3.7 Hub density/consistency regression."""
from __future__ import annotations

from pathlib import Path

import support_web

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / "support_web.py").read_text(encoding="utf-8")

# Shared numeric font-size contract. Discovery must remain usable while reading
# ui-preferences produced by pre-2.6.3 Core as well as the new numeric contract.
assert support_web._normalise_ui_text_size("normal") == 16
assert support_web._normalise_ui_text_size("small") == 14
for pixels in range(10, 21):
    assert support_web._normalise_ui_text_size(pixels) == pixels
    assert support_web._normalise_ui_text_size(str(pixels)) == pixels
    assert support_web._normalise_ui_text_size(f"{pixels}px") == pixels
for invalid in (9, 21, "9", "21px", "", "giant", None, True, 14.5):
    assert support_web._normalise_ui_text_size(invalid) == 16

# One component geometry contract must drive every Core/SNMP2MQTT/Discovery Hub
# settings subsection. Sections may choose a denser column count, but not their
# own input/select/button dimensions.
for marker in (
    "--control-height:38px",
    "--control-radius:8px",
    "--hub-control-height:var(--control-height)",
    ".hub-toggle-grid{display:grid",
    ".hub-control-grid",
    ".hub-header-layout{display:grid",
    ".hub-grid-dense",
    ".hub-setting-toggle .hub-option-label{font-weight:400",
    ".hub-setting-field>input,.hub-setting-field>select{width:100%;height:var(--hub-control-height)",
    "#settingsCard button{min-height:var(--hub-control-height)",
    ".hub-order-list{width:100%;max-width:420px",
    "function fontChoices()",
    "Array.from({length:11}",
):
    assert marker in SOURCE, marker

# The shared 38px geometry also applies to ordinary Hub form controls rather
# than only the settings iframe-like region.
assert "height:var(--control-height);min-height:var(--control-height)" in SOURCE

# Selectable option labels should be visually subordinate to themed headings
# and field labels. The dynamic Hub toggle renderer must not inject <b>.
toggle_start = SOURCE.index("function tog(")
toggle_end = SOURCE.index("function sel(", toggle_start)
toggle_source = SOURCE[toggle_start:toggle_end]
assert "hub-option-label" in toggle_source
assert "createElement('b')" not in toggle_source

# The shortcut sequence stays a single vertical sequence, but it must share the
# desktop row with the toggle group instead of stretching an empty full-width
# box underneath it.
assert "headerLayout.className='hub-header-layout'" in SOURCE
assert "headerLayout.append(headerTog,box)" in SOURCE
assert "grid-template-columns:minmax(0,1fr) minmax(320px,420px)" in SOURCE

# Activity LED controls are the intentionally denser variant of the same field
# geometry, never a separate control size system.
assert "g.className='grid hub-grid-dense'" in SOURCE
assert "grid-template-columns:repeat(4,minmax(0,1fr))" in SOURCE

# SHA-256 remains an internal integrity primitive. Do not surface an integrity
# key as a normal Last-bundle/Support My Switch summary tile.
assert "hashlib.sha256" in SOURCE
assert '"SHA-256"' not in SOURCE
assert ">SHA-256<" not in SOURCE

print("Switch Vision Discovery 2.3.7 Hub density/consistency: PASS")
