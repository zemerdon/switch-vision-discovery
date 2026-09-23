#!/usr/bin/env python3
"""Read-only network candidate discovery for Switch Vision Hub.

AutoDiscover deliberately does not guess SNMP credentials. It probes only with
an explicitly supplied one-time SNMPv2c community and/or credentials already
saved on real configured switch rows. Exact hardware identification remains the
normal Discovery pipeline's responsibility after a candidate is saved.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import ipaddress
import re
import subprocess
from typing import Any, Callable

from registry_lookup import lookup as registry_lookup

MAX_SCAN_HOSTS = 1024
MAX_SCAN_TOTAL_HOSTS = 4096
MAX_SCAN_SUBNETS = 32
DEFAULT_WORKERS = 64
SYS_DESCR_OID = ".1.3.6.1.2.1.1.1.0"
SYS_OBJECT_ID_OID = ".1.3.6.1.2.1.1.2.0"
SYS_NAME_OID = ".1.3.6.1.2.1.1.5.0"
ENTITY_MODEL_OID = ".1.3.6.1.2.1.47.1.1.1.1.13"


def validate_subnet(value: Any, *, max_hosts: int = MAX_SCAN_HOSTS) -> ipaddress.IPv4Network:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Enter an IPv4 network in CIDR form, for example 192.168.1.0/24.")
    try:
        network = ipaddress.ip_network(text, strict=False)
    except ValueError as exc:
        raise ValueError("AutoDiscover network must be a valid IPv4 CIDR.") from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise ValueError("AutoDiscover currently supports IPv4 networks only.")
    if network.network_address.is_multicast or network.network_address.is_unspecified:
        raise ValueError("AutoDiscover requires a unicast IPv4 network.")
    if network.prefixlen >= 31:
        host_count = network.num_addresses
    else:
        host_count = max(0, network.num_addresses - 2)
    if host_count > max_hosts:
        raise ValueError(
            f"AutoDiscover is limited to {max_hosts} usable addresses per subnet. "
            "Use a smaller subnet."
        )
    return network


def validate_subnets(
    values: Any,
    *,
    max_hosts_per_subnet: int = MAX_SCAN_HOSTS,
    max_total_hosts: int = MAX_SCAN_TOTAL_HOSTS,
    max_subnets: int = MAX_SCAN_SUBNETS,
) -> tuple[list[ipaddress.IPv4Network], dict[str, list[str]], int]:
    """Validate CIDRs and return canonical networks plus a deduplicated host map."""
    raw_values = [values] if isinstance(values, str) else values
    if not isinstance(raw_values, list) or not raw_values:
        raise ValueError("AutoDiscover requires at least one IPv4 network.")
    if len(raw_values) > max_subnets:
        raise ValueError(f"AutoDiscover supports at most {max_subnets} subnets per scan.")

    networks: list[ipaddress.IPv4Network] = []
    seen_networks: set[str] = set()
    for raw in raw_values:
        network = validate_subnet(raw, max_hosts=max_hosts_per_subnet)
        canonical = str(network)
        if canonical in seen_networks:
            continue
        seen_networks.add(canonical)
        networks.append(network)
    if not networks:
        raise ValueError("AutoDiscover requires at least one IPv4 network.")

    host_networks: dict[str, list[str]] = {}
    raw_host_count = 0
    for network in networks:
        network_text = str(network)
        for address in network.hosts():
            raw_host_count += 1
            host = str(address)
            host_networks.setdefault(host, []).append(network_text)
            if len(host_networks) > max_total_hosts:
                raise ValueError(
                    f"AutoDiscover is limited to {max_total_hosts} unique addresses per scan. "
                    "Use fewer or smaller subnets."
                )
    return networks, host_networks, raw_host_count


def credential_specs(
    options: dict[str, Any],
    *,
    use_saved: bool = True,
    manual_community: str = "",
) -> list[dict[str, str]]:
    """Return private probe credentials with non-secret references.

    Blank placeholder rows are intentionally ignored so the add-on's factory
    placeholder cannot become an implicit/default credential guess.
    """
    specs: list[dict[str, str]] = []
    seen: set[str] = set()
    if use_saved:
        rows = options.get("switches") if isinstance(options, dict) else []
        if not isinstance(rows, list):
            rows = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("switch_name") or "").strip()
            host = str(raw.get("switch_host") or "").strip()
            community = str(raw.get("snmp_community") or "").strip()
            if not (name and host and community) or community in seen:
                continue
            seen.add(community)
            specs.append(
                {
                    "ref": f"saved:{name}",
                    "label": f"Saved from {name}",
                    "community": community,
                }
            )
    manual = str(manual_community or "").strip()
    if manual and manual not in seen:
        specs.append({"ref": "manual", "label": "One-time community", "community": manual})
    return specs


def resolve_credential(
    options: dict[str, Any],
    credential_ref: Any,
    *,
    manual_community: str = "",
) -> str:
    ref = str(credential_ref or "").strip()
    if ref == "manual":
        value = str(manual_community or "").strip()
        if not value:
            raise ValueError("The one-time SNMP community is no longer available.")
        if len(value) > 256:
            raise ValueError("SNMP community is too long.")
        return value
    if not ref.startswith("saved:"):
        raise ValueError("AutoDiscover credential reference is invalid.")
    wanted = ref.removeprefix("saved:")
    rows = options.get("switches") if isinstance(options, dict) else []
    if not isinstance(rows, list):
        rows = []
    matches = [
        str(row.get("snmp_community") or "").strip()
        for row in rows
        if isinstance(row, dict)
        and str(row.get("switch_name") or "").strip() == wanted
        and str(row.get("switch_host") or "").strip()
        and str(row.get("snmp_community") or "").strip()
    ]
    if len(matches) != 1:
        raise ValueError("The saved AutoDiscover credential could not be uniquely resolved.")
    return matches[0]


def _clean_snmp_value(value: str) -> str:
    text = str(value or "").strip()
    for prefix in ("STRING: ", "OID: ", "INTEGER: "):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1]
    return text.strip()


def _infer_vendor(sys_descr: str) -> str:
    lowered = str(sys_descr or "").casefold()
    for needle, vendor in (
        ("cisco", "Cisco"),
        ("juniper", "Juniper"),
        ("huawei", "Huawei"),
        ("dell", "Dell"),
        ("procurve", "HPE"),
        ("hewlett", "HPE"),
        ("aruba", "HPE"),
        ("zyxel", "Zyxel"),
        ("mikrotik", "MikroTik"),
        ("routeros", "MikroTik"),
        ("ubiquiti", "Ubiquiti"),
        ("unifi", "Ubiquiti"),
    ):
        if needle in lowered:
            return vendor
    return ""


def _runner_call(
    runner: Callable[..., subprocess.CompletedProcess[str]],
    command: list[str],
    *,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return runner(
        command,
        text=True,
        capture_output=True,
        timeout=max(2.0, timeout + 1.0),
        check=False,
    )


def probe_host(
    host: str,
    credential: dict[str, str],
    *,
    registry_data: dict[str, Any] | None = None,
    timeout: float = 1.0,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any] | None:
    """Probe one IPv4 host with one already-authorized SNMPv2c credential."""
    community = str(credential.get("community") or "")
    if not community:
        return None
    get_command = [
        "snmpget",
        "-On",
        "-Oqv",
        "-v2c",
        "-c",
        community,
        "-t",
        str(max(0.2, float(timeout))),
        "-r",
        "0",
        host,
        SYS_DESCR_OID,
        SYS_OBJECT_ID_OID,
        SYS_NAME_OID,
    ]
    try:
        proc = _runner_call(runner, get_command, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    if proc.returncode != 0:
        return None
    lines = [_clean_snmp_value(line) for line in (proc.stdout or "").splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return None
    sys_descr = lines[0] if len(lines) >= 1 else ""
    sys_object_id = lines[1] if len(lines) >= 2 else ""
    sys_name = lines[2] if len(lines) >= 3 else ""

    model_values: list[str] = []
    walk_command = [
        "snmpwalk",
        "-On",
        "-Oqv",
        "-v2c",
        "-c",
        community,
        "-t",
        str(max(0.2, float(timeout))),
        "-r",
        "0",
        host,
        ENTITY_MODEL_OID,
    ]
    try:
        model_proc = _runner_call(runner, walk_command, timeout=timeout)
        if model_proc.returncode == 0:
            for line in (model_proc.stdout or "").splitlines():
                value = _clean_snmp_value(line)
                if value and value.casefold() not in {"unknown", "n/a", "not available", "none"}:
                    model_values.append(value)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass

    registry = registry_data if isinstance(registry_data, dict) else {"devices": []}
    match = None
    model_hint = ""
    for candidate in model_values:
        found = registry_lookup(registry, candidate)
        if found:
            match = found
            model_hint = str(found.get("model") or candidate)
            break
    if match is None and sys_descr:
        found = registry_lookup(registry, sys_descr)
        if found:
            match = found
            model_hint = str(found.get("model") or "")
    if not model_hint and model_values:
        model_hint = model_values[0][:160]

    result = {
        "host": host,
        "source": "SNMP",
        "credential_ref": str(credential.get("ref") or ""),
        "credential_label": str(credential.get("label") or ""),
        "sys_name": sys_name[:255],
        "sys_descr": sys_descr[:500],
        "sys_object_id": sys_object_id[:255],
        "model": str(match.get("model") or "") if match else "",
        "model_hint": model_hint,
        "vendor": str(match.get("vendor") or "") if match else _infer_vendor(sys_descr),
        "registry_match": bool(match),
        "registry_status": str(match.get("status") or "detected") if match else "detected",
        "dashboard_support": bool(match.get("dashboard_support")) if match else False,
        "addable": True,
        "ready_to_add": bool(match and match.get("dashboard_support")),
        "configured": False,
        "already_managed": False,
    }
    return result


def _probe_with_credentials(
    host: str,
    credentials: list[dict[str, str]],
    *,
    registry_data: dict[str, Any],
    timeout: float,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> dict[str, Any] | None:
    for credential in credentials:
        result = probe_host(
            host,
            credential,
            registry_data=registry_data,
            timeout=timeout,
            runner=runner,
        )
        if result is not None:
            return result
    return None


def _unifi_candidates(
    snapshot: Any,
    *,
    registry_data: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = snapshot.get("devices") if isinstance(snapshot, dict) else []
    if not isinstance(rows, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        device_id = str(raw.get("id") or "").strip()
        if not device_id:
            continue
        model = str(raw.get("model") or "").strip()
        match = registry_lookup(registry_data, model) if model else None
        result.append(
            {
                "host": str(raw.get("ip_address") or "").strip(),
                "source": "UniFi API",
                "unifi_device_id": device_id,
                "sys_name": str(raw.get("name") or "").strip()[:255],
                "sys_descr": "",
                "sys_object_id": "",
                "model": str(match.get("model") or model) if match else model,
                "model_hint": model,
                "vendor": str(match.get("vendor") or "Ubiquiti") if match else "Ubiquiti",
                "registry_match": bool(match),
                "registry_status": str(match.get("status") or "detected") if match else "detected",
                "dashboard_support": bool(match.get("dashboard_support")) if match else False,
                "addable": False,
                "ready_to_add": False,
                "configured": True,
                "already_managed": True,
                "online": str(raw.get("state") or "").upper() == "ONLINE",
            }
        )
    return result


def _identity_base(candidate: dict[str, Any]) -> str:
    sys_name = str(candidate.get("sys_name") or "").strip()
    if sys_name:
        base = re.sub(r"[^A-Za-z0-9_. -]+", "-", sys_name).strip(" .-_")
        if base and base[0].isalnum():
            return base[:64]
    host = str(candidate.get("host") or "").strip()
    try:
        ip = ipaddress.ip_address(host)
        if isinstance(ip, ipaddress.IPv4Address):
            return f"SW-{str(ip).split('.')[-1]}"
    except ValueError:
        pass
    return "Switch"


def suggest_switch_name(candidate: dict[str, Any], existing_names: set[str]) -> str:
    base = _identity_base(candidate)
    used = {str(value).casefold() for value in existing_names}
    selected = base
    suffix = 2
    while selected.casefold() in used:
        tail = f"-{suffix}"
        selected = f"{base[: max(1, 64 - len(tail))]}{tail}"
        suffix += 1
    return selected


def sensor_prefix_for_name(name: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", str(name or "").strip().replace(".", "_"))
    text = re.sub(r"_+", "_", text).strip("_-")
    if not text:
        text = "switch"
    return text[:64]


def scan(
    subnets: Any,
    *,
    options: dict[str, Any],
    manual_community: str = "",
    use_saved: bool = True,
    registry_data: dict[str, Any] | None = None,
    unifi_snapshot: Any = None,
    timeout: float = 1.0,
    workers: int = DEFAULT_WORKERS,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    networks, host_networks, raw_host_count = validate_subnets(subnets)
    network_texts = [str(network) for network in networks]
    registry = registry_data if isinstance(registry_data, dict) else {"devices": []}
    credentials = credential_specs(
        options,
        use_saved=use_saved,
        manual_community=manual_community,
    )
    configured_hosts = {
        str(row.get("switch_host") or "").strip()
        for row in (options.get("switches") if isinstance(options.get("switches"), list) else [])
        if isinstance(row, dict) and str(row.get("switch_host") or "").strip()
    }
    existing_names = {
        str(row.get("switch_name") or "").strip()
        for row in (options.get("switches") if isinstance(options.get("switches"), list) else [])
        if isinstance(row, dict) and str(row.get("switch_name") or "").strip()
    }

    snmp_results: list[dict[str, Any]] = []
    hosts = list(host_networks)
    if credentials and hosts:
        max_workers = max(1, min(int(workers), DEFAULT_WORKERS, len(hosts)))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="sv-autodiscover") as pool:
            futures = {
                pool.submit(
                    _probe_with_credentials,
                    host,
                    credentials,
                    registry_data=registry,
                    timeout=timeout,
                    runner=runner,
                ): host
                for host in hosts
            }
            for future in as_completed(futures):
                try:
                    candidate = future.result()
                except Exception:
                    candidate = None
                if candidate is None:
                    continue
                host = str(candidate.get("host") or "")
                memberships = list(host_networks.get(host, []))
                candidate["networks"] = memberships
                candidate["network"] = memberships[0] if memberships else ""
                candidate["configured"] = host in configured_hosts
                candidate["addable"] = not candidate["configured"]
                candidate["ready_to_add"] = bool(
                    candidate["addable"]
                    and candidate.get("registry_match")
                    and candidate.get("dashboard_support")
                )
                candidate["suggested_switch_name"] = suggest_switch_name(candidate, existing_names)
                existing_names.add(candidate["suggested_switch_name"])
                candidate["suggested_display_name"] = (
                    str(candidate.get("sys_name") or "").strip()
                    or str(candidate.get("model") or candidate.get("model_hint") or "").strip()
                    or host
                )[:120]
                snmp_results.append(candidate)

    by_host = {str(item.get("host") or ""): item for item in snmp_results if item.get("host")}
    results = list(snmp_results)
    for item in _unifi_candidates(unifi_snapshot, registry_data=registry):
        host = str(item.get("host") or "")
        memberships = list(host_networks.get(host, []))
        item["networks"] = memberships
        item["network"] = memberships[0] if memberships else ""
        existing = by_host.get(host) if host else None
        if existing is not None:
            existing["source"] = "SNMP + UniFi API"
            existing["unifi_device_id"] = item.get("unifi_device_id")
            existing["already_managed"] = True
            existing["configured"] = True
            existing["addable"] = False
            existing["ready_to_add"] = False
            existing["online"] = item.get("online")
            if not existing.get("model") and item.get("model"):
                for key in ("model", "model_hint", "vendor", "registry_match", "registry_status", "dashboard_support"):
                    existing[key] = item.get(key)
            continue
        results.append(item)

    def sort_key(item: dict[str, Any]) -> tuple[int, int]:
        host = str(item.get("host") or "")
        try:
            return (0, int(ipaddress.ip_address(host)))
        except ValueError:
            return (1, 0)

    results.sort(key=sort_key)
    return {
        "network": network_texts[0] if len(network_texts) == 1 else "",
        "networks": network_texts,
        "network_count": len(network_texts),
        "network_hosts": len(hosts),
        "raw_network_hosts": raw_host_count,
        "overlap_deduplicated_hosts": max(0, raw_host_count - len(hosts)),
        "scanned_hosts": len(hosts) if credentials else 0,
        "snmp_probe_hosts": len(hosts) if credentials else 0,
        "credential_count": len(credentials),
        "saved_credential_count": len([item for item in credentials if item.get("ref", "").startswith("saved:")]),
        "manual_credential_used": any(item.get("ref") == "manual" for item in credentials),
        "snmp_version": "2c",
        "max_scan_hosts": MAX_SCAN_HOSTS,
        "max_total_hosts": MAX_SCAN_TOTAL_HOSTS,
        "max_subnets": MAX_SCAN_SUBNETS,
        "devices": results,
        "snmp_devices": sum(1 for item in results if "SNMP" in str(item.get("source") or "")),
        "unifi_devices": sum(1 for item in results if "UniFi API" in str(item.get("source") or "")),
        "note": (
            "AutoDiscover probes only with SNMP communities you supplied or already saved, "
            "plus the current UniFi API inventory. It never guesses communities."
        ),
    }
