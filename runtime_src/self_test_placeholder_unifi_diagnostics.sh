# Switch Vision Discovery self-test placeholder/UniFi diagnostics module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# v2.1.18 placeholder and UniFi diagnostics regressions.
python3 - "$BASE_DIR" <<'PYTEST_V217'
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

base = Path(sys.argv[1])
sys.path.insert(0, str(base))

spec = importlib.util.spec_from_file_location(
    "switch_vision_support_web_v217",
    base / "support_web.py",
)
assert spec and spec.loader
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)

placeholder = {
    "switch_name": "",
    "switch_host": "",
    "sensor_prefix": "stale_placeholder",
    "snmp_community": "readonly",
    "enabled": "enabled",
    "walk_mode": "targeted",
    "switch_model": "auto",
}

validated = web._validate_switch_row(
    placeholder,
    1,
)

assert validated["switch_name"] == ""
assert validated["switch_host"] == ""
assert validated["sensor_prefix"] == ""

web._validate_inventory_identities(
    {
        "switches": [
            placeholder,
        ],
        "stack_member_prefixes": [],
    }
)

assert web._configured_switch_count(
    [placeholder]
) == 0

bad = dict(placeholder)
bad["switch_host"] = "192.0.2.55"

try:
    web._validate_inventory_identities(
        {
            "switches": [bad],
            "stack_member_prefixes": [],
        }
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "real incomplete switch row was accepted"
    )

with tempfile.TemporaryDirectory() as td:
    path = Path(td) / "diagnostics.json"

    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "product":
                    "Switch Vision UniFi2MQTT",
                "version": "2.0.43",
                "status": "error",
                "stage": "list_devices",
                "adopted_devices": 0,
                "switching_devices": 0,
                "rejected_devices": 0,
                "empty_switch_polls": 0,
                "error_type": "RuntimeError",
                "device_classification": [],
                "api_key": "must-not-surface",
            }
        ),
        encoding="utf-8",
    )

    old_path = web.DEFAULT_UNIFI_DIAGNOSTICS

    try:
        web.DEFAULT_UNIFI_DIAGNOSTICS = path

        status = (
            web._unifi2mqtt_diagnostics_status()
        )

        assert status["found"] is True
        assert status["valid"] is True
        assert status["version"] == "2.0.43"
        assert status["status"] == "error"
        assert status["stage"] == "list_devices"
        assert (
            status["error_type"]
            == "RuntimeError"
        )
        assert "api_key" not in status
    finally:
        web.DEFAULT_UNIFI_DIAGNOSTICS = (
            old_path
        )

print(
    "Switch Vision Discovery v2.1.20 "
    "UniFi diagnostics regressions: PASS"
)
PYTEST_V217
