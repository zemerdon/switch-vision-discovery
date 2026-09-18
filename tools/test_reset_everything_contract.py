#!/usr/bin/env python3
"""Permanent contract for the destructive-but-bounded Hub Reset Everything workflow."""
from __future__ import annotations

import copy
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime_src'))

import support_web as hub  # noqa: E402


@contextmanager
def patched(**values):
    original = {name: getattr(hub, name) for name in values}
    try:
        for name, value in values.items():
            setattr(hub, name, value)
        yield
    finally:
        for name, value in original.items():
            setattr(hub, name, value)


def test_running_discovery_blocks_before_mutation() -> None:
    touched = []
    with patched(
        _discovery_state_snapshot=lambda: {'running': True},
        _self_addon_options=lambda: touched.append('options') or {},
    ):
        try:
            hub._reset_everything()
        except RuntimeError as exc:
            assert 'Stop Discovery' in str(exc)
        else:
            raise AssertionError('Reset Everything did not block active Discovery')
    assert touched == []


def test_reset_everything_is_switch_vision_scoped_and_preserves_recovery_content() -> None:
    calls = []
    with tempfile.TemporaryDirectory(prefix='sv-reset-everything-') as tmp:
        root = Path(tmp)
        paths = [root / name for name in (
            'devices.json', 'diagnostics.json', 'device-control.json',
            'restore-pending.json', 'ui-preferences.json', 'discovery-history.json',
            'installer-maintenance-response.json', 'discovery.log', 'current-debug.txt'
        )]
        for path in paths:
            path.write_text('temporary runtime state', encoding='utf-8')

        def supervisor(path, *, method='GET', timeout=12.0, payload=None):
            calls.append(('supervisor', path, method, copy.deepcopy(payload)))
            if path.endswith('/info'):
                return {'data': {'state': 'started', 'options': {
                    'mqtt_topic_prefix': 'switch_vision/unifi',
                    'mqtt_discovery_prefix': 'homeassistant',
                }}}
            return {}

        def ha_service(domain, service, data):
            calls.append(('service', domain, service, copy.deepcopy(data)))
            return {}

        snapshot = {
            'devices': [{
                'id': 'device-a', 'name': 'Switch A',
                'ports': [{'idx': 1, 'connector': 'RJ45'}],
            }]
        }
        with patched(
            _discovery_state_snapshot=lambda: {'running': False},
            _self_addon_options=lambda: {'switches': [{'switch_name': 'SW1'}]},
            create_pre_mutation_backup=lambda options, *, reason: calls.append(('backup', reason, copy.deepcopy(options))),
            _unifi2mqtt_settings_status=lambda: {'installed': True, 'slug': 'local_unifi'},
            _read_json=lambda path: snapshot if path == paths[0] else {},
            _supervisor_json=supervisor,
            _reset_snmp_discovery_data=lambda: {'warnings': [], 'mqtt_topics_found': 2, 'mqtt_topics_cleared': 2},
            _home_assistant_service=ha_service,
            _save_core_settings=lambda payload: calls.append(('core_settings', copy.deepcopy(payload))) or {},
            _installer_settings_status=lambda: {'installed': True},
            _save_installer_settings=lambda payload: calls.append(('installer_settings', copy.deepcopy(payload))) or {},
            _find_snmp2mqtt_addon=lambda: {'slug': 'local_snmp'},
            DEFAULT_UNIFI_SNAPSHOT=paths[0],
            DEFAULT_UNIFI_DIAGNOSTICS=paths[1],
            DEFAULT_DEVICE_CONTROL=paths[2],
            DEFAULT_CONFIGURATION_RESTORE_PENDING=paths[3],
            UI_PREFERENCES_PATH=paths[4],
            DEFAULT_DISCOVERY_HISTORY=paths[5],
            DEFAULT_INSTALLER_MAINTENANCE_RESPONSE=paths[6],
            DEFAULT_DISCOVERY_LOG=paths[7],
            DEFAULT_CURRENT_DISCOVERY_DEBUG=paths[8],
        ):
            result = hub._reset_everything()

        assert result['reset'] is True
        assert result['core_calibrations_reset'] is True
        assert result['discovery_settings_reset'] is True
        assert result['snmp2mqtt_settings_reset'] is True
        assert result['unifi2mqtt_settings_reset'] is True
        assert result['installer_settings_reset'] is True
        assert result['unifi_mqtt_topics_found'] > 0
        assert result['unifi_mqtt_topics_cleared'] == result['unifi_mqtt_topics_found']
        assert all(not path.exists() for path in paths)
        assert 'custom faceplate and logo files' in result['preserved']
        assert 'Installer recovery backups' in result['preserved']
        assert 'Discovery configuration backups' in result['preserved']
        assert 'protected contribution/source originals' in result['preserved']

        assert ('backup', 'reset_everything', {'switches': [{'switch_name': 'SW1'}]}) in calls
        assert ('service', 'switch_vision', 'reset_calibrations', {'scope': 'all'}) in calls
        assert ('core_settings', {'reset_to_defaults': True}) in calls
        assert any(row[:3] == ('supervisor', '/addons/local_unifi/stop', 'POST') for row in calls)
        assert any(row[:3] == ('supervisor', '/addons/local_snmp/options', 'POST') for row in calls)
        assert any(row[:3] == ('supervisor', '/addons/local_unifi/options', 'POST') for row in calls)
        assert any(row[:3] == ('supervisor', '/addons/self/options', 'POST') for row in calls)


def test_ui_and_route_require_exact_confirmation() -> None:
    source = (ROOT / 'runtime_src' / 'support_web.py').read_text(encoding='utf-8')
    maintenance = (ROOT / 'runtime_src' / 'maintenance.js').read_text(encoding='utf-8')
    assert 'RESET_EVERYTHING_CONFIRMATION = "RESET EVERYTHING"' in source
    assert 'path == "/api/maintenance/reset-everything"' in source
    assert 'data.get("confirmation")' in source
    assert 'id="resetEverythingButton"' in source
    assert 'id="resetEverythingStatus"' in source
    assert 'confirmation !== "RESET EVERYTHING"' in maintenance
    assert 'api/maintenance/reset-everything' in maintenance
    assert 'custom faceplates/logos' in maintenance


if __name__ == '__main__':
    test_running_discovery_blocks_before_mutation()
    test_reset_everything_is_switch_vision_scoped_and_preserves_recovery_content()
    test_ui_and_route_require_exact_confirmation()
    print('Discovery Reset Everything contract: PASS')
