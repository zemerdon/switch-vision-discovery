#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"
JOB = ROOT / "runtime_src/discovery_job.sh"

payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
device = next(row for row in payload["devices"] if row.get("model") == "N2128PX-ON")

assert device["status"] == "experimental"
assert device["default_faceplate"] == "faceplates/dell-28-rj45-2sfp.png"
assert device["calibration_profile"] == "dell_28rj45_2sfp"
assert device["visuals"]["recommended_faceplate"] == "faceplates/dell-28-rj45-2sfp.png"
assert device["visuals"]["calibration_profile"] == "dell_28rj45_2sfp"

notes = "\n".join(str(note) for note in device.get("notes") or [])
lowered = notes.casefold()
for required in (
    "current-build field feedback confirms",
    "faceplate alignment",
    "port-description presentation",
    "detailed per-port poe card/presentation",
    "system-sensor applicability",
    "vlan/trunk semantics",
):
    assert required in lowered, required
for stale in (
    "generic 48 rj45 + 4 sfp",
    "exact dell faceplate pending",
    "final dell faceplate calibration",
):
    assert stale not in lowered, stale

source = JOB.read_text(encoding="utf-8")
expected = '- Faceplate: dedicated Dell 28 RJ45 + 2 SFP+ visual; current-build alignment confirmed'
assert expected in source
assert 'generic 48 RJ45 + 4 SFP fallback visual; exact Dell faceplate pending' not in source

print("Switch Vision Discovery 2.4.46 Dell visual-state regression: PASS")
