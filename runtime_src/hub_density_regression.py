#!/usr/bin/env python3
"""Permanent Discovery 2.3.17 grouped Calibration Profiles manager regression."""
from __future__ import annotations

from pathlib import Path

import support_web

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / "support_web.py").read_text(encoding="utf-8")
MAINTENANCE = (ROOT / "maintenance.js").read_text(encoding="utf-8")
PROFILES = (ROOT / "calibration_profiles.js").read_text(encoding="utf-8")
PROFILE_MANAGER = (ROOT / "calibration_profiles_manager.js").read_text(encoding="utf-8")

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

# Discovery content width must use ten distinct viewport-relative steps. Fixed
# pixel caps collapse together inside Home Assistant ingress once the viewport
# is narrower than the cap, so only position 10 may be full width.
width_steps = (
    ("standard", 64),
    ("standard_plus", 68),
    ("wide", 72),
    ("wide_plus", 76),
    ("extra_wide", 80),
    ("extra_wide_plus", 84),
    ("ultra_wide", 88),
    ("ultra_wide_plus", 92),
    ("max_wide", 96),
    ("full", 100),
)
for name, percent in width_steps:
    assert f"body.width-{name} main{{max-width:none;width:{percent}%}}" in SOURCE
assert [percent for _, percent in width_steps] == list(range(64, 101, 4))
width_start = SOURCE.index("body.width-standard main")
width_end = SOURCE.index("body.density-spacious", width_start)
width_block = SOURCE[width_start:width_end]
assert width_block.count("width:100%") == 1
for legacy_cap in (880, 990, 1100, 1220, 1340, 1460, 1600, 1740, 1880):
    assert f"max-width:{legacy_cap}px" not in width_block


# Discovery Settings density must visibly scale all five positions, including
# nested switch rows that previously remained near Comfortable spacing.
density_contract = {
    "spacious": (16, 14, "14px 16px", "14px 16px 16px", 12, 12, 42),
    "comfortable": (12, 10, "10px 12px", "10px 12px 12px", 10, 10, 38),
    "compact": (10, 8, "8px 10px", "8px 10px 10px", 8, 8, 36),
    "dense": (8, 7, "6px 8px", "6px 8px 8px", 6, 7, 34),
    "ultra_dense": (6, 6, "4px 6px", "4px 6px 6px", 4, 5, 32),
}
for name, (section, component, header, body, between, gap, height) in density_contract.items():
    assert f"body.density-{name} #settingsCard{{--hub-control-height:{height}px;--hub-grid-row-gap:{gap}px}}" in SOURCE
    assert f"body.density-{name} .hub-settings-section{{padding:{section}px}}" in SOURCE
    assert f"body.density-{name} .hub-component{{padding:{component}px}}" in SOURCE
    assert f"body.density-{name} .hub-switch-setting-summary" in SOURCE
    assert f"padding:{header}" in SOURCE
    assert f"body.density-{name} .hub-switch-setting-body{{padding:{body}}}" in SOURCE
    assert f"body.density-{name} .hub-setting-row{{margin:{between}px 0}}" in SOURCE

# One component geometry contract must drive every Core/SNMP2MQTT/Discovery Hub
# settings subsection. Sections may choose a denser column count, but not their
# own input/select/button dimensions.
for marker in (
    "--control-height:38px",
    "--control-radius:8px",
    "--hub-control-height:var(--control-height)",
    ".hub-toggle-grid{display:grid",
    "--hub-toggle-min-height:24px",
    "repeat(2,minmax(240px,300px));column-gap:10px",
    ".hub-control-grid",
    ".hub-header-layout{display:grid",
    ".hub-grid-dense",
    ".hub-setting-toggle{min-height:var(--hub-toggle-min-height);padding:2px 0;display:grid;grid-template-columns:18px minmax(0,auto) 20px",
    ".hub-setting-toggle input{margin:0;width:16px;height:16px;align-self:center",
    ".hub-setting-toggle .hub-option-label{font-weight:400;display:block;min-width:0;line-height:1.2",
    ".hub-setting-toggle>.hub-help{align-self:center;justify-self:start",
    ".hub-setting-field>input,.hub-setting-field>select{width:100%;height:var(--hub-control-height)",
    "#settingsCard button{min-height:var(--hub-control-height)",
    ".hub-order-list{width:100%;max-width:none",
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
assert "x.append(i,s);if(help)x.append(hubHelp(help));return x" in toggle_source
assert "s.append(hubHelp(help))" not in toggle_source

# Native-header settings use a balanced four-part desktop layout: display toggles,
# enabled shortcuts, dashboard presentation, and persistent shortcut order.
# It collapses responsively without putting Dashboard presentation in a second card.
assert "headerLayout.className='hub-header-layout'" in SOURCE
assert "headerLayout.append(displayGroup,shortcutGroup,presentationGroup,box)" in SOURCE
assert "grid-template-columns:minmax(260px,.8fr) minmax(420px,1.2fr)" in SOURCE
assert ".hub-header-shortcuts{display:grid;grid-template-columns:repeat(2,minmax(180px,1fr))" in SOURCE
assert ".hub-header-presentation .hub-toggle-grid{grid-template-columns:1fr}" in SOURCE
assert "@media(max-width:1150px){.hub-header-layout" in SOURCE
assert "@media(max-width:800px)" in SOURCE
assert "border:1px solid var(--line-soft);border-radius:10px;padding:12px;margin:10px 0;background:var(--surface-inset)" in SOURCE

# The Hub homepage has one consolidated Switch Vision Settings entry. Discovery
# and SNMP2MQTT remain first-class settings sections, but no longer duplicate
# themselves as separate landing-page cards.
assert '<span>UI Settings</span><span>Discovery Settings</span><span>SNMP2MQTT Settings</span>' in SOURCE
assert 'id="openDiscoverySettingsButton"' not in SOURCE
assert 'id="openSnmp2mqttSettingsButton"' not in SOURCE
assert "$('openDiscoverySettingsButton').addEventListener" not in SOURCE
assert "$('openSnmp2mqttSettingsButton').addEventListener" not in SOURCE

# Activity LED controls are the intentionally denser variant of the same field
# geometry, never a separate control size system.
assert "g.className='grid hub-grid-dense'" in SOURCE
assert "grid-template-columns:repeat(4,minmax(0,1fr))" in SOURCE

# v2.3.16: keep the established Hub header/card framing while tightening the
# profile rows, preserving hidden internal IDs, and keeping summaries single-line.
assert '<p id="pageLead" class="lead hidden"></p>' in SOURCE
assert 'class="lead topbar-lead hidden"' not in SOURCE
assert "settings:['Switch Vision Hub Settings','Configure how Switch Vision Hub appears and behaves.']" in SOURCE
assert '<section id="calibrationProfilesCard" class="card hidden">' in SOURCE
assert '<h2>Calibration Profiles</h2>' in SOURCE
assert '<p class="lead">Manage saved Switch Vision faceplate calibration profiles.</p>' in SOURCE
assert '<h2>Switch Vision Settings</h2>' not in SOURCE
assert ".hub-settings-actions{position:sticky;bottom:6px" in SOURCE
assert ".hub-component{border:1px solid var(--line-soft);border-radius:12px;padding:10px;margin:10px 0" in SOURCE

for marker in (
    ".sv-profiles-toolbar{",
    ".sv-profiles-stats{",
    ".sv-profiles-toolbar-actions{",
    "flex-wrap:nowrap;",
    "min-height:32px;",
    "padding:4px 8px",
    'id="svProfilesSummary"',
    'id="svProfilesSelectionSummary"',
    'id="svProfilesRefresh"',
    ".sv-profile-card{",
    "grid-template-areas:",
    '"select meta"',
    ".sv-profile-top-meta{",
    "grid-area:meta;",
    ".sv-profile-meta-actions{",
    "grid-area:actions;",
):
    assert marker in PROFILES, marker
assert ".sv-profile-internal" not in PROFILES
assert ".sv-profile-actions{justify-content:flex-start" not in PROFILES
assert ".sv-profile-actions{justify-content:flex-end;width:100%;overflow-x:auto}" in PROFILES
assert "Active — Protected" not in PROFILES
assert "Factory — Protected" not in PROFILES
assert ".sv-profile-summary-line{" in PROFILES
assert "flex:1 1 auto;" in PROFILES
assert "overflow:hidden;" in PROFILES
assert "text-overflow:ellipsis;" in PROFILES
assert "white-space:nowrap" in PROFILES

# v2.3.17: grouped profile manager presentation remains layered over the
# established profile-operation implementation so protected actions stay enforced.
for marker in (
    "svProfileManagerActions",
    "svProfileManagerExport",
    "svProfileManagerImport",
    "svProfileManagerDelete",
    "svProfileManagerDeleteAllUnused",
    "ACTIVE PROFILES",
    "UNUSED PROFILES",
    "manager-selected",
    ".sv-profiles-toolbar-actions{",
    ".sv-profile-section-unused .sv-profile-select{",
    ".sv-profile-meta-actions{",
    "max-width:clamp(90px,30vw,420px)!important",
    "max-width:clamp(88px,30vw,210px)!important",
    "summary.title = text;",
    "showTooltip(text);",
    "new MutationObserver",
    "[data-profile-export]",
    "[data-profile-import]",
):
    assert marker in PROFILE_MANAGER, marker

assert "svProfileManagerCopyTarget" not in PROFILE_MANAGER
assert "svProfileManagerCopy" not in PROFILE_MANAGER
assert "Copy Profile" not in PROFILE_MANAGER
assert "Copy to…" not in PROFILE_MANAGER
assert "data-profile-copy" not in PROFILES
assert "Copy Profile" not in PROFILES
assert "Copy to…" not in PROFILES
assert ".sv-profile-section-unused .sv-profile-select{" in PROFILE_MANAGER
assert "Delete All Unused" in PROFILE_MANAGER
assert "Delete All Inactive" not in PROFILE_MANAGER
assert "Select inactive calibration profile" in PROFILE_MANAGER

# Unused profile multi-selection remains checkbox-owned. Delete All Unused
# delegates to the base profile manager's stateful operation instead of trying
# to synthesize checkbox DOM changes after the grouped manager has rerendered.
delete_all_block = PROFILE_MANAGER.split(
    '$("svProfileManagerDeleteAllUnused")', 1
)[1].split("function selectCard", 1)[0]
assert '$("svProfilesClearSelection")' not in delete_all_block
assert "window.setTimeout" not in delete_all_block
assert "querySelectorAll" not in delete_all_block
assert "dispatchEvent" not in delete_all_block
assert "SwitchVisionCalibrationProfiles" in delete_all_block
assert "?.deleteAllUnused?.();" in delete_all_block

select_card_block = PROFILE_MANAGER.split("function selectCard", 1)[1].split(
    "function wireCard", 1
)[0]
assert "if (input && !input.disabled)" in select_card_block
assert '$("svProfilesClearSelection")' not in select_card_block
assert "window.setTimeout" not in select_card_block
assert "syncActions();" in select_card_block
wire_card_block = PROFILE_MANAGER.split("function wireCard", 1)[1].split(
    "function sectionHeading", 1
)[0]
assert "selectableInactive" in wire_card_block
assert 'selectionInput.addEventListener(' in wire_card_block
assert '"change",' in wire_card_block
assert 'card.removeAttribute("role")' in wire_card_block
assert 'card.removeAttribute("tabindex")' in wire_card_block
assert 'event.target.closest(' in wire_card_block
assert ".sv-profile-section-unused .sv-profile-card{" in PROFILE_MANAGER
assert "cursor:default" in PROFILE_MANAGER
assert "root.style.setProperty('--preview-width',`${64+wi*4}%`)" in SOURCE
assert "root.style.setProperty('--preview-width',`${55+wi*5}%`)" not in SOURCE
assert '<span>Import / Export Profiles</span>' in SOURCE
assert '<span>Copy / Import / Export Profiles</span>' not in SOURCE
assert 'subgroup(\n          "CUSTOM"' in PROFILE_MANAGER
assert 'subgroup(\n          "NATIVE"' in PROFILE_MANAGER
assert "opacity:.42;" in PROFILE_MANAGER
assert "filter:saturate(.15);" in PROFILE_MANAGER
assert "background:var(--accent-soft)" in PROFILE_MANAGER
assert "display:none!important" in PROFILE_MANAGER
assert 'elif path in {"/calibration_profiles.js", "/calibration_profiles_manager.js", "/maintenance.js", "/credits_v25.js", "/credits_v25.css"}:' in SOURCE
assert '<script src="calibration_profiles_manager.js"></script>' in SOURCE

# SHA-256 remains an internal integrity primitive. Do not surface an integrity
# key as a normal Last-bundle/Support My Switch summary tile.
assert "hashlib.sha256" in SOURCE
assert '"SHA-256"' not in SOURCE
assert ">SHA-256<" not in SOURCE

# v2.3.10: field/option labels use a theme-owned secondary hierarchy colour
# while section headings keep their stronger theme accent and controls keep
# ordinary content text.
for marker in (
    "--field-label:#b8c7d9",
    "--field-label:#c1ced6",
    "--field-label:#b7c8d2",
    "--field-label:#4f6077",
    ".option>span,.option>span>b{font-weight:400;color:var(--field-label)}",
    ".field>span,.field>span>b{color:var(--field-label)}",
):
    assert marker in SOURCE, marker

# v2.3.10: Maintenance has one Installer recovery-backup manager only. The
# retention control is a button, the configurable retained-limit field and
# redundant Discovery backup UI are gone, and the visible count is rendered
# directly from the same backups array as the rows.
for removed in (
    'id="installerBackupRetentionCount"',
    'id="saveInstallerBackupPolicyButton"',
    'id="applyInstallerBackupRetentionButton"',
    '<h3>Discovery Configuration Backups</h3>',
    'id="discoveryBackupSummary"',
    'id="refreshDiscoveryBackupsButton"',
):
    assert removed not in SOURCE, removed
assert 'id="installerBackupAutomaticRetention" type="button" aria-pressed="false"' in SOURCE
assert 'class="installer-backup-summary muted">0 retained backups<' in SOURCE
assert ".installer-backup-row{display:grid;grid-template-columns:minmax(0,1fr) auto" in SOURCE
assert "function toggleInstallerBackupRetention()" in MAINTENANCE
assert 'summary.textContent = `${backups.length} retained backup${backups.length === 1 ? "" : "s"}`;' in MAINTENANCE
assert 'automatic.classList.toggle("primary", retentionEnabled);' in MAINTENANCE
assert "loadBackups();" not in MAINTENANCE
assert 'endpoint("api/maintenance/discovery-backups")' not in MAINTENANCE

print("Switch Vision Discovery 2.3.17 grouped Calibration Profiles manager contract: PASS")
