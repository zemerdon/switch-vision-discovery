#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "runtime_src" / "opt" / "switch-vision" / "devices" / "supported_devices.json"
CONFIG = ROOT / "switch_vision_discovery" / "config.yaml"
CHANGELOG = ROOT / "switch_vision_discovery" / "CHANGELOG.md"
VERSION = "2.4.19"

# Exact visual ownership shared with Switch Vision Core 2.7.9.
# Physical port counts remain authoritative and are asserted separately.
MATRIX = {
    "USW Flex": {
        "ports": (5, 0),
        "faceplate": "faceplates/unifi-5rj45.png",
        "profile": "default_unifi_5_rj45",
    },
    "USW Flex Mini": {
        "ports": (5, 0),
        "faceplate": "faceplates/unifi-5rj45.png",
        "profile": "default_unifi_5_rj45",
    },
    "USW-Lite-8-PoE": {
        "ports": (8, 0),
        "faceplate": "faceplates/unifi-8rj45.png",
        "profile": "default_unifi_8_rj45",
    },
    "USW-Enterprise-8-PoE": {
        "ports": (8, 2),
        "faceplate": "faceplates/unifi-8-rj45-2sfp.png",
        "profile": "unifi_8_rj45_2sfp",
    },
    "USW Pro XG 8 PoE": {
        "ports": (8, 2),
        "faceplate": "faceplates/unifi-8-rj45-2sfp.png",
        "profile": "unifi_8_rj45_2sfp",
    },
    "USW Pro HD 24 PoE": {
        "ports": (24, 4),
        "faceplate": "faceplates/unifi-24-rj45-4sfp-inline.png",
        "profile": "unifi_24_rj45_4sfp_inline",
    },
    "USW Pro Aggregation": {
        "ports": (0, 32),
        "faceplate": "faceplates/unifi-32sfp.png",
        "profile": "unifi_32sfp",
    },
    "US 16 PoE 150W": {
        "ports": (16, 2),
        "faceplate": "faceplates/24rj45-2sfp.png",
        "profile": "stock_24rj45_2sfp",
    },
}

CHANGELOG_SECTION = """## 2.4.19 — Exact-model faceplate matrix alignment\n\n- Align Discovery visual recommendations with Switch Vision Core 2.7.9 for reviewed UniFi exact models.\n- Use the dedicated 5-RJ45, 8-RJ45, 8+2, 24+4 and 32-optical profiles where those exact layouts are already owned by Core.\n- Keep `US 16 PoE 150W` on the safe 24+2 stock canvas while preserving its true 16+2 physical topology.\n- Preserve physical port counts, support-confidence states and API mapping profiles; this is a presentation-contract correction only.\n- Add an exact-model regression so Discovery cannot silently drift from the approved faceplate/profile matrix again.\n\n"""


def write_lf(path: Path, text: str) -> None:
    path.write_text(text.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8", newline="\n")


def main() -> None:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    rows = payload.get("devices")
    if not isinstance(rows, list):
        raise SystemExit("supported_devices.json has no devices list")

    by_model: dict[str, list[dict]] = {}
    for row in rows:
        if isinstance(row, dict):
            by_model.setdefault(str(row.get("model") or ""), []).append(row)

    changed = 0
    for model, spec in MATRIX.items():
        matches = by_model.get(model, [])
        if len(matches) != 1:
            raise SystemExit(f"expected exactly one registry entry for {model!r}, found {len(matches)}")
        row = matches[0]
        ports = row.get("ports") if isinstance(row.get("ports"), dict) else {}
        actual = (int(ports.get("rj45") or 0), int(ports.get("uplinks") or 0))
        if actual != spec["ports"]:
            raise SystemExit(f"physical topology changed for {model}: expected {spec['ports']}, got {actual}")

        before = json.dumps(row, sort_keys=True)
        row["dashboard_support"] = True
        row["default_faceplate"] = spec["faceplate"]
        row["calibration_profile"] = spec["profile"]
        visuals = row.get("visuals") if isinstance(row.get("visuals"), dict) else {}
        visuals["recommended_faceplate"] = spec["faceplate"]
        visuals["calibration_profile"] = spec["profile"]
        row["visuals"] = visuals
        after = json.dumps(row, sort_keys=True)
        if after != before:
            changed += 1

    write_lf(REGISTRY, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    config = CONFIG.read_text(encoding="utf-8")
    updated, count = re.subn(r'(?m)^version:\s*"[0-9.]+"\s*$', f'version: "{VERSION}"', config, count=1)
    if count != 1:
        raise SystemExit("could not update Discovery version in config.yaml")
    write_lf(CONFIG, updated)

    changelog = CHANGELOG.read_text(encoding="utf-8")
    if not changelog.startswith("## 2.4.19 —"):
        write_lf(CHANGELOG, CHANGELOG_SECTION + changelog)

    print(f"Discovery {VERSION} faceplate matrix applied; {changed} registry rows changed")


if __name__ == "__main__":
    main()
