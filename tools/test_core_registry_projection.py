#!/usr/bin/env python3
"""Contracts for Discovery-owned Core registry projection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

import project_core_registry as projection


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sv-core-registry-projection-") as tmp:
        root = Path(tmp)
        discovery_registry = root / "discovery.json"
        core_root = root / "core"
        catalog = core_root / "src/faceplates/catalog.json"
        catalog.parent.mkdir(parents=True, exist_ok=True)
        catalog.write_text(
            json.dumps(
                {
                    "schema": "switch-vision-faceplate-catalog-v1",
                    "faceplates": [
                        {"filename": "24rj45-2sfp.png", "display_name": "test"}
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        source = {
            "schema_version": 1,
            "generated_documents": {"markdown": "docs/SUPPORTED_DEVICES.md"},
            "support_statuses": {"experimental": "test"},
            "devices": [
                {
                    "vendor": "Test",
                    "family": "Family",
                    "model": "TEST-24",
                    "status": "experimental",
                    "confirmed_since": "1.0.0",
                    "last_validated_version": "1.0.0",
                    "ports": {"rj45": 24, "poe": False, "uplinks": 2},
                    "stack_support": False,
                    "discovery_support": True,
                    "dashboard_support": True,
                    "mapping_profile": "test-profile",
                    "calibration_profile": "stock_24rj45_2sfp",
                    "default_faceplate": "faceplates/24rj45-2sfp.png",
                    "optional_faceplates": [],
                    "evidence": "discovery-only provenance",
                    "tested_firmware": ["1.0.0"],
                    "contributor": {"display_name": "community contributor", "public_credit": False},
                    "contributions": [{"id": "discovery-only"}],
                    "notes": ["discovery-only note"],
                    "discovery_optional_interfaces": ["Loopback0"],
                    "validation": {},
                    "visuals": {
                        "recommended_faceplate": "faceplates/24rj45-2sfp.png",
                        "optional_faceplates": [],
                        "calibration_profile": "stock_24rj45_2sfp",
                    },
                    "discovery_only_future_field": {"must": "not leak"},
                }
            ],
        }
        discovery_registry.write_text(
            json.dumps(source, indent=2) + "\n",
            encoding="utf-8",
        )

        projected = projection.project_registry(discovery_registry)
        assert projected["projection"]["source_component"] == "discovery"
        assert projected["projection"]["source_registry_sha256"] == hashlib.sha256(
            discovery_registry.read_bytes()
        ).hexdigest()
        assert projected["projection"]["device_field_allowlist"] == list(
            projection.CORE_DEVICE_FIELDS
        )
        for field in (
            "evidence",
            "tested_firmware",
            "contributor",
            "contributions",
            "notes",
            "discovery_optional_interfaces",
            "discovery_only_future_field",
        ):
            assert field not in projected["devices"][0], field
        assert projected["devices"][0]["model"] == "TEST-24"

        projection.validate_core_faceplates(projected, core_root)

        projected["devices"][0]["default_faceplate"] = "faceplates/missing.png"
        try:
            projection.validate_core_faceplates(projected, core_root)
        except SystemExit as exc:
            assert "unknown Core faceplates" in str(exc)
        else:
            raise AssertionError("Unknown Core faceplate reference must fail closed")

    print("Discovery-owned Core registry projection contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
