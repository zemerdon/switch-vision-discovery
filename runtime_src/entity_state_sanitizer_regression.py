"""Entity-state sanitization parity and protected-data redaction."""
from entity_state_sanitizer import safe_entity_state
import walk_correlation
import support_diagnostics
import ha_entity_snapshot_sanitizer

checks = {
    ("sensor.port_rx_bytes", " 10.25 "): "10.25",
    ("sensor.port_tx_bytes", "-3.14"): "-3.14",
    ("binary_sensor.port_status", "UP"): "up",
    ("sensor.port_status", " off "): "off",
    ("sensor.port_status", "UNKNOWN"): "unknown",
    ("sensor.port_rx_bytes", "on"): "<NON_NUMERIC>",
    ("sensor.port_status", "connected"): "<NON_NUMERIC>",
    ("sensor.port_status", "user@example.com"): "<NON_NUMERIC>",
    ("sensor.port_status", "1e5"): "<NON_NUMERIC>",
    ("sensor.port_status", True): "true",
    ("sensor.port_status", None): None,
    ("sensor.port_status", " \n "): None,
}
for (entity, value), expected in checks.items():
    assert safe_entity_state(entity, value) == expected, (entity, value)
    for owner in (walk_correlation, support_diagnostics, ha_entity_snapshot_sanitizer):
        assert owner._safe_state(entity, value) == expected, (owner, entity)
        assert owner._safe_state is safe_entity_state, owner
assert "unknown" in ha_entity_snapshot_sanitizer.SAFE_TEXT_STATES
print("Discovery shared entity-state sanitizer parity/privacy: PASS")
