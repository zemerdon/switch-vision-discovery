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
UPTIME_OID = "1.3.6.1.2.1.1.3.0"


def _sensor_oid(sensor: object) -> str:
    if not isinstance(sensor, dict):
        return ""
    return str(sensor.get("oid") or "").strip().lstrip(".")


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

    host_evidence: dict[str, dict[str, int]] = {}
    for index, target in enumerate(targets, start=1):
        if not isinstance(target, dict):
            return False, f"target {index} is not a mapping"
        host = str(target.get("host") or target.get("target") or "").strip()
        if not host:
            return False, f"target {index} has no host"
        sensors = target.get("sensors")
        if sensors is not None and not isinstance(sensors, list):
            return False, f"target {index} sensors is not a list"

        sensor_oids = {
            oid
            for oid in (_sensor_oid(sensor) for sensor in (sensors or []))
            if oid
        }
        evidence = host_evidence.setdefault(
            host,
            {"meaningful_sensor_groups": 0, "uptime_only_groups": 0},
        )
        if any(oid != UPTIME_OID for oid in sensor_oids):
            evidence["meaningful_sensor_groups"] += 1
        elif UPTIME_OID in sensor_oids:
            evidence["uptime_only_groups"] += 1

    # A failed/insufficient stored walk can still reach the historical-walk
    # generator with a mapped host. The legacy generator then emits only the
    # unconditional sysUpTime sensor, which is not enough evidence to publish
    # a usable Switch Vision target. Refuse that candidate atomically.
    for host, evidence in host_evidence.items():
        if evidence["meaningful_sensor_groups"] == 0:
            return (
                False,
                f"host {host} has no usable sensors beyond uptime; failed/insufficient walk suspected",
            )
        if evidence["uptime_only_groups"] > 1:
            return (
                False,
                f"host {host} has duplicate uptime-only groups; stale/duplicate walk source suspected",
            )

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
