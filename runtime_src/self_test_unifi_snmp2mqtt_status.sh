# Switch Vision Discovery self-test UniFi-only SNMP2MQTT status module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# v2.1.36 UniFi-only SNMP2MQTT status regression.
PYTHONPATH="$BASE_DIR" python3 - <<'PYTEST_V2136_UNIFI_ONLY'
import tempfile
from pathlib import Path
import support_web as web

tmp = tempfile.TemporaryDirectory()
web.DEFAULT_GENERATED_SNMP2MQTT = Path(tmp.name) / "generated-snmp2mqtt.yaml"

web._self_addon_options = lambda: {
    "generate_snmp2mqtt": "true",
    "parse_all_walks": "false",
    "switches": [],
}
status = web._generated_yaml_status()
assert status["applicable"] is False
assert status["validation"]["valid"] is None
assert "UniFi2MQTT-only" in status["reason"]

source = (
    Path(web.__file__).read_text(encoding="utf-8")
    + "\n"
    + Path(web.__file__).with_name("hub_diagnostics.py").read_text(encoding="utf-8")
)
assert 'if not generated_yaml["found"] and snmp2mqtt_applicability["applicable"]:' in source
assert '"snmp2mqtt_applicability": snmp2mqtt_applicability' in source
assert 'if snmp2mqtt_applicability["applicable"]:' in source
assert "stale_candidates.insert(" in source
assert '("SNMP2MQTT YAML", share / "generated-snmp2mqtt.yaml")' in source
assert 'id="generatedYamlDescription"' in web._PAGE
assert 'id="generatedYamlActions"' in web._PAGE
assert 'id="regenerateYamlHelp"' in web._PAGE
assert "d.applicable!==false" in web._PAGE
assert "regen.hidden=true" in web._PAGE
assert "Not in use · no enabled SNMP targets" in web._PAGE

web._self_addon_options = lambda: {
    "generate_snmp2mqtt": "true",
    "parse_all_walks": "false",
    "switches": [{
        "switch_name": "SW1",
        "switch_host": "192.0.2.10",
        "enabled": "enabled",
    }],
}
status = web._generated_yaml_status()
assert status["applicable"] is True
assert status["validation"]["valid"] is False
assert "not found" in status["validation"]["error"].lower()

web._self_addon_options = lambda: {
    "generate_snmp2mqtt": "false",
    "parse_all_walks": "false",
    "switches": [{
        "switch_name": "SW1",
        "switch_host": "192.0.2.10",
        "enabled": "enabled",
    }],
}
status = web._generated_yaml_status()
assert status["applicable"] is False
assert "disabled" in status["reason"].lower()
print("Switch Vision Discovery v2.1.36 UniFi-only SNMP2MQTT status regression: PASS")
PYTEST_V2136_UNIFI_ONLY
