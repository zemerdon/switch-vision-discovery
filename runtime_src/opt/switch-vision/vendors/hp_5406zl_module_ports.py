#!/usr/bin/env python3
"""Derive HP 5406zl populated module ports from numeric ENTITY-MIB evidence.

Only a physical ENTITY-MIB port, an entAliasMappingIdentifier -> ifIndex
binding, and an explicitly recognized installed module can create a connector.
IF-MIB slot placeholders on an empty bay are never sufficient evidence.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ENTITY_PARENT = "1.3.6.1.2.1.47.1.1.1.1.4."
ENTITY_CLASS = "1.3.6.1.2.1.47.1.1.1.1.5."
ENTITY_MODEL = "1.3.6.1.2.1.47.1.1.1.1.13."
ENTITY_ALIAS = "1.3.6.1.2.1.47.1.3.2.1.2."
IFNAME = "1.3.6.1.2.1.31.1.1.1.1."
IFINDEX_POINTER = "1.3.6.1.2.1.2.2.1.1."
WALK_ROW = re.compile(r"^\.?([0-9]+(?:\.[0-9]+)*)\s+=\s+(.+)$")
SLOT_PORT = re.compile(r"^([A-F])([1-9]|1[0-9]|2[0-4])$")


def unquote(raw: str) -> str:
    return raw.split(":", 1)[-1].strip().strip('"')


def integer(raw: str) -> int | None:
    match = re.search(r"(\d+)\)?\s*$", raw)
    return int(match.group(1)) if match else None


def classify(text: str) -> dict[int, str]:
    parent: dict[int, int] = {}
    entity_class: dict[int, int] = {}
    model: dict[int, str] = {}
    names: dict[int, str] = {}
    aliases: dict[int, int] = {}
    conflicting: set[int] = set()
    for line in text.splitlines():
        match = WALK_ROW.match(line)
        if not match:
            continue
        oid, raw = match.groups()
        if oid.startswith(ENTITY_PARENT):
            entity = integer(oid[len(ENTITY_PARENT):])
            number = integer(raw)
            if entity is not None and number is not None:
                parent[entity] = number
        elif oid.startswith(ENTITY_CLASS):
            entity = integer(oid[len(ENTITY_CLASS):])
            number = integer(raw)
            if entity is not None and number is not None:
                entity_class[entity] = number
        elif oid.startswith(ENTITY_MODEL):
            entity = integer(oid[len(ENTITY_MODEL):])
            if entity is not None:
                model[entity] = unquote(raw).upper()
        elif oid.startswith(IFNAME):
            index = integer(oid[len(IFNAME):])
            if index is not None:
                names[index] = unquote(raw)
        elif oid.startswith(ENTITY_ALIAS) and raw.upper().startswith(("OID:", "OBJECT IDENTIFIER:")):
            entity = integer(oid[len(ENTITY_ALIAS):].split(".", 1)[0])
            pointer = unquote(raw).lstrip(".")
            if entity is None or not pointer.startswith(IFINDEX_POINTER):
                continue
            index = integer(pointer[len(IFINDEX_POINTER):])
            if index is None:
                continue
            if entity in aliases and aliases[entity] != index:
                conflicting.add(entity)
            aliases[entity] = index

    result: dict[int, str] = {}
    for entity, index in aliases.items():
        if entity in conflicting or entity_class.get(entity) != 10:
            continue
        slot_port = SLOT_PORT.fullmatch(names.get(index, ""))
        if slot_port is None:
            continue
        module = parent.get(entity)
        part = ""
        # ENTITY-MIB may nest a physical port beneath an intermediate carrier.
        for _ in range(5):
            if not module or module == entity:
                break
            part = model.get(module, "")
            if "J8702A" in part or "J8707A" in part:
                break
            module = parent.get(module)
        slot, port = slot_port.group(1), int(slot_port.group(2))
        media = (
            "rj45" if "J8702A" in part and port <= 24 else
            "sfp_plus" if "J8707A" in part and port <= 4 else
            None
        )
        if media is not None and index not in result:
            result[index] = media
    return dict(sorted(result.items()))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: hp_5406zl_module_ports.py <numeric-walk>")
    walk = Path(sys.argv[1])
    mapping = classify(walk.read_text(encoding="utf-8", errors="replace"))
    for index, media in mapping.items():
        print(f"{index}\t{media}")


if __name__ == "__main__":
    main()
