from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
sys.path.insert(0, str(RUNTIME))

import discovery_contract_entrypoint as contract  # noqa: E402
import support_web as web  # noqa: E402


def switch(name: str, host: str, prefix: str) -> dict[str, str]:
    return {
        "switch_name": name,
        "switch_host": host,
        "sensor_prefix": prefix,
        "snmp_community": "readonly",
        "enabled": "enabled",
        "walk_mode": "targeted",
        "switch_model": "auto",
    }


def exported(rows: list[dict[str, str]], stack: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "format": web.DISCOVERY_EXPORT_FORMAT,
        "configuration": {
            "switches": rows,
            "stack_member_prefixes": stack or [],
        },
    }


def must_fail(payload: dict[str, object], marker: str) -> None:
    try:
        web._validate_discovery_import(payload)
    except ValueError as exc:
        if marker not in str(exc):
            raise AssertionError(f"expected {marker!r} in {exc!r}") from exc
    else:
        raise AssertionError(f"payload unexpectedly accepted; expected {marker!r}")


def main() -> None:
    mahncke = "Cisco 3560-C"
    validated = web._validate_discovery_import(
        exported(
            [switch(mahncke, "192.0.2.10", "c3560")],
            [{"switch_name": mahncke, "member": "1", "sensor_prefix": "c3560"}],
        )
    )
    assert validated["switches"][0]["switch_name"] == mahncke
    assert validated["stack_member_prefixes"][0]["switch_name"] == mahncke
    assert web._switch_name_identity(mahncke) == "cisco_3560-c"
    assert contract._safe(mahncke) == "Cisco_3560-C"

    must_fail(
        exported(
            [
                switch("Cisco 3560-C", "192.0.2.10", "c3560a"),
                switch("Cisco_3560-C", "192.0.2.11", "c3560b"),
            ]
        ),
        "normalizes to internal key",
    )
    must_fail(
        exported(
            [
                switch("SW__1", "192.0.2.20", "sw1a"),
                switch("SW_1", "192.0.2.21", "sw1b"),
            ]
        ),
        "normalizes to internal key",
    )
    must_fail(
        exported([switch("Cisco:3560-C", "192.0.2.30", "c3560")]),
        "unsupported characters",
    )
    must_fail(
        exported(
            [switch("Cisco 3560-C", "192.0.2.40", "c3560")],
            [{"switch_name": "Cisco_3560-C", "member": "1", "sensor_prefix": "c3560"}],
        ),
        "references unknown switch_name",
    )

    print("Switch Vision switch_name space compatibility: PASS")


if __name__ == "__main__":
    main()
