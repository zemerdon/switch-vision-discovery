#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import os
import stat
import tempfile
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent

spec = importlib.util.spec_from_file_location(
    "switch_vision_support_web_card_regression",
    RUNTIME / "support_web.py",
)
assert spec and spec.loader
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)

saved_options = {
    "enable_switch_list": False,
    "run_snmp_walks": True,
    "run_live_snmpwalk": True,
    "clean_output_before_walk": True,
    "parse_all_walks": False,
    "generate_snmp2mqtt": True,
    "generate_support_my_switch_bundle": True,
    "snmpwalks_dir": "/share/switch_vision/snmpwalks",
    "generated_yaml_path": "/share/switch_vision/generated-snmp2mqtt.yaml",
    "generated_card_path": "/share/switch_vision/generated-dashboard-card.yaml",
    "report_path": "/share/switch_vision/discovery-report.txt",
    "last_run_summary_path": "/share/switch_vision/last-discovery-run.txt",
    "snmp_log_path": "/share/switch_vision/snmpwalk.log",
    "switches": [
        {
            "switch_name": "LAB-SW1",
            "display_name": "Regression Switch",
            "switch_host": "192.0.2.10",
            "sensor_prefix": "LAB_SW1",
            "snmp_community": "private-test-value",
            "enabled": "enabled",
            "walk_mode": "targeted",
            "switch_model": "auto",
            "card_header_title": "",
        },
        {
            "switch_name": "LAB-SW2",
            "display_name": "Disabled Regression Switch",
            "switch_host": "192.0.2.11",
            "sensor_prefix": "LAB_SW2",
            "snmp_community": "private-test-value-2",
            "enabled": "disabled",
            "walk_mode": "targeted",
            "switch_model": "auto",
            "card_header_title": "",
        },
    ],
    "stack_member_prefixes": [],
}

web._self_addon_options = lambda: copy.deepcopy(saved_options)
web._validate_inventory_identities = lambda options: None

with tempfile.TemporaryDirectory(prefix="sv-card-regeneration-") as temp_dir:
    temp = Path(temp_dir)
    share = temp / "share"
    share.mkdir()
    walks = share / "snmpwalks" / "LAB-SW1"
    walks.mkdir(parents=True)
    stored_walk = walks / "stored-walk.txt"
    stored_walk.write_text(
        '.1.3.6.1.2.1.1.1.0 = STRING: "stored regression evidence"\n',
        encoding="utf-8",
    )

    live_yaml = share / "generated-snmp2mqtt.yaml"
    live_yaml_bytes = b"# live SNMP2MQTT sentinel - must remain byte-identical\n"
    live_yaml.write_bytes(live_yaml_bytes)
    live_card = share / "generated-dashboard-card.yaml"
    log_path = temp / "discovery-web.log"
    log_path.write_text("", encoding="utf-8")

    web.DEFAULT_GENERATED_SNMP2MQTT = live_yaml
    web.DEFAULT_GENERATED_CARD = live_card
    web.DEFAULT_DISCOVERY_LOG = log_path
    web._ensure_runtime_paths = lambda: None

    # Keep the stored inventory but point its walk root at this disposable fixture.
    web._self_addon_options = lambda: {
        **copy.deepcopy(saved_options),
        "snmpwalks_dir": str(share / "snmpwalks"),
    }

    snapshot_path = temp / "card-options.json"
    result = web._write_dashboard_card_regeneration_options_snapshot(snapshot_path)
    assert result == snapshot_path
    generated = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert generated["switches"][0]["switch_name"] == "LAB-SW1"
    assert generated["switches"][0]["switch_host"] == "192.0.2.10"
    assert generated["switches"][0]["enabled"] == "enabled"
    assert generated["switches"][1]["switch_name"] == "LAB-SW2"
    assert generated["switches"][1]["enabled"] == "disabled"
    assert generated["enable_switch_list"] is True
    assert generated["run_snmp_walks"] is False
    assert generated["run_live_snmpwalk"] is False
    assert generated["clean_output_before_walk"] is False
    assert generated["parse_all_walks"] is True
    assert generated["generate_snmp2mqtt"] is False
    assert generated["generate_support_my_switch_bundle"] is False
    assert generated["generated_card_path"] == str(live_card)
    assert generated["generated_yaml_path"].startswith("/tmp/")
    assert generated["report_path"].startswith("/tmp/")
    assert generated["last_run_summary_path"].startswith("/tmp/")
    assert generated["snmp_log_path"].startswith("/tmp/")
    assert stat.S_IMODE(snapshot_path.stat().st_mode) == 0o600

    fake_discovery = temp / "stored-state-generator.py"
    fake_discovery.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

options = json.loads(Path(os.environ["SWITCH_VISION_OPTIONS_FILE"]).read_text(encoding="utf-8"))
assert options["run_snmp_walks"] is False
assert options["run_live_snmpwalk"] is False
assert options["parse_all_walks"] is True
assert options["generate_snmp2mqtt"] is False
walk_root = Path(options["snmpwalks_dir"])
walks = list(walk_root.rglob("*.txt"))
assert walks, "stored walk fixture was not reused"
evidence = walks[0].read_text(encoding="utf-8")
Path(options["generated_card_path"]).write_text(
    "type: custom:switch-vision-regression\\n"
    "source: stored-state\\n"
    f"evidence_present: {str('stored regression evidence' in evidence).lower()}\\n",
    encoding="utf-8",
)
print("SV_STATUS|stage=Generating dashboard card YAML|switch=LAB-SW1|target=stored|command=stored-parser|activity=Parsing stored walks")
""",
        encoding="utf-8",
    )
    fake_discovery.chmod(0o755)

    def forbidden(name):
        def _raise(*_args, **_kwargs):
            raise AssertionError(f"{name} must not be called by regenerate_card")
        return _raise

    web._remember_current_snmp2mqtt_topics = forbidden("_remember_current_snmp2mqtt_topics")
    web._load_snmp2mqtt_retirement_topics = forbidden("_load_snmp2mqtt_retirement_topics")
    web._ensure_snmp2mqtt_running = forbidden("_ensure_snmp2mqtt_running")
    web._generate_automatic_support_bundle = forbidden("_generate_automatic_support_bundle")

    web._run_discovery(fake_discovery, "regenerate_card")

    state = web._discovery_state_snapshot()
    assert state["running"] is False
    assert state["success"] is True, state
    assert state["mode"] == "regenerate_card"
    assert state["snmp2mqtt"]["status"] == "Not touched", state["snmp2mqtt"]
    assert state["snmp2mqtt"]["action"] == "none"
    assert "not started or restarted" in state["snmp2mqtt"]["message"]
    assert live_yaml.read_bytes() == live_yaml_bytes
    assert live_card.is_file()
    card_text = live_card.read_text(encoding="utf-8")
    assert "source: stored-state" in card_text
    assert "evidence_present: true" in card_text

# Shared operation locking must reject card regeneration while another operation owns the lock.
web._claim_operation("Discovery")
try:
    try:
        web._claim_operation("Dashboard Card YAML regeneration")
    except web.OperationConflict as exc:
        assert "Discovery is already running" in str(exc)
    else:
        raise AssertionError("regenerate-card operation conflict was not enforced")
finally:
    web._release_operation("Discovery")

source = (RUNTIME / "support_web.py").read_text(encoding="utf-8")
for marker in (
    '/api/discovery/regenerate-card',
    'mode="regenerate_card"',
    'id="regenerateCardYamlButton"',
    'Regenerate Dashboard Card YAML',
    'id="devicesRegenerateCardYamlButton"',
    'async function startDashboardCardYamlRegeneration(btn,status)',
    'async function regenerateDashboardCardYaml()',
    'async function regenerateDashboardCardYamlFromDevices()',
    "$('regenerateCardYamlButton').addEventListener('click',regenerateDashboardCardYaml)",
    "$('devicesRegenerateCardYamlButton').addEventListener('click',regenerateDashboardCardYamlFromDevices)",
    'Regenerate Dashboard Card YAML to apply this saved state immediately; no Discovery run is required.',
    'Dashboard Card YAML regeneration started from the current saved device state. No Discovery run or new SNMP walks are required',
    'SNMP2MQTT was not started or restarted during Dashboard Card YAML regeneration.',
):
    assert marker in source, marker

job_source = (RUNTIME / "discovery_job.sh").read_text(encoding="utf-8")
assert 'RUN_LIVE_SNMPWALK=$(json_get run_snmp_walks "$(json_get run_live_snmpwalk "$RUN_LIVE_SNMPWALK")")' in job_source
assert 'if ! truthy "$RUN_LIVE_SNMPWALK"; then' in job_source

print("Discovery stored-state Dashboard Card YAML regeneration contract: PASS")
