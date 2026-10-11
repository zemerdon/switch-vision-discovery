#!/usr/bin/env python3
"""Hub Calibration Theme grouping, live preview and Core-only save contract."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "support_web.html").read_text(encoding="utf-8")
PY = (ROOT / "support_web.py").read_text(encoding="utf-8")
JS = (ROOT / "calibration_theme_manager.js").read_text(encoding="utf-8")

for marker in (
    'id="hubTab-calibration-theme"', 'id="hubComponent-calibration-theme"',
    '<script src="calibration_theme_manager.js"></script>',
    "'core','discovery','snmp2mqtt','custom-theme','calibration-theme'",
    "window.SwitchVisionCalibrationTheme?.load?.()",
):
    assert marker in HTML, marker
assert '"/calibration_theme_manager.js"' in PY
for marker in (
    "Workspace & Sections", "Assets & Selection", "Labels & Fields",
    "Buttons & Inputs", "Dropdowns", "Closed control", "Open menu & options",
    '"desktop"', '"mobile"', "font_weight", "font_size", "row_height",
    "max_height", "padding", "gap", "Live preview",
    "Reset section", "Reset ", "Default (unchanged)", "Save Calibration Theme",
    'api/settings/core', "method:\"POST\"",
    "calibration_theme:{calibration_theme:theme}",
):
    assert marker in JS, marker
assert "localStorage.setItem" not in JS
assert "set_calibration" not in JS
assert "send" not in JS
print("HUB_CALIBRATION_THEME_CONTRACT_PASS")
