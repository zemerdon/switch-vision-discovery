#!/usr/bin/env python3
"""Emit Switch Vision card YAML for normalized UniFi2MQTT devices."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

UNIVERSAL_FALLBACK_FACEPLATE = "faceplates/48rj45-4sfp.png"
UNIVERSAL_FALLBACK_PROFILE = "default_cisco_48_port"


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


def render(snapshot: dict[str, Any], registry: dict[str, Any], indent: int = 6) -> tuple[str, int, int, int]:
    pad = " " * indent
    devices = snapshot.get("devices")
    reg_devices = registry.get("devices")
    if not isinstance(devices, list):
        raise JsonInputError("UniFi2MQTT snapshot field 'devices' must be a list")
    if not isinstance(reg_devices, list):
        raise JsonInputError("supported-device registry field 'devices' must be a list")

    lines: list[str] = []
    emitted = 0
    skipped = 0
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
        reg = registry_match(reg_devices, model)
        profile = str((reg or {}).get("calibration_profile") or "").strip()
        faceplate = str((reg or {}).get("default_faceplate") or "").strip()
        status = str((reg or {}).get("status") or "detected")
        ports = device.get("ports") if isinstance(device.get("ports"), list) else []
        rj45 = [p for p in ports if isinstance(p, dict) and str(p.get("connector") or "").upper() == "RJ45"]
        sfp = [p for p in ports if isinstance(p, dict) and str(p.get("connector") or "").upper() in {"SFP", "SFPPLUS", "SFP+", "SFP28"}]

        if not reg:
            lines.append(f"{pad}# UniFi {json.dumps(model)} detected, but no exact Switch Vision registry entry exists yet.")
            skipped += 1
            continue
        if reg.get("dashboard_support") is not True:
            lines.append(f"{pad}# UniFi {json.dumps(model)} detected; dashboard support is pending verified visuals.")
            skipped += 1
            continue
        api_port_map = reg.get("unifi_api_port_map") if isinstance(reg.get("unifi_api_port_map"), dict) else None
        visual_fallback = False
        if not profile or not faceplate or not visual_geometry_matches(faceplate, len(rj45), len(sfp)):
            # The 48 RJ45 + 4 SFP artwork is the project-wide temporary visual
            # fallback. Port-count fields still limit the live card to the real
            # device geometry; unused visual positions remain inactive.
            profile = UNIVERSAL_FALLBACK_PROFILE
            faceplate = UNIVERSAL_FALLBACK_FACEPLATE
            visual_fallback = True

        member = safe_member(device_id)
        title = str(device.get("name") or model).strip() or model
        capabilities = device.get("api_capabilities") if isinstance(device.get("api_capabilities"), dict) else {}
        card = {
            "type": "custom:switch-vision-3650",
            "title": title,
            "member": member,
            "selected_switch": member,
            "switch_model": model,
            "vendor": "Ubiquiti",
            "data_source": "unifi_api",
            "unifi_device_id": device_id,
            "unifi_rj45_ports": len(rj45),
            "unifi_sfp_port_offset": len(rj45),
            "port_count": len(rj45),
            "sfp_port_count": len(sfp),
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
        }
        if api_port_map is not None:
            card["unifi_api_port_map"] = api_port_map
        if visual_fallback:
            lines.append(f"{pad}# Generic 48 RJ45 + 4 SFP temporary visual fallback for {json.dumps(model)}.")
        dumped = yaml.safe_dump([card], sort_keys=False, allow_unicode=True, default_flow_style=False).rstrip().splitlines()
        for line in dumped:
            lines.append(pad + line)
        emitted += 1
    return "\n".join(lines), emitted, skipped, invalid


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
        text, emitted, skipped, invalid = render(snapshot, registry, indent)
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
            f"# UniFi cards emitted: {emitted}; "
            f"waiting for visuals/registry: {skipped}; invalid devices: {invalid}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
