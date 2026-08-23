#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / "runtime_src"
sys.path.insert(0, str(RUNTIME_DIR))
import supervisor_runtime

MODULE_PATH = RUNTIME_DIR / "ha_entity_snapshot_sanitizer.py"
spec = importlib.util.spec_from_file_location("ha_entity_snapshot_sanitizer", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main() -> None:
    dockerfile = (ROOT / "runtime_src/Dockerfile").read_text(encoding="utf-8")
    assert "COPY sanitize_support_bundle.py /sanitize_support_bundle.py" in dockerfile
    assert "COPY ha_entity_snapshot_sanitizer.py /ha_entity_snapshot_sanitizer.py" in dockerfile

    support_script = (ROOT / "runtime_src/support_my_switch.sh").read_text(encoding="utf-8")
    assert 'SANITIZER_SCRIPT="${SUPPORT_SANITIZER_SCRIPT:-/ha_entity_snapshot_sanitizer.py}"' in support_script
    assert 'BASE_SANITIZER_SCRIPT="${SUPPORT_BASE_SANITIZER_SCRIPT:-/sanitize_support_bundle.py}"' in support_script
    assert 'python3 "$BASE_SANITIZER_SCRIPT" "$BUNDLE_ROOT"' in support_script
    assert str(module.BASE_SANITIZER) == "/sanitize_support_bundle.py"

    original_token_files = supervisor_runtime.TOKEN_FILES
    original_supervisor = os.environ.pop("SUPERVISOR_TOKEN", None)
    original_hassio = os.environ.pop("HASSIO_TOKEN", None)
    try:
        with tempfile.TemporaryDirectory() as token_tmp:
            token_file = Path(token_tmp) / "SUPERVISOR_TOKEN"
            token_file.write_text("s6-test-token\x00", encoding="utf-8")
            supervisor_runtime.TOKEN_FILES = (token_file,)
            assert supervisor_runtime.read_supervisor_token() == "s6-test-token"
            os.environ["SUPERVISOR_TOKEN"] = "env-test-token"
            assert supervisor_runtime.read_supervisor_token() == "env-test-token"
    finally:
        supervisor_runtime.TOKEN_FILES = original_token_files
        if original_supervisor is None:
            os.environ.pop("SUPERVISOR_TOKEN", None)
        else:
            os.environ["SUPERVISOR_TOKEN"] = original_supervisor
        if original_hassio is None:
            os.environ.pop("HASSIO_TOKEN", None)
        else:
            os.environ["HASSIO_TOKEN"] = original_hassio

    with tempfile.TemporaryDirectory() as tmp:
        generated = Path(tmp) / "generated-snmp2mqtt.yaml"
        generated.write_text(
            "targets:\n"
            "  - name: Switch Vision test Traffic\n"
            "    sensors:\n"
            "      - oid: 1.3.6.1.2.1.31.1.1.1.6.4\n"
            "        name: RackSW Port 4 RX Bytes\n"
            "      - oid: 1.3.6.1.2.1.31.1.1.1.10.4\n"
            "        name: RackSW Port 4 TX Bytes\n"
            "      - oid: 1.3.6.1.2.1.2.2.1.8.4\n"
            "        name: RackSW Port 4 Status\n"
            "      - oid: 1.3.6.1.2.1.31.1.1.1.15.4\n"
            "        name: RackSW Port 4 Speed Mbps\n"
            "      - oid: 1.3.6.1.2.1.31.1.1.1.18.4\n"
            "        name: RackSW Port 4 Alias\n",
            encoding="utf-8",
        )
        expected = module.expected_entity_ids(generated)
        assert expected == [
            "sensor.racksw_port_4_rx_bytes",
            "sensor.racksw_port_4_speed_mbps",
            "sensor.racksw_port_4_status",
            "sensor.racksw_port_4_tx_bytes",
        ], expected

        states = [
            {
                "entity_id": "sensor.racksw_port_4_rx_bytes",
                "state": "123456789",
                "last_updated": "2026-08-23T04:00:00+00:00",
                "attributes": {"friendly_name": "PRIVATE DESCRIPTION MUST NOT BE COPIED"},
            },
            {
                "entity_id": "sensor.racksw_port_4_tx_bytes_2",
                "state": "987654321",
                "last_updated": "2026-08-23T04:00:01+00:00",
                "attributes": {"friendly_name": "PRIVATE DESCRIPTION MUST NOT BE COPIED"},
            },
            {
                "entity_id": "sensor.racksw_port_4_status",
                "state": "1",
                "last_updated": "2026-08-23T04:00:02+00:00",
                "attributes": {"friendly_name": "PRIVATE DESCRIPTION MUST NOT BE COPIED"},
            },
            {
                "entity_id": "sensor.racksw_port_4_speed_mbps",
                "state": "not-a-number-private-text",
                "last_updated": "2026-08-23T04:00:03+00:00",
                "attributes": {"friendly_name": "PRIVATE DESCRIPTION MUST NOT BE COPIED"},
            },
            {"entity_id": "sensor.unrelated_private_entity", "state": "secret"},
        ]
        snapshot = module.build_snapshot(expected, states)
        assert snapshot["status"] == "ok"
        assert snapshot["summary"] == {
            "expected_count": 4,
            "exact_present_count": 3,
            "missing_exact_count": 1,
            "suffix_alternative_count": 1,
        }
        serialized = json.dumps(snapshot)
        assert "PRIVATE DESCRIPTION" not in serialized
        assert "unrelated_private_entity" not in serialized
        assert "not-a-number-private-text" not in serialized
        assert "<NON_NUMERIC>" in serialized

        by_id = {item["expected_entity_id"]: item for item in snapshot["entities"]}
        assert by_id["sensor.racksw_port_4_rx_bytes"]["state"] == "123456789"
        assert by_id["sensor.racksw_port_4_status"]["state"] == "1"
        assert by_id["sensor.racksw_port_4_tx_bytes"]["exact_present"] is False
        assert by_id["sensor.racksw_port_4_tx_bytes"]["suffix_alternatives"][0]["entity_id"] == "sensor.racksw_port_4_tx_bytes_2"

    print("HA entity resolution snapshot: PASS")


if __name__ == "__main__":
    main()
