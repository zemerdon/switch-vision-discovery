from __future__ import annotations
import json
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[1]
registry = json.loads((ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json").read_text(encoding="utf-8"))
device = next(d for d in registry["devices"] if d.get("model") == "WS-C3750-48P")
assert device["status"] == "experimental"
assert device["ports"]["rj45"] == 48 and device["ports"]["poe"] is True
assert device["ports"]["gigabit_sfp"] == 4 and device["ports"]["ten_gigabit_sfp_plus"] == 0
assert device["mapping_profile"] == "cisco-3750-48p-48fe-4sfp"
assert device["default_faceplate"] == "faceplates/48rj45-4sfp.png"
assert device["calibration_profile"] == "default_cisco_48_port"
assert device["contributor"] == {"display_name": "Community contributor", "public_credit": False}
assert "SV-2026-" not in json.dumps(device)
profiles = yaml.safe_load((ROOT / "runtime_src/profiles/switch-vision-profiles.yaml").read_text(encoding="utf-8"))["profiles"]
profile = profiles["cisco-3750-48p-48fe-4sfp"]
assert profile["model_patterns"] == ["WS-C3750-48P"]
assert profile["layout"] == {"members": "auto", "rj45_ports": 48, "sfp_1g_ports": 4, "sfp_10g_ports": 0}
assert "Fa{member}/0/{port}" in profile["interface_patterns"]["rj45"]
assert "Gi{member}/0/{port}" in profile["interface_patterns"]["sfp_1g"]
print("Switch Vision Discovery Catalyst 3750 contract: PASS")
