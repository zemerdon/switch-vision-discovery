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

# Dashboard presentation lives inside the Native dashboard header section as a
# balanced 2x2 responsive layout instead of a separate settings card.
for marker in (
    "presentationGroup.className='hub-header-group hub-header-presentation'",
    "presentationGroup.innerHTML='<h4>Dashboard presentation</h4>'",
    "headerLayout.append(displayGroup,shortcutGroup,presentationGroup,box)",
    ".hub-header-layout{display:grid;grid-template-columns:minmax(260px,.8fr) minmax(420px,1.2fr)",
    ".hub-header-presentation .hub-toggle-grid{grid-template-columns:1fr}",
    ".hub-header-presentation-width{grid-template-columns:1fr!important",
):
    assert marker in SOURCE, marker
assert "const dash=sec('Dashboard presentation'" not in SOURCE

# Show UniFi integration belongs to Native dashboard header -> Dashboard
# presentation. The saved Core discovery preference is reused in-place; it must
# not be rendered in the Discovery appearance card again.
assert "if(s.discovery&&Object.prototype.hasOwnProperty.call(s.discovery,'show_unifi_integration'))presentationTog.append(tog('Show UniFi integration',s.discovery.show_unifi_integration" in SOURCE
assert "if(grp==='discovery')b.append(tog('Show UniFi integration'" not in SOURCE

# The old accordion contract must be gone; tabs are the sole top-level settings navigation.
for old in (
    '<details id="hubComponent-core"',
    '<details id="hubComponent-discovery"',
    '<details id="hubComponent-snmp2mqtt"',
    'x.open=true',
):
    assert old not in SOURCE, old


# Discovery Settings now owns Discovery workflow/path/privacy settings only.
# Saved switch rows and stack-member display mapping live under Devices ->
# Configure Devices. Existing saved switches all start collapsed; expansion is
# user-driven for the current page session.
for marker in (
    "function renderDeviceConfiguration(){",
    "expandedDiscoverySwitches=new Set();",
    "sw=sec('Switches','SNMP communities are masked by default.",
    "const st=sec('Stack member display mapping')",
    "const c=document.createElement('div');c.className='device-card hub-setting-row hub-switch-setting-row'",
    "const hd=document.createElement('div');hd.className='hub-switch-setting-summary'",
    "const toggle=document.createElement('button');toggle.type='button';toggle.className='hub-switch-setting-toggle'",
    "toggle.setAttribute('aria-expanded',String(expandedDiscoverySwitches.has(key)))",
    "g.hidden=!expandedDiscoverySwitches.has(key)",
    "toggle.addEventListener('click',()=>{const open=g.hidden;",
    ".hub-switch-setting-summary{display:flex",
    ".hub-switch-setting-toggle{display:flex!important",
    ".hub-switch-setting-label>strong{color:var(--accent-strong)",
    'id="devicesTab-configure" class="hub-settings-tab is-active"',
    'data-devices-tab="configure">Configure Devices</button>',
    'data-devices-tab="autodiscover">AutoDiscover</button>',
    'id="devicesTab-overview" class="hub-settings-tab"',
    'id="devicesPanel-autodiscover"',
    'id="hubDeviceConfiguration"',
    "function selectDevicesTab(which='configure',focus=false)",
    "const ids=['configure','autodiscover','overview']",
    "selectDevicesTab('configure')",
):
    assert marker in SOURCE, marker

settings_start = SOURCE.index("function renderDiscovery(){")
settings_end = SOURCE.index("function renderDeviceConfiguration(){", settings_start)
settings_block = SOURCE[settings_start:settings_end]
for moved in (
    "const sw=sec('Switches'",
    "const st=sec('Stack member display mapping')",
    "SNMP community",
    "Add switch",
    "Add stack member",
):
    assert moved not in settings_block, moved

device_start = SOURCE.index("function renderDeviceConfiguration(){")
device_end = SOURCE.index("function renderDiscoveryBackupSettings(){", device_start)
device_block = SOURCE[device_start:device_end]
assert "discoverySwitchExpansionInitialized" not in SOURCE
assert "switches[0]" not in device_block
assert "expandedDiscoverySwitches.add(`index:${s.switches.length-1}`)" in device_block
for obsolete in (
    "hub-switch-setting-order",
    "const move=delta=>",
    "up.addEventListener('click',()=>move(-1))",
    "down.addEventListener('click',()=>move(1))",
    "Use the arrows to reorder switches",
    "document.createElement('summary')",
    "document.createElement('details')",
):
    assert obsolete not in device_block, obsolete

# Backup retention moved out of Discovery Settings and into Maintenance -> Backups.
assert "const bk=sec('Discovery configuration backups')" not in settings_block
for marker in (
    'id="maintenanceDiscoveryBackupSettings"',
    'id="maintenanceBackupSettingsSave"',
    'id="maintenanceBackupSettingsReload"',
    "function renderDiscoveryBackupSettings(){",
):
    assert marker in SOURCE, marker

# Maintenance is the single home for backups, SNMP cleanup, configuration
# transfer, calibration profiles, and destructive reset actions.
for marker in (
    'class="maintenance-tabs" role="tablist"',
    'data-maintenance-tab="backups">Backups</button>',
    'data-maintenance-tab="snmp">SNMP</button>',
    'data-maintenance-tab="configuration">Configuration Import / Export</button>',
    'data-maintenance-tab="calibrations">Calibration Profiles</button>',
    'data-maintenance-tab="reset">Reset</button>',
    'id="maintenancePanel-configuration"',
    'id="maintenancePanel-calibrations"',
    'id="calibrationProfilesRoot"',
    'id="exportConfigurationButton"',
    'id="exportSwitchesButton"',
):
    assert marker in SOURCE, marker
assert 'id="configurationCard"' not in SOURCE
assert 'id="calibrationProfilesCard"' not in SOURCE
assert 'id="openConfigurationButton"' not in SOURCE
assert 'id="openCalibrationProfilesButton"' not in SOURCE

# Save/reload remains shared across all panes and dirty state is not cleared by tab changes.
select_start = SOURCE.index("function selectTab(which='core',focus=false)")
select_end = SOURCE.index("function tabKeydown", select_start)
select_block = SOURCE[select_start:select_end]
assert 'dirty.clear()' not in select_block
assert 'hubSettingsSave' in SOURCE and 'hubSettingsReload' in SOURCE

# Shared sticky action bar remains on direct working views. Maintenance owns
# several different operations, so it deliberately has no single fake primary
# action and the removed standalone Configuration/Profile views are absent.
for marker in (
    'id="hubSharedActions" class="hub-settings-actions hub-shared-actions hidden"',
    'id="hubSharedPrimary" class="primary"',
    'id="hubSharedReload"',
    'id="hubSharedBack"',
    "const HUB_SHARED_PAGE_ACTIONS={discovery:{label:'Run Discovery'",
    "devices:{label:'Refresh Devices'",
    "support:{label:'Create Contribution'",
    "unifi2mqtt:{label:'Save UniFi2MQTT Settings'",
    "function runSharedHubPrimary()",
    "function reloadSharedHubView()",
    "updateSharedHubActions(view);window.scrollTo",
    "$('hubSharedPrimary').addEventListener('click',runSharedHubPrimary)",
    "$('hubSharedReload').addEventListener('click',reloadSharedHubView)",
    "$('hubSharedBack').addEventListener('click',goBack)",
):
    assert marker in SOURCE, marker
for removed_mapping in (
    "configuration:{label:'Export Configuration'",
    "maintenance:{label:'Scan MQTT Entities'",
    "profiles:{label:'Refresh Profiles'",
):
    assert removed_mapping not in SOURCE, removed_mapping

# Hub navigation reflects the consolidated architecture.
for marker in (
    'Add / Remove Devices',
    'Show Detected Devices &amp; Status',
    'Reorder Switches',
    '<b>Maintenance</b>',
    '<span>Backups</span>',
    '<span>SNMP Maintenance</span>',
    '<span>Configuration Import / Export</span>',
    '<span>Calibration Profiles</span>',
):
    assert marker in SOURCE, marker
assert '<b>Calibration Profiles</b>' not in SOURCE
assert '<b>Import / Export Configuration</b>' not in SOURCE
assert '<span>Add / Remove Switches</span>' not in SOURCE

# Configure Devices is the first/default Devices surface.
assert SOURCE.index('id="devicesTab-configure"') < SOURCE.index('id="devicesTab-autodiscover"') < SOURCE.index('id="devicesTab-overview"')
assert SOURCE.index('id="devicesPanel-configure"') < SOURCE.index('id="devicesPanel-autodiscover"') < SOURCE.index('id="devicesPanel-overview"')
assert "window.SwitchVisionHubSettings?.selectDevicesTab?.('configure')" in SOURCE

print("Switch Vision Settings top tabs regression: PASS")
