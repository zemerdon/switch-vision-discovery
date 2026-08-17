#!/usr/bin/env python3
"""Derive Juniper switch-port mode from standard BRIDGE/Q-BRIDGE tables.

Output TSV: physical_port, mode, pvid, allowed_vlan_row_ids
The VLAN row IDs are diagnostic only; PVID is the authoritative native VLAN.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

OID_IFNAME = "1.3.6.1.2.1.31.1.1.1.1."
OID_BRIDGE_IFINDEX = "1.3.6.1.2.1.17.1.4.1.2."
OID_PVID = "1.3.6.1.2.1.17.7.1.4.5.1.1."
OID_STATIC_NAME = "1.3.6.1.2.1.17.7.1.4.3.1.1."
OID_STATIC_EGRESS = "1.3.6.1.2.1.17.7.1.4.3.1.2."
OID_STATIC_UNTAGGED = "1.3.6.1.2.1.17.7.1.4.3.1.4."

LINE_RE = re.compile(r"^\.?([0-9.]+)\s+=\s+([^:]+):\s*(.*)$")
HEX_RE = re.compile(r"(?:[0-9A-Fa-f]{2})(?:\s+[0-9A-Fa-f]{2})*")


def parse_walk(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    current_oid: str | None = None
    current_type = ""
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.rstrip()
        match = LINE_RE.match(line)
        if match:
            oid, value_type, value = match.groups()
            current_oid = oid
            current_type = value_type.strip().upper()
            values[oid] = value.strip()
            continue
        # net-snmp wraps long Hex-STRING values onto continuation lines.
        if current_oid and current_type == "HEX-STRING":
            stripped = line.strip()
            if stripped and HEX_RE.fullmatch(stripped):
                values[current_oid] = (values[current_oid] + " " + stripped).strip()
            else:
                current_oid = None
                current_type = ""
    return values


def suffix_int(oid: str, base: str) -> int | None:
    if not oid.startswith(base):
        return None
    try:
        return int(oid[len(base) :])
    except ValueError:
        return None


def int_value(value: str) -> int | None:
    match = re.search(r"-?\d+", value)
    return int(match.group(0)) if match else None


def portlist_has(hex_value: str, bridge_port: int) -> bool:
    octets = bytes(int(part, 16) for part in re.findall(r"[0-9A-Fa-f]{2}", hex_value))
    if bridge_port < 1:
        return False
    bit_index = bridge_port - 1
    byte_index = bit_index // 8
    if byte_index >= len(octets):
        return False
    mask = 0x80 >> (bit_index % 8)
    return bool(octets[byte_index] & mask)


def vlan_id_from_name(name: str, fallback: int) -> int:
    text = name.strip().strip('"')
    match = re.search(r"(?:VLAN|VID)[ _-]?(\d{1,4})\b", text, re.I)
    return int(match.group(1)) if match else fallback


def derive(path: Path) -> list[tuple[int, str, int, str]]:
    values = parse_walk(path)
    logical_ifindex: dict[int, int] = {}
    bridge_for_ifindex: dict[int, int] = {}
    pvid_for_bridge: dict[int, int] = {}
    vlan_names: dict[int, str] = {}
    egress: dict[int, str] = {}
    untagged: dict[int, str] = {}

    for oid, value in values.items():
        idx = suffix_int(oid, OID_IFNAME)
        if idx is not None:
            match = re.fullmatch(r'"?ge-0/0/(\d+)\.0"?', value.strip())
            if match:
                logical_ifindex[int(match.group(1))] = idx
            continue
        bridge = suffix_int(oid, OID_BRIDGE_IFINDEX)
        if bridge is not None:
            ifindex = int_value(value)
            if ifindex and ifindex > 0:
                bridge_for_ifindex[ifindex] = bridge
            continue
        bridge = suffix_int(oid, OID_PVID)
        if bridge is not None:
            pvid = int_value(value)
            if pvid is not None:
                pvid_for_bridge[bridge] = pvid
            continue
        vlan_row = suffix_int(oid, OID_STATIC_NAME)
        if vlan_row is not None:
            vlan_names[vlan_row] = value
            continue
        vlan_row = suffix_int(oid, OID_STATIC_EGRESS)
        if vlan_row is not None:
            egress[vlan_row] = value
            continue
        vlan_row = suffix_int(oid, OID_STATIC_UNTAGGED)
        if vlan_row is not None:
            untagged[vlan_row] = value

    rows: list[tuple[int, str, int, str]] = []
    for port in sorted(logical_ifindex):
        bridge = bridge_for_ifindex.get(logical_ifindex[port])
        if not bridge or bridge not in pvid_for_bridge:
            continue
        pvid = pvid_for_bridge[bridge]
        member_rows = [row for row, bitmap in egress.items() if portlist_has(bitmap, bridge)]
        untagged_rows = {row for row, bitmap in untagged.items() if portlist_has(bitmap, bridge)}
        tagged_rows = [row for row in member_rows if row not in untagged_rows]
        # Multiple VLAN memberships or any tagged membership means trunk. A
        # single untagged/PVID membership is an access port.
        mode = "trunk" if len(member_rows) > 1 or tagged_rows else "access"
        allowed_ids = sorted(vlan_id_from_name(vlan_names.get(row, ""), row) for row in member_rows)
        rows.append((port, mode, pvid, ",".join(str(v) for v in allowed_ids)))
    return rows


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} WALK_FILE", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file():
        return 1
    for port, mode, pvid, allowed in derive(path):
        print(f"{port}\t{mode}\t{pvid}\t{allowed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
