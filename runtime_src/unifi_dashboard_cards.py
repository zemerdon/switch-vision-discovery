#!/usr/bin/env python3
"""Emit Switch Vision card YAML for normalized UniFi2MQTT devices.

Exact registered hardware topology is authoritative. Normalized UniFi snapshot
rows are source bindings/evidence, not permission to redefine a known physical
chassis. Unknown devices, and legacy/partial registry records that do not carry
a physical topology contract, may still use observed topology as an inferred
contract.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

# Existing generic Switch Vision faceplates for UniFi devices. These are visual
# containers only; choosing an oversized temporary visual never changes the
# physical port_count/sfp_port_count contract emitted on the card.
GENERIC_VISUALS: tuple[tuple[int, int, str, str], ...] = (
    (24, 2, "unifi_24p_rj45_2sfp", "faceplates/unifi-24p-rj45-2sfp.png"),
    (24, 4, "stock_24rj45_4sfp", "faceplates/24rj45-4sfp.png"),
    (48, 2, "stock_48rj45_2sfp", "faceplates/48rj45-2sfp.png"),
    (48, 4, "stock_48rj45_4sfp", "faceplates/48rj45-4sfp.png"),
)
OPTICAL_CONNECTORS = {"SFP", "SFPPLUS", "SFP+", "SFP28"}


class JsonInputError(RuntimeError):
    """Raised when a required JSON input cannot be safely consumed."""


def canonical_model(value: Any) -> str:
    text = " ".join(str(value or "").strip().split()).casefold()
    for prefix in ("unknown ubiquiti ", "ubiquiti unifi ", "ubiquiti ", "unknown "):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    # UniFi API and SNMP sources use both `USW Pro 24 PoE` and
    # `USW-Pro-24-PoE` for the same exact model. Normalize separators only.
    return re.sub(r"[^a-z0-9]+", "", text)


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise JsonInputError(f"{label} could not be read") from exc
    except UnicodeDecodeError as exc:
        raise JsonInputError(f"{label} is not valid UTF-8") from exc

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise JsonInputError(f"{label} is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise JsonInputError(f"{label} root must be a JSON object")
    return payload


def safe_member(device_id: str) -> str:
    compact = re.sub(r"[^a-z0-9]", "", str(device_id).casefold())
    return "unifi_" + (compact[:16] or "device")


def registry_match(devices: list[dict[str, Any]], model: str) -> dict[str, Any] | None:
    wanted = canonical_model(model)
    for item in devices:
        if canonical_model(item.get("model")) == wanted:
            return item
    return None


def visual_geometry_matches(faceplate: str, rj45_count: int, sfp_count: int) -> bool:
    name = Path(str(faceplate or "")).name.casefold()
    match = re.search(r"(\d+)rj45-(\d+)sfp", name)
    if match:
        return int(match.group(1)) == rj45_count and int(match.group(2)) == sfp_count
    # Model-specific/legacy visual names cannot be inferred from the filename;
    # trust the authoritative registry for those until they are replaced.
    return bool(name)


def generic_visual(rj45_count: int, sfp_count: int) -> tuple[str, str, int, int] | None:
    """Return the smallest existing generic visual able to contain the device."""
    for max_rj45, max_sfp, profile, faceplate in GENERIC_VISUALS:
        if rj45_count <= max_rj45 and sfp_count <= max_sfp:
            return profile, faceplate, max_rj45, max_sfp
    # Never force an optical-heavy or otherwise oversized topology onto artwork
    # that cannot represent it.
    return None


def _connector(port: dict[str, Any]) -> str:
    return str(port.get("connector") or "").upper()


def _observed_ports(ports: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rj45 = [p for p in ports if isinstance(p, dict) and _connector(p) == "RJ45"]
    sfp = [p for p in ports if isinstance(p, dict) and _connector(p) in OPTICAL_CONNECTORS]
    return rj45, sfp


def _has_registry_topology(reg: dict[str, Any]) -> bool:
    ports = reg.get("ports")
    if not isinstance(ports, dict) or "rj45" not in ports:
        return False
    return any(
        key in ports
        for key in (
            "uplinks",
            "gigabit_sfp",
            "ten_gigabit_sfp_plus",
            "twenty_five_gigabit_sfp28",
        )
    )


def _registry_topology(reg: dict[str, Any]) -> tuple[int, int]:
    ports = reg.get("ports") if isinstance(reg.get("ports"), dict) else {}
    try:
        rj45 = int(ports.get("rj45") or 0)
    except (TypeError, ValueError):
        rj45 = 0
    uplinks_raw = ports.get("uplinks")
    if uplinks_raw is None:
        uplinks_raw = (
            (ports.get("gigabit_sfp") or 0)
            + (ports.get("ten_gigabit_sfp_plus") or 0)
            + (ports.get("twenty_five_gigabit_sfp28") or 0)
        )
    try:
        sfp = int(uplinks_raw or 0)
    except (TypeError, ValueError):
        sfp = 0
    return max(0, rj45), max(0, sfp)


def _normalise_port_map(value: Any) -> list[int] | None:
    if not isinstance(value, list):
        return None
    result: list[int] = []
    for raw in value:
        if isinstance(raw, bool):
            return None
        try:
            idx = int(raw)
        except (TypeError, ValueError):
            return None
        if idx <= 0 or idx in result:
            return None
        result.append(idx)
    return result


def _ports_by_idx(ports: list[Any]) -> tuple[dict[int, dict[str, Any]], set[int]]:
    by_idx: dict[int, dict[str, Any]] = {}
    duplicates: set[int] = set()
    for port in ports:
        if not isinstance(port, dict) or isinstance(port.get("idx"), bool):
            continue
        try:
            idx = int(port.get("idx"))
        except (TypeError, ValueError):
            continue
        if idx <= 0:
            continue
        if idx in by_idx:
            duplicates.add(idx)
        else:
            by_idx[idx] = port
    return by_idx, duplicates


def resolve_registered_unifi_ports(
    reg: dict[str, Any], ports: list[Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """Bind normalized UniFi rows to an exact registered physical topology.

    A registry API-port map, when present, is the strongest source binding.
    Without one, observed connector counts must exactly match registry topology;
    we refuse to guess which rows are physical when they disagree.
    """
    observed_rj45, observed_sfp = _observed_ports(ports)
    if not _has_registry_topology(reg):
        # Compatibility boundary for old test fixtures/partial registries. A
        # record without physical connector counts is not a topology contract.
        return observed_rj45, observed_sfp, None

    expected_rj45, expected_sfp = _registry_topology(reg)
    api_port_map = reg.get("unifi_api_port_map")

    if isinstance(api_port_map, dict):
        rj45_map = _normalise_port_map(api_port_map.get("rj45"))
        sfp_map = _normalise_port_map(api_port_map.get("sfp"))
        if rj45_map is None or sfp_map is None:
            return [], [], "registry API port map is malformed"
        if len(rj45_map) != expected_rj45 or len(sfp_map) != expected_sfp:
            return [], [], (
                "registry API port map geometry does not match registry topology "
                f"({len(rj45_map)} RJ45 + {len(sfp_map)} SFP map vs "
                f"{expected_rj45} RJ45 + {expected_sfp} SFP topology)"
            )
        by_idx, duplicates = _ports_by_idx(ports)
        mapped_indexes = set(rj45_map) | set(sfp_map)
        duplicate_mapped = sorted(mapped_indexes & duplicates)
        if duplicate_mapped:
            return [], [], f"API port map references duplicate snapshot idx {duplicate_mapped[0]}"
        missing = [idx for idx in [*rj45_map, *sfp_map] if idx not in by_idx]
        if missing:
            return [], [], f"API port map references missing snapshot idx {missing[0]}"
        mapped_rj45 = [by_idx[idx] for idx in rj45_map]
        mapped_sfp = [by_idx[idx] for idx in sfp_map]
        bad_rj45 = next((idx for idx, row in zip(rj45_map, mapped_rj45) if _connector(row) != "RJ45"), None)
        if bad_rj45 is not None:
            return [], [], f"API port map RJ45 idx {bad_rj45} is reported as {_connector(by_idx[bad_rj45]) or 'UNKNOWN'}"
        bad_sfp = next((idx for idx, row in zip(sfp_map, mapped_sfp) if _connector(row) not in OPTICAL_CONNECTORS), None)
        if bad_sfp is not None:
            return [], [], f"API port map SFP idx {bad_sfp} is reported as {_connector(by_idx[bad_sfp]) or 'UNKNOWN'}"
        return mapped_rj45, mapped_sfp, None

    if len(observed_rj45) != expected_rj45 or len(observed_sfp) != expected_sfp:
        return [], [], (
            f"registry expects {expected_rj45} RJ45 + {expected_sfp} SFP but snapshot reports "
            f"{len(observed_rj45)} RJ45 + {len(observed_sfp)} SFP"
        )
    return observed_rj45, observed_sfp, None


def render(
    snapshot: dict[str, Any], registry: dict[str, Any], indent: int = 6
) -> tuple[str, int, int, int, int, int]:
    pad = " " * indent
    devices = snapshot.get("devices")
    reg_devices = registry.get("devices")
    if not isinstance(devices, list):
        raise JsonInputError("UniFi2MQTT snapshot field 'devices' must be a list")
    if not isinstance(reg_devices, list):
        raise JsonInputError("supported-device registry field 'devices' must be a list")

    lines: list[str] = []
    emitted = 0
    exact = 0
    generic = 0
    pending_exact = 0
    invalid = 0
    if not devices:
        lines.append(f"{pad}# UniFi snapshot contains 0 normalized switching devices.")

    for device in devices:
        if not isinstance(device, dict):
            lines.append(f"{pad}# UniFi snapshot entry skipped because it is not a device object.")
            invalid += 1
            continue

        model = str(device.get("model") or "Unknown").strip()
        device_id = str(device.get("id") or "").strip()
        if not device_id:
            lines.append(f"{pad}# UniFi {json.dumps(model)} skipped because normalized device ID is missing.")
            invalid += 1
            continue

        ports = device.get("ports") if isinstance(device.get("ports"), list) else []
        observed_rj45, observed_sfp = _observed_ports(ports)
        reg = registry_match(reg_devices, model)

        if reg:
            rj45, sfp, conflict = resolve_registered_unifi_ports(reg, ports)
            if conflict:
                expected_rj45, expected_sfp = _registry_topology(reg)
                lines.append(
                    f"{pad}# TOPOLOGY_CONFLICT: UniFi {json.dumps(model)} {conflict}; "
                    f"exact {expected_rj45} RJ45 + {expected_sfp} SFP card withheld."
                )
                pending_exact += 1
                invalid += 1
                continue
        else:
            rj45, sfp = observed_rj45, observed_sfp

        if not rj45 and not sfp:
            lines.append(
                f"{pad}# UniFi {json.dumps(model)} skipped because no usable RJ45/SFP physical ports were reported."
            )
            invalid += 1
            continue

        physical_rj45 = len(rj45)
        physical_sfp = len(sfp)
        profile = str((reg or {}).get("calibration_profile") or "").strip()
        faceplate = str((reg or {}).get("default_faceplate") or "").strip()
        status = str((reg or {}).get("status") or "detected")
        api_port_map = (
            reg.get("unifi_api_port_map")
            if isinstance((reg or {}).get("unifi_api_port_map"), dict)
            else None
        )

        exact_visual = bool(
            reg
            and reg.get("dashboard_support") is True
            and profile
            and faceplate
            and visual_geometry_matches(faceplate, physical_rj45, physical_sfp)
        )
        visual_fallback = not exact_visual

        if visual_fallback:
            pending_exact += 1
            generic_choice = generic_visual(physical_rj45, physical_sfp)
            if generic_choice is None:
                if reg and reg.get("dashboard_support") is not True:
                    lines.append(
                        f"{pad}# UniFi {json.dumps(model)} detected; dashboard support is pending verified visuals "
                        f"and no suitable generic faceplate exists for {physical_rj45} RJ45 + {physical_sfp} SFP."
                    )
                else:
                    lines.append(
                        f"{pad}# UniFi {json.dumps(model)} detected, but no suitable generic faceplate exists for "
                        f"{physical_rj45} RJ45 + {physical_sfp} SFP; exact support remains pending."
                    )
                continue

            profile, faceplate, visual_rj45, visual_sfp = generic_choice
            generic += 1
            if not reg:
                reason = "no exact Switch Vision registry entry exists yet"
            elif reg.get("dashboard_support") is not True:
                reason = "exact dashboard visuals are still pending"
            else:
                reason = "the exact visual does not match the registered physical geometry"
            lines.append(
                f"{pad}# UniFi {json.dumps(model)}: {reason}; using generic "
                f"{visual_rj45} RJ45 + {visual_sfp} SFP faceplate while preserving "
                f"the {physical_rj45} RJ45 + {physical_sfp} SFP physical contract."
            )
        else:
            exact += 1

        member = safe_member(device_id)
        title = str(device.get("name") or model).strip() or model
        capabilities = (
            device.get("api_capabilities")
            if isinstance(device.get("api_capabilities"), dict)
            else {}
        )
        card = {
            "type": "custom:switch-vision-3650",
            "title": title,
            "member": member,
            "selected_switch": member,
            "switch_model": model,
            "vendor": "Ubiquiti",
            "data_source": "unifi_api",
            "unifi_device_id": device_id,
            "unifi_rj45_ports": physical_rj45,
            "unifi_sfp_port_offset": physical_rj45,
            "port_count": physical_rj45,
            "sfp_port_count": physical_sfp,
            "unifi_port_detail": bool(capabilities.get("port_detail")),
            "unifi_per_port_traffic": bool(capabilities.get("per_port_traffic")),
            "calibration_profile": profile,
            "faceplate_file": Path(faceplate).name,
            "calibration_profile_load": True,
            "calibration_profile_auto_load": True,
            "calibration_button": True,
            "activity_hold_seconds": 12,
            "auto_speed_entity": False,
            "unifi_refresh_seconds": 30,
            "support_status": status,
            "generic_faceplate": visual_fallback,
        }
        if api_port_map is not None:
            card["unifi_api_port_map"] = api_port_map

        dumped = yaml.safe_dump(
            [card], sort_keys=False, allow_unicode=True, default_flow_style=False
        ).rstrip().splitlines()
        for line in dumped:
            lines.append(pad + line)
        emitted += 1

    return "\n".join(lines), emitted, exact, generic, pending_exact, invalid


def yaml_safe_error(message: str, indent: int) -> str:
    """Return a comment-only diagnostic that cannot invalidate generated YAML."""
    safe = re.sub(r"[\r\n\t]+", " ", str(message)).strip()
    return f"{' ' * max(0, indent)}# ERROR: UniFi dashboard card generation failed: {safe}."


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--indent", type=int, default=6)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    indent = max(0, args.indent)

    try:
        snapshot = load_json(args.snapshot, "UniFi2MQTT snapshot")
        registry = load_json(args.registry, "supported-device registry")
        text, emitted, exact, generic, pending_exact, issues = render(
            snapshot, registry, indent
        )
    except JsonInputError as exc:
        # stdout is intentional: Discovery embeds this helper output inside the
        # generated YAML and historically suppresses helper stderr. Keep the
        # error as a YAML comment so the preview tells users why cards vanished.
        print(yaml_safe_error(str(exc), indent))
        return 2

    if text:
        print(text)
    if args.summary:
        print(
            f"# UniFi cards emitted: {emitted}; exact cards: {exact}; "
            f"generic fallbacks: {generic}; exact support pending: {pending_exact}; "
            f"issues: {issues}"
        )
        print(
            f"# UniFi cards emitted: {emitted}; waiting for visuals/registry: {pending_exact}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
