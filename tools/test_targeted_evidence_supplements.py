#!/usr/bin/env python3
"""Offline regression for evidence-backed exact-model SNMP supplements."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "runtime_src" / "discovery_job.sh"
DELL = "1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1"
ZYXEL = "1.3.6.1.4.1.890.1.15.3"


def targeted_extras(identity: str, mode: str = "targeted") -> list[str]:
    text = SCRIPT.read_text()
    start = text.index('  MODEL_SUPPLEMENTAL_OIDS=""')
    stop = text.index('  for oid in $MODEL_SUPPLEMENTAL_OIDS; do', start)
    block = text[start:stop]
    with tempfile.TemporaryDirectory(prefix="sv_targeted_evidence_") as td:
        p = Path(td) / "precheck.txt"
        p.write_text(identity + "\n")
        shell = (
            "set -eu\nSNMP_PRECHECK_PATH=" + str(p) + "\n" +
            "LIVE_SNMPWALK_MODE=" + mode + "\n" +
            block + "\nprintf '%s\\n' \"$MODEL_SUPPLEMENTAL_OIDS\"\n"
        )
        r = subprocess.run(["sh"], input=shell, text=True,
                           capture_output=True, timeout=10)
        assert r.returncode == 0, r.stderr
        return [s.strip() for s in r.stdout.splitlines() if s.strip()]


def test_bounded_exact_model_selection():
    # Dell optical collection is already implemented in its existing
    # supplemental path; never add it a second time.
    assert targeted_extras("Dell N2128PX-ON") == []
    script = SCRIPT.read_text()
    assert "Running Dell N2128PX-ON optical supplemental walks" in script
    assert DELL + ".18" in script and DELL + ".19" in script
    # A shared sysObjectID does not imply shared hardware telemetry.
    assert targeted_extras("Zyxel GS1900-8") == [
        ZYXEL + ".1", ZYXEL + ".2",
        "1.3.6.1.2.1.17.7.1.4.2.1.4",
    ]
    assert targeted_extras("Zyxel GS1915-24EP") == [
        ZYXEL + ".1", ZYXEL + ".2",
    ]
    assert targeted_extras("Zyxel XS1930-10") == [
        ZYXEL + ".1", ZYXEL + ".2", ZYXEL + ".26",
    ]
    for identity in ("Zyxel GS1900-8HP", "Zyxel GS1915-24EP-PLUS",
                     "Zyxel XS1930-10HP", "Zyxel GS1900-16", "Zyxel GS1900-24E"):
        assert targeted_extras(identity) == [], identity
    for model in ("GS1900-8", "GS1915-24EP", "XS1930-10"):
        assert targeted_extras("Zyxel " + model, mode="full") == []
    for identity in ("Cisco C3650", "Dell N4032F", "HP J8697A Switch 5406zl",
                     "MikroTik CRS328-24P-4S+", "Juniper EX3300"):
        assert targeted_extras(identity) == [], identity


def test_source_generator_uses_queried_subtrees():
    source = (ROOT / "runtime_src" / "discovery_yaml_stage.sh").read_text()
    assert DELL + ".18.1." in source.replace("\\", "")
    assert DELL + ".19.1." in source.replace("\\", "")
    assert ZYXEL + ".3" not in targeted_extras("Dell N2128PX-ON")
    for part in (ZYXEL + ".1.", ZYXEL + ".2.", ZYXEL + ".26."):
        assert part in source.replace("\\", "")


def test_curated_dell_sensor_mib_mapping():
    # Reviewed numeric definitions are shipped with the existing vendor MIB
    # database; no external MIB download is required to parse these OIDs.
    import importlib.util
    db = ROOT / "runtime_src/opt/switch-vision/mib_database"
    module = ROOT / "runtime_src/vendor_sensor_scan.py"
    spec = importlib.util.spec_from_file_location("sv_vendor_sensor_scan", module)
    assert spec and spec.loader
    scanner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scanner)
    with tempfile.TemporaryDirectory(prefix="sv_dell_mib_") as tmp:
        walk = Path(tmp) / "walk.txt"
        walk.write_text(
            ".1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.18.1.2.29 = INTEGER: 315\n"
            ".1.3.6.1.4.1.674.10895.5000.2.6132.1.1.43.1.18.1.5.29 = INTEGER: -42\n"
        )
        result = scanner.build(walk, {"device": {"vendor": "dell"}}, db)
        assert result["pack_loaded"]
        assert result["counts_by_category"]["temperature"] == 1
        assert result["counts_by_category"]["environment"] == 1
        assert all(x["source"] == "curated-known-oid" for x in result["candidates"])
        assert all(x["confidence"] == "high" for x in result["candidates"])


if __name__ == "__main__":
    test_bounded_exact_model_selection()
    test_source_generator_uses_queried_subtrees()
    test_curated_dell_sensor_mib_mapping()
    print("Targeted evidence-derived exact-model OID selection: PASS")
