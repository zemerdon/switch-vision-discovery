#!/usr/bin/env python3
"""Apply Switch Vision unified device order/state to generated dashboard YAML.

This intentionally preserves the generated text blocks instead of re-dumping the
entire YAML document, so comments and human-readable diagnostics remain intact.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml

from device_control import load as load_control, ordered_keys, state_for

CARD_START = re.compile(r"(?m)^      - type:\s*.+$")


def _card_key(card: Any) -> str | None:
    if not isinstance(card, dict):
        return None
    selected = str(card.get("discovery_selected_switch") or "").strip()
    if selected:
        return f"snmp:{selected}"
    unifi_id = str(card.get("unifi_device_id") or "").strip()
    if unifi_id:
        return f"unifi:{unifi_id}"
    return None


def apply_dashboard_order(path: Path, control_path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise RuntimeError("Generated dashboard YAML root is invalid.")
    views = document.get("views")
    if not isinstance(views, list) or not views or not isinstance(views[0], dict):
        raise RuntimeError("Generated dashboard YAML has no usable view.")
    cards = views[0].get("cards")
    if not isinstance(cards, list):
        raise RuntimeError("Generated dashboard YAML has no card list.")

    starts = [match.start() for match in CARD_START.finditer(text)]
    if len(starts) != len(cards):
        raise RuntimeError("Generated dashboard text/card count mismatch.")
    prefix = text[: starts[0]] if starts else text
    blocks = [
        text[start : (starts[index + 1] if index + 1 < len(starts) else len(text))]
        for index, start in enumerate(starts)
    ]

    control = load_control(control_path)
    pinned: list[tuple[int, str]] = []
    keyed: dict[str, list[tuple[int, str]]] = {}
    unknown: list[tuple[int, str]] = []
    disabled = 0

    for index, (card, block) in enumerate(zip(cards, blocks, strict=True)):
        key = _card_key(card)
        if key and not state_for(control, key, True):
            disabled += 1
            continue
        if key is None:
            if index == 0 and isinstance(card, dict) and card.get("type") == "markdown":
                pinned.append((index, block))
            else:
                unknown.append((index, block))
            continue
        keyed.setdefault(key, []).append((index, block))

    desired = ordered_keys(keyed.keys(), control)
    output: list[str] = [prefix]
    output.extend(block for _index, block in pinned)
    emitted_keys: set[str] = set()
    for key in desired:
        rows = keyed.get(key, [])
        if not rows:
            continue
        emitted_keys.add(key)
        output.extend(block for _index, block in rows)
    for key, rows in keyed.items():
        if key in emitted_keys:
            continue
        output.extend(block for _index, block in rows)
    output.extend(block for _index, block in unknown)

    updated = "".join(output)
    if updated != text:
        temporary = path.with_suffix(path.suffix + ".device-order.tmp")
        temporary.write_text(updated, encoding="utf-8")
        temporary.replace(path)

    return {
        "cards": len(cards),
        "device_keys": len(keyed),
        "disabled_cards_removed": disabled,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dashboard", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    args = parser.parse_args()
    result = apply_dashboard_order(args.dashboard, args.control)
    print(
        "Switch Vision device order applied: "
        f"{result['device_keys']} device key(s), "
        f"{result['disabled_cards_removed']} disabled card(s) removed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
