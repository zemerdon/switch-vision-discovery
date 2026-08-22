#!/usr/bin/env python3
"""Regression coverage for UniFi dashboard-card failures and generic fallbacks."""
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


def ports(rj45: int, sfp: int = 0) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx in range(1, rj45 + 1):
        rows.append({"idx": idx, "connector": "RJ45", "max_speed_mbps": 1000})
    for idx in range(rj45 + 1, rj45 + sfp + 1):
        rows.append({"idx": idx, "connector": "SFPPLUS", "max_speed_mbps": 10000})
    return rows


def device(device_id: str, model: str, rj45: int, sfp: int = 0) -> dict[str, object]:
    return {
        "id": device_id,
        "name": model,
        "model": model,
        "ports": ports(rj45, sfp),
        "api_capabilities": {"port_detail": True, "per_port_traffic": False},
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sv-unifi-dashboard-") as tmp:
        root = Path(tmp)
        snapshot = root / "devices.json"
        registry = root / "supported_devices.json"

        # Existing exact-model behavior remains unchanged.
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
            {"schema_version": 1, "devices": [device("test-switch-1", "USW Test 8", 8)]},
        )
        healthy = run(snapshot, registry)
        assert healthy.returncode == 0, healthy
        assert "type: custom:switch-vision-3650" in healthy.stdout
        assert "switch_model: USW Test 8" in healthy.stdout
        assert "generic_faceplate: false" in healthy.stdout
        assert (
            "UniFi cards emitted: 1; exact cards: 1; generic fallbacks: 0; "
            "exact support pending: 0; issues: 0"
        ) in healthy.stdout

        # Brendan regression: positively classified but unregistered UniFi
        # switching devices must still receive working generic dashboard cards,
        # and layouts up to 24 RJ45 + 2 optical must prefer our UniFi generic.
        write_json(registry, {"devices": []})
        write_json(
            snapshot,
            {
                "schema_version": 1,
                "devices": [
                    device("brendan-ucg", "UCG Ultra", 5),
                    device("brendan-us16", "US 16 PoE 150W", 16, 2),
                    device("brendan-promax24", "USW Pro Max 24", 24, 2),
                    device("brendan-ultra", "USW Ultra", 8),
                ],
            },
        )
        brendan = run(snapshot, registry)
        assert brendan.returncode == 0, brendan
        assert brendan.stdout.count("type: custom:switch-vision-3650") == 4
        for model in ("UCG Ultra", "US 16 PoE 150W", "USW Pro Max 24", "USW Ultra"):
            assert f"switch_model: {model}" in brendan.stdout
        assert brendan.stdout.count("calibration_profile: unifi_24p_rj45_2sfp") == 4
        assert brendan.stdout.count("faceplate_file: unifi-24p-rj45-2sfp.png") == 4
        assert brendan.stdout.count("generic_faceplate: true") == 4
        assert (
            "UniFi cards emitted: 4; exact cards: 0; generic fallbacks: 4; "
            "exact support pending: 4; issues: 0"
        ) in brendan.stdout

        # Registered devices waiting for exact visuals also get a generic card.
        # A 48-port topology still uses the neutral stock 48+2 because we do not
        # yet ship a UniFi-specific 48-port generic faceplate.
        write_json(
            registry,
            {
                "devices": [
                    {
                        "vendor": "Ubiquiti",
                        "model": "USW Pending 48",
                        "status": "experimental",
                        "dashboard_support": False,
                    }
                ]
            },
        )
        write_json(
            snapshot,
            {"schema_version": 1, "devices": [device("pending-48", "USW Pending 48", 48, 2)]},
        )
        pending = run(snapshot, registry)
        assert pending.returncode == 0, pending
        assert "calibration_profile: stock_48rj45_2sfp" in pending.stdout
        assert "faceplate_file: 48rj45-2sfp.png" in pending.stdout
        assert "generic_faceplate: true" in pending.stdout

        # Input failures remain loud and YAML-safe.
        snapshot.write_text("{not-json", encoding="utf-8")
        invalid_snapshot = run(snapshot, registry)
        assert invalid_snapshot.returncode != 0
        assert (
            "# ERROR: UniFi dashboard card generation failed: "
            "UniFi2MQTT snapshot is not valid JSON."
        ) in invalid_snapshot.stdout
        assert "custom:switch-vision-3650" not in invalid_snapshot.stdout

        write_json(snapshot, {"schema_version": 1, "devices": []})
        registry.write_text("[not-an-object]", encoding="utf-8")
        invalid_registry = run(snapshot, registry)
        assert invalid_registry.returncode != 0
        assert (
            "# ERROR: UniFi dashboard card generation failed: "
            "supported-device registry is not valid JSON."
        ) in invalid_registry.stdout

        write_json(registry, {"devices": []})
        empty = run(snapshot, registry)
        assert empty.returncode == 0, empty
        assert "# UniFi snapshot contains 0 normalized switching devices." in empty.stdout
        assert (
            "UniFi cards emitted: 0; exact cards: 0; generic fallbacks: 0; "
            "exact support pending: 0; issues: 0"
        ) in empty.stdout

        write_json(snapshot, {"schema_version": 1, "devices": {"bad": "shape"}})
        bad_shape = run(snapshot, registry)
        assert bad_shape.returncode != 0
        assert "snapshot field 'devices' must be a list" in bad_shape.stdout

        write_json(snapshot, {"schema_version": 1, "devices": [{"model": "USW Test 8", "ports": []}]})
        missing_id = run(snapshot, registry)
        assert missing_id.returncode == 0, missing_id
        assert "normalized device ID is missing" in missing_id.stdout
        assert "issues: 1" in missing_id.stdout

    print("Switch Vision Discovery UniFi dashboard fallback regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())