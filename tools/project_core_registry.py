#!/usr/bin/env python3
"""Project Discovery's authoritative model registry into Core.

Discovery owns exact-model support/topology/capability state. Core receives only
an explicit generated projection plus provenance, and remains authoritative for
faceplate metadata/geometry names.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DISCOVERY_REGISTRY = (
    ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"
)

CORE_DEVICE_FIELDS = (
    "vendor",
    "family",
    "model",
    "status",
    "confirmed_since",
    "last_validated_version",
    "ports",
    "stack_support",
    "discovery_support",
    "dashboard_support",
    "mapping_profile",
    "calibration_profile",
    "default_faceplate",
    "optional_faceplates",
    "validation",
    "visuals",
    "unifi_api_port_map",
    "port_roles",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Registry root must be a JSON object: {path}")
    devices = payload.get("devices")
    if not isinstance(devices, list):
        raise SystemExit(f"Registry devices must be a list: {path}")
    return payload


def project_registry(source_path: Path) -> dict[str, Any]:
    source = load_json(source_path)
    projected_devices: list[dict[str, Any]] = []
    seen_models: set[str] = set()

    for index, raw in enumerate(source["devices"], start=1):
        if not isinstance(raw, dict):
            raise SystemExit(f"Discovery registry device {index} is not an object")
        model = str(raw.get("model") or "").strip()
        if not model:
            raise SystemExit(f"Discovery registry device {index} has no exact model")
        if model in seen_models:
            raise SystemExit(f"Duplicate exact model in Discovery registry: {model}")
        seen_models.add(model)

        projected: dict[str, Any] = {}
        for field in CORE_DEVICE_FIELDS:
            if field in raw:
                projected[field] = copy.deepcopy(raw[field])
        projected_devices.append(projected)

    return {
        "schema_version": source.get("schema_version", 1),
        "generated_documents": copy.deepcopy(source.get("generated_documents", {})),
        "support_statuses": copy.deepcopy(source.get("support_statuses", {})),
        "projection": {
            "schema": 1,
            "source_component": "discovery",
            "source_registry_sha256": sha256_file(source_path),
            "device_field_allowlist": list(CORE_DEVICE_FIELDS),
        },
        "devices": projected_devices,
    }


def validate_core_faceplates(projected: dict[str, Any], core_root: Path) -> None:
    catalog_path = core_root / "src/faceplates/catalog.json"
    catalog = load_json_object(catalog_path)
    rows = catalog.get("faceplates")
    if not isinstance(rows, list):
        raise SystemExit("Core faceplate catalog has no faceplates list")
    known = {
        str(row.get("filename") or "").strip()
        for row in rows
        if isinstance(row, dict) and str(row.get("filename") or "").strip()
    }

    missing: list[str] = []
    for device in projected["devices"]:
        model = str(device.get("model") or "")
        refs: list[tuple[str, str]] = []
        default = str(device.get("default_faceplate") or "").strip()
        if default:
            refs.append(("default_faceplate", default))
        for value in device.get("optional_faceplates") or []:
            refs.append(("optional_faceplates", str(value)))
        visuals = device.get("visuals")
        if isinstance(visuals, dict):
            recommended = str(visuals.get("recommended_faceplate") or "").strip()
            if recommended:
                refs.append(("visuals.recommended_faceplate", recommended))
            for value in visuals.get("optional_faceplates") or []:
                refs.append(("visuals.optional_faceplates", str(value)))
        for label, ref in refs:
            filename = ref.removeprefix("faceplates/")
            if filename not in known:
                missing.append(f"{model}: {label} -> {ref}")
    if missing:
        raise SystemExit(
            "Discovery registry references unknown Core faceplates: "
            + "; ".join(missing[:20])
        )


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object: {path}")
    return payload


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--discovery-registry",
        type=Path,
        default=DEFAULT_DISCOVERY_REGISTRY,
    )
    parser.add_argument("--core-source-root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()

    source = args.discovery_registry.resolve()
    core_root = args.core_source_root.resolve()
    target = core_root / "src/devices/supported_devices.json"

    projected = project_registry(source)
    validate_core_faceplates(projected, core_root)
    expected = canonical_json(projected)

    if args.check:
        if not target.is_file():
            raise SystemExit(f"Core registry projection is missing: {target}")
        actual = target.read_text(encoding="utf-8")
        if actual != expected:
            raise SystemExit(
                "Core registry projection differs from authoritative Discovery registry. "
                "Run project_core_registry.py --write for the reviewed coordinated update."
            )
        print(
            "Discovery -> Core registry projection: PASS "
            f"({len(projected['devices'])} models; "
            f"source_sha256={projected['projection']['source_registry_sha256']})"
        )
        return 0

    target.write_text(expected, encoding="utf-8", newline="\n")
    print(
        "Wrote Core registry projection "
        f"({len(projected['devices'])} models) to {target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
