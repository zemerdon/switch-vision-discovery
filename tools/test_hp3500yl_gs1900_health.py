#!/usr/bin/env python3
"""Contributed HP 3500yl temperature and GS1900-8 identity/health regression."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[1] / "runtime_src"
HP3500 = "HP J8693A Switch 3500yl-48G"
HP_TEMP = "1.3.6.1.2.1.99.1.1.1.4.25"
ZYXEL = "1.3.6.1.4.1.890.1.15.3."


def generate(raw: str, model: str) -> str:
    with tempfile.TemporaryDirectory(prefix="sv_hp_zyxel_health_") as td:
        p = Path(td) / "evidence.txt"
        p.write_text(raw)
        script = (". " + str(RUNTIME / "discovery_yaml_stage.sh") +
                  "\nwrite_generated_yaml_for_walk " + str(p) +
                  " 10.0.0.1 DEV public\n")
        result = subprocess.run(["sh"], input=script, text=True,
                                capture_output=True, timeout=50)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip(), model
        return result.stdout


def hp3500_walk(*, temp: int | None = 31, status: int = 1, scale: int = 9,
                kind: int = 8, name: str = "Chassis Temperature", model: str = HP3500,
                groups: bool = True) -> str:
    rows = [
        f'.1.3.6.1.2.1.1.1.0 = STRING: "{model}"',
        '.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.11.2.3.7.11.59',
    ]
    for i in range(1, 49):
        rows.append(f'.1.3.6.1.2.1.31.1.1.1.1.{i} = STRING: "{i}"')
        rows.append(f'.1.3.6.1.2.1.2.2.1.8.{i} = INTEGER: up(1)')
    if temp is not None:
        rows.extend((
            f'.1.3.6.1.2.1.47.1.1.1.1.7.25 = STRING: "{name}"',
            f'.1.3.6.1.2.1.99.1.1.1.1.25 = INTEGER: {kind}',
            f'.1.3.6.1.2.1.99.1.1.1.2.25 = INTEGER: {scale}',
            '.1.3.6.1.2.1.99.1.1.1.3.25 = INTEGER: 0',
            f'.1.3.6.1.2.1.99.1.1.1.4.25 = INTEGER: {temp}',
            f'.1.3.6.1.2.1.99.1.1.1.5.25 = INTEGER: {status}',
            '.1.3.6.1.2.1.47.1.1.1.1.7.11 = STRING: "Fan"',
            '.1.3.6.1.2.1.99.1.1.1.1.11 = INTEGER: 1',
            '.1.3.6.1.2.1.99.1.1.1.4.11 = INTEGER: 0',
            '.1.3.6.1.2.1.99.1.1.1.5.11 = INTEGER: 1',
        ))
    if groups:
        for g in (1, 2):
            rows.append(f'.1.3.6.1.2.1.105.1.3.1.1.2.{g} = Gauge32: 199')
            rows.append(f'.1.3.6.1.2.1.105.1.3.1.1.4.{g} = Gauge32: 0')
    return "\n".join(rows) + "\n"


def zyxel_walk(*, present: bool = True, model: str = "GS1900-8",
               cpu: int = 75, memory: int = 13, firmware: bool = True,
               serial: bool = True) -> str:
    rows = [
        f'.1.3.6.1.2.1.1.1.0 = STRING: "Zyxel {model}"',
        '.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.890.1.15',
    ]
    for i in range(1, 9):
        rows.append(f'.1.3.6.1.2.1.31.1.1.1.1.{i} = STRING: GigabitEthernet{i}')
    if present:
        rows.append(f'.{ZYXEL}1.11.0 = STRING: "{model}"')
        if firmware:
            rows.append(f'.{ZYXEL}1.6.0 = STRING: "Firmware 2.9"')
        if serial:
            rows.append(f'.{ZYXEL}1.12.0 = STRING: "synthetic-serial"')
        rows.extend((
            f'.{ZYXEL}2.4.0 = INTEGER: {cpu}',
            f'.{ZYXEL}2.5.0 = INTEGER: {memory}',
            f'.{ZYXEL}2.7.0 = INTEGER: 82',
            f'.{ZYXEL}2.8.0 = INTEGER: 31',
            f'.{ZYXEL}2.9.0 = INTEGER: 27',
        ))
    return "\n".join(rows) + "\n"


def test_hp3500_real_chassis_temperature_only():
    out = generate(hp3500_walk(), HP3500)
    assert f"oid: {HP_TEMP}" in out
    assert "DEV Chassis Temperature" in out
    assert 'unit_of_measurement: "°C"' in out
    assert "device_class: temperature" in out
    assert "Switch Vision DEV Chassis Temperature" in out
    assert "DEV Fan 1 RPM" not in out
    # Standard aggregate groups are already supported: do not introduce a
    # duplicate or reinterpret the 48 group/port PSE rows.
    assert "1.3.6.1.2.1.105.1.3.1.1.2.1" in out
    assert "1.3.6.1.2.1.105.1.3.1.1.2.2" in out


def test_hp3500_missing_invalid_and_wrong_model():
    for kwargs in ({'temp': None}, {'status': 2}, {'scale': 8},
                   {'kind': 1}, {'name': 'Other Sensor'}):
        out = generate(hp3500_walk(**kwargs), HP3500)
        assert f"oid: {HP_TEMP}" not in out, kwargs
    other = generate(hp3500_walk(model='Unrelated Network Switch'), "Other model")
    assert f"oid: {HP_TEMP}" not in other


def test_zyxel_exact_model_identity_cpu_and_memory():
    out = generate(zyxel_walk(), "GS1900-8")
    assert "# Detected model: GS1900-8" in out
    for oid in (
        "1.3.6.1.4.1.890.1.15.3.1.11.0",
        "1.3.6.1.4.1.890.1.15.3.1.6.0",
        "1.3.6.1.4.1.890.1.15.3.1.12.0",
        "1.3.6.1.4.1.890.1.15.3.2.4.0",
        "1.3.6.1.4.1.890.1.15.3.2.5.0",
        "1.3.6.1.4.1.890.1.15.3.2.7.0",
        "1.3.6.1.4.1.890.1.15.3.2.8.0",
        "1.3.6.1.4.1.890.1.15.3.2.9.0",
    ):
        assert "oid: " + oid in out, oid
    assert 'name: DEV Memory Utilization' in out
    assert 'unit_of_measurement: "%"' in out
    assert "1.3.6.1.4.1.890.1.15.3.2.4.3" not in out
    assert "Switch Vision DEV CPU and Memory" in out
    assert "Fan RPM" not in out


def test_zyxel_missing_bad_values_and_other_variants():
    out = generate(zyxel_walk(present=False), "GS1900-8")
    assert "DEV Memory Utilization" not in out
    assert "DEV Firmware" not in out
    out = generate(zyxel_walk(cpu=108, memory=999, firmware=False, serial=False), "GS1900-8")
    assert "DEV CPU 5sec" in out
    assert "name: DEV CPU\n" not in out
    assert "DEV Memory Utilization" not in out
    assert "DEV Firmware" not in out
    assert "DEV Serial" not in out
    out = generate(zyxel_walk(model="GS1900-8HP"), "GS1900-8HP")
    assert "# Detected model: GS1900-8" not in out
    assert "DEV Memory Utilization" not in out
    assert "DEV Firmware" not in out


def test_zyxel_shared_identity_does_not_conflate_models():
    # These three products share sysObjectID 890.1.15 but differ physically.
    gs1915 = generate(zyxel_walk(model="GS1915-24EP"), "GS1915-24EP")
    assert "# Detected model: GS1915-24EP" in gs1915
    assert "DEV CPU and Memory" in gs1915
    assert f"oid: {ZYXEL}2.5.0" in gs1915
    assert "DEV Firmware" in gs1915
    assert "DEV Serial" in gs1915
    assert "DEV Fan 1 RPM" not in gs1915

    xs1930 = generate(zyxel_walk(model="XS1930-10"), "XS1930-10")
    assert "# Detected model: XS1930-10" in xs1930
    assert f"oid: {ZYXEL}2.5.0" in xs1930
    assert f"oid: {ZYXEL}2.4.3" not in xs1930

    # No loosely matching product names are accepted as exact models.
    for model in ("GS1900-8-HP", "GS1915-24EP-PLUS", "XS1930-10HP"):
        other = generate(zyxel_walk(model=model), model)
        assert f"# Detected model: {model.split('-')[0]}-" not in other
        assert "DEV CPU and Memory" not in other


if __name__ == "__main__":
    test_hp3500_real_chassis_temperature_only()
    test_hp3500_missing_invalid_and_wrong_model()
    test_zyxel_exact_model_identity_cpu_and_memory()
    test_zyxel_missing_bad_values_and_other_variants()
    test_zyxel_shared_identity_does_not_conflate_models()
    print("HP 3500yl and Zyxel shared-OID model health tests: PASS")
