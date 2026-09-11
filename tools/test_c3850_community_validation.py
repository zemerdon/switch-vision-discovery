#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
sys.path.insert(0, str(RUNTIME))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


vendor_sensor = load_module("sv_vendor_sensor_scan_c3850", RUNTIME / "vendor_sensor_scan.py")
support_diag = load_module("sv_support_diag_c3850", RUNTIME / "support_diagnostics.py")

registry = json.loads((RUNTIME / "opt/switch-vision/devices/supported_devices.json").read_text(encoding="utf-8"))
rows = {row.get("model"): row for row in registry.get("devices", []) if isinstance(row, dict)}

c3850 = rows["WS-C3850-12XS-E"]
assert c3850["status"] == "community_validated", c3850
assert c3850["ports"] == {
    "rj45": 0,
    "poe": False,
    "uplinks": 12,
    "uplink_type": "12x 10G SFP+",
    "gigabit_sfp": 0,
    "ten_gigabit_sfp_plus": 12,
}, c3850["ports"]
assert c3850["validation"]["system_sensors"].startswith("community_confirmed_cisco_envmon"), c3850["validation"]
assert c3850["validation"]["uplinks"].startswith("community_confirmed_te_member_0_1_12"), c3850["validation"]
assert c3850["visuals"]["status"] == "community_validated", c3850["visuals"]

# Owner-confirmed hold: the 24-port 2960X remains Experimental until its four
# physical uplinks are field-confirmed, even though SNMP sees candidate positions.
c2960 = rows["WS-C2960X-24PS-L"]
assert c2960["status"] == "experimental", c2960
assert c2960["ports"]["rj45"] == 24 and c2960["ports"]["uplinks"] == 4, c2960["ports"]
assert c2960["validation"]["uplinks"] == "pending", c2960["validation"]

products = json.loads((RUNTIME / "opt/switch-vision/mib_database/vendors/cisco/products.json").read_text(encoding="utf-8"))
product = next(row for row in products["products"] if row.get("sys_object_id") == "1.3.6.1.4.1.9.1.1745")
assert product["family"] == "Catalyst 3850", product
assert "WS-C3850-12XS-E" in product["tested_models"], product

with tempfile.TemporaryDirectory(prefix="sv-c3850-evidence-") as temp_name:
    temp = Path(temp_name)
    walk = temp / "c3850.walk"
    walk.write_text(
        """.1.3.6.1.4.1.9.9.13.1.3.1.3.1012 = Gauge32: 26
.1.3.6.1.4.1.9.9.13.1.3.1.3.1013 = Gauge32: 36
.1.3.6.1.4.1.9.9.13.1.3.1.3.1014 = Gauge32: 46
.1.3.6.1.4.1.9.9.13.1.4.1.3.1017 = INTEGER: 1
.1.3.6.1.4.1.9.9.13.1.4.1.3.1018 = INTEGER: 1
.1.3.6.1.4.1.9.9.13.1.4.1.3.1019 = INTEGER: 1
.1.3.6.1.4.1.9.9.13.1.5.1.3.1015 = INTEGER: 1
.1.3.6.1.4.1.9.9.13.1.5.1.3.1016 = INTEGER: 5
""",
        encoding="utf-8",
    )
    caps = {
        "device": {
            "vendor": "cisco",
            "vendor_name": "Cisco Systems",
            "family": "Unknown Cisco",
            "model_text": "WS-C3850-12XS-E",
            "support_status": "experimental",
            "sys_object_id": "1.3.6.1.4.1.9.1.1745",
        },
        "registry": {
            "match": True,
            "exact_model": "WS-C3850-12XS-E",
            "family": "Catalyst 3850",
            "status": "community_validated",
        },
        "summary": {"interface_count": 16, "physical_count": 12, "rj45_count": 0, "sfp_plus_count": 12, "uplink_count": 12},
    }
    payload = vendor_sensor.build(walk, caps, RUNTIME / "opt/switch-vision/mib_database")
    assert payload["vendor"] == "cisco" and payload["pack_loaded"] is True, payload
    assert payload["counts_by_category"].get("temperature") == 3, payload
    assert payload["counts_by_category"].get("fan") == 3, payload
    assert payload["counts_by_category"].get("power") == 2, payload

    cap_path = temp / "3850_server-capabilities.json"
    cap_path.write_text(json.dumps(caps, indent=2) + "\n", encoding="utf-8")
    provenance = support_diag._capability_model(cap_path)
    assert provenance is not None
    assert provenance["registry_match"] is True, provenance
    assert provenance["family"] == "Catalyst 3850", provenance
    assert provenance["model"] == "WS-C3850-12XS-E", provenance
    assert provenance["support_status"] == "community_validated", provenance

job = (RUNTIME / "discovery_job.sh").read_text(encoding="utf-8")
ready_line = next(line for line in job.splitlines() if line.strip().startswith("ready = (c3850_ready"))
assert "is_2960(model)) && if_total > 0 && physical_if > 0 && trunk_status_count > 0" not in ready_line, ready_line

print("Catalyst 3850 Community Validated evidence and 2960X experimental-hold regression: PASS")
