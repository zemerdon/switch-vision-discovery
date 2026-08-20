#!/usr/bin/env python3
"""Validate and atomically publish Switch Vision generated SNMP2MQTT YAML."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import yaml

HEADER = "# Switch Vision generated SNMP2MQTT YAML"
SOURCE_HEADER = "# Source: Switch Vision Discovery"


def validate(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, f"candidate not found: {path}"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return False, f"candidate could not be read: {exc}"
    if not text.startswith(HEADER):
        return False, "Switch Vision generated YAML header missing"
    if SOURCE_HEADER not in text:
        return False, "Switch Vision Discovery source header missing"
    if "CHANGE_ME" in text:
        return False, "CHANGE_ME placeholder found"
    try:
        document: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return False, f"YAML parse failed: {exc}"
    if not isinstance(document, dict):
        return False, "generated YAML root is not a mapping"
    targets = document.get("targets")
    if not isinstance(targets, list) or not targets:
        return False, "generated YAML does not contain a non-empty targets list"
    for index, target in enumerate(targets, start=1):
        if not isinstance(target, dict):
            return False, f"target {index} is not a mapping"
        host = str(target.get("host") or target.get("target") or "").strip()
        if not host:
            return False, f"target {index} has no host"
        sensors = target.get("sensors")
        if sensors is not None and not isinstance(sensors, list):
            return False, f"target {index} sensors is not a list"
    return True, "valid"


def publish(candidate: Path, destination: Path) -> tuple[bool, str]:
    valid, reason = validate(candidate)
    if not valid:
        return False, reason
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(candidate, destination)
    except OSError as exc:
        return False, f"atomic replace failed: {exc}"
    return True, "published"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", metavar="PATH", type=Path)
    parser.add_argument("--publish", nargs=2, metavar=("CANDIDATE", "DESTINATION"), type=Path)
    args = parser.parse_args()
    if bool(args.validate) == bool(args.publish):
        parser.error("choose exactly one of --validate or --publish")
    if args.validate:
        ok, reason = validate(args.validate)
    else:
        candidate, destination = args.publish
        ok, reason = publish(candidate, destination)
    if ok:
        print(f"Switch Vision generated YAML guard: PASS ({reason})")
        return 0
    print(f"Switch Vision generated YAML guard: REFUSED ({reason})")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
