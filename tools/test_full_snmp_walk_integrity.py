#!/usr/bin/env python3
"""Exercise real full-walk collection with a synthetic out-of-order Dell SNMP agent.

The fixtures are generated locally; no network, private evidence, or device writes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "runtime_src/discovery_job.sh"
MOCK = r'''#!/usr/bin/env python3
import os
import sys

root = sys.argv[-1]
mode = os.environ["SV_WALK_TEST_MODE"]
if root == "1.3.6.1.2.1.1.1.0":
    print('.1.3.6.1.2.1.1.1.0 = STRING: "Dell PowerConnect synthetic test"')
    raise SystemExit(0)
if root == "1":
    sys.stderr.write("ERROR: obsolete root-1 walk must never be used\n")
    raise SystemExit(99)
if root != "1.3.6.1":
    sys.stderr.write("ERROR: unexpected full SNMP root\n")
    raise SystemExit(98)

if mode == "lldp_only":
    # Simulate the submitted case: thousands of LLDP rows, no MIB-2 identity,
    # a non-increasing agent OID and a nonzero full-walk exit status.
    for idx in range(1, 301):
        print(f".1.0.8802.1.1.2.1.4.1.1.4.{idx} = STRING: \"neighbor\"")
    sys.stderr.write("Error: OID not increasing\n")
    raise SystemExit(1)
if mode != "interfaces_only":
    print('.1.3.6.1.2.1.1.1.0 = STRING: "Dell PowerConnect synthetic test"')
    print('.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.674.10895.3031')
if mode != "identity_only":
    for idx in range(1, 49):
        print(f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: "Gi1/0/{idx}"')
if mode in ("identity_only", "interfaces_only"):
    for idx in range(1, 301):
        print(f".1.3.6.1.4.1.674.10895.999.{idx} = INTEGER: {idx}")
if mode == "warn_with_tables":
    sys.stderr.write("Synthetic optional OID unavailable\n")
    raise SystemExit(1)
raise SystemExit(0)
'''


def run_case(root: Path, mode: str, result: str, exit_code: int) -> None:
    target = root / mode
    (target / "bin").mkdir(parents=True)
    (target / "caps").mkdir()
    (target / "share").mkdir()
    walker = target / "bin/snmpwalk"
    walker.write_text(MOCK)
    walker.chmod(0o755)
    options = {
        "run_snmp_walks": "true",
        "enable_switch_list": "true",
        "parse_all_walks": "false",
        "generate_snmp2mqtt": "false",
        "generate_support_my_switch_bundle": "false",
        "minimum_valid_walk_lines": "100",
        "snmpwalks_dir": str(target / "walks"),
        "report_path": str(target / "report.txt"),
        "last_run_summary_path": str(target / "run-summary.txt"),
        "generated_yaml_path": str(target / "generated.yaml"),
        "generated_card_path": str(target / "card.yaml"),
        "snmp_log_path": str(target / "collector.log"),
        "switches": [{
            "switch_name": "one",
            "switch_host": "192.0.2.31",
            "sensor_prefix": "ONE",
            "snmp_community": "test-only",
            "enabled": "enabled",
            "walk_mode": "full",
            "switch_model": "auto",
        }],
    }
    opt_path = target / "options.json"
    opt_path.write_text(json.dumps(options))
    env = os.environ.copy()
    env.update({
        "PATH": str(target / "bin") + os.pathsep + env.get("PATH", ""),
        "SV_WALK_TEST_MODE": mode,
        "SWITCH_VISION_OPTIONS_FILE": str(opt_path),
        "SWITCH_VISION_COLLECTION_ONLY": "true",
        "SWITCH_VISION_COLLECTION_SUMMARY_PATH": str(target / "summary.txt"),
        "SWITCH_VISION_CAPABILITIES_DIR": str(target / "caps"),
        "SWITCH_VISION_SHARE_DIR": str(target / "share"),
    })
    p = subprocess.run(
        [str(JOB)], env=env, cwd=ROOT, text=True, capture_output=True, timeout=45,
    )
    assert p.returncode == exit_code, (
        mode, p.returncode, p.stdout[-1800:], p.stderr[-1800:]
    )
    summary = (target / "summary.txt").read_text()
    walk = (target / "walks/one/live-full-snmpwalk.txt").read_text()
    log = (target / "collector.log").read_text()
    assert f"SNMP walk result: {result}" in summary, (mode, summary)
    commands = [line for line in log.splitlines() if line.startswith("Command: snmpwalk")]
    assert any(line.endswith(" 1.3.6.1") for line in commands), (mode, commands)
    assert not any(line.endswith(" 1") for line in commands), (mode, commands)
    assert "# --- full walk: 1.3.6.1 ---" in walk
    if result == "FAIL":
        assert "insufficient_data" in walk, mode
        assert "Full SNMP walk missing system identity or interface-name table" in summary
        assert "Queued for current-run parse" not in log, mode
        assert "Current-run parse skipped for failed walk" in log, mode
    else:
        assert "1.3.6.1.2.1.1.2.0" in walk, mode
        assert "1.3.6.1.2.1.31.1.1.1.1.1" in walk, mode
        assert "Queued for current-run parse" in log, mode
        assert "1.0.8802" not in walk, mode


with tempfile.TemporaryDirectory(prefix="sv-fullwalk-oid-integrity-") as tmp:
    base = Path(tmp)
    run_case(base, "valid_tables", "PASS", 0)
    run_case(base, "lldp_only", "FAIL", 2)
    run_case(base, "identity_only", "FAIL", 2)
    run_case(base, "interfaces_only", "FAIL", 2)
    run_case(base, "warn_with_tables", "WARN", 0)

print("FULL_SNMP_WALK_OID_ORDER_AND_INTEGRITY_PASS")
