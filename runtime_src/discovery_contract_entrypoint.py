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


def _stream_legacy(options_path: Path, *, capabilities_dir: Path) -> int:
    env = os.environ.copy()
    env["SWITCH_VISION_OPTIONS_FILE"] = str(options_path)
    env["SWITCH_VISION_CAPABILITIES_DIR"] = str(capabilities_dir)
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
            for _ in range(4000):
                line = handle.readline()
                if not line:
                    break
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
        print(f"SV_STATUS|stage=Topology conflict|switch={source.parent.name}|target=|command=Physical contract|activity={detail or 'Resolver rejected topology'}")
        raise RuntimeError(f"Physical contract rejected {source}: {detail or 'unknown resolver error'}")

    try:
        contract_data = json.loads(contract.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(contract_data, dict) or contract_data.get("status") != "resolved":
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
            if existing is not None:
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


def _stage_options(options: dict[str, Any], work: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    staged = copy.deepcopy(options)
    staged["run_snmp_walks"] = "false"
    staged["run_live_snmpwalk"] = "false"
    staged["clean_output_before_walk"] = "false"

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
                    ordered.append(info)
                    seen.add(source.resolve())
    for source_path, info in prepared.items():
        if info is not None and source_path not in seen:
            ordered.append(info)
            seen.add(source_path)

    return staged, ordered


def _patch_report(path: Path, ordered: list[dict[str, Any]]) -> None:
    if not path.is_file() or not ordered:
        return
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    section = -1
    for index, line in enumerate(lines):
        if re.match(r"^Device \d+: ", line) or line.startswith("Single walk: "):
            section += 1
            continue
        if not (0 <= section < len(ordered)):
            continue
        contract = ordered[section]["contract"]
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
    if not path.is_file() or not ordered:
        return
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    section = -1
    for index, line in enumerate(lines):
        if line.startswith("# Device source: "):
            section += 1
            continue
        if not (0 <= section < len(ordered)):
            continue
        model = str(ordered[section]["contract"].get("device", {}).get("model") or "unknown")
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


def _stage_live_collection(options: dict[str, Any], work: Path) -> None:
    if not _bool(options.get("run_snmp_walks", options.get("run_live_snmpwalk", False))):
        return
    stage = copy.deepcopy(options)
    stage["generate_snmp2mqtt"] = "false"
    stage["generate_support_my_switch_bundle"] = "false"
    stage["report_path"] = str(work / "live_collection_report.txt")
    stage["generated_yaml_path"] = str(work / "live_collection_generated.yaml")
    stage["generated_card_path"] = str(work / "live_collection_card.yaml")
    stage["last_run_summary_path"] = str(work / "live_collection_summary.txt")
    stage_path = work / "live_collection_options.json"
    _write_options(stage_path, stage)
    return_code = _stream_legacy(stage_path, capabilities_dir=work / "live_collection_capabilities")
    if return_code != 0:
        raise RuntimeError(f"Live SNMP collection exited with code {return_code}.")


def main() -> int:
    if not LEGACY.is_file() or not PREPARE.is_file() or not REGISTRY.is_file():
        print("Physical-contract runtime is incomplete; refusing to bypass the authority layer.", file=sys.stderr)
        return 2
    options = _read_options(DEFAULT_OPTIONS)
    with tempfile.TemporaryDirectory(prefix="switch_vision_physical_contract_") as tmp:
        work = Path(tmp)
        _stage_live_collection(options, work)
        staged, ordered = _stage_options(options, work)
        stage_path = work / "resolved_options.json"
        _write_options(stage_path, staged)
        return_code = _stream_legacy(stage_path, capabilities_dir=work / "runtime_capabilities")
        if return_code != 0:
            return return_code

        report = Path(str(options.get("report_path") or "/share/switch_vision/discovery-report.txt"))
        generated_yaml = Path(str(options.get("generated_yaml_path") or "/share/switch_vision/generated-snmp2mqtt.yaml"))
        _patch_report(report, ordered)
        _patch_yaml(generated_yaml, ordered)
        _publish_contracts(ordered, DEFAULT_CAPABILITIES)
        print(f"SV_DEBUG|Physical contract authority: resolved {len(ordered)} registered device walk(s)")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"SV_DEBUG|Physical contract failure: {exc}")
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
