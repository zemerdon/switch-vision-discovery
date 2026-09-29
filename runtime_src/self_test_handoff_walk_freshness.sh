# Switch Vision Discovery self-test generated-config handoff/walk-freshness module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# v2.2.5 generated-config activation and transaction-aware walk freshness regression.
PYTHONPATH="$BASE_DIR" python3 - "$tmp_dir" <<'PYTEST_V225_HANDOFF'
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import tempfile
import yaml

import support_web as web
import walk_correlation as correlation

tmp = Path(sys.argv[1]) / "v225-handoff"
tmp.mkdir(parents=True, exist_ok=True)
generated = tmp / "generated-snmp2mqtt.yaml"
generated.write_text(
    yaml.safe_dump(
        {
            "targets": [
                {
                    "host": "192.0.2.40",
                    "name": "Regression target",
                    "sensors": [
                        {
                            "oid": "1.3.6.1.2.1.2.2.1.8.1",
                            "name": "SW1 Port 1 Status",
                            "object_id": "sw1_port_1_status",
                        }
                    ],
                }
            ]
        },
        sort_keys=False,
    ),
    encoding="utf-8",
)
web.DEFAULT_GENERATED_SNMP2MQTT = generated
web.time.sleep = lambda _seconds: None

base_runtime = {
    "installed": True,
    "slug": "test_switch_vision_snmp2mqtt",
    "state": "started",
    "options_readable": True,
    "homeassistant_prefix": "homeassistant",
    "base_topic": "snmp2mqtt",
    "host_name_as_target": False,
    "wrapper_options_readable": True,
    "use_switch_vision_generated_yaml": True,
    "switch_vision_generated_yaml_path": str(generated),
}

# Explicit manual-target mode must fail closed without restarting the app.
manual_runtime = dict(base_runtime)
manual_runtime["use_switch_vision_generated_yaml"] = False
web._snmp2mqtt_runtime_info = lambda: dict(manual_runtime)
unexpected_actions = []
web._supervisor_json = lambda *args, **kwargs: unexpected_actions.append((args, kwargs)) or {}
manual_result = web._ensure_snmp2mqtt_running([], 0.0, [])
assert manual_result["handoff_failed"] is True
assert manual_result["configuration_mode"] == "manual"
assert manual_result["action"] == "blocked_configuration"
assert unexpected_actions == []

# A configured generated path that does not match Discovery output must also
# fail before any restart.
path_runtime = dict(base_runtime)
path_runtime["switch_vision_generated_yaml_path"] = str(tmp / "different.yaml")
web._snmp2mqtt_runtime_info = lambda: dict(path_runtime)
unexpected_actions.clear()
path_result = web._ensure_snmp2mqtt_running([], 0.0, [])
assert path_result["handoff_failed"] is True
assert path_result["configuration_mode"] == "generated_path_mismatch"
assert unexpected_actions == []

# Successful restart is proven by exact generated-config identity, not by the
# timing of Home Assistant retained MQTT Discovery publication.
events = []
web._snmp2mqtt_runtime_info = lambda: dict(base_runtime)
web.generated_yaml_generation_id = lambda _path: "123e4567-e89b-12d3-a456-426614174000"
retry_checks = []
def delayed_exact_load(base_topic, generation_id):
    retry_checks.append((base_topic, generation_id))
    return len(retry_checks) >= 3
web.verify_generated_yaml_loaded = delayed_exact_load
retry_lines = []
assert web._verify_snmp2mqtt_generated_config_loaded(retry_lines, base_runtime) is True
assert len(retry_checks) == 3
assert "after 3 checks" in retry_lines[-1]
web.verify_generated_yaml_loaded = lambda base_topic, generation_id: (
    base_topic == "snmp2mqtt"
    and generation_id == "123e4567-e89b-12d3-a456-426614174000"
)
def supervisor(path, *, method="GET", timeout=12.0, payload=None):
    events.append(("supervisor", method, path))
    if path.endswith("/info"):
        return {"data": {"state": "started"}}
    return {"result": "ok"}
web._supervisor_json = supervisor

def unexpected_scan():
    raise AssertionError("retained MQTT entity counts must not gate SNMP2MQTT handoff")
web.scan_mqtt_entities = unexpected_scan
clears = []
def clear_topics(topics):
    events.append(("clear", len(topics)))
    clears.append(list(topics))
    return len(topics), []
web._clear_retained_snmp2mqtt_discovery = clear_topics
web._save_snmp2mqtt_retirement_topics = lambda topics: events.append(("save", len(topics)))
old_topic = "homeassistant/sensor/snmp2mqtt/old_identity/config"
success = web._ensure_snmp2mqtt_running([], 0.0, [old_topic])
assert success["handoff_failed"] is False
assert success["config_load_verified"] is True
assert success["activation_verified"] is True
assert success["mqtt_current_expected"] is None
assert success["mqtt_current_retained"] is None
assert success["mqtt_current_missing"] is None
assert clears == [[old_topic]]
assert "verified active from exact generated configuration load" in success["message"]
assert "catching up" not in success["message"]

# If exact generated-file activation cannot be proven, preserve old retained
# identities and surface a warning. This is a handoff warning, not a false
# overall Discovery failure caused by MQTT publication counts.
events.clear()
clears.clear()
web.verify_generated_yaml_loaded = lambda _base_topic, _generation_id: False
failed = web._ensure_snmp2mqtt_running([], 0.0, [old_topic])
assert failed["handoff_failed"] is True
assert failed["config_load_verified"] is False
assert failed["activation_verified"] is False
assert clears == []
assert "exact generated-configuration load was not verified yet" in failed["message"]

source = Path(web.__file__).read_text(encoding="utf-8")
assert 'handoff_warning = bool(snmp2mqtt_result.get("handoff_failed"))' in source
assert 'operation_warning = degraded_result or partial_result or handoff_warning' in source
assert 'stage="SNMP2MQTT handoff not verified"' not in source
assert 'retained MQTT discovery' in source
assert 'entity counts are never a Discovery success gate' in source
assert '"mqtt_current_expected": None' in source

# A long multi-switch Discovery run must not age out its own early walk.
root = tmp / "walk-freshness"
walk_dir = root / "snmpwalks" / "SW1"
walk_dir.mkdir(parents=True, exist_ok=True)
walk = walk_dir / "live-full-snmpwalk.txt"
walk.write_text(
    ".1.3.6.1.2.1.2.2.1.8.1 = INTEGER: 1\n",
    encoding="utf-8",
)
now = datetime(2026, 8, 24, 4, 30, 0, tzinfo=timezone.utc)
captured = now - timedelta(minutes=20)
os.utime(walk, (captured.timestamp(), captured.timestamp()))
(root / "last-discovery-run.txt").write_text(
    "Switch Vision Discovery last run\n"
    f"Discovery app loaded: {(now - timedelta(minutes=22)).isoformat()}\n"
    f"Generated: {(now - timedelta(minutes=4)).isoformat()}\n",
    encoding="utf-8",
)
generated_doc = {
    "targets": [
        {
            "name": "SW1",
            "sensors": [
                {
                    "object_id": "sw1_port_1_status",
                    "oid": "1.3.6.1.2.1.2.2.1.8.1",
                }
            ],
        }
    ]
}
bindings = {
    "cards": [
        {
            "discovery_selected_switch": "SW1",
            "sensor_prefix": "sw1",
        }
    ]
}
same_run = correlation.build_port_pipeline(
    root,
    generated_doc,
    [],
    bindings,
    ha_available=False,
    now=now,
)
assert same_run["summary"]["fresh_walk_status_rows"] == 1
assert same_run["summary"]["current_run_walk_status_rows"] == 1
assert same_run["ports"][0]["walk_source_status"] == "fresh"
assert same_run["ports"][0]["walk_current_discovery_run"] is True
assert same_run["ports"][0]["walk_freshness_reason"] == "current_discovery_run"

# The same 20-minute-old walk must remain stale when it predates the recorded
# run window, and malformed run metadata must safely fall back to age.
(root / "last-discovery-run.txt").write_text(
    "Switch Vision Discovery last run\n"
    f"Discovery app loaded: {(now - timedelta(minutes=10)).isoformat()}\n"
    f"Generated: {(now - timedelta(minutes=4)).isoformat()}\n",
    encoding="utf-8",
)
old_walk = correlation.build_port_pipeline(
    root,
    generated_doc,
    [],
    bindings,
    ha_available=False,
    now=now,
)
assert old_walk["summary"]["fresh_walk_status_rows"] == 0
assert old_walk["summary"]["stale_walk_status_rows"] == 1
assert old_walk["ports"][0]["walk_current_discovery_run"] is False
assert old_walk["ports"][0]["walk_freshness_reason"] == "stale"

(root / "last-discovery-run.txt").write_text(
    "Switch Vision Discovery last run\nDiscovery app loaded: not-a-time\nGenerated: also-not-a-time\n",
    encoding="utf-8",
)
malformed = correlation.build_port_pipeline(
    root,
    generated_doc,
    [],
    bindings,
    ha_available=False,
    now=now,
)
assert malformed["summary"]["stale_walk_status_rows"] == 1
assert malformed["ports"][0]["walk_freshness_reason"] == "stale"

print("Switch Vision Discovery v2.2.5 verified handoff + walk freshness regression: PASS")
PYTEST_V225_HANDOFF
