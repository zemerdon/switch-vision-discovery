#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "runtime_src/ha_entity_snapshot_sanitizer.py"
spec = importlib.util.spec_from_file_location("ha_entity_snapshot_sanitizer", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main() -> None:
    dockerfile = (ROOT / "runtime_src/Dockerfile").read_text(encoding="utf-8")
    assert "COPY sanitize_support_bundle.py /sanitize_support_bundle_base.py" in dockerfile
    assert "COPY ha_entity_snapshot_sanitizer.py /sanitize_support_bundle.py" in dockerfile

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
