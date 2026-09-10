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

# Save/reload remains shared across all panes and dirty state is not cleared by tab changes.
select_start = SOURCE.index("function selectTab(which='core',focus=false)")
select_end = SOURCE.index("function tabKeydown", select_start)
select_block = SOURCE[select_start:select_end]
assert 'dirty.clear()' not in select_block
assert 'hubSettingsSave' in SOURCE and 'hubSettingsReload' in SOURCE

print("Switch Vision Settings top tabs regression: PASS")
