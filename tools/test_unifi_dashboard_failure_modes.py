#!/usr/bin/env python3
"""Regression coverage for UniFi dashboard-card input failures."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "runtime_src" / "unifi_dashboard_cards.py"


def run(snapshot: Path, registry: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(HELPER),
            "--snapshot",
            str(snapshot),
            "--registry",
            str(registry),
            "--indent",
            "6",
            "--summary",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sv-unifi-dashboard-") as tmp:
        root = Path(tmp)
        snapshot = root / "devices.json"
        registry = root / "supported_devices.json"

        write_json(
            registry,
            {
                "devices": [
                    {
                        "vendor": "Ubiquiti",
                        "model": "USW Test 8",
                        "status": "experimental",
                        "dashboard_support": True,
                        "calibration_profile": "stock_8rj45",
                        "default_faceplate": "faceplates/8rj45-0sfp.png",
                    }
                ]
            },
        )
        write_json(
            snapshot,
            {
                "schema_version": 1,
                "devices": [
                    {
                        "id": "test-switch-1",
                        "name": "Test Switch",
                        "model": "USW Test 8",
                        "ports": [
                            {"idx": i, "connector": "RJ45", "max_speed_mbps": 1000}
                            for i in range(1, 9)
                        ],
                        "api_capabilities": {
                            "port_detail": True,
                            "per_port_traffic": False,
                        },
                    }
                ],
            },
        )

        healthy = run(snapshot, registry)
        assert healthy.returncode == 0, healthy
        assert "type: custom:switch-vision-3650" in healthy.stdout
        assert "switch_model: USW Test 8" in healthy.stdout
        assert "UniFi cards emitted: 1; waiting for visuals/registry: 0; invalid devices: 0" in healthy.stdout

        snapshot.write_text("{not-json", encoding="utf-8")
        invalid_snapshot = run(snapshot, registry)
        assert invalid_snapshot.returncode != 0
        assert "# ERROR: UniFi dashboard card generation failed: UniFi2MQTT snapshot is not valid JSON." in invalid_snapshot.stdout
        assert "custom:switch-vision-3650" not in invalid_snapshot.stdout

        write_json(snapshot, {"schema_version": 1, "devices": []})
        registry.write_text("[not-an-object]", encoding="utf-8")
        invalid_registry = run(snapshot, registry)
        assert invalid_registry.returncode != 0
        assert "# ERROR: UniFi dashboard card generation failed: supported-device registry is not valid JSON." in invalid_registry.stdout

        write_json(registry, {"devices": []})
        empty = run(snapshot, registry)
        assert empty.returncode == 0, empty
        assert "# UniFi snapshot contains 0 normalized switching devices." in empty.stdout
        assert "UniFi cards emitted: 0; waiting for visuals/registry: 0; invalid devices: 0" in empty.stdout

        write_json(snapshot, {"schema_version": 1, "devices": {"bad": "shape"}})
        bad_shape = run(snapshot, registry)
        assert bad_shape.returncode != 0
        assert "snapshot field 'devices' must be a list" in bad_shape.stdout

        write_json(snapshot, {"schema_version": 1, "devices": [{"model": "USW Test 8", "ports": []}]})
        write_json(registry, {"devices": []})
        missing_id = run(snapshot, registry)
        assert missing_id.returncode == 0, missing_id
        assert "normalized device ID is missing" in missing_id.stdout
        assert "invalid devices: 1" in missing_id.stdout

    print("Switch Vision Discovery UniFi dashboard failure-mode regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
