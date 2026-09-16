#!/usr/bin/env python3
"""Project Switch Vision device order/state onto generated dashboard YAML.

The visible Native dashboard is a projection. A private full-card source keeps
cards that are temporarily disabled so re-enabling never depends on rebuilding a
card that was destructively removed from the visible YAML.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

from device_control import load as load_control, ordered_keys, state_for

CARD_START = re.compile(r"(?m)^      - type:\s*.+$")
_DISABLED_STATES = {"false", "disabled", "disable", "off", "no", "0"}


def full_dashboard_path(output: Path) -> Path:
    """Return the full-card source path for a visible generated dashboard."""
    override = os.environ.get("SWITCH_VISION_GENERATED_CARD_FULL_PATH", "").strip()
    if override:
        return Path(override)
    if output.suffix:
        return output.with_name(f"{output.stem}.full{output.suffix}")
    return output.with_name(output.name + ".full")


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


def _enabled_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in _DISABLED_STATES
    return True


def snmp_states_from_options(options: Any) -> dict[str, bool]:
    """Extract only SNMP Enabled/Disabled state from Discovery options."""
    if not isinstance(options, dict):
        return {}
    rows = options.get("switches")
    if not isinstance(rows, list):
        return {}
    result: dict[str, bool] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("switch_name") or "").strip()
        if not name:
            continue
        result[f"snmp:{name}"] = _enabled_value(row.get("enabled", "enabled"))
    return result


def snmp_states_from_options_file(path: Path | None) -> dict[str, bool]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Discovery options could not be read for dashboard projection.") from exc
    return snmp_states_from_options(payload)


def _parse_dashboard(text: str) -> tuple[str, list[Any], list[str]]:
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise RuntimeError("Generated dashboard YAML root is invalid.")
    views = document.get("views")
    if not isinstance(views, list) or not views or not isinstance(views[0], dict):
        raise RuntimeError("Generated dashboard YAML has no usable view.")
    cards = views[0].get("cards")
    if cards is None:
        cards = []
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
    return prefix, cards, blocks


def _write_if_changed(path: Path, text: str, *, mode: int | None = None) -> bool:
    current = path.read_text(encoding="utf-8") if path.is_file() else None
    if current == text:
        if mode is not None and path.is_file():
            os.chmod(path, mode)
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.projection.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        if mode is not None:
            os.chmod(temporary, mode)
        temporary.replace(path)
        if mode is not None:
            os.chmod(path, mode)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    return True


def _keyed_blocks(cards: list[Any], blocks: list[str]) -> tuple[list[str], dict[str, list[str]], list[str], list[str]]:
    pinned: list[str] = []
    keyed: dict[str, list[str]] = {}
    order: list[str] = []
    unknown: list[str] = []
    for index, (card, block) in enumerate(zip(cards, blocks, strict=True)):
        key = _card_key(card)
        if key is None:
            if index == 0 and isinstance(card, dict) and card.get("type") == "markdown":
                pinned.append(block)
            else:
                unknown.append(block)
            continue
        if key not in keyed:
            order.append(key)
        keyed.setdefault(key, []).append(block)
    return pinned, keyed, order, unknown


def refresh_full_dashboard_source(
    fresh_path: Path,
    full_path: Path,
    *,
    snmp_states: dict[str, bool] | None = None,
) -> dict[str, int | bool]:
    """Merge fresh generated cards with retained cards for currently disabled SNMP rows.

    Fresh generation remains authoritative for enabled SNMP devices and all
    UniFi devices. Only a currently configured *disabled* SNMP card may be
    retained from the previous full source when fresh generation intentionally
    omitted it.
    """
    fresh_text = fresh_path.read_text(encoding="utf-8")
    prefix, fresh_cards, fresh_blocks = _parse_dashboard(fresh_text)
    fresh_pinned, fresh_keyed, fresh_order, fresh_unknown = _keyed_blocks(
        fresh_cards, fresh_blocks
    )

    old_keyed: dict[str, list[str]] = {}
    if full_path.is_file():
        try:
            _old_prefix, old_cards, old_blocks = _parse_dashboard(
                full_path.read_text(encoding="utf-8")
            )
            _old_pinned, old_keyed, _old_order, _old_unknown = _keyed_blocks(
                old_cards, old_blocks
            )
        except (OSError, UnicodeDecodeError, RuntimeError, yaml.YAMLError):
            old_keyed = {}

    states = dict(snmp_states or {})
    retained: dict[str, list[str]] = {}
    for key, enabled in states.items():
        if enabled or key in fresh_keyed:
            continue
        rows = old_keyed.get(key)
        if rows:
            retained[key] = rows

    output: list[str] = [prefix]
    output.extend(fresh_pinned)
    emitted: set[str] = set()
    for key in fresh_order:
        output.extend(fresh_keyed[key])
        emitted.add(key)
    for key in states:
        if key in emitted or key not in retained:
            continue
        output.extend(retained[key])
        emitted.add(key)
    output.extend(fresh_unknown)
    merged = "".join(output)
    changed = _write_if_changed(full_path, merged, mode=0o600)
    return {
        "fresh_cards": len(fresh_cards),
        "retained_disabled_snmp_keys": len(retained),
        "full_source_changed": changed,
    }


def _device_enabled(key: str, control: dict[str, Any], snmp_states: dict[str, bool]) -> bool:
    if key.startswith("snmp:") and key in snmp_states:
        return snmp_states[key]
    return state_for(control, key, True)


def apply_dashboard_order(
    path: Path,
    control_path: Path,
    *,
    source_path: Path | None = None,
    snmp_states: dict[str, bool] | None = None,
) -> dict[str, int | bool]:
    """Project full cards into ``path`` using current state/order without data loss."""
    source = source_path or path
    text = source.read_text(encoding="utf-8")
    prefix, cards, blocks = _parse_dashboard(text)

    control = load_control(control_path)
    effective_snmp_states = dict(snmp_states or {})
    pinned: list[str] = []
    keyed: dict[str, list[str]] = {}
    unknown: list[str] = []
    disabled = 0

    for index, (card, block) in enumerate(zip(cards, blocks, strict=True)):
        key = _card_key(card)
        if key and not _device_enabled(key, control, effective_snmp_states):
            disabled += 1
            continue
        if key is None:
            if index == 0 and isinstance(card, dict) and card.get("type") == "markdown":
                pinned.append(block)
            else:
                unknown.append(block)
            continue
        keyed.setdefault(key, []).append(block)

    desired = ordered_keys(keyed.keys(), control)
    output: list[str] = [prefix]
    output.extend(pinned)
    emitted_keys: set[str] = set()
    for key in desired:
        rows = keyed.get(key, [])
        if not rows:
            continue
        emitted_keys.add(key)
        output.extend(rows)
    for key, rows in keyed.items():
        if key in emitted_keys:
            continue
        output.extend(rows)
    output.extend(unknown)

    updated = "".join(output)
    changed = _write_if_changed(path, updated)
    return {
        "cards": len(cards),
        "device_keys": len(keyed),
        "disabled_cards_removed": disabled,
        "visible_changed": changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dashboard", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--fresh", type=Path)
    parser.add_argument("--options", type=Path)
    args = parser.parse_args()
    states = snmp_states_from_options_file(args.options)
    source = args.source or full_dashboard_path(args.dashboard)
    refresh: dict[str, int | bool] = {}
    if args.fresh is not None:
        refresh = refresh_full_dashboard_source(
            args.fresh,
            source,
            snmp_states=states,
        )
    result = apply_dashboard_order(
        args.dashboard,
        args.control,
        source_path=source,
        snmp_states=states,
    )
    print(
        "Switch Vision dashboard projection applied: "
        f"{result['device_keys']} device key(s), "
        f"{result['disabled_cards_removed']} disabled card(s) hidden, "
        f"{refresh.get('retained_disabled_snmp_keys', 0)} disabled SNMP key(s) retained in full source."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
