#!/usr/bin/env python3
"""Hub AutoDiscover orchestration with explicit runtime dependencies.

The SNMP scan/probe engine remains owned by autodiscover.py. This module owns
Hub-facing status/request/scan/add coordination and never imports support_web.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
from pathlib import Path
from typing import Any, Callable

import autodiscover


@dataclass(frozen=True)
class HubAutoDiscoverRuntime:
    self_addon_options: Callable[[], dict[str, Any]]
    effective_discovery_options: Callable[[dict[str, Any]], dict[str, Any]]
    plain_text: Callable[..., str]
    validate_switch_row: Callable[[Any, int], dict[str, Any]]
    save_discovery_settings: Callable[[Any], dict[str, Any]]
    registry_loader: Callable[[], dict[str, Any]]
    unifi_snapshot_loader: Callable[[], dict[str, Any]]


def load_registry(read_json: Callable[[Path], Any], path: Path) -> dict[str, Any]:
    data = read_json(path)
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {"devices": data}
    return {"devices": []}


def load_unifi_snapshot(read_json: Callable[[Path], Any], path: Path) -> dict[str, Any]:
    data = read_json(path)
    return data if isinstance(data, dict) else {"devices": []}


def validated_networks(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError("autodiscover_networks must be a list.")
    if not value:
        return []
    networks, _hosts, _raw_count = autodiscover.validate_subnets(value)
    return [str(network) for network in networks]


def suggested_network(
    options: dict[str, Any],
    unifi_snapshot: dict[str, Any],
) -> str:
    """Return an editable /24 suggestion from existing device evidence only."""
    addresses: list[str] = []
    rows = options.get("switches") if isinstance(options.get("switches"), list) else []
    for row in rows:
        if isinstance(row, dict):
            addresses.append(str(row.get("switch_host") or "").strip())
    unifi_rows = (
        unifi_snapshot.get("devices")
        if isinstance(unifi_snapshot.get("devices"), list)
        else []
    )
    for row in unifi_rows:
        if isinstance(row, dict):
            addresses.append(str(row.get("ip_address") or "").strip())
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if isinstance(address, ipaddress.IPv4Address):
            return str(ipaddress.ip_network(f"{address}/24", strict=False))
    return ""


def status(*, runtime: HubAutoDiscoverRuntime) -> dict[str, Any]:
    options = runtime.effective_discovery_options(runtime.self_addon_options())
    unifi_snapshot = runtime.unifi_snapshot_loader()
    credentials = autodiscover.credential_specs(options, use_saved=True)
    rows = options.get("switches") if isinstance(options.get("switches"), list) else []
    unifi_rows = (
        unifi_snapshot.get("devices")
        if isinstance(unifi_snapshot.get("devices"), list)
        else []
    )
    saved_networks = validated_networks(options.get("autodiscover_networks", []))
    return {
        "schema_version": 2,
        "snmp_version": "2c",
        "max_scan_hosts": autodiscover.MAX_SCAN_HOSTS,
        "max_total_hosts": autodiscover.MAX_SCAN_TOTAL_HOSTS,
        "max_subnets": autodiscover.MAX_SCAN_SUBNETS,
        "saved_switch_count": sum(
            1
            for row in rows
            if isinstance(row, dict)
            and str(row.get("switch_name") or "").strip()
            and str(row.get("switch_host") or "").strip()
        ),
        "saved_credential_count": len(credentials),
        "saved_credentials": [
            {
                "ref": str(item.get("ref") or ""),
                "label": str(item.get("label") or ""),
            }
            for item in credentials
        ],
        "unifi_device_count": len(
            [row for row in unifi_rows if isinstance(row, dict)]
        ),
        "saved_networks": saved_networks,
        "suggested_network": suggested_network(options, unifi_snapshot),
        "policy": (
            "AutoDiscover uses only SNMP communities already saved on real configured "
            "switches and/or a one-time community you enter for this scan. It never guesses communities."
        ),
    }


def parse_request(
    data: Any,
    *,
    runtime: HubAutoDiscoverRuntime,
) -> tuple[list[str], bool, str]:
    if not isinstance(data, dict):
        raise ValueError("AutoDiscover request must contain a JSON object.")
    unknown = sorted(set(data) - {"network", "networks", "use_saved", "manual_community"})
    if unknown:
        raise ValueError(f"Unsupported AutoDiscover field: {unknown[0]}")
    if "network" in data and "networks" in data:
        raise ValueError("Use networks, not both network and networks.")
    raw_networks = data.get("networks")
    if raw_networks is None and "network" in data:
        raw_networks = [data.get("network")]
    networks, _hosts, _raw_count = autodiscover.validate_subnets(raw_networks)
    network_values = [str(network) for network in networks]

    use_saved_value = data.get("use_saved", True)
    if isinstance(use_saved_value, bool):
        use_saved = use_saved_value
    elif str(use_saved_value).strip().lower() in {"true", "1", "yes", "on"}:
        use_saved = True
    elif str(use_saved_value).strip().lower() in {"false", "0", "no", "off"}:
        use_saved = False
    else:
        raise ValueError("use_saved must be true or false.")

    manual = runtime.plain_text(
        data.get("manual_community", ""),
        "manual_community",
        max_length=256,
    ).strip()
    return network_values, use_saved, manual


def scan(data: Any, *, runtime: HubAutoDiscoverRuntime) -> dict[str, Any]:
    networks, use_saved, manual = parse_request(data, runtime=runtime)
    options = runtime.effective_discovery_options(runtime.self_addon_options())
    try:
        configured_timeout = float(str(options.get("snmp_timeout") or "1"))
    except ValueError:
        configured_timeout = 1.0
    timeout = min(1.5, max(0.5, configured_timeout))

    result = autodiscover.scan(
        networks,
        options=options,
        manual_community=manual,
        use_saved=use_saved,
        registry_data=runtime.registry_loader(),
        unifi_snapshot=runtime.unifi_snapshot_loader(),
        timeout=timeout,
    )

    serialized = json.dumps(result, sort_keys=True)
    for credential in autodiscover.credential_specs(
        options,
        use_saved=use_saved,
        manual_community=manual,
    ):
        secret = str(credential.get("community") or "")
        if secret and secret in serialized:
            raise RuntimeError(
                "AutoDiscover refused a response containing credential material."
            )

    runtime.save_discovery_settings(
        {"settings": {"autodiscover_networks": networks}}
    )
    return result


def add(data: Any, *, runtime: HubAutoDiscoverRuntime) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("AutoDiscover add request must contain a JSON object.")
    unknown = sorted(set(data) - {"network", "networks", "manual_community", "devices"})
    if unknown:
        raise ValueError(f"Unsupported AutoDiscover add field: {unknown[0]}")
    if "network" in data and "networks" in data:
        raise ValueError("Use networks, not both network and networks.")

    raw_networks = data.get("networks")
    if raw_networks is None and "network" in data:
        raw_networks = [data.get("network")]
    networks, _host_networks, _raw_count = autodiscover.validate_subnets(raw_networks)
    manual = runtime.plain_text(
        data.get("manual_community", ""),
        "manual_community",
        max_length=256,
    ).strip()
    requested = data.get("devices")
    if not isinstance(requested, list) or not requested or len(requested) > 256:
        raise ValueError(
            "AutoDiscover add requires between 1 and 256 candidate devices."
        )

    options = runtime.effective_discovery_options(runtime.self_addon_options())
    current_rows = (
        options.get("switches") if isinstance(options.get("switches"), list) else []
    )
    configured_hosts = {
        str(row.get("switch_host") or "").strip()
        for row in current_rows
        if isinstance(row, dict) and str(row.get("switch_host") or "").strip()
    }
    existing_names = {
        str(row.get("switch_name") or "").strip()
        for row in current_rows
        if isinstance(row, dict) and str(row.get("switch_name") or "").strip()
    }
    registry = runtime.registry_loader()
    try:
        configured_timeout = float(str(options.get("snmp_timeout") or "1"))
    except ValueError:
        configured_timeout = 1.0
    timeout = min(1.5, max(0.5, configured_timeout))

    additions: list[dict[str, Any]] = []
    added_safe: list[dict[str, str]] = []
    seen_hosts: set[str] = set()

    for index, raw in enumerate(requested, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"AutoDiscover candidate {index} must be an object.")
        unexpected = sorted(set(raw) - {"host", "credential_ref"})
        if unexpected:
            raise ValueError(
                f"Unsupported AutoDiscover candidate field: {unexpected[0]}"
            )

        host = runtime.plain_text(
            raw.get("host", ""),
            f"AutoDiscover candidate {index} host",
            max_length=64,
            allow_empty=False,
        ).strip()
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError(
                f"AutoDiscover candidate {index} host must be IPv4."
            ) from exc
        if not isinstance(address, ipaddress.IPv4Address):
            raise ValueError(f"AutoDiscover candidate {index} host must be IPv4.")
        if not any(address in network for network in networks):
            raise ValueError(
                f"AutoDiscover candidate {index} is outside the scanned networks."
            )
        if host in configured_hosts or host in seen_hosts:
            raise ValueError(
                f"AutoDiscover candidate {host} is already configured or duplicated."
            )

        credential_ref = runtime.plain_text(
            raw.get("credential_ref", ""),
            f"AutoDiscover candidate {index} credential_ref",
            max_length=128,
            allow_empty=False,
        ).strip()
        community = autodiscover.resolve_credential(
            options,
            credential_ref,
            manual_community=manual,
        )
        verified = autodiscover.probe_host(
            host,
            {"ref": credential_ref, "label": "", "community": community},
            registry_data=registry,
            timeout=timeout,
        )
        if verified is None:
            raise ValueError(
                f"AutoDiscover candidate {host} no longer responds with the selected SNMP credential. "
                "Run the scan again."
            )

        switch_name = autodiscover.suggest_switch_name(verified, existing_names)
        existing_names.add(switch_name)
        display_name = (
            str(verified.get("sys_name") or "").strip()
            or str(verified.get("model") or verified.get("model_hint") or "").strip()
            or host
        )[:120]
        row = {
            "switch_name": switch_name,
            "display_name": display_name,
            "switch_host": host,
            "sensor_prefix": autodiscover.sensor_prefix_for_name(switch_name),
            "snmp_community": community,
            "enabled": "enabled",
            "walk_mode": "targeted",
            "switch_model": "auto",
            "card_header_title": "",
        }
        additions.append(
            runtime.validate_switch_row(
                row,
                len(current_rows) + len(additions) + 1,
            )
        )
        added_safe.append(
            {
                "host": host,
                "switch_name": switch_name,
                "display_name": display_name,
                "model_hint": str(
                    verified.get("model") or verified.get("model_hint") or ""
                )[:160],
            }
        )
        seen_hosts.add(host)

    retained = [
        dict(row)
        for row in current_rows
        if isinstance(row, dict)
        and (
            str(row.get("switch_name") or "").strip()
            or str(row.get("switch_host") or "").strip()
        )
    ]
    runtime.save_discovery_settings(
        {"settings": {"switches": retained + additions}}
    )
    return {
        "ok": True,
        "added_count": len(added_safe),
        "added": added_safe,
    }
