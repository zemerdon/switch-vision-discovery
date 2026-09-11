#!/usr/bin/env python3
"""Production entrypoint for the Switch Vision physical-device contract.

The legacy discovery_job.sh remains the proven polling/YAML engine during the
strangler migration. This entrypoint keeps live collection untouched, resolves
stored walks into immutable compatibility copies, then runs the legacy parser
and generator against those copies.

Original SNMP evidence is never edited. Exact registered topology conflicts fail
closed instead of silently changing the dashboard geometry.
"""
from __future__ import annotations

import copy
import csv
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

LEGACY = Path(os.environ.get("SWITCH_VISION_LEGACY_DISCOVERY_SCRIPT", "/discovery_job.sh"))
PREPARE = Path(os.environ.get("SWITCH_VISION_PHYSICAL_PREPARE", "/physical_contract_prepare.sh"))
REGISTRY = Path(os.environ.get("SWITCH_VISION_DEVICE_REGISTRY", "/opt/switch-vision/devices/supported_devices.json"))
DEFAULT_OPTIONS = Path(os.environ.get("SWITCH_VISION_OPTIONS_FILE", "/data/options.json"))
DEFAULT_CAPABILITIES = Path(os.environ.get("SWITCH_VISION_CAPABILITIES_DIR", "/share/switch_vision/capabilities"))
DEFAULT_WALK_ROOT = Path("/share/switch_vision/snmpwalks")
CURRENT_RUN_SEPARATOR = "\x1c"


class DegradedDiscoveryError(RuntimeError):
    """Useful evidence exists, but downstream generation cannot be trusted."""


def _fallback_contract_usable(contract: dict[str, Any]) -> bool:
    """Return True only for observed, unregistered physical topology.

    Fallback display is allowed to reuse observed physical ports, never to infer
    missing ports or override an exact registered topology conflict.
    """
    if str(contract.get("status") or "") != "unregistered":
        return False
    observed = contract.get("observed") if isinstance(contract.get("observed"), dict) else {}
    ports = contract.get("ports") if isinstance(contract.get("ports"), list) else []
    try:
        physical = int(observed.get("physical") or 0)
    except (TypeError, ValueError):
        physical = 0
    return physical > 0 and len(ports) == physical


def _contract_usable_for_display(contract: dict[str, Any]) -> bool:
    return str(contract.get("status") or "") == "resolved" or _fallback_contract_usable(contract)


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on", "enabled", "enable"}
    if value is None:
        return default
    return bool(value)


def _safe(value: str) -> str:
    text = re.sub(r"\s+", "_", str(value or "").strip())
    text = re.sub(r"[^A-Za-z0-9._-]", "_", text)
    text = re.sub(r"_+", "_", text).strip("_ .-")
    return text or "switch"


def _read_options(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to read Discovery options snapshot: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Discovery options snapshot is not a JSON object.")
    return data


def _write_options(path: Path, options: dict[str, Any]) -> None:
    path.write_text(json.dumps(options, indent=2) + "\n", encoding="utf-8")


def _stream_legacy(
    options_path: Path,
    *,
    capabilities_dir: Path,
    env_overrides: dict[str, str] | None = None,
) -> int:
    env = os.environ.copy()
    env["SWITCH_VISION_OPTIONS_FILE"] = str(options_path)
    env["SWITCH_VISION_CAPABILITIES_DIR"] = str(capabilities_dir)
    if env_overrides:
        env.update(env_overrides)
    process = subprocess.Popen(
        [str(LEGACY)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    return process.wait()


def _is_walk(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix.casefold() not in {".txt", ".walk", ".snmpwalk"}:
        return False
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "1.3.6.1.2.1.31.1.1.1.1." in line or "1.3.6.1.2.1.2.2.1.2." in line:
                    return True
    except OSError:
        return False
    return False


def _prepare_walk(source: Path, destination: Path, work: Path) -> dict[str, Any] | None:
    key = _safe(f"{source.parent.name}_{source.name}")
    capability = work / "authoritative_capabilities" / f"{key}.json"
    contract = work / "contracts" / f"{key}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    capability.parent.mkdir(parents=True, exist_ok=True)
    contract.parent.mkdir(parents=True, exist_ok=True)

    if not _is_walk(source):
        shutil.copy2(source, destination)
        return None

    result = subprocess.run(
        [str(PREPARE), str(source), str(destination), str(capability), str(contract)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=os.environ.copy(),
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip()
        contract_data: dict[str, Any] = {}
        try:
            contract_data = json.loads(contract.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        errors = contract_data.get("errors") if isinstance(contract_data, dict) else None
        if isinstance(errors, list) and errors:
            detail = "; ".join(str(item) for item in errors)
        # Preserve authoritative capability/contract artifacts even when the
        # exact topology is rejected. The caller excludes this target from
        # generated output but continues independently valid targets.
        if isinstance(contract_data, dict):
            return {
                "source": source,
                "destination": destination,
                "capability": capability,
                "contract_path": contract,
                "contract": contract_data,
            }
        print(
            "SV_STATUS|stage=Topology conflict|"
            f"switch={source.parent.name}|target=|command=Physical contract|"
            f"activity={detail or 'Resolver rejected topology; target excluded'}"
        )
        return None

    try:
        contract_data = json.loads(contract.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(contract_data, dict):
        return None
    return {
        "source": source,
        "destination": destination,
        "capability": capability,
        "contract_path": contract,
        "contract": contract_data,
    }


def _copy_tree_normalized(source_root: Path, destination_root: Path, work: Path, prepared: dict[Path, dict[str, Any] | None]) -> None:
    if not source_root.is_dir():
        destination_root.mkdir(parents=True, exist_ok=True)
        return
    for source in sorted(source_root.rglob("*")):
        relative = source.relative_to(source_root)
        destination = destination_root / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if not source.is_file():
            continue
        resolved_source = source.resolve()
        if resolved_source in prepared:
            existing = prepared[resolved_source]
            if existing is not None and _contract_usable_for_display(existing["contract"]):
                shutil.copy2(existing["destination"], destination)
            else:
                shutil.copy2(source, destination)
            continue
        info = _prepare_walk(source, destination, work)
        prepared[resolved_source] = info


def _staged_path_for(path: Path, source_root: Path, staged_root: Path) -> Path | None:
    try:
        return staged_root / path.resolve().relative_to(source_root.resolve())
    except (OSError, ValueError):
        return None


def _read_current_run_records(
    current_run_walks: Path,
    current_run_targets: Path,
) -> list[dict[str, str]]:
    if not current_run_walks.is_file() or not current_run_walks.stat().st_size:
        return []

    metadata: dict[str, dict[str, str]] = {}
    if current_run_targets.is_file():
        # The manifest uses ASCII FS (0x1c) as its field separator. Python's
        # splitlines() also treats FS as a line boundary, so split only on LF.
        for raw in current_run_targets.read_text(encoding="utf-8", errors="replace").split("\n"):
            parts = raw.split(CURRENT_RUN_SEPARATOR)
            if len(parts) != 5:
                continue
            walk, switch, host, prefix, community = parts
            if not walk:
                continue
            metadata[str(Path(walk).resolve())] = {
                "switch": switch,
                "host": host,
                "prefix": prefix,
                "community": community,
            }

    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in current_run_walks.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        source = Path(raw)
        resolved = str(source.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        target = metadata.get(resolved)
        if target is None:
            raise RuntimeError("Current-run SNMP walk is missing authoritative target metadata.")
        if not source.is_file():
            raise RuntimeError("Current-run SNMP walk disappeared before physical-contract staging.")
        records.append({"walk": str(source), **target})
    return records


def _write_current_run_targets_csv(path: Path, records: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for record in records:
            staged_path = Path(record["staged_walk"])
            switch = record.get("switch") or staged_path.parent.name
            writer.writerow([
                switch,
                record.get("host", ""),
                record.get("prefix", ""),
                record.get("community", ""),
                str(staged_path.parent),
                switch,
            ])


def _stage_current_run_options(
    options: dict[str, Any],
    staged: dict[str, Any],
    work: Path,
    current_run: list[dict[str, str]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    staged_root = work / "snmpwalks"
    staged_root.mkdir(parents=True, exist_ok=True)
    ordered: list[dict[str, Any]] = []
    accepted_evidence: list[dict[str, Any]] = []
    staged_records: list[dict[str, str]] = []
    by_source: dict[Path, Path] = {}

    for record in current_run:
        source = Path(record["walk"])
        switch = _safe(record.get("switch") or source.parent.name)
        destination = staged_root / switch / source.name
        info = _prepare_walk(source, destination, work)
        if info is None:
            destination.unlink(missing_ok=True)
            print(
                "SV_STATUS|stage=Support contribution recommended|"
                f"switch={switch}|target=|command=Physical contract|"
                "activity=Switch responded, but there was not enough trustworthy physical interface evidence to draw a safe card; submit Support My Switch so exact support can be added"
            )
            continue
        accepted_evidence.append(info)
        contract = info["contract"]
        status = str(contract.get("status") or "unresolved")
        if status == "resolved":
            ordered.append(info)
            by_source[source.resolve()] = destination
            staged_records.append({**record, "staged_walk": str(destination)})
            continue
        if _fallback_contract_usable(contract):
            observed = contract.get("observed") if isinstance(contract.get("observed"), dict) else {}
            model = str(contract.get("device", {}).get("model") or "unknown")
            print(
                "SV_STATUS|stage=Unsupported model fallback|"
                f"switch={switch}|target=|command=Physical contract|"
                f"activity={model} is not in the exact registry; preserving {int(observed.get('physical') or 0)} observed physical ports and showing the safest best-fit card. Submit Support My Switch to add exact support"
            )
            # Keep the evidence in the accepted set, but do not feed the unknown
            # model into exact-model YAML generation. A best-fit display card is
            # appended after the exact/registered generation phase.
            destination.unlink(missing_ok=True)
            continue
        destination.unlink(missing_ok=True)
        if status == "topology_conflict":
            model = str(contract.get("device", {}).get("model") or "unknown")
            activity = (
                f"{model} is registered, but this walk conflicts with the exact physical contract. "
                "The registered layout will be shown without trusting conflicting port bindings; submit Support My Switch if the mismatch persists"
            )
            stage = "Registered model fallback"
        else:
            activity = (
                "Switch responded, but there is no safe exact or generic physical layout yet; "
                "submit Support My Switch so support can be added"
            )
            stage = "Support contribution recommended"
        print(
            f"SV_STATUS|stage={stage}|switch={switch}|target=|"
            f"command=Physical contract|activity={activity}"
        )

    # The compatibility tree contains only this run's exact resolved switch walks.
    # Unsupported or conflicting devices are handled by a display-only fallback
    # after generation, so parse_all_walks never mistakes a best-fit visual for
    # authoritative topology or SNMP2MQTT bindings.
    staged["snmpwalks_dir"] = str(staged_root)
    staged["parse_all_walks"] = "true"

    resolved_switches = {
        _safe(record.get("switch") or Path(record["walk"]).parent.name)
        for record in staged_records
    }
    current_run_switches = {
        _safe(record.get("switch") or Path(record["walk"]).parent.name)
        for record in current_run
    }
    dashboard_switches: set[str] = set()
    rows_key = "switches" if isinstance(staged.get("switches"), list) else "multi_switch_walks"
    rows = staged.get(rows_key)
    if isinstance(rows, list):
        # Dashboard presentation and telemetry generation intentionally have
        # different safety contracts. Exact current-run rows remain available
        # to both paths. Saved rows with no successful current-run walk remain
        # available only to the Dashboard Card so a temporary SNMP failure does
        # not make the device disappear. Rows that did respond but require an
        # unsupported/conflict fallback are excluded here because the physical
        # contract layer appends their safe display-only card separately.
        dashboard_rows: list[dict[str, Any]] = []
        filtered_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("switch_name") or row.get("switch") or row.get("selected_switch") or row.get("name") or "").strip()
            safe_name = _safe(name)
            if safe_name in resolved_switches or safe_name not in current_run_switches:
                dashboard_rows.append(copy.deepcopy(row))
                dashboard_switches.add(safe_name)
            if safe_name not in resolved_switches:
                continue
            row["output_dir"] = str(staged_root / safe_name)
            filtered_rows.append(row)
        staged["dashboard_switches"] = dashboard_rows
        staged[rows_key] = filtered_rows

    members = staged.get("stack_member_prefixes")
    if isinstance(members, list):
        staged["dashboard_stack_member_prefixes"] = [
            copy.deepcopy(member)
            for member in members
            if isinstance(member, dict)
            and _safe(
                str(
                    member.get("switch_name")
                    or member.get("switch")
                    or member.get("selected_switch")
                    or member.get("name")
                    or ""
                )
            )
            in dashboard_switches
        ]
        staged["stack_member_prefixes"] = [
            member
            for member in members
            if isinstance(member, dict)
            and _safe(
                str(
                    member.get("switch_name")
                    or member.get("switch")
                    or member.get("selected_switch")
                    or member.get("name")
                    or ""
                )
            )
            in resolved_switches
        ]

    input_value = str(options.get("input_path") or "").strip()
    if input_value:
        mapped = by_source.get(Path(input_value).resolve())
        if mapped is not None:
            staged["input_path"] = str(mapped)
        elif ordered:
            staged["input_path"] = str(ordered[0]["destination"])
    elif ordered:
        staged["input_path"] = str(ordered[0]["destination"])

    target_csv = work / "current-run-targets.csv"
    _write_current_run_targets_csv(target_csv, staged_records)
    staged["targets_csv"] = str(target_csv)
    return staged, ordered, accepted_evidence


def _stage_options(
    options: dict[str, Any],
    work: Path,
    current_run: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    staged = copy.deepcopy(options)
    staged["run_snmp_walks"] = "false"
    staged["run_live_snmpwalk"] = "false"
    staged["clean_output_before_walk"] = "false"

    if current_run:
        return _stage_current_run_options(options, staged, work, current_run)

    source_root = Path(str(options.get("snmpwalks_dir") or DEFAULT_WALK_ROOT))
    staged_root = work / "snmpwalks"
    prepared: dict[Path, dict[str, Any] | None] = {}
    _copy_tree_normalized(source_root, staged_root, work, prepared)
    staged["snmpwalks_dir"] = str(staged_root)

    input_value = str(options.get("input_path") or "").strip()
    if input_value:
        source_input = Path(input_value)
        mapped = _staged_path_for(source_input, source_root, staged_root)
        if mapped is not None and mapped.exists():
            staged["input_path"] = str(mapped)
        elif source_input.is_file():
            destination = work / "single_input" / source_input.name
            info = _prepare_walk(source_input, destination, work)
            prepared[source_input.resolve()] = info
            staged["input_path"] = str(destination)

    rows = staged.get("switches")
    if not isinstance(rows, list):
        rows = staged.get("multi_switch_walks")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("switch_name") or row.get("switch") or row.get("selected_switch") or row.get("name") or "").strip()
            source_output = Path(str(row.get("output_dir") or (source_root / _safe(name))))
            mapped = _staged_path_for(source_output, source_root, staged_root)
            if mapped is None:
                mapped = work / "switches" / _safe(name)
                _copy_tree_normalized(source_output, mapped, work, prepared)
            row["output_dir"] = str(mapped)

    # Build the same practical order used by switch inventory parsing first,
    # then append any remaining single/offline walks. This order is used only
    # for patching legacy model labels; source ifIndex bindings remain in each
    # contract regardless of order.
    ordered: list[dict[str, Any]] = []
    accepted_evidence: list[dict[str, Any]] = []
    seen: set[Path] = set()
    original_rows = options.get("switches")
    if not isinstance(original_rows, list):
        original_rows = options.get("multi_switch_walks")
    if isinstance(original_rows, list):
        for row in original_rows:
            if not isinstance(row, dict) or not _bool(row.get("enabled", "enabled"), True):
                continue
            name = str(row.get("switch_name") or row.get("switch") or row.get("selected_switch") or row.get("name") or "").strip()
            output = Path(str(row.get("output_dir") or (source_root / _safe(name))))
            if not output.is_dir():
                continue
            for source in sorted(output.iterdir()):
                info = prepared.get(source.resolve()) if source.is_file() else None
                if info is not None and source.resolve() not in seen:
                    accepted_evidence.append(info)
                    if str(info["contract"].get("status") or "") == "resolved":
                        ordered.append(info)
                    seen.add(source.resolve())
    for source_path, info in prepared.items():
        if info is not None and source_path not in seen:
            accepted_evidence.append(info)
            if str(info["contract"].get("status") or "") == "resolved":
                ordered.append(info)
            seen.add(source_path)

    # Stored-walk regeneration follows the same boundary as a live run: only
    # exact resolved walks feed telemetry generation. Reachable unsupported or
    # conflicting evidence is retained for display-only fallback/CTA output.
    for source_path, info in prepared.items():
        if info is None or str(info["contract"].get("status") or "") == "resolved":
            continue
        mapped = _staged_path_for(source_path, source_root, staged_root)
        if mapped is not None:
            mapped.unlink(missing_ok=True)

    resolved_switches = {_safe(Path(info["source"]).parent.name) for info in ordered}
    rows_key = "switches" if isinstance(staged.get("switches"), list) else "multi_switch_walks"
    rows = staged.get(rows_key)
    if isinstance(rows, list):
        staged[rows_key] = [
            row for row in rows
            if isinstance(row, dict)
            and _safe(str(row.get("switch_name") or row.get("switch") or row.get("selected_switch") or row.get("name") or "")) in resolved_switches
        ]
    members = staged.get("stack_member_prefixes")
    if isinstance(members, list):
        staged["stack_member_prefixes"] = [
            member for member in members
            if isinstance(member, dict)
            and _safe(str(member.get("switch_name") or member.get("switch") or member.get("selected_switch") or member.get("name") or "")) in resolved_switches
        ]
    if ordered:
        staged["input_path"] = str(ordered[0]["destination"])

    return staged, ordered, accepted_evidence


def _patch_report(path: Path, ordered: list[dict[str, Any]]) -> None:
    """Patch legacy report metadata by exact staged walk identity, never list order."""
    if not path.is_file() or not ordered:
        return
    by_path = {
        str(Path(info["destination"]).resolve()): info["contract"]
        for info in ordered
        if info.get("destination") and isinstance(info.get("contract"), dict)
    }
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    contract: dict[str, Any] | None = None
    for index, line in enumerate(lines):
        if re.match(r"^Device \d+: ", line) or line.startswith("Single walk: "):
            contract = None
            continue
        if line.startswith("File: "):
            raw_path = line.removeprefix("File: ").strip()
            try:
                key = str(Path(raw_path).resolve())
            except (OSError, RuntimeError):
                key = raw_path
            contract = by_path.get(key)
            continue
        if not contract:
            continue
        model = str(contract.get("device", {}).get("model") or "unknown")
        physical = int(contract.get("observed", {}).get("physical") or 0)
        if line.startswith("Model/platform: "):
            lines[index] = f"Model/platform: {model}"
        elif line.startswith("- Physical switch interfaces detected: "):
            lines[index] = f"- Physical switch interfaces detected: {physical}"
        elif line.startswith("- Mapped physical interfaces: "):
            lines[index] = f"- Mapped physical interfaces: {physical}"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _patch_yaml(path: Path, ordered: list[dict[str, Any]]) -> None:
    """Patch generated model metadata by stable switch key, never section order."""
    if not path.is_file() or not ordered:
        return
    by_switch = {
        _safe(Path(info["destination"]).parent.name): info["contract"]
        for info in ordered
        if info.get("destination") and isinstance(info.get("contract"), dict)
    }
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    contract: dict[str, Any] | None = None
    for index, line in enumerate(lines):
        if line.startswith("# Device source: "):
            contract = None
            continue
        if line.startswith("# Switch key: "):
            contract = by_switch.get(_safe(line.removeprefix("# Switch key: ").strip()))
            continue
        if not contract:
            continue
        model = str(contract.get("device", {}).get("model") or "unknown")
        if line.startswith("# Detected model: "):
            lines[index] = f"# Detected model: {model}"
        elif re.match(r"^\s*device_model:\s*", line):
            indent = line[: len(line) - len(line.lstrip())]
            lines[index] = f"{indent}device_model: {model}"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _publish_contracts(ordered: list[dict[str, Any]], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for info in ordered:
        source: Path = info["source"]
        safe_parent = _safe(source.parent.name)
        shutil.copy2(info["capability"], destination / f"{safe_parent}-capabilities.json")
        shutil.copy2(info["contract_path"], destination / f"{safe_parent}-physical-contract.json")


def _expected_generated_snmp_cards(ordered: list[dict[str, Any]]) -> int:
    expected = 0
    for info in ordered:
        contract = info.get("contract") if isinstance(info, dict) else None
        if not isinstance(contract, dict) or str(contract.get("status") or "") != "resolved":
            continue
        observed = contract.get("observed") if isinstance(contract.get("observed"), dict) else {}
        try:
            members = int(observed.get("members") or 1)
        except (TypeError, ValueError):
            members = 1
        expected += max(1, members)
    return expected


def _expected_generated_dashboard_cards(options: dict[str, Any]) -> int | None:
    rows = options.get("dashboard_switches")
    if not isinstance(rows, list):
        rows = options.get("switches") if isinstance(options.get("switches"), list) else options.get("multi_switch_walks")
    if not isinstance(rows, list):
        return None
    members = options.get("dashboard_stack_member_prefixes")
    if not isinstance(members, list):
        members = options.get("stack_member_prefixes") if isinstance(options.get("stack_member_prefixes"), list) else []

    def enabled(row: dict[str, Any]) -> bool:
        value = row.get("enabled", "enabled")
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"false", "disabled", "disable", "off", "no", "0"}
        return True

    expected = 0
    for row in rows:
        if not isinstance(row, dict) or not enabled(row):
            continue
        name = str(row.get("switch_name") or row.get("switch") or row.get("selected_switch") or row.get("name") or "").strip()
        if not name:
            continue
        safe_name = _safe(name)
        matching_members = []
        for member in members:
            if not isinstance(member, dict):
                continue
            member_switch = str(
                member.get("switch_name")
                or member.get("switch")
                or member.get("selected_switch")
                or member.get("name")
                or ""
            ).strip()
            if _safe(member_switch) == safe_name:
                matching_members.append(member)
        non_primary = 0
        for member in matching_members:
            member_id = str(member.get("member") or member.get("member_number") or "")
            if member_id != "1":
                non_primary += 1
        expected += 1 + non_primary
    return expected


def _best_generic_profile(rj45: int, uplinks: int) -> tuple[str, str, int, int] | None:
    # Neutral stock visuals only. Vendor-specific artwork is never used as an
    # unsupported-model guess. port_count/sfp_port_count cap unused sockets.
    candidates = (
        (24, 2, "stock_24rj45_2sfp", "24 RJ45 + 2 uplink"),
        (24, 4, "stock_24rj45_4sfp", "24 RJ45 + 4 uplink"),
        (48, 2, "stock_48rj45_2sfp", "48 RJ45 + 2 uplink"),
        (48, 4, "stock_48rj45_4sfp", "48 RJ45 + 4 uplink"),
    )
    fits = [row for row in candidates if rj45 <= row[0] and uplinks <= row[1]]
    if not fits:
        return None
    fits.sort(key=lambda row: ((row[0] - rj45) + (row[1] - uplinks) * 4, row[0], row[1]))
    capacity_rj45, capacity_uplinks, profile, label = fits[0]
    return profile, label, capacity_rj45, capacity_uplinks


def _switch_row(options: dict[str, Any], switch: str) -> dict[str, Any]:
    rows = options.get("switches") if isinstance(options.get("switches"), list) else options.get("multi_switch_walks")
    if not isinstance(rows, list):
        return {}
    target = _safe(switch)
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("switch_name") or row.get("switch") or row.get("selected_switch") or row.get("name") or "").strip()
        if _safe(name) == target:
            return row
    return {}


def _ensure_dashboard_card_base(path: Path) -> None:
    if path.is_file() and path.stat().st_size:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Switch Vision generated dashboard card examples\n"
        "# Reachable devices are kept diagnosable even when exact support is not registered.\n"
        "views:\n"
        "  - title: Switch Vision\n"
        "    path: switch-vision\n"
        "    type: custom:vertical-layout\n"
        "    layout:\n"
        "      width: 800\n"
        "      max_cols: 1\n"
        "    cards:\n",
        encoding="utf-8",
    )


def _append_report_fallback_notices(
    path: Path,
    accepted_evidence: list[dict[str, Any]],
    *,
    replace: bool = False,
) -> int:
    rows: list[str] = []
    count = 0
    for info in accepted_evidence:
        contract = info.get("contract") if isinstance(info, dict) else None
        if not isinstance(contract, dict) or str(contract.get("status") or "") == "resolved":
            continue
        device = contract.get("device") if isinstance(contract.get("device"), dict) else {}
        observed = contract.get("observed") if isinstance(contract.get("observed"), dict) else {}
        model = str(device.get("model") or "Unknown switch")
        status = str(contract.get("status") or "unresolved")
        registered = bool(device.get("registry_match"))
        count += 1
        rows.extend(["", f"Reachable device support note: {model}"])
        if status == "topology_conflict" and registered:
            rows.append("- Result: exact model exists in the Switch Vision registry; registered visual retained for diagnosis")
            rows.append("- Telemetry binding: not trusted for this capture because observed topology conflicted with the exact registry contract")
            rows.append("- Action: Discovery still passes; use Support My Switch if the mismatch persists so the model evidence can be reviewed")
        elif _fallback_contract_usable(contract):
            rows.append("- Result: exact model is not registered; best-fit visual may be shown from observed physical ports")
            rows.append(f"- Observed physical ports: {int(observed.get('physical') or 0)}")
            rows.append("- Action: submit Support My Switch to add exact registry support, telemetry mapping and faceplate alignment")
        else:
            rows.append("- Result: switch is reachable, but there is not enough trustworthy topology to draw a safe card")
            rows.append("- Action: submit Support My Switch so exact support can be added; no phantom topology was invented")
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    if replace or not path.exists():
        prefix = [
            "Switch Vision Discovery",
            "=======================",
            "Discovery communication succeeded. The notes below describe display/support limitations, not reachability failures.",
        ]
        path.write_text("\n".join(prefix + rows) + "\n", encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(rows) + "\n")
    return count


def _append_display_fallbacks(
    path: Path,
    accepted_evidence: list[dict[str, Any]],
    options: dict[str, Any],
) -> tuple[int, int]:
    """Append display-only cards/CTAs for reachable non-resolved hardware.

    Returns (cards_appended, contribution_notices). No fallback is allowed to
    create SNMP entities or alter the exact-model registry.
    """
    fallbacks: list[tuple[dict[str, Any], str]] = []
    for info in accepted_evidence:
        contract = info.get("contract") if isinstance(info, dict) else None
        if not isinstance(contract, dict) or str(contract.get("status") or "") == "resolved":
            continue
        switch = _safe(Path(info["source"]).parent.name)
        fallbacks.append((contract, switch))
    if not fallbacks:
        return 0, 0

    _ensure_dashboard_card_base(path)
    out: list[str] = []
    cards = 0
    notices = 0
    for contract, switch in fallbacks:
        status = str(contract.get("status") or "unresolved")
        device = contract.get("device") if isinstance(contract.get("device"), dict) else {}
        observed = contract.get("observed") if isinstance(contract.get("observed"), dict) else {}
        expected = contract.get("expected") if isinstance(contract.get("expected"), dict) else {}
        model = str(device.get("model") or "Unknown switch")
        row = _switch_row(options, switch)
        title = str(row.get("display_name") or switch or model).strip() or model
        host = str(row.get("switch_host") or row.get("host") or "").strip()
        prefix = str(row.get("sensor_prefix") or row.get("entity_prefix") or switch).strip() or switch
        profile = ""
        rj45 = 0
        uplinks = 0
        detail = ""
        exact_registered = bool(device.get("registry_match"))

        if status == "topology_conflict" and exact_registered:
            profile = str(device.get("calibration_profile") or "").strip()
            rj45 = int(expected.get("rj45") or 0)
            uplinks = int(expected.get("uplinks") or 0)
            if not profile:
                generic = _best_generic_profile(rj45, uplinks)
                if generic:
                    profile, label, _, _ = generic
                    detail = f"Registered topology is shown with the neutral {label} visual."
            else:
                detail = "The exact registered Switch Vision layout is shown, but this walk was not trusted for port bindings."
        elif _fallback_contract_usable(contract):
            rj45 = int(observed.get("rj45") or 0)
            uplinks = int(observed.get("uplinks") or 0)
            generic = _best_generic_profile(rj45, uplinks)
            if generic:
                profile, label, _, _ = generic
                detail = f"Showing a neutral best-fit {label} card using only the {rj45} RJ45 and {uplinks} uplink positions observed in this walk."

        notices += 1
        out.extend([
            "",
            "      - type: markdown",
            "        content: |",
            f"          ### {title}",
        ])
        if exact_registered:
            out.append(f"          **{model} is registered, but this capture did not match the exact physical binding contract.**")
            if detail:
                out.append(f"          {detail}")
            out.append("          Discovery completed so the card remains diagnosable. If the mismatch persists, use **Support My Switch** and submit the contribution bundle.")
        else:
            out.append(f"          **{model} is reachable but does not yet have exact Switch Vision registry support.**")
            if detail:
                out.append(f"          {detail}")
            else:
                out.append("          Switch Vision could not choose a safe neutral card layout from the observed ports, so no topology was invented.")
            out.append("          Use **Support My Switch** to submit a contribution so exact model support, telemetry and faceplate mapping can be added.")

        if not profile:
            continue
        cards += 1
        out.extend([
            "",
            "      - type: custom:switch-vision-3650",
            f"        title: {json.dumps(title)}",
            f"        member: {json.dumps(switch)}",
            f"        selected_switch: {json.dumps(switch)}",
            f"        discovery_selected_switch: {json.dumps(switch)}",
            f"        switch_model: {json.dumps(model)}",
            f"        calibration_profile: {json.dumps(profile)}",
            "        calibration_profile_load: true",
            "        calibration_profile_auto_load: true",
            "        calibration_button: true",
            f"        port_count: {max(0, rj45)}",
            f"        sfp_port_count: {max(0, uplinks)}",
            "        activity_hold_seconds: 12",
            f"        status_entity_prefix: sensor.{_safe(prefix).lower()}_port_",
            "        status_entity_suffix: _status",
        ])
        if host:
            out.append(f"        switch_ip: {json.dumps(host)}")
            out.append(f"        management_ip: {json.dumps(host)}")
        if not exact_registered:
            out.append("        # Best-fit unsupported-model visual; exact support requires Support My Switch evidence.")
        else:
            out.append("        # Exact registered visual shown in diagnostic mode; conflicting walk bindings were not trusted.")

    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")
    return cards, notices


def _generated_snmp_card_count(path: Path) -> int:
    if not path.is_file():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    snmp_only = text.split("# UniFi API devices", 1)[0]
    return len(
        re.findall(
            r"(?m)^\s*-\s*type:\s*custom:switch-vision-3650\s*$",
            snmp_only,
        )
    )


def _stage_live_collection(
    options: dict[str, Any],
    work: Path,
) -> tuple[list[dict[str, str]], bool]:
    if not _bool(options.get("run_snmp_walks", options.get("run_live_snmpwalk", False))):
        return [], False
    stage = copy.deepcopy(options)
    stage["generate_snmp2mqtt"] = "false"
    stage["generate_support_my_switch_bundle"] = "false"
    stage["report_path"] = str(work / "live_collection_report.txt")
    stage["generated_yaml_path"] = str(work / "live_collection_generated.yaml")
    stage["generated_card_path"] = str(work / "live_collection_card.yaml")
    stage["last_run_summary_path"] = str(work / "live_collection_summary.txt")
    stage_path = work / "live_collection_options.json"
    current_run_walks = work / "current_run_walks.txt"
    current_run_targets = work / "current_run_targets.txt"
    _write_options(stage_path, stage)
    return_code = _stream_legacy(
        stage_path,
        capabilities_dir=work / "live_collection_capabilities",
        env_overrides={
            "SWITCH_VISION_CURRENT_RUN_WALKS": str(current_run_walks),
            "SWITCH_VISION_CURRENT_RUN_TARGETS": str(current_run_targets),
        },
    )
    if return_code == 10:
        raise DegradedDiscoveryError(
            "Live SNMP collection produced useful evidence, but safe downstream generation cannot be trusted."
        )
    if return_code not in {0, 11}:
        raise RuntimeError(f"Live SNMP collection exited with code {return_code}.")
    current_run = _read_current_run_records(current_run_walks, current_run_targets)
    if return_code == 11 and not current_run:
        raise RuntimeError(
            "Live SNMP collection reported PARTIAL without any successful current-run walk."
        )
    return current_run, return_code == 11


def main() -> int:
    if not LEGACY.is_file() or not PREPARE.is_file() or not REGISTRY.is_file():
        print("Physical-contract runtime is incomplete; refusing to bypass the authority layer.", file=sys.stderr)
        return 2
    options = _read_options(DEFAULT_OPTIONS)
    with tempfile.TemporaryDirectory(prefix="switch_vision_physical_contract_") as tmp:
        work = Path(tmp)
        current_run, live_collection_partial = _stage_live_collection(options, work)
        staged, ordered, accepted_evidence = _stage_options(options, work, current_run)
        # Persist validated physical evidence before downstream generation. A
        # later generator/cardinality failure must not discard useful evidence.
        _publish_contracts(accepted_evidence, DEFAULT_CAPABILITIES)
        report = Path(str(options.get("report_path") or "/share/switch_vision/discovery-report.txt"))
        generated_yaml = Path(str(options.get("generated_yaml_path") or "/share/switch_vision/generated-snmp2mqtt.yaml"))
        generated_card = Path(
            str(
                options.get("generated_card_path")
                or "/share/switch_vision/generated-dashboard-card.yaml"
            )
        )

        if not ordered:
            # A reachable switch with unsupported/incomplete topology is a
            # successful diagnostic Discovery, not a failed run. Preserve the
            # evidence, show the safest display we can, and ask for a Support My
            # Switch contribution. The existing generated SNMP2MQTT YAML is not
            # replaced or activated because there are no trusted bindings.
            notices = _append_report_fallback_notices(report, accepted_evidence, replace=True)
            generated_card.unlink(missing_ok=True)
            fallback_cards, card_notices = _append_display_fallbacks(generated_card, accepted_evidence, options)
            if not notices and not card_notices:
                report.parent.mkdir(parents=True, exist_ok=True)
                report.write_text(
                    "Switch Vision Discovery\n"
                    "=======================\n"
                    "Discovery completed with no exact displayable switch contract.\n"
                    "If the switch is reachable but no card can be shown, use Support My Switch to submit a contribution so support can be added.\n",
                    encoding="utf-8",
                )
                _ensure_dashboard_card_base(generated_card)
            print(
                "SV_STATUS|stage=Complete with warnings|switch=All configured switches|"
                "target=|command=Physical contract|"
                "activity=Discovery communication succeeded, but exact telemetry generation was unavailable; best-fit display/contribution guidance was preserved"
            )
            print(f"SV_DEBUG|Physical contract authority: display-only fallback cards={fallback_cards}; support notices={max(notices, card_notices)}")
            print("SV_RESULT|warnings=true|degraded=true")
            return 0

        stage_path = work / "resolved_options.json"
        _write_options(stage_path, staged)
        return_code = _stream_legacy(stage_path, capabilities_dir=work / "runtime_capabilities")
        if return_code != 0:
            raise DegradedDiscoveryError(
                f"Downstream Discovery generation exited with code {return_code} after validated physical evidence was collected."
            )
        expected_cards = _expected_generated_dashboard_cards(staged)
        if expected_cards is None:
            expected_cards = _expected_generated_snmp_cards(ordered)
        actual_cards = _generated_snmp_card_count(generated_card)
        if actual_cards != expected_cards:
            raise DegradedDiscoveryError(
                f"Generated SNMP card count mismatch: expected {expected_cards}, found {actual_cards}."
            )
        _patch_report(report, ordered)
        _patch_yaml(generated_yaml, ordered)
        if generated_yaml.is_file():
            guard = Path(__file__).with_name("generated_yaml_guard.py")
            if not guard.is_file():
                raise DegradedDiscoveryError(
                    "Generated YAML post-contract validation could not run because the guard is missing."
                )
            guard_result = subprocess.run(
                [sys.executable, str(guard), "--validate", str(generated_yaml)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if guard_result.returncode != 0:
                detail = guard_result.stdout.strip() or "generated YAML guard refused patched output"
                raise DegradedDiscoveryError(
                    f"Generated YAML post-contract validation failed: {detail}"
                )
        fallback_notices = _append_report_fallback_notices(report, accepted_evidence)
        fallback_cards, card_notices = _append_display_fallbacks(generated_card, accepted_evidence, options)
        partial_result = live_collection_partial or fallback_notices > 0 or (
            bool(current_run) and len(ordered) != len(current_run)
        )
        if current_run:
            print(f"SV_DEBUG|Physical contract authority: accepted {len(ordered)} exact walk(s) of {len(current_run)} current-run walk(s) for normalized telemetry generation")
        if live_collection_partial:
            print("SV_DEBUG|Physical contract authority: one or more configured targets were unreachable/auth-failed while other targets remained usable")
        print(f"SV_DEBUG|Physical contract authority: resolved exact models={len(ordered)}; display-only fallback cards={fallback_cards}; support notices={max(fallback_notices, card_notices)}")
        if partial_result:
            print(
                "SV_STATUS|stage=Complete with warnings|switch=All configured switches|"
                "target=|command=Physical contract|"
                "activity=Discovery completed; exact registered devices were generated and reachable unsupported/partial devices were kept diagnosable with best-fit display or Support My Switch guidance"
            )
            print("SV_RESULT|warnings=true|degraded=false")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DegradedDiscoveryError as exc:
        print(
            "SV_STATUS|stage=Complete with warnings|switch=All configured switches|"
            f"target=|command=Physical contract|activity={exc}"
        )
        print(f"SV_DEBUG|Physical contract degraded result: {exc}")
        raise SystemExit(10)
    except Exception as exc:
        print(f"SV_DEBUG|Physical contract failure: {exc}")
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
