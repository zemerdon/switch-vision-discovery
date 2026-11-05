"""Evidence-bounded HP 5406zl optional telemetry and targeted walk regressions."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from test_hp_5406zl_modular_registration import RUNTIME, fixture

DISCOVERY_JOB = RUNTIME / "discovery_job.sh"


def supplemental_rows(*, temperature=True, sensors=True):
    rows = []
    # Full evidence: 72 module-backed RJ45 PSE interfaces plus 24 empty-slot
    # placeholders. A/B/E groups expose 91 W budgets; C has 0 W.
    for group, begin in ((1, 1), (2, 25), (3, 49), (5, 97)):
        for index in range(begin, begin + 24):
            key = f"{group}.{index}"
            rows.extend((
                f".1.3.6.1.2.1.105.1.1.1.3.{key} = INTEGER: 1",
                f".1.3.6.1.2.1.105.1.1.1.6.{key} = INTEGER: {1 if group == 3 else 2}",
                f".1.3.6.1.2.1.105.1.1.1.10.{key} = INTEGER: 1",
            ))
        rows.extend((
            f".1.3.6.1.2.1.105.1.3.1.1.2.{group} = Gauge32: {0 if group == 3 else 91}",
            f".1.3.6.1.2.1.105.1.3.1.1.4.{group} = Gauge32: 0",
        ))
    if sensors:
        for index, name, typ, value in ((11, "Fan 1", 1, 0),
                                        (12, "Fan 2", 1, 0),
                                        (25, "Chassis Temperature", 8, 28)):
            rows.extend((
                f'.1.3.6.1.2.1.47.1.1.1.1.7.{index} = STRING: "{name}"',
                f".1.3.6.1.2.1.99.1.1.1.1.{index} = INTEGER: {typ}",
                f".1.3.6.1.2.1.99.1.1.1.2.{index} = INTEGER: 9",
                f".1.3.6.1.2.1.99.1.1.1.3.{index} = INTEGER: 0",
                f".1.3.6.1.2.1.99.1.1.1.4.{index} = INTEGER: {value}",
                f".1.3.6.1.2.1.99.1.1.1.5.{index} = INTEGER: 1",
            ))
    if not temperature:
        rows = [x for x in rows if not x.startswith(".1.3.6.1.2.1.99.1.1.1.2.25")]
    return "\n".join(rows) + "\n"


def generate(*, populated="ABDE", temperature=True, sensors=True):
    source = fixture(populated=populated) + supplemental_rows(
        temperature=temperature, sensors=sensors
    )
    with tempfile.TemporaryDirectory(prefix="sv_5406zl_optionals_") as td:
        root = Path(td)
        walk = root / "input.txt"
        walk.write_text(source)
        norm = root / "normalized.txt"
        cmd = ["sh", str(RUNTIME / "physical_contract_prepare.sh"),
               str(walk), str(norm), str(root / "caps.json"),
               str(root / "contract.json")]
        prepared = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        assert prepared.returncode == 0, prepared.stderr
        script = (
            "set -eu\n. " + str(RUNTIME / "discovery_yaml_stage.sh") +
            "\nwrite_generated_yaml_for_walk " + str(norm) + " 10.0.0.1 TEST public\n"
        )
        generated = subprocess.run(["sh"], input=script, capture_output=True,
                                   text=True, timeout=40)
        assert generated.returncode == 0, generated.stderr
        return generated.stdout


def test_targeted_mode_collects_entity_aliases():
    script = DISCOVERY_JOB.read_text()
    match = re.search(r'LIVE_OIDS="\n(.*?)\n"', script, re.S)
    assert match, "targeted OID list absent"
    assert "1.3.6.1.2.1.47.1.1.1.1" in match.group(1).splitlines()
    assert "1.3.6.1.2.1.47.1.3.2.1.2" not in match.group(1).splitlines()
    assert "1.3.6.1.2.1.99.1.1.1" in match.group(1).splitlines()
    # Execute the actual narrow conditional from discovery_job.sh. Other
    # models must not gain an extra possibly unsupported SNMP table request.
    start = script.index("    # ENTITY-MIB alias joins are required")
    end = script.index("    for oid in $LIVE_OIDS; do", start)
    selection = script[start:end]
    with tempfile.TemporaryDirectory(prefix="sv_hp_targeted_") as td:
        precheck = Path(td) / "precheck.txt"
        for identity, should_collect in (
            ("HP J8697A Switch 5406zl", True),
            ("Cisco WS-C3650", False),
        ):
            precheck.write_text(identity + "\n")
            shell = ("LIVE_OIDS=1.3.6.1.2.1.1\nSNMP_PRECHECK_PATH=" +
                     str(precheck) + "\n" + selection +
                     "\nprintf '%s\n' \"$LIVE_OIDS\"\n")
            result = subprocess.run(["sh"], input=shell, capture_output=True,
                                    text=True, timeout=5)
            assert result.returncode == 0, result.stderr
            aliases = "1.3.6.1.2.1.47.1.3.2.1.2" in result.stdout.splitlines()
            assert aliases is should_collect, identity


def test_module_bound_poe_and_chassis_sensors():
    output = generate()
    assert output.count(" PoE Status Code") == 72
    assert output.count(" PoE Class Code") == 72
    assert output.count(" PoE Admin Code") == 72
    for group in (1, 2, 5):
        name = "ABCDEF"[group - 1]
        assert f"TEST PoE Module {name} Budget W" in output
        assert f"TEST PoE Module {name} Used W" in output
    assert "TEST PoE Module C" not in output
    assert "1.3.6.1.2.1.105.1.1.1.6.3.49" not in output
    assert "1.3.6.1.2.1.105.1.3.1.1.2.3" not in output
    assert "TEST Chassis Temperature" in output
    assert "oid: 1.3.6.1.2.1.99.1.1.1.4.25" in output
    assert "unit_of_measurement: \"°C\"" in output
    assert "TEST Fan 1 Sensor Status Code" in output
    assert "TEST Fan 2 Sensor Status Code" in output
    assert "RPM" not in output


def test_unpopulated_modules_cannot_inherit_pse_rows():
    output = generate(populated="AD")
    assert output.count(" PoE Status Code") == 24
    assert "TEST PoE Module A Budget W" in output
    for slot in "BCE":
        assert f"TEST PoE Module {slot}" not in output
    assert "1.3.6.1.2.1.105.1.1.1.6.2.25" not in output
    assert "1.3.6.1.2.1.105.1.1.1.6.5.97" not in output


def test_optional_temperature_requires_evidence():
    output = generate(temperature=False)
    assert "TEST Chassis Temperature" not in output
    assert "TEST Fan 1 Sensor Status Code" in output
    output = generate(sensors=False)
    assert "TEST Chassis Temperature" not in output
    assert "TEST Fan 1 Sensor Status Code" not in output


if __name__ == "__main__":
    test_targeted_mode_collects_entity_aliases()
    test_module_bound_poe_and_chassis_sensors()
    test_unpopulated_modules_cannot_inherit_pse_rows()
    test_optional_temperature_requires_evidence()
    print("HP 5406zl targeted/PoE/chassis telemetry tests passed")
