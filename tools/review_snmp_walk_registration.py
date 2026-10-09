#!/usr/bin/env python3
"""Offline, read-only review of full/targeted SNMP walks for model admission.

Produces reviewable facts; never registers a device, touches a live switch or
modifies a raw contribution. A curated sysObjectID AND exact *local* sysDescr
plus a complete verified IF-MIB binding contract are required to propose
Experimental admission. Unknown/contradictory walks remain pending.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "runtime_src/opt/switch-vision/mib_database/vendors"
MAX_WALK_BYTES = 8 * 1024 * 1024
MAX_ZIP_ENTRIES = 250
MAX_ZIP_EXPANDED = 24 * 1024 * 1024
WALK_OID = re.compile(r"^\.?(\d+(?:\.\d+)*)\s+=\s+(.+)$")
SYS_DESCR = "1.3.6.1.2.1.1.1.0"
SYS_OBJECT = "1.3.6.1.2.1.1.2.0"
IFNAME = "1.3.6.1.2.1.31.1.1.1.1."
IFTYPE = "1.3.6.1.2.1.2.2.1.3."
IFOPER = "1.3.6.1.2.1.2.2.1.8."
IFCOUNTER_RX = "1.3.6.1.2.1.31.1.1.1.6."
IFCOUNTER_TX = "1.3.6.1.2.1.31.1.1.1.10."
BRIDGE_PORT = "1.3.6.1.2.1.17.1.4.1.2."


def _decode(value: str) -> str:
    prefix = ""
    if ":" in value:
        prefix, text = value.split(":", 1)
        if prefix.strip().upper() in {"OID", "STRING", "INTEGER", "COUNTER64", "COUNTER32", "GAUGE32", "INTEGER32", "TIMETICKS"}:
            value = text.strip()
    return value.strip().strip('"').lstrip(".") if prefix.strip().upper() == "OID" else value.strip().strip('"')


def _curated_products(db: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted(db.glob("*/products.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for row in doc.get("products", []):
            if all(key in row for key in ("sys_object_id", "sys_descr_exact", "model_hint", "port_contract")):
                results.append(row)
    return results


def inspect_walk(payload: bytes, products: list[dict[str, Any]], *, source: str) -> dict[str, Any]:
    digest = hashlib.sha256(payload).hexdigest()
    result: dict[str, Any] = {
        "source_kind": "targeted" if "targeted" in source.lower() else "full",
        "sha256": digest,
        "registration": "review_required",
        "reason": "",
    }
    if len(payload) > MAX_WALK_BYTES:
        return {**result, "reason": "walk_size_limit"}
    text = payload.decode("utf-8", errors="replace")
    # Plain numeric net-snmp full walks generally have no SV pass footer.
    # Accept them only when a validated interface contract is complete.
    # Explicit failed/running/timeout markers are never allowed.
    statuses = re.findall(r"(?im)^#\s*Switch Vision SNMP walk result:\s*(\w+)\s*$", text)
    if (statuses and statuses[-1].casefold() != "pass") or (
        not statuses and any(x in text.lower() for x in ("no snmp response from switch during", "timeout: no response"))
    ):
        return {**result, "reason": "walk_not_completed_successfully"}
    values: dict[str, str] = {}
    for line in text.splitlines():
        if len(line) > 8192:
            return {**result, "reason": "walk_line_size_limit"}
        match = WALK_OID.match(line.strip())
        if not match:
            continue
        oid, value = match.groups()
        if oid in values and values[oid] != value:
            return {**result, "reason": "duplicate_oid_conflict"}
        values[oid] = value
    descr = _decode(values.get(SYS_DESCR, ""))
    oid = _decode(values.get(SYS_OBJECT, ""))
    result["sys_object_id"] = oid
    matches = [
        item for item in products
        if item["sys_object_id"] == oid and item["sys_descr_exact"] == descr
    ]
    if len(matches) != 1:
        return {**result, "reason": "no_unique_curated_oid_and_sysdescr", "if_name_rows": sum(k.startswith(IFNAME) for k in values)}
    row = matches[0]
    contract = row["port_contract"]
    count = int(contract["logical_port_count"])
    base = int(contract["ifindex_base"])
    prefix = str(contract["ifname_prefix"])
    name_rows = {oid[len(IFNAME):]: _decode(value) for oid, value in values.items() if oid.startswith(IFNAME)}
    # Model-family mapping comes from a reviewed knowledge row, not a
    # TP-Link-specific hardcoded parser; additional manufacturers can extend
    # the curated catalog with a different ifName prefix and index base.
    ethernet = [
        (idx, name) for idx, name in name_rows.items()
        if name.startswith(prefix) and re.fullmatch(r"[1-9][0-9]*", name[len(prefix):])
    ]
    expected = {(str(base + port), f"{prefix}{port}") for port in range(1, count + 1)}
    observed = set(ethernet)
    problems: list[str] = []
    if observed != expected:
        problems.append("physical_interface_set_not_exact")
    for idx, name in expected:
        kind = values.get(IFTYPE + idx, "")
        if "ethernetCsmacd(6)" not in kind and not re.search(r"(?:^|\D)6$",kind):
            problems.append("iftype_not_ethernet")
            break
    bridge_rows = {idx for k, v in values.items() if k.startswith(BRIDGE_PORT) for idx in [_decode(v)]}
    bridge_complete = all(str(base + i) in bridge_rows for i in range(1, count + 1))
    present = {
        "oper_status": sum(IFOPER + str(base + i) in values for i in range(1, count + 1)),
        "rx_counter": sum(IFCOUNTER_RX + str(base + i) in values for i in range(1, count + 1)),
        "tx_counter": sum(IFCOUNTER_TX + str(base + i) in values for i in range(1, count + 1)),
    }
    # Counter/bridge/status coverage describes operational availability but
    # absence in some full walks is not an invented physical connector.
    # Do not promote unsupported sensors from these optional captures.
    telemetry_gaps = [k for k, n in present.items() if n != count]
    # The candidate derives only manufacturer-reviewed port classes, not live
    # media selection, PoE consumption or inferred enterprise sensor values.
    result.update({
        "candidate_model": row["model_hint"],
        "hardware_revision": row.get("hardware_revision", "unknown"),
        "if_name_rows": len(name_rows),
        "observed_physical_interfaces": len(observed),
        "verified_port_contract": {
            "rj45": int(contract["rj45"]),
            "sfp": int(contract["sfp"]),
            "logical": count,
            "poe_capable_copper": int(contract.get("poe_capable_copper", 0)),
        },
        "ifindex_min": base + 1,
        "ifindex_max": base + count,
        "present_telemetry_rows": present,
        "bridge_identity_complete": bridge_complete,
        "telemetry_pending": telemetry_gaps,
        "poe_power_telemetry": "unknown",
        "source": "curated_product_oid_and_local_sysdescr",
    })
    if problems:
        result["reason"] = ",".join(sorted(set(problems)))
    else:
        result["registration"] = "experimental_candidate"
        result["reason"] = "hardware_revision_and_field_visual_confirmation_pending"
    return result


def _iter_walks(path: Path) -> list[tuple[str, bytes]]:
    if path.suffix.lower() not in {".zip", ".txt", ".log", ".walk"}:
        raise ValueError("Unsupported input type")
    if path.suffix.lower() != ".zip":
        size = path.stat().st_size
        if size > MAX_WALK_BYTES:
            raise ValueError("Walk exceeds size limit")
        return [(path.name, path.read_bytes())]
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ZIP_ENTRIES or sum(e.file_size for e in entries) > MAX_ZIP_EXPANDED:
            raise ValueError("Archive exceeds safety limit")
        chosen = [
            e for e in entries if not e.is_dir()
            and e.filename.endswith(("live-full-snmpwalk.txt", "live-targeted-snmpwalk.txt"))
            and not e.filename.startswith("/")
            and ".." not in Path(e.filename).parts
            and e.file_size <= MAX_WALK_BYTES
            and not ((e.external_attr >> 16) & 0o170000) == 0o120000
        ]
        if not chosen:
            raise ValueError("No readable full/targeted walks found in archive")
        return [(e.filename.rsplit("/", 1)[-1], archive.read(e)) for e in chosen]


def review(path: Path, knowledge: Path) -> dict[str, Any]:
    products = _curated_products(knowledge)
    walks = _iter_walks(path)
    reviewed = [inspect_walk(payload, products, source=name) for name, payload in walks]
    return {"schema_version": 1, "read_only": True, "requires_human_review": True,
            "walks": reviewed, "experimental_candidates": sum(
                row["registration"] == "experimental_candidate" for row in reviewed)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Review a full SNMP walk or Support My Switch ZIP without modifying evidence.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--knowledge", type=Path, default=KNOWLEDGE.parent)
    args = parser.parse_args()
    print(json.dumps(review(args.input, args.knowledge), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
