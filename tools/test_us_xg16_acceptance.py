#!/usr/bin/env python3
from pathlib import Path
import json
import yaml

ROOT = Path(__file__).resolve().parents[1]
registry = json.loads((ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json").read_text(encoding="utf-8"))
profiles = yaml.safe_load((ROOT / "runtime_src/profiles/switch-vision-profiles.yaml").read_text(encoding="utf-8"))
row = next(item for item in registry["devices"] if item.get("model") == "US XG 16")
assert row["status"] == "experimental"
assert row["visuals"]["status"] == "detected"
assert row["ports"] == {
    "rj45": 4,
    "poe": False,
    "uplinks": 12,
    "uplink_type": "12x 10G SFP+",
    "gigabit_sfp": 0,
    "ten_gigabit_sfp_plus": 12,
}
assert row["unifi_api_port_map"] == {"rj45": [13, 14, 15, 16], "sfp": list(range(1, 13))}
assert row["validation"]["exact_model_detection"] == "live_api_confirmed_two_units"
assert row["contributions"][0]["devices_observed"] >= 2
assert row["contributions"][0]["dashboard_validation"] == "pending"
assert profiles["profiles"]["ubiquiti-us-xg-16-api"]["status"] == "experimental"
print("US XG 16 Experimental acceptance contract: PASS")
