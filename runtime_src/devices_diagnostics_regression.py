#!/usr/bin/env python3
from pathlib import Path

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

print("Discovery Devices inline diagnostics contract: PASS")
