#!/usr/bin/env python3
"""Sanitize a copied Switch Vision data folder before contribution packaging."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import ipaddress
import json
import re
from pathlib import Path

TEXT_EXTENSIONS = {
    ".txt", ".log", ".json", ".yaml", ".yml", ".csv", ".conf", ".cfg",
    ".ini", ".md", ".xml", ".sh", ".env",
}
MAX_TEXT_BYTES = 64 * 1024 * 1024
MAX_PROCESSING_ISSUE_SAMPLES = 50

IPV4_RE = re.compile(r"(?<![\w.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\w.])")
MAC_RE = re.compile(
    r"(?i)(?<![0-9a-f:.-])(?:(?:[0-9a-f]{1,2}[:-]){5}[0-9a-f]{1,2}|(?:[0-9a-f]{4}\.){2}[0-9a-f]{4})(?![0-9a-f:.-])"
)

SECRET_LINE_RE = re.compile(
    r"(?im)^(?P<prefix>\s*[\"']?(?:[-\w.]*?(?:snmp_community|community|mqtt_username|mqtt_password|password|passwd|token|access_token|api_key|secret|client_secret)[-\w.]*?)[\"']?\s*[:=]\s*)(?P<value>.*)$"
)
URL_CREDENTIAL_RE = re.compile(r"(?i)(?P<scheme>\b(?:mqtt|mqtts|http|https)://)(?P<creds>[^/@\s]+@)")
CLI_SECRET_ARG_RE = re.compile(
    r"(?im)(?P<prefix>(?:\b(?:snmpwalk|snmpget|snmpgetnext|snmpbulkget|snmpbulkwalk)\b[^\r\n]*?\s-c\s+|(?:^|\s)--(?:password|passwd|token|access-token|api-key|secret|client-secret|community)\s+))(?P<quote>[\"']?)(?P<value>[^\s\"']+)(?P=quote)"
)
AUTH_HEADER_RE = re.compile(
    r"(?im)^(?P<prefix>\s*(?:authorization|proxy-authorization)\s*:\s*(?:(?:bearer|basic)\s+)?)(?P<value>\S.*)$"
)
ENTITY_LOGICAL_COMMUNITY_RE = re.compile(
    r"(?im)^(?P<prefix>.*(?:(?:ENTITY-MIB::entLogicalCommunity)|(?:\.?1\.3\.6\.1\.2\.1\.47\.1\.2\.1\.1\.4))\.\d+.*?(?:STRING:|=)\s*)(?P<value>.*)$"
)
SERIAL_WALK_RE = re.compile(
    r"(?im)^(?P<prefix>.*(?:\.?1\.3\.6\.1\.2\.1\.47\.1\.1\.1\.1\.11\.\d+).*?(?:STRING:|=)\s*)(?P<value>.*)$"
)
SERIAL_VALUE_RE = re.compile(
    r"(?im)^(?P<prefix>\s*(?:[-*]\s*)?[\"']?(?:serial|serial_number|serialnumber|serial_no|serialno|chassis_serial|chassis_serial_number)[\"']?\s*[:=]\s*)(?P<value>.*)$"
)
SYSNAME_WALK_RE = re.compile(r"(?im)^(?P<prefix>.*(?:SNMPv2-MIB::sysName\.0|\.?1\.3\.6\.1\.2\.1\.1\.5\.0).*?(?:STRING:|=)\s*)(?P<value>.*)$")
HOST_KEY_RE = re.compile(
    r"(?im)^(?P<prefix>\s*[\"']?(?:hostname|host_name|sys_name|sysname|domain|domain_name|switch_host|management_host|system_name|device_name)[\"']?\s*[:=]\s*)(?P<value>.*)$"
)
CISCO_LOCAL_HOSTNAME_RE = re.compile(
    r"(?im)^(?P<prefix>\s*Cisco\s+local\s+hostname\s*[:=]\s*)(?P<value>.*)$"
)
CISCO_LOCAL_HOSTNAME_OID_RE = re.compile(
    r"(?im)^(?P<prefix>.*\.?1\.3\.6\.1\.4\.1\.9\.2\.1\.3\.0\s*=\s*(?:STRING:\s*)?)(?P<value>.*)$"
)
HOST_LABEL_RE = re.compile(
    r"(?im)^(?P<prefix>\s*(?:[-*]\s*)?(?:host(?:name)?|system\s+name|sysname|device\s+name|domain(?:\s+name)?)\s*[:=]\s*)(?P<value>.*)$"
)
VLAN_VALUE_LINE_RE = re.compile(
    r"(?im)^(?P<prefix>.*(?:vlanName|vmVlanName|vlan_name|VLAN name).*?(?:STRING:|[:=])\s*)(?P<value>.*)$"
)
VLAN_TOKEN_RE = re.compile(r"(?i)(?<!masked-)\bVLAN(?:[-_ ]?)(?P<id>\d+)\b")
ALIAS_WALK_RE = re.compile(
    r"(?im)^(?P<prefix>.*(?:IF-MIB::ifAlias|ifAlias\.|\.?1\.3\.6\.1\.2\.1\.31\.1\.1\.1\.18\.\d+).*?(?:STRING:|=)\s*)(?P<value>.*)$"
)
ALIAS_KEY_RE = re.compile(
    r"(?im)^(?P<prefix>\s*[\"']?(?:interface_alias|if_alias|ifalias|interface_description|port_description|alias)[\"']?\s*[:=]\s*)(?P<value>.*)$"
)
HOST_JSON_RE = re.compile(r'(?i)(?P<prefix>["\'](?:hostname|host_name|sys_name|sysname|domain|domain_name|switch_host|management_host|system_name|device_name)["\']\s*:\s*)(?P<value>["\'][^"\']*["\'])')
ALIAS_JSON_RE = re.compile(r'(?i)(?P<prefix>["\'](?:interface_alias|if_alias|ifalias|interface_description|port_description|alias)["\']\s*:\s*)(?P<value>["\'][^"\']*["\'])')
UNIFI_DEVICE_ID_LINE_RE = re.compile(
    r"(?im)^(?P<prefix>\s*unifi_device_id\s*:\s*)(?P<value>[^#\r\n]+?)\s*$"
)
UNIFI_MEMBER_LINE_RE = re.compile(
    r"(?im)^(?P<prefix>\s*(?:member|selected_switch)\s*:\s*)(?P<value>unifi_[a-z0-9_-]+)\s*$"
)
UNIFI_COMMENT_NAME_RE = re.compile(
    r'(?im)(?P<prefix>^\s*#\s*UniFi\s+)["\'](?P<value>.*?)["\'](?=\s*\()'
)


def bool_arg(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def stable_number(value: str, modulo: int) -> int:
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).digest()
    return int.from_bytes(digest[:4], "big") % modulo


def masked_ip(value: str) -> str:
    return f"198.51.100.{stable_number(value, 254) + 1}"


def masked_mac(value: str) -> str:
    digest = hashlib.sha256(value.lower().encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"masked-mac-{digest}"


def masked_serial(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"masked-serial-{digest}"


def clean_scalar_value(value: str) -> str:
    return value.strip().rstrip(",").strip().strip("\"'")


def is_redacted_secret(value: str) -> bool:
    cleaned = clean_scalar_value(value)
    return not cleaned or cleaned.startswith("<REDACTED>")


def is_masked_serial(value: str) -> bool:
    cleaned = clean_scalar_value(value)
    return (
        not cleaned
        or cleaned.startswith("masked-serial-")
        or cleaned.lower() in {"n/a", "na", "unknown", "not specified", "none", "null"}
    )


def masked_unifi_id(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"masked-device-{digest}"


def masked_unifi_member(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"unifi_masked_{digest}"



def sanitize_unifi_diagnostics(
    text: str,
    counts: dict[str, int],
) -> str:
    """Allowlist privacy-safe UniFi2MQTT diagnostics fields."""
    try:
        source = json.loads(text)
    except json.JSONDecodeError:
        return "{}\n"

    if not isinstance(source, dict):
        return "{}\n"

    def safe_text(
        value: object,
        limit: int,
        pattern: str | None = None,
    ) -> str | None:
        text_value = str(value or "").strip()
        if not text_value or len(text_value) > limit:
            return None
        if any(
            ord(ch) < 32 or ord(ch) == 127
            for ch in text_value
        ):
            return None
        if pattern and not re.fullmatch(
            pattern,
            text_value,
        ):
            return None
        return text_value

    def safe_count(key: str) -> int:
        value = source.get(key)
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return max(0, min(value, 100000))
        return 0

    output: dict[str, object] = {
        "schema_version": 1,
        "product": "Switch Vision UniFi2MQTT",
        "version": safe_text(
            source.get("version"),
            32,
            r"[A-Za-z0-9_.+-]+",
        ),
        "generated_at": (
            source.get("generated_at")
            if isinstance(source.get("generated_at"), int)
            else None
        ),
        "status": safe_text(
            source.get("status"),
            32,
            r"[A-Za-z0-9_.:+-]+",
        ),
        "stage": safe_text(
            source.get("stage"),
            64,
            r"[A-Za-z0-9_.:+-]+",
        ),
        "adopted_devices": safe_count(
            "adopted_devices"
        ),
        "switching_devices": safe_count(
            "switching_devices"
        ),
        "rejected_devices": safe_count(
            "rejected_devices"
        ),
        "empty_switch_polls": safe_count(
            "empty_switch_polls"
        ),
        "device_classification": [],
    }

    error_type = safe_text(
        source.get("error_type"),
        128,
        r"[A-Za-z0-9_.:+-]+",
    )
    if error_type:
        output["error_type"] = error_type

    rows = source.get("device_classification")
    if isinstance(rows, list):
        safe_rows = []

        for raw in rows[:256]:
            if not isinstance(raw, dict):
                continue

            model = safe_text(
                raw.get("model"),
                128,
                r"[A-Za-z0-9 ._+:/()'-]+",
            ) or "Unknown"

            features = []
            raw_features = raw.get("features")

            if isinstance(raw_features, list):
                for value in raw_features[:64]:
                    feature = safe_text(
                        value,
                        64,
                        r"[A-Za-z0-9_.:+-]+",
                    )
                    if feature:
                        features.append(feature)

            reason = safe_text(
                raw.get("reason"),
                64,
                r"[A-Za-z0-9_.:+-]+",
            )

            safe_rows.append(
                {
                    "model": model,
                    "features": sorted(
                        set(features),
                        key=str.casefold,
                    ),
                    "accepted": bool(
                        raw.get("accepted")
                    ),
                    "reason": reason,
                }
            )

        output["device_classification"] = safe_rows

    counts["unifi_diagnostics_sanitized"] = (
        counts.get(
            "unifi_diagnostics_sanitized",
            0,
        )
        + 1
    )

    return json.dumps(
        output,
        indent=2,
        sort_keys=True,
    ) + "\n"


def sanitize_unifi_generated_dashboard(text: str, mask_hostnames: bool, counts: dict[str, int]) -> str:
    """Sanitize UniFi card identities/names in generated dashboard YAML."""
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not re.match(r"^\s*-\s+type:\s+custom:switch-vision-3650\s*$", line.rstrip("\r\n")):
            output.append(line)
            index += 1
            continue

        indent = len(line) - len(line.lstrip(" "))
        block = [line]
        index += 1
        while index < len(lines):
            candidate = lines[index]
            stripped = candidate.rstrip("\r\n")
            candidate_indent = len(candidate) - len(candidate.lstrip(" "))
            if re.match(r"^\s*-\s+type:\s+", stripped) and candidate_indent == indent:
                break
            block.append(candidate)
            index += 1

        block_text = "".join(block)
        if not re.search(r"(?im)^\s*data_source\s*:\s*unifi_api\s*$", block_text):
            output.extend(block)
            continue

        raw_id_match = UNIFI_DEVICE_ID_LINE_RE.search(block_text)
        raw_id = raw_id_match.group("value").strip().strip('"\'') if raw_id_match else ""
        if raw_id and not raw_id.startswith("masked-device-"):
            masked_id = masked_unifi_id(raw_id)
            masked_member = masked_unifi_member(raw_id)
            block_text, id_count = UNIFI_DEVICE_ID_LINE_RE.subn(
                lambda m: m.group("prefix") + masked_id, block_text
            )
            counts["unifi_dashboard_ids_masked"] += id_count
            block_text, member_count = UNIFI_MEMBER_LINE_RE.subn(
                lambda m: m.group("prefix") + masked_member, block_text
            )
            counts["unifi_dashboard_members_masked"] += member_count
        elif raw_id.startswith("masked-device-"):
            # Second sanitizer pass: keep already-masked IDs and only normalize
            # a remaining legacy member value. This keeps masking counts idempotent.
            suffix = raw_id.removeprefix("masked-device-")
            def masked_member_repl(match: re.Match[str]) -> str:
                current = match.group("value").strip()
                expected = f"unifi_masked_{suffix}"
                if current == expected:
                    return match.group(0)
                counts["unifi_dashboard_members_masked"] += 1
                return match.group("prefix") + expected
            block_text = UNIFI_MEMBER_LINE_RE.sub(masked_member_repl, block_text)

        if mask_hostnames:
            def title_repl(match: re.Match[str]) -> str:
                current = match.group("value").strip().strip('"\'')
                if current == "masked-switch":
                    return match.group(0)
                counts["hostnames_masked"] += 1
                counts["unifi_dashboard_names_masked"] += 1
                return match.group("prefix") + "masked-switch"

            block_text = re.sub(
                r"(?im)^(?P<prefix>\s*title\s*:\s*)(?P<value>[^#\r\n]+?)\s*$",
                title_repl,
                block_text,
            )

        output.append(block_text)

    result = "".join(output)
    if mask_hostnames:
        def comment_repl(match: re.Match[str]) -> str:
            if match.group("value") == "masked-switch":
                return match.group(0)
            counts["hostnames_masked"] += 1
            counts["unifi_dashboard_names_masked"] += 1
            return match.group("prefix") + '"masked-switch"'
        result = UNIFI_COMMENT_NAME_RE.sub(comment_repl, result)
    return result


def sanitize_unifi_snapshot(text: str, mask_hostnames: bool, counts: dict[str, int]) -> str:
    """Sanitize Switch Vision UniFi2MQTT's normalized devices.json snapshot."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(data, dict) or not isinstance(data.get("devices"), list):
        return text

    changed = False
    for device in data["devices"]:
        if not isinstance(device, dict):
            continue
        raw_id = device.get("id")
        if isinstance(raw_id, str) and raw_id and not raw_id.startswith("masked-device-"):
            device["id"] = masked_unifi_id(raw_id)
            counts["unifi_device_ids_masked"] += 1
            changed = True
        if mask_hostnames:
            raw_name = device.get("name")
            if isinstance(raw_name, str) and raw_name and raw_name != "masked-switch":
                device["name"] = "masked-switch"
                counts["hostnames_masked"] += 1
                counts["unifi_device_names_masked"] += 1
                changed = True
    return json.dumps(data, indent=2) + "\n" if changed else text


def replace_value_line(match: re.Match[str], placeholder: str) -> str:
    raw = match.group("value")
    stripped = raw.strip()
    suffix = "," if stripped.endswith(",") else ""
    stripped = stripped[:-1].rstrip() if suffix else stripped
    quote = '"' if stripped.startswith('"') else "'" if stripped.startswith("'") else ""
    replacement = f"{quote}{placeholder}{quote}" if quote else placeholder
    return match.group("prefix") + replacement + suffix


def looks_text(path: Path) -> bool:
    """Return whether a file is safe to process as text.

    Read failures intentionally propagate to the caller so they are recorded as
    incomplete privacy processing instead of being misreported as binary files.
    """
    sample = path.read_bytes()[:4096]
    if b"\x00" in sample:
        return False
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    try:
        decoded = sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    disallowed_controls = sum(
        1 for char in decoded if ord(char) < 32 and char not in {"\t", "\n", "\r"}
    )
    return disallowed_controls <= max(1, len(decoded) // 100)


def processing_issue(path: Path, root: Path, reason: str, size: int | None = None) -> dict[str, object]:
    """Create a privacy-safe issue record without exposing the original path."""
    try:
        relative = path.resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        relative = path.name
    digest = hashlib.sha256(relative.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return {
        "file_id": digest,
        "reason": reason,
        "suffix": path.suffix.lower() or "(none)",
        "size_bytes": size,
    }



def sanitize_discovery_targets_csv(text: str, counts: dict[str, int]) -> str:
    # Redact the positional SNMP community column in Discovery's targets CSV.
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error:
        return text
    changed = False
    for index, row in enumerate(rows):
        if len(row) < 4:
            continue
        field = row[3].strip()
        if index == 0 and "community" in field.lower():
            continue
        if not field or field == "<REDACTED>":
            continue
        row[3] = "<REDACTED>"
        counts["csv_community_values_removed"] += 1
        changed = True
    if not changed:
        return text
    output = io.StringIO()
    csv.writer(output, lineterminator="\n").writerows(rows)
    return output.getvalue()


def discovery_targets_csv_credentials_remaining(text: str) -> int:
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error:
        return 1
    remaining = 0
    for index, row in enumerate(rows):
        if len(row) < 4:
            continue
        field = row[3].strip()
        if index == 0 and "community" in field.lower():
            continue
        if field and field != "<REDACTED>":
            remaining += 1
    return remaining


def credential_residual_count(text: str) -> int:
    remaining = 0
    for match in SECRET_LINE_RE.finditer(text):
        if not is_redacted_secret(match.group("value")):
            remaining += 1
    for match in URL_CREDENTIAL_RE.finditer(text):
        creds = match.group("creds")[:-1]
        if not is_redacted_secret(creds):
            remaining += 1
    for match in CLI_SECRET_ARG_RE.finditer(text):
        if not is_redacted_secret(match.group("value")):
            remaining += 1
    for match in AUTH_HEADER_RE.finditer(text):
        if not is_redacted_secret(match.group("value")):
            remaining += 1
    for match in ENTITY_LOGICAL_COMMUNITY_RE.finditer(text):
        if not is_redacted_secret(match.group("value")):
            remaining += 1
    return remaining


def serial_residual_count(text: str) -> int:
    remaining = 0
    for regex in (SERIAL_WALK_RE, SERIAL_VALUE_RE):
        for match in regex.finditer(text):
            if not is_masked_serial(match.group("value")):
                remaining += 1
    return remaining


def sanitize_text(text: str, options: dict[str, bool], counts: dict[str, int]) -> str:
    def secret_repl(match: re.Match[str]) -> str:
        if is_redacted_secret(match.group("value")):
            return match.group(0)
        counts["secrets_removed"] += 1
        suffix = "," if match.group("value").rstrip().endswith(",") else ""
        return match.group("prefix") + '"<REDACTED>"' + suffix

    text = SECRET_LINE_RE.sub(secret_repl, text)

    def url_repl(match: re.Match[str]) -> str:
        creds = match.group("creds")[:-1]
        if is_redacted_secret(creds):
            return match.group(0)
        counts["url_credentials_removed"] += 1
        return match.group("scheme") + "<REDACTED>@"

    text = URL_CREDENTIAL_RE.sub(url_repl, text)

    def cli_secret_repl(match: re.Match[str]) -> str:
        if is_redacted_secret(match.group("value")):
            return match.group(0)
        counts["cli_credentials_removed"] += 1
        return match.group("prefix") + "<REDACTED>"

    text = CLI_SECRET_ARG_RE.sub(cli_secret_repl, text)

    def auth_header_repl(match: re.Match[str]) -> str:
        if is_redacted_secret(match.group("value")):
            return match.group(0)
        counts["authorization_headers_removed"] += 1
        return match.group("prefix") + "<REDACTED>"

    text = AUTH_HEADER_RE.sub(auth_header_repl, text)

    def entity_logical_community_repl(match: re.Match[str]) -> str:
        if is_redacted_secret(match.group("value")):
            return match.group(0)
        counts["entity_logical_communities_removed"] += 1
        return replace_value_line(match, "<REDACTED>")

    text = ENTITY_LOGICAL_COMMUNITY_RE.sub(entity_logical_community_repl, text)

    def serial_repl(match: re.Match[str]) -> str:
        raw = clean_scalar_value(match.group("value"))
        if is_masked_serial(raw):
            return match.group(0)
        counts["serial_numbers_masked"] += 1
        return replace_value_line(match, masked_serial(raw))

    text = SERIAL_WALK_RE.sub(serial_repl, text)
    text = SERIAL_VALUE_RE.sub(serial_repl, text)

    if options["mask_management_ips"]:
        def ip_repl(match: re.Match[str]) -> str:
            counts["ip_addresses_masked"] += 1
            return masked_ip(match.group(0))
        text = IPV4_RE.sub(ip_repl, text)

    if options["mask_mac_addresses"]:
        def mac_repl(match: re.Match[str]) -> str:
            counts["mac_addresses_masked"] += 1
            return masked_mac(match.group(0))
        text = MAC_RE.sub(mac_repl, text)

    if options["mask_hostnames"]:
        def host_repl(match: re.Match[str]) -> str:
            counts["hostnames_masked"] += 1
            return replace_value_line(match, "masked-switch")
        text = SYSNAME_WALK_RE.sub(host_repl, text)
        text = HOST_KEY_RE.sub(host_repl, text)
        text = HOST_LABEL_RE.sub(host_repl, text)
        text = CISCO_LOCAL_HOSTNAME_RE.sub(host_repl, text)
        text = CISCO_LOCAL_HOSTNAME_OID_RE.sub(host_repl, text)
        text = HOST_JSON_RE.sub(host_repl, text)

    if options["mask_interface_descriptions"]:
        def alias_repl(match: re.Match[str]) -> str:
            value = match.group("value").strip().rstrip(",").strip('"\'')
            if not value or value in {"masked-interface-description", "<REDACTED>"}:
                return match.group(0)
            counts["interface_descriptions_masked"] += 1
            return replace_value_line(match, "masked-interface-description")
        text = ALIAS_WALK_RE.sub(alias_repl, text)
        text = ALIAS_KEY_RE.sub(alias_repl, text)
        text = ALIAS_JSON_RE.sub(alias_repl, text)

    if options["mask_vlan_names"]:
        def vlan_value_repl(match: re.Match[str]) -> str:
            counts["vlan_names_masked"] += 1
            return replace_value_line(match, "masked-vlan")
        text = VLAN_VALUE_LINE_RE.sub(vlan_value_repl, text)

        def vlan_token_repl(match: re.Match[str]) -> str:
            counts["vlan_names_masked"] += 1
            return f"masked-vlan-{match.group('id')}"
        text = VLAN_TOKEN_RE.sub(vlan_token_repl, text)

    return text


def residual_audit(root: Path, options: dict[str, bool]) -> dict[str, int | None]:
    findings = {
        "credential_values_remaining": 0,
        "serial_values_remaining": 0,
        "private_ipv4_remaining": 0,
        "unmasked_mac_remaining": 0,
        "hostname_fields_remaining": 0,
        "unifi_device_ids_remaining": 0,
        "unifi_device_names_remaining": 0,
        "unifi_dashboard_ids_remaining": 0,
        "unifi_dashboard_names_remaining": 0,
        "interface_alias_values_remaining": 0,
        "vlan_labels_remaining": 0,
    }
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            if path.stat().st_size > MAX_TEXT_BYTES or not looks_text(path):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeError):
            continue
        try:
            relative_parts = path.resolve().relative_to(root).parts
        except (OSError, ValueError):
            relative_parts = ()

        findings["credential_values_remaining"] += credential_residual_count(text)
        findings["serial_values_remaining"] += serial_residual_count(text)
        if path.name == "discovery-targets.csv":
            findings["credential_values_remaining"] += discovery_targets_csv_credentials_remaining(text)

        if "unifi" in relative_parts and path.name == "devices.json":
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict) and isinstance(payload.get("devices"), list):
                for device in payload["devices"]:
                    if not isinstance(device, dict):
                        continue
                    raw_id = device.get("id")
                    if isinstance(raw_id, str) and raw_id and not raw_id.startswith("masked-device-"):
                        findings["unifi_device_ids_remaining"] += 1
                    raw_name = device.get("name")
                    if options["mask_hostnames"] and isinstance(raw_name, str) and raw_name and raw_name != "masked-switch":
                        findings["unifi_device_names_remaining"] += 1
        if path.name == "generated-dashboard-card.yaml":
            for match in UNIFI_DEVICE_ID_LINE_RE.finditer(text):
                value = match.group("value").strip().strip('"\'')
                if value and not value.startswith("masked-device-"):
                    findings["unifi_dashboard_ids_remaining"] += 1
            for match in UNIFI_MEMBER_LINE_RE.finditer(text):
                value = match.group("value").strip()
                if value.startswith("unifi_") and not value.startswith("unifi_masked_"):
                    findings["unifi_dashboard_ids_remaining"] += 1
            if options["mask_hostnames"]:
                for match in UNIFI_COMMENT_NAME_RE.finditer(text):
                    if match.group("value") != "masked-switch":
                        findings["unifi_dashboard_names_remaining"] += 1
                for block in re.split(r"(?=^\s*-\s+type:\s+custom:switch-vision-3650\s*$)", text, flags=re.M):
                    if not re.search(r"(?im)^\s*data_source\s*:\s*unifi_api\s*$", block):
                        continue
                    title = re.search(r"(?im)^\s*title\s*:\s*(?P<value>[^#\r\n]+?)\s*$", block)
                    if title and title.group("value").strip().strip('"\'') != "masked-switch":
                        findings["unifi_dashboard_names_remaining"] += 1

        if options["mask_management_ips"]:
            for value in IPV4_RE.findall(text):
                try:
                    address = ipaddress.ip_address(value)
                    if address.is_private and address not in ipaddress.ip_network("198.51.100.0/24"):
                        findings["private_ipv4_remaining"] += 1
                except ValueError:
                    pass
        if options["mask_mac_addresses"]:
            findings["unmasked_mac_remaining"] += len(MAC_RE.findall(text))
        if options["mask_hostnames"]:
            for regex in (SYSNAME_WALK_RE, HOST_KEY_RE, HOST_LABEL_RE, CISCO_LOCAL_HOSTNAME_RE, CISCO_LOCAL_HOSTNAME_OID_RE, HOST_JSON_RE):
                for match in regex.finditer(text):
                    if "masked-switch" not in match.group("value"):
                        findings["hostname_fields_remaining"] += 1
        for regex in (ALIAS_WALK_RE, ALIAS_KEY_RE, ALIAS_JSON_RE):
            for match in regex.finditer(text):
                value = match.group("value")
                if value.strip() and "masked-interface-description" not in value:
                    findings["interface_alias_values_remaining"] += 1
        findings["vlan_labels_remaining"] += len(VLAN_TOKEN_RE.findall(text))
        for match in VLAN_VALUE_LINE_RE.finditer(text):
            if "masked-vlan" not in match.group("value"):
                findings["vlan_labels_remaining"] += 1
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--mask-management-ips", default="true")
    parser.add_argument("--mask-mac-addresses", default="true")
    parser.add_argument("--mask-hostnames", default="true")
    parser.add_argument("--mask-vlan-names", default="false")
    parser.add_argument("--mask-interface-descriptions", default="false")
    args = parser.parse_args()

    options = {
        "mask_management_ips": bool_arg(args.mask_management_ips),
        "mask_mac_addresses": bool_arg(args.mask_mac_addresses),
        "mask_hostnames": bool_arg(args.mask_hostnames),
        "mask_vlan_names": bool_arg(args.mask_vlan_names),
        "mask_interface_descriptions": bool_arg(args.mask_interface_descriptions),
    }
    counts = {
        "secrets_removed": 0,
        "url_credentials_removed": 0,
        "cli_credentials_removed": 0,
        "authorization_headers_removed": 0,
        "entity_logical_communities_removed": 0,
        "csv_community_values_removed": 0,
        "serial_numbers_masked": 0,
        "ip_addresses_masked": 0,
        "mac_addresses_masked": 0,
        "hostnames_masked": 0,
        "unifi_device_ids_masked": 0,
        "unifi_device_names_masked": 0,
        "unifi_dashboard_ids_masked": 0,
        "unifi_dashboard_members_masked": 0,
        "unifi_dashboard_names_masked": 0,
        "vlan_names_masked": 0,
        "interface_descriptions_masked": 0,
        "files_scanned": 0,
        "files_changed": 0,
        "binary_files_skipped": 0,
        "oversized_files_skipped": 0,
        "read_errors": 0,
        "write_errors": 0,
        "symlinks_skipped": 0,
        "special_files_skipped": 0,
        "files_excluded": 0,
    }

    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"Sanitization root not found: {root}")

    issue_count = 0
    issue_samples: list[dict[str, object]] = []

    def add_issue(path: Path, reason: str, size: int | None = None) -> None:
        nonlocal issue_count
        issue_count += 1
        if len(issue_samples) < MAX_PROCESSING_ISSUE_SAMPLES:
            issue_samples.append(processing_issue(path, root, reason, size))

    def exclude_file(path: Path, reason: str, size: int | None = None) -> None:
        """Remove an uninspected file from the temporary bundle copy."""
        add_issue(path, reason, size)
        try:
            path.unlink()
            counts["files_excluded"] += 1
        except OSError:
            counts["write_errors"] += 1
            add_issue(path, "exclusion_failed", size)

    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            counts["symlinks_skipped"] += 1
            try:
                size = path.lstat().st_size
            except OSError:
                size = None
            exclude_file(path, "symlink_excluded", size)
            continue
        if path.is_dir():
            continue
        if not path.is_file():
            counts["special_files_skipped"] += 1
            exclude_file(path, "special_file_excluded")
            continue
        try:
            size = path.stat().st_size
        except OSError:
            counts["read_errors"] += 1
            exclude_file(path, "stat_error_excluded")
            continue
        if size > MAX_TEXT_BYTES:
            counts["oversized_files_skipped"] += 1
            exclude_file(path, "oversized_file_excluded", size)
            continue
        try:
            is_text = looks_text(path)
        except OSError:
            counts["read_errors"] += 1
            exclude_file(path, "read_error_excluded", size)
            continue
        if not is_text:
            counts["binary_files_skipped"] += 1
            exclude_file(path, "unsupported_binary_excluded", size)
            continue
        try:
            original = path.read_text(encoding="utf-8", errors="surrogateescape")
        except (OSError, UnicodeError):
            counts["read_errors"] += 1
            exclude_file(path, "read_error_excluded", size)
            continue
        counts["files_scanned"] += 1
        updated = sanitize_text(original, options, counts)
        if path.name == "discovery-targets.csv":
            updated = sanitize_discovery_targets_csv(updated, counts)
        try:
            relative_parts = path.resolve().relative_to(root).parts
        except (OSError, ValueError):
            relative_parts = ()
        if "unifi" in relative_parts and path.name == "devices.json":
            updated = sanitize_unifi_snapshot(updated, options["mask_hostnames"], counts)
        if "unifi" in relative_parts and path.name == "diagnostics.json":
            updated = sanitize_unifi_diagnostics(updated, counts)
        if path.name == "generated-dashboard-card.yaml":
            updated = sanitize_unifi_generated_dashboard(updated, options["mask_hostnames"], counts)
        if updated != original:
            try:
                path.write_text(updated, encoding="utf-8", errors="surrogateescape", newline="\n")
                counts["files_changed"] += 1
            except (OSError, UnicodeError):
                counts["write_errors"] += 1
                exclude_file(path, "write_error_excluded", size)

    raw_residuals = residual_audit(root, options)
    residuals = {
        "credential_values_remaining": raw_residuals["credential_values_remaining"],
        "serial_values_remaining": raw_residuals["serial_values_remaining"],
        "private_ipv4_remaining": raw_residuals["private_ipv4_remaining"] if options["mask_management_ips"] else None,
        "unmasked_mac_remaining": raw_residuals["unmasked_mac_remaining"] if options["mask_mac_addresses"] else None,
        "hostname_fields_remaining": (raw_residuals["hostname_fields_remaining"] + raw_residuals["unifi_device_names_remaining"]) if options["mask_hostnames"] else None,
        "unifi_device_ids_remaining": raw_residuals["unifi_device_ids_remaining"],
        "unifi_device_names_remaining": raw_residuals["unifi_device_names_remaining"] if options["mask_hostnames"] else None,
        "unifi_dashboard_ids_remaining": raw_residuals["unifi_dashboard_ids_remaining"],
        "unifi_dashboard_names_remaining": raw_residuals["unifi_dashboard_names_remaining"] if options["mask_hostnames"] else None,
        "interface_alias_values_remaining": raw_residuals["interface_alias_values_remaining"] if options["mask_interface_descriptions"] else None,
        "vlan_labels_remaining": raw_residuals["vlan_labels_remaining"] if options["mask_vlan_names"] else None,
    }
    audit_categories = {
        "credentials": {"enforced": True, "remaining": residuals["credential_values_remaining"]},
        "serial_numbers": {"enforced": True, "remaining": residuals["serial_values_remaining"]},
        "private_ipv4": {"enforced": options["mask_management_ips"], "remaining": residuals["private_ipv4_remaining"]},
        "mac_addresses": {"enforced": options["mask_mac_addresses"], "remaining": residuals["unmasked_mac_remaining"]},
        "hostnames": {"enforced": options["mask_hostnames"], "remaining": residuals["hostname_fields_remaining"]},
        "unifi_device_ids": {"enforced": True, "remaining": residuals["unifi_device_ids_remaining"]},
        "unifi_dashboard_ids": {"enforced": True, "remaining": residuals["unifi_dashboard_ids_remaining"]},
        "unifi_dashboard_names": {"enforced": options["mask_hostnames"], "remaining": residuals["unifi_dashboard_names_remaining"]},
        "interface_aliases": {"enforced": options["mask_interface_descriptions"], "remaining": residuals["interface_alias_values_remaining"]},
        "vlan_labels": {"enforced": options["mask_vlan_names"], "remaining": residuals["vlan_labels_remaining"]},
    }
    disabled_category_warnings = {
        "interface_aliases": (
            not options["mask_interface_descriptions"]
            and raw_residuals["interface_alias_values_remaining"] > 0
        ),
        "vlan_labels": (
            not options["mask_vlan_names"]
            and raw_residuals["vlan_labels_remaining"] > 0
        ),
    }
    processing_complete = issue_count == 0
    report = {
        "sanitization_version": 13,
        "secrets_always_removed": True,
        "serial_numbers_always_masked": True,
        "options": options,
        "counts": counts,
        "processing_complete": processing_complete,
        "processing_issue_count": issue_count,
        "processing_issues": issue_samples,
        "processing_issues_truncated": max(0, issue_count - len(issue_samples)),
        "residual_audit": residuals,
        "audit_categories": audit_categories,
        "enabled_category_leaks_found": any(
            item["enforced"] and bool(item["remaining"]) for item in audit_categories.values()
        ),
        "observed_values": {
            "interface_aliases": raw_residuals["interface_alias_values_remaining"],
            "vlan_labels": raw_residuals["vlan_labels_remaining"],
        },
        "disabled_category_warnings": disabled_category_warnings,
        "disabled_category_warnings_found": any(disabled_category_warnings.values()),
        "warning": (
            "Automated masking reduces common privacy risks but cannot guarantee that all "
            "identifying information was removed. Review the archive before sharing."
        ),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
