#!/usr/bin/env python3
"""Evidence-checked Dell N2128PX-ON DNOS system health regressions."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
SWITCH = "1.3.6.1.4.1.674.10895.5000.2.6132.1.1.1.1.4."
BOX = "1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1."
GLOBAL = "1.3.6.1.4.1.674.10895.3000.1.2.110.1.0"

def walk(*, model: str = "N2128PX-ON", include_health: bool = True, invalid: bool = False) -> str:
    rows = [
        f'.1.3.6.1.2.1.1.1.0 = STRING: "Dell Networking {model}"',
        '.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.674.10895.3077',
    ]
    for i in range(1, 29):
        rows += [
            f'.1.3.6.1.2.1.31.1.1.1.1.{i} = STRING: Gi1/0/{i}',
            f'.1.3.6.1.2.1.2.2.1.8.{i} = INTEGER: up(1)',
        ]
    for port, idx in ((1, 29), (2, 30)):
        rows += [
            f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: Te1/0/{port}',
            f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: up(1)',
        ]
    if include_health:
        health = [
            (SWITCH + "10.0", "Gauge32", "130" if invalid else "45"),
            (SWITCH + "11.0", "Gauge32", "38"),
            (SWITCH + "12.0", "Gauge32", "19"),
            (SWITCH + "1.0", "INTEGER", "-20" if invalid else "168792"),
            (SWITCH + "2.0", "INTEGER", "1014356"),
            (GLOBAL, "INTEGER", "99" if invalid else "3"),
            (BOX + "6.1.3.1", "INTEGER", "1" if invalid else "2"),
            (BOX + "6.1.4.1", "INTEGER", "0" if invalid else "5216"),
            (BOX + "7.1.3.1", "INTEGER", "1"),
            (BOX + "7.1.3.2", "INTEGER", "1" if invalid else "2"),
            (BOX + "8.1.4.1.2", "INTEGER", "1"),
            (BOX + "8.1.5.1.2", "INTEGER", "999" if invalid else "39"),
        ]
        rows += [f".{oid} = {kind}: {value}" for oid, kind, value in health]
    return "\n".join(rows) + "\n"

def generate(data: str) -> str:
    with tempfile.TemporaryDirectory(prefix="sv_n2128_dnos_") as td:
        file = Path(td) / "walk.txt"
        file.write_text(data, encoding="utf8")
        cmd = ". " + str(RUNTIME / "discovery_yaml_stage.sh") + "\n" + (
            "write_generated_yaml_for_walk " + str(file) + " 192.0.2.5 DEV readonly\n")
        run = subprocess.run(["sh"], input=cmd, text=True, capture_output=True, timeout=50)
        assert run.returncode == 0, run.stderr
        return run.stdout

def test_valid_evidence():
    out=generate(walk())
    assert "# Detected model: N2128PX-ON" in out
    for oid in (SWITCH+"10.0", SWITCH+"11.0", SWITCH+"12.0", SWITCH+"1.0",
                SWITCH+"2.0", GLOBAL, BOX+"6.1.3.1", BOX+"6.1.4.1",
                BOX+"7.1.3.2", BOX+"8.1.5.1.2", BOX+"8.1.4.1.2"):
        assert "oid: "+oid in out, oid
    assert "oid: "+BOX+"7.1.3.1" not in out, "Absent PSU must not be created"
    assert 'unit_of_measurement: "%"' in out
    assert 'unit_of_measurement: "MiB"' in out
    assert 'unit_of_measurement: "rpm"' in out
    assert 'unit_of_measurement: "°C"' in out
    assert "transform: value / 1024" in out
    assert "Switch Vision DEV DNOS System Health" in out
    assert "SFP 10G" in out, "Existing physical port layout must be retained"

def test_missing_or_wrong_model():
    for raw in (walk(include_health=False), walk(model="N4032F"),
                walk(model="Unrelated Hardware")):
        out=generate(raw)
        assert "DNOS System Health" not in out
        assert "oid: "+SWITCH+"10.0" not in out
        assert "oid: "+BOX+"8.1.5.1.2" not in out

def test_invalid_not_inferred():
    out=generate(walk(invalid=True))
    for oid in (SWITCH+"10.0", SWITCH+"1.0", GLOBAL, BOX+"6.1.3.1",
                BOX+"6.1.4.1", BOX+"7.1.3.1", BOX+"7.1.3.2",
                BOX+"8.1.5.1.2", BOX+"8.1.4.1.2"):
        assert "oid: "+oid not in out, oid
    # Valid independent CPU and memory entities remain present.
    assert "oid: "+SWITCH+"11.0" in out
    assert "oid: "+SWITCH+"2.0" in out

def test_absent_and_unpaired_hardware_are_suppressed():
    original = walk()
    missing_temp_state = original.replace(
        f".{BOX}8.1.4.1.2 = INTEGER: 1\n", "")
    absent_temp_state = original.replace(
        f".{BOX}8.1.4.1.2 = INTEGER: 1",
        f".{BOX}8.1.4.1.2 = INTEGER: 5")
    absent_fan_state = original.replace(
        f".{BOX}6.1.3.1 = INTEGER: 2",
        f".{BOX}6.1.3.1 = INTEGER: 1")
    for raw in (missing_temp_state, absent_temp_state):
        generated = generate(raw)
        assert f"oid: {BOX}8.1.5.1.2" not in generated
        assert f"oid: {BOX}8.1.4.1.2" not in generated
    generated = generate(absent_fan_state)
    assert f"oid: {BOX}6.1.4.1" not in generated
    assert f"oid: {BOX}6.1.3.1" not in generated
    only_unpaired_temperature = walk(include_health=False) + (
        f".{BOX}8.1.5.1.2 = INTEGER: 39\n")
    assert "DNOS System Health" not in generate(only_unpaired_temperature)


def test_bounded_targeted_collection():
    script=(RUNTIME/"discovery_job.sh").read_text()
    start=script.index('DELL_N2128_DNOS_HEALTH_OIDS="')
    end=script.index('"\n    echo "Running Dell N2128PX-ON DNOS health supplemental walks"',start)
    names=[x for x in script[start:end].splitlines()[1:] if x.strip()]
    assert len(names)==9, names
    assert len(set(names))==len(names)
    assert all(re.fullmatch(r"1\.3\.6\.1\.4\.1\.674\.10895\.[0-9.]+",x) for x in names)
    assert all(x.startswith("1.3.6.1.4.1.674.10895.5000.2.6132.1.1.") or
               x == "1.3.6.1.4.1.674.10895.3000.1.2.110.1" for x in names)
    assert not any(x in {"1.3.6.1.4.1.674",
                          "1.3.6.1.4.1.674.10895.5000"} for x in names)
    assert 'grep -Eqi \'N2128PX-ON\'' in script
    assert 'Dell N2128PX-ON optical supplemental walks' in script

if __name__=="__main__":
    test_valid_evidence()
    test_missing_or_wrong_model()
    test_invalid_not_inferred()
    test_absent_and_unpaired_hardware_are_suppressed()
    test_bounded_targeted_collection()
    print("Dell N2128PX-ON DNOS evidence-backed health: PASS")
