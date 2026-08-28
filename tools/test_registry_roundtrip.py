#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime_src"))

import registry_lookup  # noqa: E402

REGISTRY = ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"


def main() -> int:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    devices = [d for d in data.get("devices", []) if isinstance(d, dict)]
    failures: list[str] = []

    for device in devices:
        model = str(device.get("model") or "").strip()
        if not model:
            failures.append("registry entry without model")
            continue
        resolved = registry_lookup.lookup(data, model)
        if resolved is None:
            failures.append(f"{model}: exact model does not round-trip through registry_lookup")
            continue
        if str(resolved.get("model") or "") != model:
            failures.append(f"{model}: resolved as {resolved.get('model')!r}")

        # The informational lookup is deliberately tolerant of whitespace/case.
        spaced = "  " + "   ".join(model.split()) + "  "
        if registry_lookup.lookup(data, spaced.swapcase()) is None:
            failures.append(f"{model}: case/whitespace normalized lookup failed")

    # Explicit prefix/suffix contracts used by vendor sysDescr normalization.
    variants = {
        "WS-C3650-48PD-E": [
            "Unknown Cisco WS-C3650-48PD-E",
            "WS-C3650-48PD-E, Cisco IOS Software",
        ],
        "EX3300-48P": [
            "Juniper Networks EX3300-48P",
            "EX3300-48P Junos 15.1R7.9",
        ],
        "USW Pro XG 8 PoE": [
            "Ubiquiti UniFi USW Pro XG 8 PoE",
        ],
        "CRS328-24P-4S+RM": [
            "CRS328-24P-4S+",
        ],
    }
    for expected, candidates in variants.items():
        for candidate in candidates:
            resolved = registry_lookup.lookup(data, candidate)
            if resolved is None or str(resolved.get("model") or "") != expected:
                failures.append(f"{candidate!r}: expected registry model {expected!r}")

    if failures:
        for item in failures:
            print(f"FAIL: {item}")
        print(f"Registry round-trip audit: FAIL ({len(failures)} issue(s))")
        return 1

    print(f"PASS: all {len(devices)} registry models round-trip through registry_lookup")
    print("PASS: normalized vendor/sysDescr lookup variants resolve to exact registry entries")
    print("Switch Vision registry lookup round-trip audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
