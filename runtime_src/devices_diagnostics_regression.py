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

# The entire detected-device row is expandable and expansion survives Hub
# background refreshes instead of collapsing every polling cycle.
for marker in (
    "let expandedDetectedDevices=new Set();",
    "function detectedDeviceKey(item)",
    "entry.className='device-card detected-device-details'",
    "entry.open=expandedDetectedDevices.has(key)",
    "entry.addEventListener('toggle'",
    "if(entry.open)expandedDetectedDevices.add(key);else expandedDetectedDevices.delete(key)",
    "if(currentView==='devices')await refreshDevicesData(false)",
):
    assert marker in source, marker

# Expanded rows preserve the detailed information previously exposed on the
# standalone page: registry validation plus source/walk/firmware, uplinks,
# mapping and calibration profile.
for marker in (
    "const card=deviceCard(normalized);",
    "Uplinks detected:",
    "Mapping profile:",
    "Calibration profile:",
    "SNMP walk:",
    "Firmware:",
):
    assert marker in source, marker

print("Discovery Devices inline diagnostics contract: PASS")
