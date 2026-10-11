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
    "max_height", "padding", "padding_horizontal", "padding_vertical", "gap", "Live preview",
    "Reset section", "Reset ", "Default (unchanged)", "Save Calibration Theme", "calibration_theme_core.css", "cal-theme-real-iframe",
    'api/settings/core', "method:\"POST\"",
    "calibration_theme:{calibration_theme:theme}",
):
    assert marker in JS, marker
assert '"sandbox",""' in JS or 'setAttribute("sandbox","")' in JS
assert "frame.srcdoc=doc" not in JS  # the preview must be the live Core-styled frame below
assert "frame.srcdoc=" in JS
assert "SwitchVisionCalibrationThemeCoreCss" in JS
assert "data-cv-field" in JS and "cv-cal-tools-row" in JS
assert "calibration_theme_core_rules.js" in HTML
assert '"/calibration_theme_core.css"' in PY
assert '"/calibration_theme_core_rules.js"' in PY
assert (ROOT / "calibration_theme_core.css").is_file()
assert (ROOT / "calibration_theme_core_rules.js").is_file()
assert ".cv-cal-tools button" in (ROOT / "calibration_theme_core.css").read_text(encoding="utf-8")
assert "padding-inline:" in (ROOT / "calibration_theme_core_rules.js").read_text(encoding="utf-8")
assert "padding-block:" in (ROOT / "calibration_theme_core_rules.js").read_text(encoding="utf-8")
assert "localStorage.setItem" not in JS
assert "set_calibration" not in JS
assert "send" not in JS
print("HUB_CALIBRATION_THEME_CONTRACT_PASS")
