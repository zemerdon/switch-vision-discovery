#!/usr/bin/env python3
"""Switch Vision physical-device contract resolver.

This module is the migration boundary between evidence classification and the
legacy Discovery parser/generator.  Source indexes (SNMP ifIndex / UniFi idx)
remain bindings; physical IDs are independent identities.

The first production slice consumes the existing contribution-tested SNMP
capability JSON, validates it against the exact-model registry, and can write a
legacy-compatible walk without changing source indexes.  Downstream code can
therefore migrate to one resolved physical contract without adding another set
of model-specific parser clauses.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

IFNAME_PREFIX = "1.3.6.1.2.1.31.1.1.1.1."
IFDESCR_PREFIX = "1.3.6.1.2.1.2.2.1.2."


def _canon_model(value: str) -> str:
    target = " ".join(str(value or "").strip().split())
    lowered = target.casefold()
    for prefix in (
        "unknown cisco ", "unknown huawei ", "unknown zyxel ",
        "unknown ubiquiti ", "zyxel ", "ubiquiti unifi ", "ubiquiti ",
        "unknown ", "juniper networks ", "juniper ",
    ):
        if lowered.startswith(prefix):
            target = target[len(prefix):].strip()
            break
    if target.casefold() == "crs328-24p-4s+":
        target = "CRS328-24P-4S+RM"
    return target.casefold()


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _registry_device(registry: dict[str, Any], model: str) -> dict[str, Any] | None:
    target = _canon_model(model)
    devices = [d for d in registry.get("devices", []) if isinstance(d, dict)]
    for device in devices:
        if _canon_model(str(device.get("model", ""))) == target:
            return device
    suffix: list[tuple[int, dict[str, Any]]] = []
    for device in devices:
        candidate = _canon_model(str(device.get("model", "")))
        if candidate and (target.startswith(candidate + " ") or target.startswith(candidate + ",") or target.startswith(candidate + ";")):
            suffix.append((len(candidate), device))
    if suffix:
        suffix.sort(key=lambda item: item[0], reverse=True)
        return suffix[0][1]
    return None


def _member_from_name(name: str) -> int:
    for pattern in (
        r"^(?:gi|te|fa|gigabitethernet|tengigabitethernet|fastethernet)(\d+)/\d+/\d+$",
        r"^(?:gi|te)(\d+)/\d+$",
    ):
        match = re.match(pattern, name, re.I)
        if match:
            try:
                return max(1, int(match.group(1)))
            except ValueError:
                pass
    return 1


def _source_port_hint(name: str) -> int | None:
    match = re.search(r"(?:^|/)(\d+)$", name)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


@dataclass(frozen=True)
class Port:
    physical_id: str
    member: int
    position: int
    media: str
    if_index: int
    source_name: str
    compatibility_name: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "physical_id": self.physical_id,
            "member": self.member,
            "position": self.position,
            "media": self.media,
            "source": {"type": "snmp", "if_index": self.if_index, "if_name": self.source_name},
            "compatibility_name": self.compatibility_name,
        }


def resolve(capabilities: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    device_info = capabilities.get("device") if isinstance(capabilities.get("device"), dict) else {}
    model = str(device_info.get("model_text") or "").strip()
    registry_device = _registry_device(registry, model)
    interfaces = [row for row in capabilities.get("interfaces", []) if isinstance(row, dict)]

    physical_rows = [row for row in interfaces if row.get("physical") is True and str(row.get("media", "")) in {"rj45", "sfp", "sfp_plus", "sfp28", "uplink"}]
    physical_rows.sort(key=lambda row: int(row.get("if_index") or 0))

    members = sorted({_member_from_name(str(row.get("name") or "")) for row in physical_rows}) or [1]
    member_count = len(members)
    member_map = {member: pos + 1 for pos, member in enumerate(members)}

    # Stable physical position counters are per member and per physical role.
    # SFP/SFP+/combo rows share one uplink position namespace so downstream
    # geometry sees physical cages rather than protocol/media aliases.
    rj45_pos: dict[int, int] = {}
    uplink_pos: dict[int, int] = {}
    ports: list[Port] = []
    seen_source: set[int] = set()

    for row in physical_rows:
        try:
            if_index = int(row.get("if_index"))
        except (TypeError, ValueError):
            continue
        if if_index in seen_source:
            continue
        seen_source.add(if_index)
        source_name = str(row.get("name") or "")
        media = str(row.get("media") or "other")
        source_member = _member_from_name(source_name)
        member = member_map.get(source_member, 1)
        hint = _source_port_hint(source_name)

        if media == "rj45":
            rj45_pos[member] = rj45_pos.get(member, 0) + 1
            position = rj45_pos[member]
            physical_id = f"m{member}:rj45:{position}"
            compatibility = f"Gi{member}/0/{position}"
        else:
            uplink_pos[member] = uplink_pos.get(member, 0) + 1
            position = uplink_pos[member]
            physical_id = f"m{member}:uplink:{position}"
            if media == "sfp28":
                compatibility = f"TwentyFiveGigE{member}/1/{position}"
            elif media == "sfp_plus":
                compatibility = f"Te{member}/1/{position}"
            else:
                compatibility = f"Gi{member}/1/{position}"

        ports.append(Port(physical_id, member, position, media, if_index, source_name, compatibility))

    observed = {
        "members": member_count,
        "physical": len(ports),
        "rj45": sum(1 for port in ports if port.media == "rj45"),
        "uplinks": sum(1 for port in ports if port.media in {"sfp", "sfp_plus", "sfp28", "uplink"}),
        "sfp": sum(1 for port in ports if port.media == "sfp"),
        "sfp_plus": sum(1 for port in ports if port.media == "sfp_plus"),
        "sfp28": sum(1 for port in ports if port.media == "sfp28"),
        "combo_or_unspecified_uplink": sum(1 for port in ports if port.media == "uplink"),
    }

    expected: dict[str, Any] = {}
    status = "unregistered"
    errors: list[str] = []
    if registry_device:
        registry_ports = registry_device.get("ports") if isinstance(registry_device.get("ports"), dict) else {}
        expected_rj45_per_member = int(registry_ports.get("rj45") or 0)
        expected_uplinks_per_member = int(registry_ports.get("uplinks") or ((registry_ports.get("gigabit_sfp") or 0) + (registry_ports.get("ten_gigabit_sfp_plus") or 0) + (registry_ports.get("twenty_five_gigabit_sfp28") or 0)))
        stack_allowed = bool(registry_device.get("stack_support"))
        expected_members = member_count if stack_allowed else 1
        expected = {
            "members": expected_members,
            "rj45_per_member": expected_rj45_per_member,
            "uplinks_per_member": expected_uplinks_per_member,
            "rj45": expected_rj45_per_member * expected_members,
            "uplinks": expected_uplinks_per_member * expected_members,
            "physical": (expected_rj45_per_member + expected_uplinks_per_member) * expected_members,
        }
        if not stack_allowed and member_count != 1:
            errors.append(f"registry marks model non-stackable but observed {member_count} members")
        if observed["rj45"] != expected["rj45"]:
            errors.append(f"RJ45 expected {expected['rj45']} observed {observed['rj45']}")
        if observed["uplinks"] != expected["uplinks"]:
            errors.append(f"uplinks expected {expected['uplinks']} observed {observed['uplinks']}")
        if observed["physical"] != expected["physical"]:
            errors.append(f"physical expected {expected['physical']} observed {observed['physical']}")
        status = "resolved" if not errors else "topology_conflict"

    return {
        "schema_version": 1,
        "authority": "switch_vision_physical_contract",
        "device": {
            "model": str(registry_device.get("model")) if registry_device else model or "unknown",
            "vendor": str(registry_device.get("vendor")) if registry_device else str(device_info.get("vendor_name") or device_info.get("vendor") or "unknown"),
            "registry_match": bool(registry_device),
            "mapping_profile": str(registry_device.get("mapping_profile") or "") if registry_device else "",
            "calibration_profile": str(registry_device.get("calibration_profile") or "") if registry_device else "",
            "faceplate": str(registry_device.get("default_faceplate") or "") if registry_device else "",
            "dashboard_support": bool(registry_device.get("dashboard_support")) if registry_device else False,
        },
        "status": status,
        "errors": errors,
        "expected": expected,
        "observed": observed,
        "ports": [port.as_dict() for port in ports],
        "source_bindings_are_physical_identity": False,
    }


def _parse_oid_index(line: str, prefix: str) -> int | None:
    left = line.split("=", 1)[0].strip()
    left = left.lstrip(".")
    if left.startswith("iso."):
        left = "1." + left[4:]
    if not left.startswith(prefix):
        return None
    tail = left[len(prefix):]
    try:
        return int(tail)
    except ValueError:
        return None


def _replace_value(line: str, value: str) -> str:
    if "=" not in line:
        return line
    left, right = line.split("=", 1)
    value_type = "STRING:"
    stripped = right.strip()
    if ":" in stripped:
        value_type = stripped.split(":", 1)[0] + ":"
    return f'{left}= {value_type} "{value}"\n'


def normalize_walk(source: Path, destination: Path, contract: dict[str, Any]) -> None:
    """Write a compatibility view without altering original evidence.

    Exact-model contracts with a topology conflict fail closed: the source is
    copied unchanged so no fabricated physical topology can reach production.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if contract.get("status") != "resolved":
        destination.write_bytes(source.read_bytes())
        return

    by_index: dict[int, str] = {}
    physical_indexes: set[int] = set()
    for port in contract.get("ports", []):
        source_binding = port.get("source") if isinstance(port, dict) else None
        if not isinstance(source_binding, dict):
            continue
        try:
            idx = int(source_binding.get("if_index"))
        except (TypeError, ValueError):
            continue
        physical_indexes.add(idx)
        by_index[idx] = str(port.get("compatibility_name") or "")

    # Any interface classified non-physical remains evidence, but if it looks
    # like a front-panel alias of a resolved physical interface it must not be
    # rediscovered by the legacy parser.  Mask only ifName/ifDescr text; all OID
    # values and ifIndex bindings remain intact for diagnostics.
    capabilities_physical_names = {str(port.get("source", {}).get("if_name") or "") for port in contract.get("ports", []) if isinstance(port, dict)}

    out: list[str] = []
    for raw in source.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True):
        idx = _parse_oid_index(raw, IFNAME_PREFIX)
        if idx is None:
            idx = _parse_oid_index(raw, IFDESCR_PREFIX)
        if idx is not None and idx in by_index:
            out.append(_replace_value(raw, by_index[idx]))
            continue
        out.append(raw)

    destination.write_text("".join(out), encoding="utf-8")


def patch_text_outputs(report_path: Path | None, yaml_path: Path | None, contract: dict[str, Any]) -> None:
    if contract.get("status") != "resolved":
        return
    model = str(contract.get("device", {}).get("model") or "unknown")
    observed_physical = int(contract.get("observed", {}).get("physical") or 0)

    if report_path and report_path.exists():
        text = report_path.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"(?m)^Model/platform: .*?$", f"Model/platform: {model}", text, count=1)
        text = re.sub(r"(?m)^- Physical switch interfaces detected: \d+$", f"- Physical switch interfaces detected: {observed_physical}", text, count=1)
        text = re.sub(r"(?m)^- Mapped physical interfaces: \d+$", f"- Mapped physical interfaces: {observed_physical}", text, count=1)
        report_path.write_text(text, encoding="utf-8")

    if yaml_path and yaml_path.exists():
        text = yaml_path.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"(?m)^# Detected model: .*?$", f"# Detected model: {model}", text)
        text = re.sub(r"(?m)^(\s*device_model:)\s*.*?$", lambda m: f"{m.group(1)} {model}", text)
        yaml_path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capabilities", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--walk", type=Path)
    parser.add_argument("--normalized-walk", type=Path)
    parser.add_argument("--patch-report", type=Path)
    parser.add_argument("--patch-yaml", type=Path)
    args = parser.parse_args()

    contract = resolve(_load(args.capabilities), _load(args.registry))
    args.contract.parent.mkdir(parents=True, exist_ok=True)
    args.contract.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")

    if args.walk and args.normalized_walk:
        normalize_walk(args.walk, args.normalized_walk, contract)
    if args.patch_report or args.patch_yaml:
        patch_text_outputs(args.patch_report, args.patch_yaml, contract)

    if contract.get("status") == "topology_conflict":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
