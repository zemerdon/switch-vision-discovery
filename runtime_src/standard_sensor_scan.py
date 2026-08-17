#!/usr/bin/env python3
"""Extract vendor-neutral standard-MIB sensor candidates from an SNMP walk.

The output is observational and is intended to help users of unknown/non-Cisco
switches quickly identify useful values without changing the proven generator.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

LINE_RE = re.compile(r"^\s*(?:iso\.|\.)?(?P<oid>[0-9.]+)\s*=\s*(?P<type>[^:]+):?\s*(?P<value>.*)$")

ENTITY_BASE = "1.3.6.1.2.1.47.1.1.1.1."
SENSOR_BASE = "1.3.6.1.2.1.99.1.1.1."
POE_BASE = "1.3.6.1.2.1.105.1.3.1.1."
CPU_BASE = "1.3.6.1.2.1.25.3.3.1.2."

SENSOR_TYPES = {
    1: "other", 2: "unknown", 3: "volts_ac", 4: "volts_dc", 5: "amperes",
    6: "watts", 7: "hertz", 8: "celsius", 9: "percent_relative_humidity",
    10: "rpm", 11: "cubic_metres_per_minute", 12: "truth_value",
}
SCALES = {
    1: -24, 2: -21, 3: -18, 4: -15, 5: -12, 6: -9, 7: -6,
    8: -3, 9: 0, 10: 3, 11: 6, 12: 9, 13: 12, 14: 15,
    15: 18, 16: 21, 17: 24,
}
STATUS = {1: "ok", 2: "unavailable", 3: "nonoperational"}


def clean_value(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    return value


def as_int(value: str) -> int | None:
    match = re.search(r"-?\d+", value)
    return int(match.group(0)) if match else None


def parse_walk(path: Path) -> dict[str, tuple[str, str]]:
    rows: dict[str, tuple[str, str]] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = LINE_RE.match(raw)
        if not match:
            continue
        rows[match.group("oid").lstrip(".")] = (
            match.group("type").strip(), clean_value(match.group("value"))
        )
    return rows


def indexed(rows: dict[str, tuple[str, str]], prefix: str) -> dict[str, tuple[str, str]]:
    return {oid[len(prefix):]: value for oid, value in rows.items() if oid.startswith(prefix)}


def entity_labels(rows: dict[str, tuple[str, str]]) -> dict[str, str]:
    # entPhysicalDescr(2), entPhysicalName(7), entPhysicalModelName(13)
    labels: dict[str, str] = {}
    for column in ("7.", "2.", "13."):
        for idx, (_, value) in indexed(rows, ENTITY_BASE + column).items():
            if value and idx not in labels:
                labels[idx] = value
    return labels


def scan_entity_sensors(rows: dict[str, tuple[str, str]]) -> list[dict[str, Any]]:
    labels = entity_labels(rows)
    types = indexed(rows, SENSOR_BASE + "1.")
    scales = indexed(rows, SENSOR_BASE + "2.")
    precision = indexed(rows, SENSOR_BASE + "3.")
    values = indexed(rows, SENSOR_BASE + "4.")
    statuses = indexed(rows, SENSOR_BASE + "5.")
    results: list[dict[str, Any]] = []

    for idx in sorted(values, key=lambda x: [int(p) if p.isdigit() else p for p in x.split(".")]):
        raw = values[idx][1]
        raw_num = as_int(raw)
        type_num = as_int(types.get(idx, ("", ""))[1])
        scale_num = as_int(scales.get(idx, ("", ""))[1])
        precision_num = as_int(precision.get(idx, ("", ""))[1]) or 0
        status_num = as_int(statuses.get(idx, ("", ""))[1])
        exponent = SCALES.get(scale_num or 9, 0) - precision_num
        scaled = (raw_num * (10 ** exponent)) if raw_num is not None else None
        kind = SENSOR_TYPES.get(type_num or 2, "unknown")
        results.append({
            "category": "environment",
            "standard": "ENTITY-SENSOR-MIB",
            "index": idx,
            "label": labels.get(idx, f"Physical sensor {idx}"),
            "sensor_type": kind,
            "value_oid": SENSOR_BASE + "4." + idx,
            "status_oid": SENSOR_BASE + "5." + idx if idx in statuses else None,
            "raw_value": raw,
            "scaled_value": scaled,
            "oper_status": STATUS.get(status_num, str(status_num) if status_num is not None else "unknown"),
            "confidence": "high" if kind not in {"unknown", "other"} else "medium",
        })
    return results


def scan_poe(rows: dict[str, tuple[str, str]]) -> list[dict[str, Any]]:
    # pethMainPsePower(2) = available/budget W, pethMainPseConsumptionPower(4) = used W
    budget = indexed(rows, POE_BASE + "2.")
    used = indexed(rows, POE_BASE + "4.")
    indices = sorted(set(budget) | set(used), key=lambda x: [int(p) if p.isdigit() else p for p in x.split(".")])
    results: list[dict[str, Any]] = []
    for idx in indices:
        if idx in used:
            results.append({
                "category": "poe", "standard": "POWER-ETHERNET-MIB", "index": idx,
                "label": f"PoE group {idx} used power", "sensor_type": "watts",
                "value_oid": POE_BASE + "4." + idx, "raw_value": used[idx][1], "confidence": "high",
            })
        if idx in budget:
            results.append({
                "category": "poe", "standard": "POWER-ETHERNET-MIB", "index": idx,
                "label": f"PoE group {idx} available power", "sensor_type": "watts",
                "value_oid": POE_BASE + "2." + idx, "raw_value": budget[idx][1], "confidence": "high",
            })
    return results


def scan_cpu(rows: dict[str, tuple[str, str]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for idx, (_, value) in sorted(indexed(rows, CPU_BASE).items()):
        results.append({
            "category": "cpu", "standard": "HOST-RESOURCES-MIB", "index": idx,
            "label": f"Processor {idx} load", "sensor_type": "percent",
            "value_oid": CPU_BASE + idx, "raw_value": value, "confidence": "medium",
        })
    return results


def build_payload(path: Path) -> dict[str, Any]:
    rows = parse_walk(path)
    candidates = scan_entity_sensors(rows) + scan_poe(rows) + scan_cpu(rows)
    counts: dict[str, int] = {}
    for item in candidates:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    return {
        "schema_version": 1,
        "source_walk": str(path),
        "standards_checked": ["ENTITY-SENSOR-MIB", "POWER-ETHERNET-MIB", "HOST-RESOURCES-MIB"],
        "candidate_count": len(candidates),
        "counts_by_category": counts,
        "candidates": candidates,
        "notes": [
            "Candidates are derived only from OIDs present in the supplied walk.",
            "This is vendor-neutral discovery assistance; no mapping is installed automatically.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--walk", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--enrich", type=Path)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    payload = build_payload(args.walk)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.enrich:
        try:
            existing = json.loads(args.enrich.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        existing["standard_sensor_discovery"] = payload
        capabilities = existing.setdefault("capabilities", {})
        counts = payload["counts_by_category"]
        capabilities["environment"] = counts.get("environment", 0) > 0
        capabilities["poe"] = counts.get("poe", 0) > 0
        capabilities["standard_cpu"] = counts.get("cpu", 0) > 0
        args.enrich.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    if args.report:
        counts = payload["counts_by_category"]
        print("Standard sensor discovery:")
        print("- Standards checked: ENTITY-SENSOR-MIB, POWER-ETHERNET-MIB, HOST-RESOURCES-MIB")
        print(f"- Candidate sensors found: {payload['candidate_count']}")
        print(f"- Environmental candidates: {counts.get('environment', 0)}")
        print(f"- PoE candidates: {counts.get('poe', 0)}")
        print(f"- CPU candidates: {counts.get('cpu', 0)}")
        print("- Review location: normalized capabilities JSON for this switch")
        print("- Installation behaviour: review-only; no entities are installed automatically")


if __name__ == "__main__":
    main()
