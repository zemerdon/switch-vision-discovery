#!/usr/bin/env python3
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
HTML = (HERE / "support_web.html").read_text(encoding="utf-8")
JS = (HERE / "custom_theme_manager.js").read_text(encoding="utf-8")
WEB = (HERE / "support_web.py").read_text(encoding="utf-8")

for marker in (
    'data-hub-settings-tab="custom-theme">Custom Theme</button>',
    'id="hubComponent-custom-theme"',
    '<script src="custom_theme_manager.js"></script>',
    '"/custom_theme_manager.js"',
    'switch-vision-custom-themes-v1',
    "custom_themes",
    "management_theme_selected",
    "Theme library",
    "Live sample page",
    "Switch Vision Installer",
    "Save Theme",
    "Save & Apply",
    "Custom Themes",
    "CUSTOM_THEME_VAR_KEYS",
    "for(const key of CUSTOM_THEME_VAR_KEYS)",
):
    assert marker in HTML or marker in JS or marker in WEB, marker

expected_roles = {
    "page","card","card_strong","surface_input","surface_button","surface_inset",
    "surface_hover","text","muted","field_label","line","line_soft","accent",
    "accent_strong","accent_dark","accent_dark_hover","accent_soft","heading",
    "heading_strong","heading_line","heading_soft","heading_glow","warn","warn_soft",
    "ok","ok_soft","bad","bad_soft","neutral_soft","on_accent","on_primary","shadow",
    "status_bg","code_bg","chip_bg","chip_hover","heart","link","link_hover",
    "button_primary_bg","button_primary_text","button_secondary_bg",
    "button_secondary_text","button_danger_bg","button_danger_text",
}
keys_match = re.search(r"const ROLE_KEYS = ROLE_GROUPS\.flatMap", JS)
assert keys_match
for role in expected_roles:
    assert f'["{role}",' in JS or f'{role}:"' in JS, role
assert len(expected_roles) == 45

for behavior in (
    "createThemeFromCurrent",
    "duplicateTheme",
    "deleteTheme",
    "saveTheme",
    "selectGlobalTheme",
    "populateThemeDropdown",
    "applyPreviewVars",
    'color.type = "color"',
    'hex.type = "text"',
    'management_theme_selected: state.selected',
    'custom_themes: state.custom_themes',
):
    assert behavior in JS, behavior

# Theme Library is the one sidebar section expanded by default. Theme name
# and save/apply controls live inside it; all colour-role groups remain native
# collapsed details sections.
for marker in (
    'group = document.createElement("details")',
    'group.className = "theme-color-group theme-sidebar-section"',
    'const heading = document.createElement("summary")',
    'const library = document.createElement("details")',
    'library.className = "theme-library theme-sidebar-section"',
    'library.open = true',
    'librarySummary.textContent = "Theme library"',
    'nameLabel.className = "field theme-library-name"',
    'library.append(nameLabel)',
    'library.append(actions)',
    '.theme-sidebar-section[open]>summary::after',
):
    assert marker in JS, marker
for forbidden in (
    'const nameSection = document.createElement("details")',
    'nameSummary.textContent = "Theme details"',
    'theme-name-section',
    'group.open = true',
    '.open=true',
):
    assert forbidden not in JS, forbidden

# Built-ins remain selectable and custom names are appended to the same top-right selector.
for value in ("switch-vision", "cisco-classic", "cisco-nexus", "unifi"):
    assert value in JS and value in HTML
assert 'select.querySelector(\'optgroup[data-custom-themes="true"]\')' in JS
assert 'group.label = "Custom Themes"' in JS

# The custom builder affects management UI only; it must explicitly preserve dashboard/faceplate scope.
assert "Generated switch dashboards and faceplates are not changed." in JS

print("Discovery custom management theme regression: PASS")
