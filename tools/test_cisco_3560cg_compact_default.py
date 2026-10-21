#!/usr/bin/env python3
"""Cisco 3560CG Compact default: identity, fallback, projection and confidence remain independent."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"
MODEL = "WS-C3560CG-8PC-S"
DEFAULT = "faceplates/c3560cg-8pc-s-compact.png"
ORIGINAL = "faceplates/c3560cg-8pc-s.png"
OLD_LABEL = "Cisco Catalyst 3560CG-8PC-S · 8 × RJ45 · 2 × SFP"


def main():
    rows = json.loads(REGISTRY.read_text(encoding="utf-8"))["devices"]
    device = next(r for r in rows if r.get("model") == MODEL)
    assert device["status"] == "experimental"
    assert device["mapping_profile"] == "cisco-3560cg-8pc-8p-2dual"
    assert device["calibration_profile"] == "cisco_3560cg_8pc_compact"
    assert device["ports"]["rj45"] == 8
    assert device["ports"]["uplinks"] == 2
    assert "dual-purpose" in device["ports"]["uplink_type"]
    assert device["default_faceplate"] == DEFAULT
    assert device["optional_faceplates"] == [ORIGINAL, "faceplates/24rj45-2sfp.png"]
    assert device["visuals"]["recommended_faceplate"] == DEFAULT
    assert device["visuals"]["optional_faceplates"] == device["optional_faceplates"]
    assert device["visuals"]["canvas"] == {"width": 2680, "height": 356}
    assert not any(other["default_faceplate"] == DEFAULT for other in rows if other["model"] != MODEL)
    core_dir = os.environ.get("SWITCH_VISION_CORE_SOURCE_ROOT")
    if core_dir:
        core = Path(core_dir)
        core_registry = json.loads((core / "src/devices/supported_devices.json").read_text(encoding="utf-8"))
        projected = next(r for r in core_registry["devices"] if r.get("model") == MODEL)
        for field in ("status", "ports", "mapping_profile", "calibration_profile", "default_faceplate", "optional_faceplates", "visuals"):
            assert projected[field] == device[field], field
        catalog = json.loads((core / "src/faceplates/catalog.json").read_text(encoding="utf-8"))
        labels = {row["filename"]: row["display_name"] for row in catalog["faceplates"]}
        assert labels["c3560cg-8pc-s.png"] == OLD_LABEL
        assert labels["c3560cg-8pc-s-compact.png"] == OLD_LABEL + " Compact"
        factory = json.loads((core / "src/calibration/faceplate-c3560cg-8pc-s-compact.json").read_text(encoding="utf-8"))
        assert factory["model"] == "cisco-3560cg-8pc-8p-2dual"
        assert set(factory["ports"]) == set(map(str, range(1, 11)))
        assert set(factory["sfp"]) == {"SFP1", "SFP2"}
    print("Discovery 3560CG Compact exact default / cross-Core mapping: PASS")


if __name__ == "__main__":
    main()
