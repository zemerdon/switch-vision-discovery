from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime_src" / "discovery_job.sh"


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    required_helpers = (
        "function poe_aggregate_name(name, ordinal)",
        "ordinal = ++poe_aggregate_name_count[name]",
        'return name " Group " ordinal',
        "function yaml_poe_aggregate_sensor(oid, name)",
        "function yaml_poe_aggregate_sensor_meta(oid, name, transform, unit, device_class, state_class, icon)",
    )
    for marker in required_helpers:
        assert marker in source, marker

    aggregate_paths = (
        (
            "MikroTik aggregate PoE consumption",
            'yaml_poe_aggregate_sensor_meta("1.3.6.1.4.1.14988.1.1.3.100.1.3." idx, prefix " PoE Used"',
        ),
        (
            "Cisco PoE supply name",
            'yaml_poe_aggregate_sensor("1.3.6.1.4.1.9.9.402.1.3.1.2." idx, label " PoE Supply Name")',
        ),
        (
            "Cisco PoE supply status",
            'yaml_poe_aggregate_sensor("1.3.6.1.4.1.9.9.402.1.3.1.3." idx, label " PoE Supply Status")',
        ),
        (
            "Cisco extended PoE used",
            'yaml_poe_aggregate_sensor("1.3.6.1.4.1.9.9.402.1.3.1.4." idx, label " PoE Used " poe_unit)',
        ),
        (
            "Cisco extended PoE budget",
            'yaml_poe_aggregate_sensor("1.3.6.1.4.1.9.9.402.1.3.1.5." idx, label " PoE Budget " poe_unit)',
        ),
        (
            "standard POWER-ETHERNET-MIB PoE used",
            'yaml_poe_aggregate_sensor("1.3.6.1.2.1.105.1.3.1.1.4." idx, label " PoE Used W")',
        ),
        (
            "standard POWER-ETHERNET-MIB PoE budget",
            'yaml_poe_aggregate_sensor("1.3.6.1.2.1.105.1.3.1.1.2." idx, label " PoE Budget W")',
        ),
    )
    for description, marker in aggregate_paths:
        assert marker in source, f"{description} bypassed collision-safe aggregate naming"

    # The first aggregate must retain the historical entity name used by cards.
    assert 'if (ordinal == 1) return name' in source
    # Only a repeated would-be identity gets a deterministic suffix.
    assert 'return name " Group " ordinal' in source

    print("Switch Vision Discovery cross-model PoE aggregate identity contract: PASS")


if __name__ == "__main__":
    main()
