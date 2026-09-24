#!/usr/bin/env python3
"""Regression coverage for API/UniFi-only Discovery live-collection behavior."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

import discovery_contract_entrypoint as authority


BASE = Path(__file__).resolve().parent
DISCOVERY_JOB = BASE / "discovery_job.sh"


def _options(root: Path, switches: list[dict[str, object]]) -> dict[str, object]:
    return {
        "input_path": str(root / "legacy-unused.txt"),
        "snmpwalks_dir": str(root / "snmpwalks"),
        "report_path": str(root / "report.txt"),
        "run_snmp_walks": "true",
        "enable_switch_list": "true",
        "switches": switches,
        "stack_member_prefixes": [],
        "parse_all_walks": "false",
        "generate_snmp2mqtt": "false",
        "generate_support_my_switch_bundle": "false",
        "clean_output_before_walk": "false",
        "targets_csv": str(root / "no-import.csv"),
        "last_run_summary_path": str(root / "last-run.txt"),
        "generated_yaml_path": str(root / "generated.yaml"),
        "generated_card_path": str(root / "generated-card.yaml"),
        "snmp_timeout": "1",
        "snmp_retries": "0",
        "snmp_log_path": str(root / "snmpwalk.log"),
        "live_output_dir": str(root / "live"),
        "live_output_path": str(root / "live/live-targeted-snmpwalk.txt"),
        "minimum_valid_walk_lines": "1",
    }


def _run_collection(
    root: Path,
    switches: list[dict[str, object]],
    *,
    fail_snmp: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    for name in ("snmpwalks", "capabilities", "share", "live"):
        (root / name).mkdir(parents=True, exist_ok=True)

    options_path = root / "options.json"
    options_path.write_text(
        json.dumps(_options(root, switches), indent=2) + "\n",
        encoding="utf-8",
    )
    current_walks = root / "current-walks.txt"
    current_targets = root / "current-targets.txt"
    collection_summary = root / "collection-summary.txt"

    env = dict(os.environ)
    env.update(
        {
            "SWITCH_VISION_OPTIONS_FILE": str(options_path),
            "SWITCH_VISION_SHARE_DIR": str(root / "share"),
            "SWITCH_VISION_CAPABILITIES_DIR": str(root / "capabilities"),
            "SWITCH_VISION_CURRENT_RUN_WALKS": str(current_walks),
            "SWITCH_VISION_CURRENT_RUN_TARGETS": str(current_targets),
            "SWITCH_VISION_COLLECTION_ONLY": "true",
            "SWITCH_VISION_COLLECTION_SUMMARY_PATH": str(collection_summary),
        }
    )

    if fail_snmp:
        bin_dir = root / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        fake = bin_dir / "snmpwalk"
        fake.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        fake.chmod(0o755)
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

    result = subprocess.run(
        ["sh", str(DISCOVERY_JOB)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
        timeout=60,
    )
    return result, current_walks, current_targets, collection_summary


# Field-reported UniFi/API-only shape: switch-list mode is enabled but the only
# stored row is the empty placeholder, so there is no SNMP target to attempt.
with tempfile.TemporaryDirectory(prefix="sv-unifi-only-no-target-") as temp:
    root = Path(temp)
    placeholder = {
        "switch_name": "",
        "switch_host": "",
        "sensor_prefix": "",
        "snmp_community": "",
        "enabled": "enabled",
        "walk_mode": "targeted",
        "switch_model": "auto",
    }
    result, current_walks, current_targets, summary = _run_collection(
        root,
        [placeholder],
    )
    assert result.returncode == 0, result.stdout
    assert "Evidence collection skipped" in result.stdout, result.stdout
    assert "No enabled SNMP targets are configured" in result.stdout, result.stdout
    assert current_walks.exists() and current_walks.stat().st_size == 0
    assert current_targets.exists() and current_targets.stat().st_size == 0
    summary_text = summary.read_text(encoding="utf-8")
    assert "SNMP walk result: SKIP" in summary_text, summary_text
    assert "no enabled switch rows configured" in summary_text, summary_text


# Safety boundary: an actual configured SNMP target that cannot be reached must
# remain a hard collection failure and must not be reclassified as API-only.
with tempfile.TemporaryDirectory(prefix="sv-unifi-only-real-failure-") as temp:
    root = Path(temp)
    configured = {
        "switch_name": "FAIL-ONE",
        "display_name": "Fail One",
        "switch_host": "192.0.2.99",
        "sensor_prefix": "failone",
        "snmp_community": "regression-only",
        "enabled": "enabled",
        "walk_mode": "targeted",
        "switch_model": "auto",
    }
    result, current_walks, _current_targets, summary = _run_collection(
        root,
        [configured],
        fail_snmp=True,
    )
    assert result.returncode == 2, result.stdout
    assert "Evidence collection failed" in result.stdout, result.stdout
    assert current_walks.exists() and current_walks.stat().st_size == 0
    summary_text = summary.read_text(encoding="utf-8")
    assert "SNMP walk result: FAIL" in summary_text, summary_text
    assert "No SNMP response" in summary_text, summary_text


# None means live collection was disabled and stored/offline walks may be used.
# An empty list means live collection ran authoritatively with zero SNMP
# targets. That empty current run must never fall back to historical walks.
with tempfile.TemporaryDirectory(prefix="sv-unifi-only-authority-") as temp:
    root = Path(temp)
    stale_root = root / "stored-walks"
    stale_root.mkdir(parents=True)
    (stale_root / "stale.snmpwalk").write_text(
        ".1.3.6.1.2.1.1.1.0 = STRING: stale evidence must not be reused\n",
        encoding="utf-8",
    )
    work = root / "work"
    work.mkdir()
    options = {
        "snmpwalks_dir": str(stale_root),
        "switches": [],
        "stack_member_prefixes": [],
        "parse_all_walks": "true",
        "run_snmp_walks": "true",
    }
    staged, ordered, evidence = authority._stage_options(options, work, [])
    assert ordered == []
    assert evidence == []
    staged_root = Path(str(staged["snmpwalks_dir"]))
    assert staged_root == work / "snmpwalks"
    assert list(staged_root.rglob("*")) == []
    assert staged["parse_all_walks"] == "true"

    disabled, partial = authority._stage_live_collection(
        {"run_snmp_walks": "false"},
        work,
    )
    assert disabled is None
    assert partial is False

print("Switch Vision UniFi/API-only no-SNMP-target collection regression: PASS")
