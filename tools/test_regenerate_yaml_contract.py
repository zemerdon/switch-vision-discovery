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

spec = importlib.util.spec_from_file_location("switch_vision_support_web", RUNTIME / "support_web.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

original = {
    "enable_switch_list": False,
    "run_snmp_walks": True,
    "run_live_snmpwalk": True,
    "clean_output_before_walk": True,
    "parse_all_walks": False,
    "generate_snmp2mqtt": False,
    "generated_yaml_path": "/share/switch_vision/generated-snmp2mqtt.yaml",
    "generated_card_path": "/share/switch_vision/generated-dashboard-card.yaml",
    "report_path": "/share/switch_vision/discovery-report.txt",
    "last_run_summary_path": "/share/switch_vision/last-discovery-run.txt",
    "switches": [
        {
            "switch_name": "SW1",
            "switch_host": "192.0.2.10",
            "sensor_prefix": "SW1",
            "snmp_community": "secret-community",
            "enabled": "enabled",
        },
        {
            "switch_name": "SW2",
            "switch_host": "192.0.2.11",
            "sensor_prefix": "SW2",
            "snmp_community": "other-secret",
            "enabled": "disabled",
        },
    ],
}

module._self_addon_options = lambda: json.loads(json.dumps(original))
module._validate_inventory_identities = lambda options: None

with tempfile.TemporaryDirectory() as temp_dir:
    destination = Path(temp_dir) / "regen.json"
    result = module._write_snmp2mqtt_regeneration_options_snapshot(destination)
    assert result == destination
    assert destination.stat().st_mode & 0o077 == 0
    generated = json.loads(destination.read_text(encoding="utf-8"))

assert generated["enable_switch_list"] is True
assert generated["run_snmp_walks"] is False
assert generated["run_live_snmpwalk"] is False
assert generated["clean_output_before_walk"] is False
assert generated["parse_all_walks"] is True
assert generated["generate_snmp2mqtt"] is True
assert generated["generated_yaml_path"] == "/share/switch_vision/generated-snmp2mqtt.yaml"
assert generated["generated_card_path"].startswith("/tmp/")
assert generated["report_path"].startswith("/tmp/")
assert generated["last_run_summary_path"].startswith("/tmp/")
assert generated["switches"] == original["switches"]
assert original["run_snmp_walks"] is True
assert original["parse_all_walks"] is False

source = (RUNTIME / "support_web.py").read_text(encoding="utf-8")
for marker in (
    'id="regenerateYamlButton"',
    'Regenerate SNMP2MQTT YAML uses the existing saved Discovery data and SNMP walks.',
    '/api/discovery/regenerate-yaml',
    'mode="regenerate_yaml"',
    'SWITCH_VISION_CAPABILITIES_DIR',
    'regenerateSnmp2mqttYaml',
):
    assert marker in source, marker

assert 'generated_yaml_path"] = "/tmp/' not in source

job_source = (RUNTIME / "discovery_job.sh").read_text(encoding="utf-8")
for oid in (
    "1.3.6.1.2.1.17.1.4.1.2",
    "1.3.6.1.2.1.17.7.1.4.3",
    "1.3.6.1.2.1.17.7.1.4.5.1.1",
):
    assert oid in job_source, oid
assert "1.3.6.1.2.1.18.1.4.1.2" not in job_source
assert "1.3.6.1.2.1.18.7.1.4.3" not in job_source
assert "1.3.6.1.2.1.18.7.1.4.5.1.1" not in job_source
assert 'model="unknown"; manufacturer="Unknown"' in job_source
assert 'model="unknown"; manufacturer="Cisco"' not in job_source
assert 'manufacturer = "MikroTik"' in job_source
for marker in (
    'else if (c3750_model != "") { model = c3750_model; manufacturer = "Cisco" }',
    'else if (local_model != "") { model = local_model; manufacturer = "Cisco" }',
    'else if (sys_model != "") { model = sys_model; manufacturer = "Cisco" }',
    'else if (candidate_model != "") { model = candidate_model; manufacturer = "Cisco" }',
    'else if (generic_model != "") { model = generic_model; manufacturer = "Cisco" }',
):
    assert marker in job_source, marker
assert "MIKROTIK_SUPPLEMENTAL_OIDS" in job_source
assert "1.3.6.1.4.1.14988.1.1.15.1.1" in job_source
assert "1.3.6.1.4.1.14988\n" not in job_source

print("Discovery stored-walk SNMP2MQTT YAML regeneration, Q-BRIDGE, and manufacturer contracts: PASS")
