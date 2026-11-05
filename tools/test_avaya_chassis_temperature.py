#!/usr/bin/env python3
"""Evidence-backed Avaya ERS 3524GT-PWR+ half-degree temperature contract."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
SOURCE_OID = "1.3.6.1.4.1.45.1.6.3.7.1.1.5"
SYSOBJECT = "1.3.6.1.4.1.45.3.80.4"


def targeted_oids(descr: str, mode: str = "targeted") -> list[str]:
    script = (RUNTIME / "discovery_job.sh").read_text()
    start = script.index('  AVAYA_CHASSIS_TEMP_OIDS=""')
    end = script.index('  for oid in $AVAYA_CHASSIS_TEMP_OIDS; do', start)
    clause = script[start:end]
    with tempfile.TemporaryDirectory(prefix="sv_avaya_temp_targeted_") as tmp:
        precheck = Path(tmp) / "precheck"
        precheck.write_text(f'.1.3.6.1.2.1.1.1.0 = STRING: "{descr}"\n')
        shell = ('set -eu\nSNMP_PRECHECK_PATH="' + str(precheck) +
                 '"\nLIVE_SNMPWALK_MODE="' + mode + '"\n' + clause +
                 '\nprintf "%s\\n" "$AVAYA_CHASSIS_TEMP_OIDS"\n')
        result = subprocess.run(["sh"], input=shell, text=True,
                                capture_output=True, timeout=10)
        assert result.returncode == 0, result.stderr
        return [line for line in result.stdout.splitlines() if line]


def make_walk(*, temperature: str | None = "76", row: str = "5.10.0",
              value_type: str = "INTEGER",
              model: str = "3524GT-PWR+", sysobject: str = SYSOBJECT) -> str:
    lines = [
        f'.1.3.6.1.2.1.1.1.0 = STRING: Ethernet Routing Switch {model}',
        f'.1.3.6.1.2.1.1.2.0 = OID: .{sysobject}',
    ]
    for idx in range(1, 25):
        lines.extend([
            f'.1.3.6.1.2.1.2.2.1.2.{idx} = STRING: Slot 1 / Port {idx}',
            f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: ifc{idx} (Slot: 1 Port: {idx})',
        ])
    if temperature is not None:
        lines.append(f'.{SOURCE_OID}.{row} = {value_type}: {temperature}')
    return "\n".join(lines) + "\n"


def generate(text: str, *, physical: bool = True) -> str:
    with tempfile.TemporaryDirectory(prefix="sv_avaya_temp_yaml_") as td:
        base = Path(td)
        walk = base / "walk.txt"
        norm = base / "normalized.txt"
        walk.write_text(text)
        if physical:
            cmd = ["sh", str(RUNTIME / "physical_contract_prepare.sh"),
                   str(walk), str(norm), str(base / "caps.json"),
                   str(base / "contract.json")]
            result = subprocess.run(cmd, text=True, capture_output=True, timeout=55)
            assert result.returncode == 0, result.stderr
            contract = json.loads((base / "contract.json").read_text())
            assert contract["status"] == "resolved", contract
            assert contract["observed"]["physical"] == 24, contract
        else:
            norm.write_text(text)
        script = (". " + str(RUNTIME / "discovery_yaml_stage.sh") +
                  "\nwrite_generated_yaml_for_walk " + str(norm) +
                  " 10.0.0.1 AVAYA public\n")
        result = subprocess.run(["sh"], input=script, text=True,
                                capture_output=True, timeout=45)
        assert result.returncode == 0, result.stderr
        return result.stdout


def test_only_exact_model_gets_supplemental_targeted_walk():
    assert targeted_oids("Ethernet Routing Switch 3524GT-PWR+") == [SOURCE_OID]
    assert targeted_oids("Ethernet Routing Switch 3524GT-PWR+", "full") == []
    for other in (
        "Ethernet Routing Switch 3524GT",
        "Ethernet Routing Switch 3524GT-PWR+X",
        "Ethernet Routing Switch 3510GT-PWR+",
        "Cisco WS-C3650",
    ):
        assert targeted_oids(other) == [], other


def test_generated_chassis_temperature_is_scaled():
    generated = generate(make_walk())
    assert "# Detected model: 3524GT-PWR+" in generated
    assert "AVAYA Chassis Temperature" in generated
    assert f"oid: {SOURCE_OID}.5.10.0" in generated
    assert 'unit_of_measurement: "°C"' in generated
    assert 'device_class: temperature' in generated
    assert 'state_class: measurement' in generated
    assert 'template: "{{ (value | float / 2) | round(1) }}"' in generated
    assert "Switch Vision AVAYA Chassis Temperature" in generated
    assert 76 / 2 == 38.0


def test_no_phantom_sensors_or_wrong_models():
    for temperature, value_type in ((None, "INTEGER"), ("999", "INTEGER"),
                                    ("-999", "INTEGER"), ("74", "Gauge32")):
        generated = generate(make_walk(temperature=temperature, value_type=value_type))
        assert "AVAYA Chassis Temperature" not in generated
    generated = generate(make_walk(model="3510GT", sysobject="1.3.6.1.4.1.45.3.80.3"),
                         physical=False)
    assert "AVAYA Chassis Temperature" not in generated
    generated = generate(make_walk(temperature="73"))
    assert f"oid: {SOURCE_OID}.5.10.0" in generated
    assert 73 / 2 == 36.5


def test_curated_avaya_mib_candidate():
    import importlib.util

    db = RUNTIME / "opt/switch-vision/mib_database"
    spec = importlib.util.spec_from_file_location("sv_avaya_sensors", RUNTIME / "vendor_sensor_scan.py")
    assert spec and spec.loader
    scanner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scanner)
    with tempfile.TemporaryDirectory(prefix="sv_avaya_temp_mib_") as tmp:
        walk = Path(tmp) / "walk.txt"
        walk.write_text(f'.{SOURCE_OID}.5.10.0 = INTEGER: 76\n')
        result = scanner.build(walk, {"device": {"vendor": "avaya"}}, db)
        candidates = [x for x in result["candidates"] if x["source"] == "curated-known-oid"]
        assert len(candidates) == 1, candidates
        assert candidates[0]["category"] == "temperature"
        assert candidates[0]["confidence"] == "high"
        assert candidates[0]["unit"] == "0.5 °C"
        metadata = json.loads((db / "vendors/avaya/sensors.json").read_text())
        assert metadata["known_oids"][0]["scale_to_celsius"] == 0.5


if __name__ == "__main__":
    test_only_exact_model_gets_supplemental_targeted_walk()
    test_generated_chassis_temperature_is_scaled()
    test_no_phantom_sensors_or_wrong_models()
    test_curated_avaya_mib_candidate()
    print("Avaya exact-model half-degree chassis temperature: PASS")
