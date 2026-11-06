#!/usr/bin/env python3
"""HP 3500yl/5406zl CPU telemetry: exact-model and MIB-valid contracts."""
from __future__ import annotations

import tempfile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
CPU = "1.3.6.1.4.1.11.2.14.11.5.1.9.6.1.0"
HP3500 = "HP J8693A Switch 3500yl-48G"
HP5406 = "HP J8697A Switch 5406zl"


def walk(*, model: str = HP3500, sys_object: str | None = None,
         value: str | None = "INTEGER: 45", source_oid: str = CPU) -> str:
    if sys_object is None:
        sys_object = (
            "1.3.6.1.4.1.11.2.3.7.11.50" if "5406zl" in model
            else "1.3.6.1.4.1.11.2.3.7.11.59"
        )
    lines = [
        f'.1.3.6.1.2.1.1.1.0 = STRING: "{model}"',
        f".1.3.6.1.2.1.1.2.0 = OID: .{sys_object}",
    ]
    if value is not None:
        lines.append(f".{source_oid} = {value}")
    return "\n".join(lines) + "\n"


def generate(raw: str) -> str:
    with tempfile.TemporaryDirectory(prefix="sv_hp_cpu_contract_") as tmp:
        p = Path(tmp) / "evidence.walk"
        p.write_text(raw, encoding="utf8")
        commands = (
            ". " + str(RUNTIME / "discovery_yaml_stage.sh") +
            "\nwrite_generated_yaml_for_walk " + str(p) +
            " 192.0.2.20 HPT readonly\n"
        )
        result = subprocess.run(
            ["sh"], input=commands, text=True, capture_output=True,
            timeout=45, check=False,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout


def test_exact_cpu_models() -> None:
    for model, value in ((HP3500, 37), (HP5406, 44)):
        content = generate(walk(model=model, value=f"INTEGER: {value}"))
        assert f"# Detected model: {model}" in content, model
        assert "Switch Vision HPT Chassis CPU" in content, model
        assert f"oid: {CPU}" in content, model
        assert "HPT CPU Utilization" in content
        assert 'unit_of_measurement: "%"' in content
        assert "state_class: measurement" in content


def test_valid_bounds_and_mib_type() -> None:
    for value in ("INTEGER: 0", "INTEGER: 100"):
        assert f"oid: {CPU}" in generate(walk(value=value))
    for bad in (
        None, "INTEGER: 101", "INTEGER: -1", "INTEGER: 999",
        "Gauge32: 43", "STRING: \"43\"", "INTEGER: unknown",
    ):
        result = generate(walk(value=bad))
        assert f"oid: {CPU}" not in result, bad
        assert "Chassis CPU" not in result, bad


def test_model_and_object_must_agree() -> None:
    cases = [
        {"model": HP3500, "sys_object": "1.3.6.1.4.1.11.2.3.7.11.50"},
        {"model": HP5406, "sys_object": "1.3.6.1.4.1.11.2.3.7.11.59"},
        {"model": HP3500, "sys_object": "1.3.6.1.4.1.11.2.3.7.11.590"},
        {"model": HP5406, "sys_object": "1.3.6.1.4.1.11.2.3.7.11.501"},
        {"model": "HP J8693AX Switch 3500yl-48G"},
        {"model": "HP J8693A Switch 3500yl-48GX"},
        {"model": "HP J8697AX Switch 5406zl"},
        {"model": "HP J8697A Switch 5406zl-PLUS"},
        {"model": "Unrelated Aruba hardware"},
        {"model": HP3500, "source_oid": CPU[:-2] + ".10"},
    ]
    for kw in cases:
        result = generate(walk(**kw))
        assert f"oid: {CPU}" not in result, kw
        assert "Chassis CPU" not in result, kw


def test_targeted_oid_bounds() -> None:
    source = (RUNTIME / "discovery_job.sh").read_text()
    assert source.count('hp_cpu_oid="1.3.6.1.4.1.11.2.14.11.5.1.9.6.1"') == 1
    assert "J8693A.*3500yl-48G" in source
    assert "J8697A.*5406zl" in source
    assert "HP chassis CPU supplemental" in source
    assert '"$LIVE_SNMPWALK_MODE" != "full"' in source
    assert "hp_cpu_oid" not in (RUNTIME / "discovery_report_stage.sh").read_text()


if __name__ == "__main__":
    test_exact_cpu_models()
    test_valid_bounds_and_mib_type()
    test_model_and_object_must_agree()
    test_targeted_oid_bounds()
    print("HP 3500yl/5406zl evidence-backed chassis CPU: PASS")
