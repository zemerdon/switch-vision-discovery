#!/usr/bin/env python3
"""Exact-model Dell N4032F DNOS system-health and topology regressions."""
from __future__ import annotations

import test_dell_n2128px_dnos_health as shared

SWITCH = shared.SWITCH
BOX = shared.BOX
GLOBAL = shared.GLOBAL


def walk(*, model="N4032F", object_id="1.3.6.1.4.1.674.10895.3044", health=True) -> str:
    rows = [
        f'.1.3.6.1.2.1.1.1.0 = STRING: "Dell Networking {model}, 6.5.4.23"',
        f'.1.3.6.1.2.1.1.2.0 = OID: .{object_id}',
    ]
    for index in range(1, 25):
        rows.extend((
            f'.1.3.6.1.2.1.31.1.1.1.1.{index} = STRING: Te1/0/{index}',
            f'.1.3.6.1.2.1.2.2.1.8.{index} = INTEGER: down(2)',
        ))
    for index in (59, 60):
        rows.extend((
            f'.1.3.6.1.2.1.31.1.1.1.1.{index} = STRING: Fo1/1/{index - 58}',
            f'.1.3.6.1.2.1.2.2.1.8.{index} = INTEGER: up(1)',
        ))
    if health:
        metrics = [
            (SWITCH + "10.0", "Gauge32", 17),
            (SWITCH + "11.0", "Gauge32", 13),
            (SWITCH + "12.0", "Gauge32", 7),
            (SWITCH + "1.0", "INTEGER", 589360),
            (SWITCH + "2.0", "INTEGER", 1723232),
            (GLOBAL, "INTEGER", 4),
            (BOX + "6.1.3.1", "INTEGER", 2),
            (BOX + "6.1.4.1", "INTEGER", 14000),
            (BOX + "6.1.3.2", "INTEGER", 5),
            (BOX + "6.1.4.2", "INTEGER", 0),
            (BOX + "7.1.3.1", "INTEGER", 2),
            (BOX + "7.1.3.2", "INTEGER", 5),
            (BOX + "7.1.3.3", "INTEGER", 1),
        ]
        for index, value in enumerate((34, 37, 40, 45), 1):
            metrics.extend((
                (BOX + f"8.1.4.1.{index}", "INTEGER", 1),
                (BOX + f"8.1.5.1.{index}", "INTEGER", value),
            ))
        rows.extend(f".{oid} = {value_type}: {value}" for oid, value_type, value in metrics)
    return "\n".join(rows) + "\n"


def test_exact_model_health():
    result = shared.generate(walk())
    assert "# Detected model: N4032F" in result
    assert "Switch Vision DEV DNOS System Health" in result
    expected = (
        SWITCH + "10.0", SWITCH + "11.0", SWITCH + "12.0",
        SWITCH + "1.0", SWITCH + "2.0", GLOBAL,
        BOX + "6.1.3.1", BOX + "6.1.4.1", BOX + "6.1.3.2",
        BOX + "7.1.3.1", BOX + "7.1.3.2",
    )
    for oid in expected:
        assert "oid: " + oid in result, oid
    assert "oid: " + BOX + "6.1.4.2" not in result, "Zero fan RPM must not be emitted"
    assert "oid: " + BOX + "7.1.3.3" not in result, "Absent PSU must not be emitted"
    for index in range(1, 5):
        assert "oid: " + BOX + f"8.1.5.1.{index}" in result
        assert "oid: " + BOX + f"8.1.4.1.{index}" in result
    assert 'unit_of_measurement: "°C"' in result
    assert 'unit_of_measurement: "rpm"' in result
    assert 'unit_of_measurement: "MiB"' in result
    assert "DEV SFP 10G 1 Status" in result
    assert "DEV SFP 10G 24 Status" in result
    assert "DEV QSFP 40G 1 Status" in result
    assert "DEV QSFP 40G 2 Status" in result
    assert "Optical diagnostics" not in result, "N2128 DDMI must not leak"


def test_incorrect_identity_suppressed():
    for override in (
        {"model": "N4032F-PLUS"}, {"model": "N4032FX"},
        {"object_id": "1.3.6.1.4.1.674.10895.3077"},
        {"model": "N2128PX-ON"}, {"model": "Unrelated Switch"},
        {"health": False},
    ):
        result = shared.generate(walk(**override))
        assert "DNOS System Health" not in result, override
        assert "oid: " + SWITCH + "10.0" not in result, override
        assert "oid: " + BOX + "8.1.5.1.1" not in result, override
    mismatch = shared.walk().replace("674.10895.3077", "674.10895.3044")
    assert "DNOS System Health" not in shared.generate(mismatch)
    suffix = shared.walk(model="N2128PX-ON-PLUS")
    assert "DNOS System Health" not in shared.generate(suffix)


def test_optional_temperature_rows():
    source = walk()
    absent = source.replace(
        f".{BOX}8.1.4.1.1 = INTEGER: 1",
        f".{BOX}8.1.4.1.1 = INTEGER: 5",
    )
    result = shared.generate(absent)
    assert "oid: " + BOX + "8.1.5.1.1" not in result
    assert "oid: " + BOX + "8.1.5.1.2" in result
    missing = source.replace(f".{BOX}8.1.4.1.2 = INTEGER: 1\n", "")
    result = shared.generate(missing)
    assert "oid: " + BOX + "8.1.5.1.2" not in result
    assert "oid: " + BOX + "8.1.5.1.1" in result


def test_exact_model_collection():
    script = (shared.RUNTIME / "discovery_job.sh").read_text()
    assert "N2128PX-ON([^[:alnum:]_-]|$)|N4032F([^[:alnum:]_-]|$)" in script
    assert "Dell exact-model DNOS health supplemental walks" in script
    assert "Dell N2128PX-ON optical supplemental walks" in script


if __name__ == "__main__":
    test_exact_model_health()
    test_incorrect_identity_suppressed()
    test_optional_temperature_rows()
    test_exact_model_collection()
    print("Dell N4032F DNOS exact-model health and port isolation: PASS")
