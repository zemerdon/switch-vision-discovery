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


# Discovery Settings switch rows are compact disclosures. The first saved switch
# is expanded by default, later rows start collapsed, and per-row arrows reorder
# the same editable switches array that the shared Save action persists.
for marker in (
    "expandedDiscoverySwitches=new Set();let discoverySwitchExpansionInitialized=false",
    "if(!discoverySwitchExpansionInitialized){if(switches.length){expandedDiscoverySwitches.add",
    "const c=document.createElement('details')",
    "const hd=document.createElement('summary')",
    "c.open=expandedDiscoverySwitches.has(key)",
    "c.addEventListener('toggle',()=>{if(c.open)expandedDiscoverySwitches.add(key);else expandedDiscoverySwitches.delete(key)})",
    "up.textContent='↑';down.textContent='↓'",
    "[switches[n-1],switches[n]]=[switches[n],switches[n-1]]",
    "[switches[n+1],switches[n]]=[switches[n],switches[n+1]]",
    "mark('discovery');renderDiscovery()",
    ".hub-switch-setting-summary{display:flex",
    ".hub-switch-setting-order{display:flex",
    ".hub-switch-setting-label>strong{color:var(--accent-strong)",
    "hub-discovery-workflow-grid",
    ".hub-discovery-workflow-grid .hub-field-label{min-height:2.4em",
):
    assert marker in SOURCE, marker

# There must be no blanket open=true behavior for every switch row.
assert "c.open=true" not in SOURCE

# Save/reload remains shared across all panes and dirty state is not cleared by tab changes.
select_start = SOURCE.index("function selectTab(which='core',focus=false)")
select_end = SOURCE.index("function tabKeydown", select_start)
select_block = SOURCE[select_start:select_end]
assert 'dirty.clear()' not in select_block
assert 'hubSettingsSave' in SOURCE and 'hubSettingsReload' in SOURCE

print("Switch Vision Settings top tabs regression: PASS")
