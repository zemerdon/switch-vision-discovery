#!/usr/bin/env python3
"""Evidence-bounded HP 1810-24G/J9803A identity collection regressions."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
MODEL = "HP 1810-24G"
SYSOBJECT = "1.3.6.1.4.1.11.2.3.7.11.151"
SEMI = "1.3.6.1.4.1.11.2.36.1.1.2."


def test_model_scoped_targeted_selection() -> None:
    source = (RUNTIME / "discovery_job.sh").read_text()
    start = source.index('  HP_1810_VERSION_OIDS=""')
    end = source.index('  for oid in $HP_1810_VERSION_OIDS; do', start)
    block = source[start:end]
    with tempfile.TemporaryDirectory(prefix="sv_1810_identity_select_") as td:
        path = Path(td) / "precheck"
        for descr, mode, expected in (
            ("HP 1810-24G, PL.0.15", "targeted", [SEMI+"6", SEMI+"8"]),
            ("HP 1810-24G, PL.0.15", "full", []),
            ("HP ProCurve 1810G-24", "targeted", []),
            ("HP 1810-24G-PoE", "targeted", []),
            ("Zyxel GS1900-8", "targeted", []),
        ):
            path.write_text(f'.1.3.6.1.2.1.1.1.0 = STRING: "{descr}"\n')
            script = ('set -eu\nSNMP_PRECHECK_PATH="' + str(path) + '"\n' +
                      'LIVE_SNMPWALK_MODE=' + mode + '\n' + block +
                      '\nprintf "%s\\n" "$HP_1810_VERSION_OIDS"\n')
            result = subprocess.run(["sh"], input=script, capture_output=True,
                                    text=True, timeout=10)
            assert result.returncode == 0, result.stderr
            got = [line for line in result.stdout.splitlines() if line]
            assert got == expected, (descr, mode, got)


def walk(*, oid=SYSOBJECT, descr="HP 1810-24G, PL.0.15",
         firmware=True, rom=True, faulty_serial=True):
    rows = [
        f'.1.3.6.1.2.1.1.1.0 = STRING: "{descr}"',
        f'.1.3.6.1.2.1.1.2.0 = OID: .{oid}',
    ]
    for index in range(1, 27):
        rows.extend((
            f'.1.3.6.1.2.1.31.1.1.1.1.{index} = STRING: "{index}"',
            f'.1.3.6.1.2.1.2.2.1.2.{index} = STRING: "{index}"',
            f'.1.3.6.1.2.1.2.2.1.3.{index} = INTEGER: ethernetCsmacd(6)',
            f'.1.3.6.1.2.1.2.2.1.8.{index} = INTEGER: up(1)',
        ))
    if firmware:
        rows.append(f'.{SEMI}6.0 = STRING: "PL.2.07"')
    if rom:
        rows.append(f'.{SEMI}8.0 = STRING: "boot-image-test"')
    if faulty_serial:
        rows.append(f'.{SEMI}9.0 = No more variables left in this MIB View')
    return "\n".join(rows) + "\n"


def generate(text: str, *, physical=True) -> str:
    with tempfile.TemporaryDirectory(prefix="sv_hp1810_generator_") as td:
        base = Path(td)
        input_file = base / "walk.txt"
        input_file.write_text(text)
        norm = base / "normalized.txt"
        if physical:
            args = ["sh", str(RUNTIME / "physical_contract_prepare.sh"),
                    str(input_file), str(norm), str(base / "cap.json"),
                    str(base / "contract.json")]
            result = subprocess.run(args, capture_output=True, text=True, timeout=45)
            assert result.returncode == 0, result.stderr
            contract = json.loads((base / "contract.json").read_text())
            assert contract["status"] == "resolved", contract["errors"]
            assert contract["observed"]["physical"] == 26, contract["observed"]
        else:
            norm.write_text(text)
        run = (". " + str(RUNTIME / "discovery_yaml_stage.sh") +
               "\nwrite_generated_yaml_for_walk " + str(norm) +
               " 10.0.0.1 TEST public\n")
        result = subprocess.run(["sh"], input=run, capture_output=True,
                                text=True, timeout=45)
        assert result.returncode == 0, result.stderr
        return result.stdout


def test_hp1810_verified_identity_entities() -> None:
    yaml = generate(walk())
    assert "# Detected model: HP 1810-24G" in yaml
    assert "TEST Firmware" in yaml and SEMI+"6.0" in yaml
    assert "TEST Boot ROM" in yaml and SEMI+"8.0" in yaml
    assert "TEST Serial" not in yaml and SEMI+"9.0" not in yaml


def test_hp1810_missing_optional_and_other_identity() -> None:
    yaml = generate(walk(firmware=False, rom=True))
    assert "TEST Firmware" not in yaml
    assert "TEST Boot ROM" in yaml
    yaml = generate(walk(firmware=True, rom=False))
    assert "TEST Firmware" in yaml
    assert "TEST Boot ROM" not in yaml
    yaml = generate(walk(oid="1.3.6.1.4.1.11.2.3.7.11.150"), physical=False)
    assert "TEST Boot ROM" not in yaml
    assert "TEST Firmware" not in yaml


def test_reviewed_mib_definitions() -> None:
    db = RUNTIME / "opt/switch-vision/mib_database/vendors/hp_aruba/identity.json"
    data = json.loads(db.read_text())
    row = data["reviewed_exact_model_identity"]["HP 1810-24G (J9803A)"]
    assert row["sys_object_id"] == SYSOBJECT
    assert row["firmware_version_oid"] == SEMI+"6.0"
    assert row["boot_rom_version_oid"] == SEMI+"8.0"
    assert "serial" not in row


if __name__ == "__main__":
    test_model_scoped_targeted_selection()
    test_hp1810_verified_identity_entities()
    test_hp1810_missing_optional_and_other_identity()
    test_reviewed_mib_definitions()
    print("HP 1810-24G exact-model SEMI-MIB identity tests passed")
