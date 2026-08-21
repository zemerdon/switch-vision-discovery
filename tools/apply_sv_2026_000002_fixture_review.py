#!/usr/bin/env python3
"""Temporary review-only patch for a pre-dashboard_support self-test fixture."""
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "runtime_src" / "self-test.sh"
text = path.read_text(encoding="utf-8")
old = '''json.dump({"devices": [
    {"model": "USW-Pro-24-PoE", "status": "experimental", "calibration_profile": "cisco_2960x_24p", "default_faceplate": "faceplates/24rj45-2sfp.png"},
    {"model": "USW Lite 16 PoE", "status": "experimental", "calibration_profile": "cisco_2960x_24p", "default_faceplate": "faceplates/24rj45-4sfp.png"},
    {"model": "US 48 PoE 500W", "status": "experimental", "calibration_profile": "default_cisco_48_port", "default_faceplate": "faceplates/48rj45-4sfp.png"},
]}, open(registry, "w"))'''
new = '''json.dump({"devices": [
    {"model": "USW-Pro-24-PoE", "status": "experimental", "dashboard_support": True, "calibration_profile": "cisco_2960x_24p", "default_faceplate": "faceplates/24rj45-2sfp.png"},
    {"model": "USW Lite 16 PoE", "status": "experimental", "dashboard_support": True, "calibration_profile": "cisco_2960x_24p", "default_faceplate": "faceplates/24rj45-4sfp.png"},
    {"model": "US 48 PoE 500W", "status": "experimental", "dashboard_support": True, "calibration_profile": "default_cisco_48_port", "default_faceplate": "faceplates/48rj45-4sfp.png"},
]}, open(registry, "w"))'''
if new not in text:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"self-test fixture target count={count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
print("Discovery legacy UniFi renderable fixture marked dashboard-supported")
