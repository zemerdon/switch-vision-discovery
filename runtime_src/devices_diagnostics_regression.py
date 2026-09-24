#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import json
import tempfile

source = (Path(__file__).resolve().parent / "support_web.py").read_text(encoding="utf-8")

# Detected Device Information now lives inline on the Devices page. The old
# duplicate navigation/page must not return.
for forbidden in (
    'id="openDiagnosticsButton"',
    'id="diagnosticsCard"',
    'id="refreshDiagnosticsButton"',
    'id="diagnosticsRunDiscoveryButton"',
    "function loadDiagnostics()",
    "function refreshDiagnosticsData(",
    "function renderDiagnostics(",
):
    assert forbidden not in source, forbidden

# Devices owns the global diagnostics summary/messages and the existing report
# actions while retaining the same authoritative diagnostics API/download.
for marker in (
    'id="devicesDiagnosticsSummary"',
    'id="devicesDiagnosticsMessages"',
    'id="copyDiagnosticsButton"',
    'id="downloadDiagnosticsButton"',
    "function renderDeviceDiagnosticsSummary(d)",
    "endpoint('api/diagnostics')",
    "endpoint('download/diagnostics.txt')",
    'elif path == "/api/diagnostics":',
    'elif path == "/download/diagnostics.txt":',
):
    assert marker in source, marker

# Saved and detected devices share one expandable list. Expansion survives Hub
# background refreshes, saved-device ordering uses only the persistent arrow
# controls, and unmatched API-only devices remain visible.
for marker in (
    "let expandedUnifiedDevices=new Set();",
    "function detectedDeviceKey(item)",
    "function renderUnifiedDevices()",
    "entry.className=`device-card unified-device-details${item?' configured-device':''}${enabled?'':' disabled'}`",
    "entry.dataset.expanded=String(expanded)",
    "const summary=document.createElement('div');summary.className='unified-device-summary'",
    "className='device-order-button'",
    "className='device-order-controls'",
    "actions.append(toggle)",
    "const rowTop=document.createElement('div');rowTop.className='unified-device-row'",
    "summary.append(main,chevron)",
    "rowTop.append(orderControls,summary,actions)",
    "if(ci>0){const up=document.createElement('button')",
    "if(ci<controllable.length-1){const down=document.createElement('button')",
    "function buildUnifiedDeviceRows()",
    "for(const [index,item] of detected.entries())",
    "if(currentView==='devices')await refreshDevicesData(false)",
):
    assert marker in source, marker

for forbidden in (
    'id="devicesSummary"',
    '<h3>Detected Devices</h3>',
):
    assert forbidden not in source, forbidden

# Saved rows correlate to detected SNMP evidence using stable identity and the
# management target recorded in the walk header, preventing a capability-file
# alias such as 2960x-48-rj45 from appearing as a duplicate saved switch.
for marker in (
    "function detectedForConfigured(item,detected,used)",
    "candidate?.source_switch_name",
    "candidate?.management_target",
    "item.configured_management_target",
    "item.effective_management_target",
    'line.startswith("# Switch IP: ")',
    '"source_switch_name": source_switch_name',
    '"management_target": management_target',
    'if source_walk_value and not walk_found:',
):
    assert marker in source, marker

# The device summary alone owns expansion. Reorder controls sit to its left and
# state/source controls sit to its right, so action buttons are outside the
# expand/collapse hit area. Native <summary> remains intentionally unused.
render_start = source.index("function renderUnifiedDevices(){")
render_end = source.index("function renderConfiguredDevices", render_start)
render_block = source[render_start:render_end]
assert "document.createElement('details')" not in render_block
assert "document.createElement('summary')" not in render_block
assert "const entry=document.createElement('div')" in render_block
assert "const summary=document.createElement('div');summary.className='unified-device-summary'" in render_block
assert "summary.addEventListener('click'" in render_block
assert "summary.addEventListener('keydown'" in render_block
assert "event.target===summary" in render_block
assert render_block.count("event.preventDefault();event.stopPropagation()") >= 3
assert "if(ci>0){const up=document.createElement('button')" in render_block
assert "if(ci<controllable.length-1){const down=document.createElement('button')" in render_block
assert "orderControls.append(up,down)" not in render_block
assert "actions.append(toggle)" in render_block
assert "summary.append(main,chevron)" in render_block
assert "rowTop.append(orderControls,summary,actions)" in render_block
assert "const disclosure=document.createElement('button')" not in render_block
assert ".unified-device-body[hidden]{display:none!important}" in source

for forbidden in (
    "device-drag-handle",
    "reorderConfiguredByDrag",
    "dragstart",
    "dragover",
):
    assert forbidden not in source, forbidden

# Expanded rows preserve the detailed information previously exposed on the
# standalone page: registry validation plus source/walk/firmware, uplinks,
# mapping and calibration profile.
for marker in (
    "body.appendChild(deviceCard(normalized));",
    "Uplinks detected:",
    "Mapping profile:",
    "Calibration profile:",
    "SNMP walk:",
    "Firmware:",
):
    assert marker in source, marker


# A stale pre-rename SNMP capability whose recorded source walk no longer exists
# must not render as a separate detected-only device. Current capability records
# with an existing source walk remain visible.
spec = importlib.util.spec_from_file_location("sv_support_web_devices_regression", Path(__file__).resolve().parent / "support_web.py")
assert spec and spec.loader
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)
with tempfile.TemporaryDirectory(prefix="sv-device-diagnostics-") as tmp_name:
    tmp = Path(tmp_name)
    share = tmp / "share"
    caps = share / "capabilities"
    walks = share / "snmpwalks"
    caps.mkdir(parents=True)
    (walks / "2960x-48p").mkdir(parents=True)
    current_walk = walks / "2960x-48p" / "live-targeted-snmpwalk.txt"
    current_walk.write_text('# Switch IP: 192.0.2.103\n.1.3.6.1.2.1.1.1.0 = STRING: "current"\n', encoding="utf-8")
    stale_walk = walks / "2960x-48-rj45" / "live-targeted-snmpwalk.txt"
    live_cap = {
        "source_walk": str(current_walk),
        "device": {"model_text": "WS-C2960X-48FPD-L", "support_status": "confirmed"},
        "interfaces": [],
    }
    stale_cap = {
        "source_walk": str(stale_walk),
        "device": {"model_text": "WS-C2960X-48FPD-L", "support_status": "confirmed"},
        "interfaces": [],
    }
    (caps / "2960x-48p-capabilities.json").write_text(json.dumps(live_cap), encoding="utf-8")
    (caps / "2960x-48-rj45-capabilities.json").write_text(json.dumps(stale_cap), encoding="utf-8")
    registry = tmp / "registry.json"
    registry.write_text('{"devices": []}', encoding="utf-8")
    web.DEFAULT_SHARE_DIR = share
    web.DEFAULT_REGISTRY_FILE = registry
    web.DEFAULT_UNIFI_SNAPSHOT = share / "unifi" / "devices.json"
    web.DEFAULT_UNIFI_DIAGNOSTICS = share / "unifi" / "diagnostics.json"
    snapshot = web._diagnostics_snapshot("test")
    names = [item.get("name") for item in snapshot.get("devices", [])]
    assert "2960x-48p" in names, names
    assert "2960x-48-rj45" not in names, names

    # Existing historical walk folders must not become extra Devices rows when
    # the saved inventory contains the current identities. This reproduces the
    # field case where two configured switches appeared as four after older
    # switch_name folders remained on disk.
    stale_walk.parent.mkdir(parents=True)
    stale_walk.write_text(
        '# Switch IP: 192.0.2.103\n.1.3.6.1.2.1.1.1.0 = STRING: "historical"\n',
        encoding="utf-8",
    )
    c3560_current_dir = walks / "Cisco3560C"
    c3560_stale_dir = walks / "Cisco_3560-C"
    c3560_current_dir.mkdir(parents=True)
    c3560_stale_dir.mkdir(parents=True)
    c3560_current_walk = c3560_current_dir / "live-full-snmpwalk.txt"
    c3560_stale_walk = c3560_stale_dir / "live-full-snmpwalk.txt"
    c3560_current_walk.write_text(
        '# Switch IP: 192.0.2.104\n.1.3.6.1.2.1.1.1.0 = STRING: "current-3560"\n',
        encoding="utf-8",
    )
    c3560_stale_walk.write_text(
        '# Switch IP: 192.0.2.104\n.1.3.6.1.2.1.1.1.0 = STRING: "historical-3560"\n',
        encoding="utf-8",
    )
    c3560_cap = {
        "source_walk": str(c3560_current_walk),
        "generated_at": "2026-09-25T00:02:00+00:00",
        "device": {"model_text": "WS-C3560CG-8PC-S", "support_status": "experimental"},
        "interfaces": [],
    }
    c3560_stale_cap = {
        **c3560_cap,
        "source_walk": str(c3560_stale_walk),
        "generated_at": "2026-08-30T00:02:00+00:00",
    }
    live_cap["generated_at"] = "2026-09-25T00:01:00+00:00"
    stale_cap["generated_at"] = "2026-08-30T00:01:00+00:00"
    (caps / "2960x-48p-capabilities.json").write_text(json.dumps(live_cap), encoding="utf-8")
    (caps / "2960x-48-rj45-capabilities.json").write_text(json.dumps(stale_cap), encoding="utf-8")
    (caps / "Cisco3560C-capabilities.json").write_text(json.dumps(c3560_cap), encoding="utf-8")
    (caps / "Cisco_3560-C-capabilities.json").write_text(json.dumps(c3560_stale_cap), encoding="utf-8")
    configured_options = {
        "switches": [
            {
                "switch_name": "2960x-48p",
                "switch_host": "192.0.2.103",
                "sensor_prefix": "cisco2960",
            },
            {
                "switch_name": "Cisco3560C",
                "switch_host": "192.0.2.104",
                "sensor_prefix": "cisco3560",
            },
        ]
    }
    options_file = tmp / "options.json"
    options_file.write_text(json.dumps(configured_options), encoding="utf-8")
    web._self_addon_options = lambda: configured_options
    snapshot = web._diagnostics_snapshot("test", options_file)
    names = [item.get("name") for item in snapshot.get("devices", [])]
    assert names == ["2960x-48p", "Cisco3560C"], names

    # One physical chassis observed by both SNMP and UniFi must be one Hub row.
    # Hardware MAC is stronger than management address, so an internal UniFi IP
    # can safely reconcile with an SNMP target reached through another address.
    live_cap["device"]["mac_address"] = "02:11:22:33:44:55"
    (caps / "2960x-48p-capabilities.json").write_text(json.dumps(live_cap), encoding="utf-8")
    unifi_dir = share / "unifi"
    unifi_dir.mkdir(parents=True)
    (unifi_dir / "devices.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "devices": [
                    {
                        "id": "same-physical-switch",
                        "name": "UniFi observation",
                        "model": "USW Pro 24",
                        "ip_address": "198.51.100.55",
                        "mac_address": "02-11-22-33-44-55",
                        "state": "ONLINE",
                        "firmware": "test",
                        "ports": [],
                        "api_capabilities": {"port_detail": True},
                    },
                    {
                        "id": "different-switch",
                        "name": "Different switch",
                        "model": "US 8 60W",
                        "ip_address": "198.51.100.56",
                        "mac_address": "02:aa:bb:cc:dd:ee",
                        "state": "ONLINE",
                        "ports": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    snapshot = web._diagnostics_snapshot("test")
    rows = snapshot["devices"]
    merged = [item for item in rows if item.get("unifi_device_id") == "same-physical-switch"]
    assert len(merged) == 1, rows
    assert merged[0]["name"] == "2960x-48p"
    assert merged[0]["data_source"] == "SNMP + UniFi API"
    assert merged[0]["unifi_match_basis"] == "hardware_mac"
    assert "_identity_mac" not in merged[0] and "_identity_ip" not in merged[0]
    assert len([item for item in rows if item.get("unifi_device_id") == "different-switch"]) == 1

    # Ambiguous hardware identity must fail closed instead of collapsing rows.
    duplicate_cap = dict(live_cap)
    duplicate_cap["source_walk"] = str(current_walk)
    (caps / "second-current-capabilities.json").write_text(json.dumps(duplicate_cap), encoding="utf-8")
    snapshot = web._diagnostics_snapshot("test")
    same_id_rows = [item for item in snapshot["devices"] if item.get("unifi_device_id") == "same-physical-switch"]
    assert len(same_id_rows) == 1
    assert same_id_rows[0]["data_source"] == "UniFi API"

print("Discovery Devices inline diagnostics contract: PASS")
