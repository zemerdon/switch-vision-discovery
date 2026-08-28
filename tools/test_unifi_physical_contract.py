#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "runtime_src" / "unifi_dashboard_cards.py"
spec = importlib.util.spec_from_file_location("unifi_dashboard_cards", MODULE)
assert spec and spec.loader
cards = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cards
spec.loader.exec_module(cards)


def registry_device(
    model: str,
    rj45: int,
    uplinks: int,
    *,
    profile: str,
    faceplate: str,
    api_map: dict | None = None,
) -> dict:
    device = {
        "vendor": "Ubiquiti",
        "model": model,
        "status": "experimental",
        "ports": {
            "rj45": rj45,
            "uplinks": uplinks,
            "gigabit_sfp": 0,
            "ten_gigabit_sfp_plus": uplinks,
        },
        "dashboard_support": True,
        "calibration_profile": profile,
        "default_faceplate": faceplate,
    }
    if api_map is not None:
        device["unifi_api_port_map"] = api_map
    return device


def port(idx: int, connector: str) -> dict:
    return {"idx": idx, "connector": connector, "state": "UP"}


def render(device: dict, registry_entry: dict):
    return cards.render({"devices": [device]}, {"devices": [registry_entry]}, 0)


# Mark/HD24 regression: an exact 24+4 registry device must never become a
# 48-port dashboard merely because the normalized snapshot exposes extra rows.
hd24_registry = registry_device(
    "USW Pro HD 24 PoE",
    24,
    4,
    profile="stock_24rj45_4sfp",
    faceplate="faceplates/24rj45-4sfp.png",
)
hd24_bad = {
    "id": "hd24",
    "model": "USW Pro HD 24 PoE",
    "name": "HD24",
    "ports": [*(port(i, "RJ45") for i in range(1, 49)), *(port(i, "SFPPLUS") for i in range(49, 53))],
}
text, emitted, exact, generic, pending, issues = render(hd24_bad, hd24_registry)
assert emitted == 0, text
assert "TOPOLOGY_CONFLICT" in text, text
assert "24 RJ45 + 4 SFP" in text and "48 RJ45 + 4 SFP" in text, text
assert pending == 1 and issues == 1

# Matching exact evidence stays exact and retains the registry contract.
hd24_good = {
    "id": "hd24",
    "model": "USW Pro HD 24 PoE",
    "name": "HD24",
    "ports": [*(port(i, "RJ45") for i in range(1, 25)), *(port(i, "SFPPLUS") for i in range(25, 29))],
}
text, emitted, exact, generic, pending, issues = render(hd24_good, hd24_registry)
assert emitted == 1 and exact == 1 and generic == 0 and pending == 0 and issues == 0, text
assert "port_count: 24" in text, text
assert "sfp_port_count: 4" in text, text
assert "faceplate_file: 24rj45-4sfp.png" in text, text

# A proven API map is stronger than arbitrary extra rows. Only mapped physical
# indices define the exact device contract; unrelated controller rows cannot
# enlarge the card.
map_registry = registry_device(
    "Mapped Test 8",
    8,
    2,
    profile="test_8rj45_2sfp",
    faceplate="faceplates/8rj45-2sfp.png",
    api_map={"rj45": list(range(1, 9)), "sfp": [21, 22]},
)
map_snapshot = {
    "id": "mapped8",
    "model": "Mapped Test 8",
    "ports": [*(port(i, "RJ45") for i in range(1, 21)), port(21, "SFPPLUS"), port(22, "SFPPLUS")],
}
text, emitted, exact, generic, pending, issues = render(map_snapshot, map_registry)
assert emitted == 1 and issues == 0, text
assert "port_count: 8" in text and "sfp_port_count: 2" in text, text
assert "unifi_api_port_map:" in text, text

# A stale/broken explicit API map fails closed instead of silently falling back
# to snapshot row counts.
broken_map_registry = registry_device(
    "Broken Map 8",
    8,
    2,
    profile="test_8rj45_2sfp",
    faceplate="faceplates/8rj45-2sfp.png",
    api_map={"rj45": list(range(1, 9)), "sfp": [21, 99]},
)
text, emitted, *_rest = render(map_snapshot | {"model": "Broken Map 8"}, broken_map_registry)
assert emitted == 0, text
assert "TOPOLOGY_CONFLICT" in text and "API port map" in text, text

# Backward-compatibility guard: an exact small device may explicitly use an
# oversized temporary generic visual, but its physical card counts remain 8+0.
legacy_small_registry = registry_device(
    "Legacy Small 8",
    8,
    0,
    profile="stock_24rj45_2sfp",
    faceplate="faceplates/24rj45-2sfp.png",
)
legacy_small = {
    "id": "small8",
    "model": "Legacy Small 8",
    "ports": [port(i, "RJ45") for i in range(1, 9)],
}
text, emitted, exact, generic, pending, issues = render(legacy_small, legacy_small_registry)
assert emitted == 1 and generic == 1 and issues == 0, text
assert "port_count: 8" in text and "sfp_port_count: 0" in text, text
assert "faceplate_file: unifi-24p-rj45-2sfp.png" in text, text

print("Switch Vision UniFi physical-contract regressions: PASS")
