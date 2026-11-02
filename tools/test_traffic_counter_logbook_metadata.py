#!/usr/bin/env python3
"""Keep numeric per-port traffic counters out of HA Activity without changing polling."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "runtime_src" / "discovery_yaml_stage.sh"


def generated_yaml(lines: list[str]) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="sv-traffic-logbook-") as tmp:
        walk = Path(tmp) / "synthetic.walk"
        walk.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = subprocess.run(
            [
                "sh",
                "-c",
                '. "$1"; write_generated_yaml_for_walk "$2" 192.0.2.10 LAB readonly',
                "sh",
                str(STAGE),
                str(walk),
            ],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
    assert result.returncode == 0, result.stderr
    return yaml.safe_load(result.stdout)


def all_sensors(groups: list[dict]) -> list[tuple[dict, dict]]:
    return [(target, sensor) for target in groups for sensor in target.get("sensors", [])]


hp = [
    '.1.3.6.1.2.1.1.1.0 = STRING: "HP J9774A 2530-8G-PoEP Switch"',
]
for idx in (1, 2):
    hp.extend(
        [
            f'.1.3.6.1.2.1.2.2.1.2.{idx} = STRING: Port {idx}',
            f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: {idx}',
            f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: up(1)',
        ]
    )
hp.extend(
    [
        ".1.3.6.1.2.1.31.1.1.1.6.1 = Counter64: 1234",
        ".1.3.6.1.2.1.31.1.1.1.10.1 = Counter64: 2345",
        ".1.3.6.1.2.1.2.2.1.10.2 = Counter32: 3456",
        ".1.3.6.1.2.1.2.2.1.16.2 = Counter32: 4567",
    ]
)
rows = all_sensors(generated_yaml(hp))
traffic = [(group, sensor) for group, sensor in rows if sensor["name"].endswith((" RX Bytes", " TX Bytes"))]
assert len(traffic) == 4, traffic
assert {sensor["oid"] for _, sensor in traffic} == {
    "1.3.6.1.2.1.31.1.1.1.6.1",
    "1.3.6.1.2.1.31.1.1.1.10.1",
    "1.3.6.1.2.1.2.2.1.10.2",
    "1.3.6.1.2.1.2.2.1.16.2",
}
assert {sensor["name"] for _, sensor in traffic} == {
    "LAB Port 1 RX Bytes",
    "LAB Port 1 TX Bytes",
    "LAB Port 2 RX Bytes",
    "LAB Port 2 TX Bytes",
}
assert all(sensor.get("unit_of_measurement") == "B" for _, sensor in traffic), traffic
assert all(group["scan_interval"] == 10 for group, _ in traffic), traffic
assert all("state_class" not in sensor and "device_class" not in sensor for _, sensor in traffic)
status = [sensor for _, sensor in rows if sensor["name"].endswith(" Status")]
assert {sensor["name"] for sensor in status} >= {"LAB Port 1 Status", "LAB Port 2 Status"}
assert all("unit_of_measurement" not in sensor for sensor in status)

juniper = [
    '.1.3.6.1.2.1.1.1.0 = STRING: "Juniper Networks ex3300-48p"',
    '.1.3.6.1.2.1.31.1.1.1.1.25 = STRING: "xe-0/1/0"',
    ".1.3.6.1.2.1.2.2.1.8.25 = INTEGER: up(1)",
]
rows = all_sensors(generated_yaml(juniper))
uplinks = [(group, sensor) for group, sensor in rows if " SFP 10G " in sensor["name"] and sensor["name"].endswith((" RX Bytes", " TX Bytes"))]
assert len(uplinks) == 8, uplinks
assert all(sensor["source"] == "interface" for _, sensor in uplinks)
assert all(sensor.get("unit_of_measurement") == "B" for _, sensor in uplinks), uplinks
assert all(group["scan_interval"] == 10 for group, _ in uplinks)
assert all("state_class" not in sensor for _, sensor in uplinks)
assert all("unit_of_measurement" not in sensor for _, sensor in rows if sensor["name"].endswith(" Status"))

print("Discovery traffic-byte Logbook metadata, identity and 10s cadence: PASS")
