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
    "padding:2px 0;gap:7px;align-items:center",
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
    "svProfileManagerCopyTarget",
    "svProfileManagerDelete",
    "ACTIVE PROFILES",
    "UNUSED PROFILES",
    "manager-selected",
    ".sv-profiles-toolbar-actions{",
    ".sv-profile-select,",
    ".sv-profile-meta-actions{",
    "max-width:clamp(90px,30vw,420px)!important",
    "max-width:clamp(88px,30vw,210px)!important",
    "summary.title = text;",
    "showTooltip(text);",
    "new MutationObserver",
    "[data-profile-export]",
    "[data-profile-import]",
    "[data-profile-copy]",
):
    assert marker in PROFILE_MANAGER, marker
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
