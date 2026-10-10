#!/usr/bin/env python3
"""Model-scoped HP optical refresh Hub contract; no live write side effects."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/"runtime_src/support_web.html").read_text()
PY=(ROOT/"runtime_src/support_web.py").read_text()
BACKUP=(ROOT/"runtime_src/complete_backup.py").read_text()
assert 'id="hubHpOpticsSettings"' in HTML
assert 'class="hub-hp-optics-warning"' in HTML
assert 'possible link disruption' in HTML.lower()
assert 'id="hubHpOpticsEnabled" type="checkbox"' in HTML
assert 'id="hubHpOpticsCommunity" type="password"' in HTML
assert 'function renderHpOpticsSettings' in HTML
assert 'function saveHpOpticsSettings' in HTML
assert "renderHpOpticsSettings()" in HTML
assert "api/optics/settings" in HTML
assert 'Switch Vision SNMP2MQTT is not installed' in HTML
assert 'switch_vision/get_hp_optics_settings' in PY
assert 'switch_vision/set_hp_optics_settings' in PY
assert 'path == "/api/optics/settings"' in PY
assert "if not self._allow_ingress_request()" in PY
assert "core_settings_status=_core_settings_status" in PY
assert "SNMP community strings" in BACKUP
# No SNMP SET command implementation, shell invocation, write secret, user-selected
# OID or arbitrary device target belongs in the Hub.
assert 'snmpset' not in PY.lower()
assert 'subprocess.run(["snmpset"' not in HTML
assert 'write_community_configured' in HTML
print("HP_3500YL_HUB_WARNED_OPT_IN_SETTINGS_PASS")
