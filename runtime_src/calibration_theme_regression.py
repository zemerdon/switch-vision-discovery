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
    "Global Calibration Controls", "Closed Dropdowns", "Open Dropdown Menu",
    "Field Labels — RJ45 Targets", "Group Labels — Port manager",
    "Subsection Headings — Quick selection", "Section Headings — Selection",
    '"desktop"', '"mobile"', "font_weight", "font_size", "row_height",
    "max_height", "padding", "padding_horizontal", "padding_vertical", "gap", "cal-theme-inline-sample",
    "Reset ", "Core default (", "Save Calibration Theme", "calibration_theme_core.css", "cal-theme-sample-frame",
    'api/settings/core', "method:\"POST\"",
    "calibration_theme:{calibration_theme:theme}",
):
    assert marker in JS, marker
assert 'setAttribute("sandbox","allow-same-origin")' in JS
assert "allow-scripts" not in JS
assert "frame.addEventListener(\"load\"" in JS
assert "frame.contentDocument" in JS
assert "scrollHeight" in JS and "frame.style.height=Math.ceil" in JS
assert "Math.min(310" not in JS
assert "frame.srcdoc=doc" not in JS  # the preview must be the live Core-styled frame below
assert "frame.srcdoc=" in JS
assert "corePreviewCss" in JS
assert 'fetch(endpoint("calibration_theme_core.css")' in JS
assert 'corePreviewCss+\'</style><style>\'' in JS
assert "materializePreviewSelectShells" in JS
assert 'select.setAttribute("aria-hidden","true")' in JS
assert 'trigger.className="cv-cal-select-trigger"' in JS
assert "SwitchVisionCalibrationThemeCoreCss" in JS
assert "RJ45 Targets" in JS and "cv-cal-tools-row" in JS
assert "Port manager" in JS and "Quick selection" in JS and "Selection" in JS
assert "calibration_theme_core_rules.js" in HTML
assert '"/calibration_theme_core.css"' in PY
assert '"/calibration_theme_core_rules.js"' in PY
assert (ROOT / "calibration_theme_core.css").is_file()
assert (ROOT / "calibration_theme_core_rules.js").is_file()
assert ".cv-cal-tools button" in (ROOT / "calibration_theme_core.css").read_text(encoding="utf-8")
assert "padding-inline:" in (ROOT / "calibration_theme_core_rules.js").read_text(encoding="utf-8")
assert "padding-block:" in (ROOT / "calibration_theme_core_rules.js").read_text(encoding="utf-8")
assert "const SETTINGS = [" in JS
assert "buttonRow" in JS
assert "exampleHtml" in JS
assert 'buttonRow("cv-cal-port-manager-row",4)' in JS
assert "calibration_theme_selection_buttons.js" in HTML
assert '"/calibration_theme_selection_buttons.js"' in PY
assert (ROOT / "calibration_theme_selection_buttons.js").is_file()
selection_inventory = (ROOT / "calibration_theme_selection_buttons.js").read_text()
assert '"count": 49' in selection_inventory
for button_name in ("Remove All RJ45 Ports", "Remove All SFP Ports", "Reset name", "All Link LEDs", "Activity LEDs", "Select"):
    assert button_name in selection_inventory
assert "cal-theme-all-settings" in JS
assert "FIELD_EXAMPLES" not in JS
assert "cal-theme-preview-panel" not in JS
assert "cal-theme-open-toggle" not in JS
assert 'category==="dropdown_open"' in JS
assert "const GROUPS" not in JS
assert "focusCategory" not in JS
assert "options.width||220" in JS and "options.max_height||320" in JS
assert 'Array.from({length:key==="max_height"?64:3}' in JS
assert "max-height:'+maxHeight+'px;" in JS
assert 'key==="row_height"||key==="row_spacing"' in JS
assert "const buttons=buttonRow(\"cv-cal-port-manager-row\",4)" in JS
assert "const quick=buttonRow(\"cv-cal-quick-row\",4)" in JS
assert 'category==="field_labels"' in JS
assert 'category==="group_labels"' in JS
assert 'category==="subsection_headings"' in JS
assert 'category==="section_headings"' in JS
assert "localStorage.setItem" not in JS
assert "set_calibration" not in JS
assert "send" not in JS
print("HUB_CALIBRATION_THEME_CONTRACT_PASS")
