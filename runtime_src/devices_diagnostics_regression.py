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
    "entry.className=`device-card unified-device-details configured-device",
    "entry.open=expandedUnifiedDevices.has(key)",
    "if(entry.open)expandedUnifiedDevices.add(key);else expandedUnifiedDevices.delete(key)",
    "className='device-order-button'",
    "className='device-order-controls'",
    "summary.append(orderControls,main,actions)",
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

print("Discovery Devices inline diagnostics contract: PASS")
