#!/usr/bin/env python3
from pathlib import Path

SOURCE = Path(__file__).with_name("support_web.py").read_text(encoding="utf-8")

for marker in (
    'class="hub-settings-tabs" role="tablist"',
    'data-hub-settings-tab="core">UI Settings</button>',
    'data-hub-settings-tab="discovery">Discovery Settings</button>',
    'data-hub-settings-tab="snmp2mqtt">SNMP2MQTT Settings</button>',
    'role="tabpanel" aria-labelledby="hubTab-core"',
    'role="tabpanel" aria-labelledby="hubTab-discovery" hidden',
    'role="tabpanel" aria-labelledby="hubTab-snmp2mqtt" hidden',
    "function selectTab(which='core',focus=false)",
    "const ids=['core','discovery','snmp2mqtt']",
    "tab.addEventListener('click',()=>selectTab(tab.dataset.hubSettingsTab))",
    "tab.addEventListener('keydown',tabKeydown)",
    "async function open(which='core'){styles();setView('settings');await load();selectTab(which)}",
    '.hub-settings-pane[hidden]{display:none!important}',
):
    assert marker in SOURCE, marker

# The old accordion contract must be gone; tabs are the sole top-level settings navigation.
for old in (
    '<details id="hubComponent-core"',
    '<details id="hubComponent-discovery"',
    '<details id="hubComponent-snmp2mqtt"',
    'x.open=true',
):
    assert old not in SOURCE, old


# Discovery Settings switch rows are compact custom disclosures. The first saved
# switch is expanded by default, later rows start collapsed, and arrow buttons
# are siblings of (not children of) the disclosure toggle so HA/Chrome cannot
# swallow reorder clicks through <summary> interactive-content behavior.
for marker in (
    "expandedDiscoverySwitches=new Set();let discoverySwitchExpansionInitialized=false",
    "if(!discoverySwitchExpansionInitialized){if(switches.length){expandedDiscoverySwitches.add",
    "const c=document.createElement('div');c.className='device-card hub-setting-row hub-switch-setting-row'",
    "const hd=document.createElement('div');hd.className='hub-switch-setting-summary'",
    "const toggle=document.createElement('button');toggle.type='button';toggle.className='hub-switch-setting-toggle'",
    "toggle.setAttribute('aria-expanded',String(expandedDiscoverySwitches.has(key)))",
    "up.textContent='↑';down.textContent='↓'",
    "const move=delta=>{const target=n+delta;if(target<0||target>=switches.length)return;[switches[n],switches[target]]=[switches[target],switches[n]];mark('discovery');renderDiscovery()}",
    "up.addEventListener('click',()=>move(-1));down.addEventListener('click',()=>move(1))",
    "hd.append(order,toggle,rm)",
    "g.hidden=!expandedDiscoverySwitches.has(key)",
    "toggle.addEventListener('click',()=>{const open=g.hidden;",
    ".hub-switch-setting-summary{display:flex",
    ".hub-switch-setting-order{display:flex",
    ".hub-switch-setting-toggle{display:flex!important",
    ".hub-switch-setting-label>strong{color:var(--accent-strong)",
    "hub-discovery-workflow-grid",
    ".hub-discovery-workflow-grid .hub-field-label{min-height:2.4em",
):
    assert marker in SOURCE, marker

# Do not reintroduce real buttons inside <summary>; that was unreliable under
# Home Assistant ingress and caused the Settings reorder arrows to no-op.
settings_start = SOURCE.index("function renderDiscovery(){")
settings_end = SOURCE.index("function cleanDiscovery(){", settings_start)
settings_block = SOURCE[settings_start:settings_end]
assert "document.createElement('summary')" not in settings_block
assert "document.createElement('details')" not in settings_block
assert "c.open=true" not in SOURCE

# Save/reload remains shared across all panes and dirty state is not cleared by tab changes.
select_start = SOURCE.index("function selectTab(which='core',focus=false)")
select_end = SOURCE.index("function tabKeydown", select_start)
select_block = SOURCE[select_start:select_end]
assert 'dirty.clear()' not in select_block
assert 'hubSettingsSave' in SOURCE and 'hubSettingsReload' in SOURCE

# Shared sticky action bar is available on each working Hub view and delegates
# to the page's existing real action rather than duplicating business logic.
for marker in (
    'id="hubSharedActions" class="hub-settings-actions hub-shared-actions hidden"',
    'id="hubSharedPrimary" class="primary"',
    'id="hubSharedReload"',
    'id="hubSharedBack"',
    "const HUB_SHARED_PAGE_ACTIONS={discovery:{label:'Run Discovery'",
    "devices:{label:'Refresh Devices'",
    "support:{label:'Create Contribution'",
    "configuration:{label:'Export Configuration'",
    "maintenance:{label:'Scan MQTT Entities'",
    "profiles:{label:'Refresh Profiles'",
    "unifi2mqtt:{label:'Save UniFi2MQTT Settings'",
    "function runSharedHubPrimary()",
    "function reloadSharedHubView()",
    "updateSharedHubActions(view);window.scrollTo",
    "$('hubSharedPrimary').addEventListener('click',runSharedHubPrimary)",
    "$('hubSharedReload').addEventListener('click',reloadSharedHubView)",
    "$('hubSharedBack').addEventListener('click',goBack)",
):
    assert marker in SOURCE, marker

# Hub navigation bullets use consistent title-style capitalization for actions.
for marker in (
    'Show Detected Devices &amp; Status',
    'Reorder Switches',
    'Manage Faceplate Calibrations',
    'Copy / Import / Export Profiles',
    'Manage Backups',
    'Repair Stale MQTT Entities',
    'Add / Remove Switches',
):
    assert marker in SOURCE, marker

print("Switch Vision Settings top tabs regression: PASS")
