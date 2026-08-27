#!/usr/bin/env python3
"""Exact-model lookup for the informational Switch Vision device registry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_REGISTRY = Path('/opt/switch-vision/devices/supported_devices.json')


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {'devices': []}


def canonical_model(model: str) -> str:
    """Return the normalized model text used for exact-model registry matching."""
    target = " ".join(str(model or "").strip().split())
    lowered = target.casefold()
    for vendor_prefix in (
        "unknown cisco ",
        "unknown huawei ",
        "unknown zyxel ",
        "unknown ubiquiti ",
        "zyxel ",
        "ubiquiti unifi ",
        "ubiquiti ",
        "unknown ",
        "juniper networks ",
        "juniper ",
    ):
        if lowered.startswith(vendor_prefix):
            target = target[len(vendor_prefix):].strip()
            break
    # RouterOS reports this platform without the marketed rackmount suffix.
    # Preserve the observed evidence string while normalizing only lookup identity.
    if lowered == "crs328-24p-4s+":
        target = "CRS328-24P-4S+RM"
    return target.casefold()


def lookup(data: dict, model: str) -> dict | None:
    target = canonical_model(model)
    for device in data.get('devices', []):
        candidate = canonical_model(str(device.get('model', '')))
        if candidate == target:
            return device
        # Some vendors return the exact SKU followed by descriptive sysDescr text.
        # Only accept a description suffix after an exact registry SKU boundary.
        if candidate and (
            target.startswith(candidate + " ")
            or target.startswith(candidate + ",")
            or target.startswith(candidate + ";")
        ):
            return device
    return None


def report(model: str, device: dict | None) -> str:
    lines = ['Supported-device registry:', f'- Exact model: {model or "unknown"}']
    if not device:
        lines += [
            '- Registry match: no',
            '- Registry status: detected',
            '- Support My Switch contribution recommended: yes',
        ]
        return '\n'.join(lines)

    validation = device.get('validation', {})
    lines += [
        '- Registry match: yes',
        f'- Registry status: {device.get("status", "unknown")}',
        f'- Family: {device.get("family", "unknown")}',
        f'- Mapping profile: {device.get("mapping_profile") or "not assigned"}',
        f'- Calibration profile: {device.get("calibration_profile") or "not assigned"}',
        f'- Last validated: v{device.get("last_validated_version", "unknown")}',
        f'- Exact model detection: {validation.get("exact_model_detection", "unknown")}',
        f'- RJ45 mapping: {validation.get("rj45_mapping", "unknown")}',
        f'- PoE validation: {validation.get("poe", "unknown")}',
        f'- System sensor validation: {validation.get("system_sensors", "unknown")}',
        f'- Uplink validation: {validation.get("uplinks", "unknown")}',
        f'- Stack validation: {validation.get("stack", "unknown")}',
    ]
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--registry', type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument('--model', required=True)
    parser.add_argument('--report', action='store_true')
    parser.add_argument('--enrich', type=Path)
    parser.add_argument('--enrich-key', default='registry')
    args = parser.parse_args()

    data = load(args.registry)
    device = lookup(data, args.model)

    if args.enrich:
        try:
            payload = json.loads(args.enrich.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            payload = {}
        payload[args.enrich_key] = {
            'exact_model': args.model,
            'match': bool(device),
            'status': device.get('status', 'detected') if device else 'detected',
            'family': device.get('family', 'unknown') if device else 'unknown',
            'mapping_profile': device.get('mapping_profile', '') if device else '',
            'calibration_profile': device.get('calibration_profile', '') if device else '',
            'last_validated_version': device.get('last_validated_version', '') if device else '',
            'validation': device.get('validation', {}) if device else {},
            'informational_only': True,
        }
        args.enrich.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')

    if args.report:
        print(report(args.model, device))


if __name__ == '__main__':
    main()
