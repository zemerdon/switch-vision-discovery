"""New 24-port Compact defaults must preserve Original as an explicit option."""
import json
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime_src"))
import unifi_dashboard_cards

registry = json.loads(
    (ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json").read_text()
)
counts = {2: 0, 4: 0}
for device in registry["devices"]:
    visuals = device.get("visuals") or {}
    for uplinks in (2, 4):
        stem = f"24rj45-{uplinks}sfp"
        compact = f"faceplates/{stem}-compact.png"
        old = f"faceplates/{stem}.png"
        if visuals.get("recommended_faceplate") != compact:
            continue
        assert device["default_faceplate"] == compact, device["model"]
        assert old in device.get("optional_faceplates", []), device["model"]
        assert old in visuals.get("optional_faceplates", []), device["model"]
        assert device["calibration_profile"] == visuals["calibration_profile"]
        if device["calibration_profile"].startswith("stock_24"):
            assert device["calibration_profile"] == f"stock_24rj45_{uplinks}sfp_compact"
        counts[uplinks] += 1

assert counts == {2: 8, 4: 9}, counts
assert unifi_dashboard_cards.generic_visual(8, 0)[:2] == (
    "stock_24rj45_2sfp_compact",
    "faceplates/24rj45-2sfp-compact.png",
)
assert unifi_dashboard_cards.generic_visual(24, 4)[:2] == (
    "stock_24rj45_4sfp_compact",
    "faceplates/24rj45-4sfp-compact.png",
)
by_model = {x["model"]: x for x in registry["devices"]}
assert by_model["HP ProCurve 1810G-24"]["visuals"]["recommended_faceplate"] == (
    "faceplates/hp-1810-24g.png"
)
assert "faceplates/24rj45-2sfp.png" in by_model[
    "HP ProCurve 1810G-24"
]["visuals"]["optional_faceplates"]

print("Discovery original/compact 24-port defaults: PASS (17 exact-model recommendations)")
