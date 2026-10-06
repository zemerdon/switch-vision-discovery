#!/usr/bin/env python3
"""Regressions for field fixes derived from reviewed October hardware evidence."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
STAGE = RUNTIME / "discovery_yaml_stage.sh"
REGISTRY = RUNTIME / "opt/switch-vision/devices/supported_devices.json"
SUPPORT_DIAGNOSTICS = RUNTIME / "support_diagnostics.py"
SUPPORT_WEB = RUNTIME / "support_web.py"


def generate(walk: Path, prefix: str) -> str:
    script = '. "$1"; write_generated_yaml_for_walk "$2" "$3" "$4" "$5"'
    proc = subprocess.run(
        [
            "sh",
            "-c",
            script,
            "sv-carry-field-test",
            str(STAGE),
            str(walk),
            "192.0.2.72",
            prefix,
            "readonly",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    return proc.stdout


def sirivision_walk(path: Path) -> None:
    rows = [
        ".1.3.6.1.2.1.1.1.0 = STRING: SR-S25G3420F",
        ".1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.27282.100",
        ".1.3.6.1.2.1.1.3.0 = Timeticks: (249505870) 28 days, 21:04:18.70",
        ".1.3.6.1.2.1.1.8.0 = Timeticks: (135676500) 15 days, 16:52:45.00",
        ".1.3.6.1.6.3.10.2.1.3.0 = INTEGER: 5433267",
    ]
    for idx in range(1, 17):
        rows.extend(
            [
                f".1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: HisgmiiEthernet{idx}",
                f".1.3.6.1.2.1.2.2.1.7.{idx} = INTEGER: up(1)",
                f".1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: down(2)",
                f".1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 1410",
            ]
        )
    for port, idx in enumerate(range(17, 21), start=1):
        rows.extend(
            [
                f".1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: TenGigabitEthernet{port}",
                f".1.3.6.1.2.1.2.2.1.7.{idx} = INTEGER: up(1)",
                f".1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: down(2)",
                f".1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 10000",
            ]
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def gs1915_walk(path: Path) -> None:
    rows = [
        '.1.3.6.1.2.1.1.1.0 = STRING: "Zyxel GS1915-24EP Managed Switch"',
        ".1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.890.1.15.3.139.1",
        ".1.3.6.1.2.1.105.1.3.1.1.2.1 = Gauge32: 130",
        ".1.3.6.1.2.1.105.1.3.1.1.4.1 = Gauge32: 0",
    ]
    for idx in range(1, 25):
        rows.extend(
            [
                f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: "swp{idx - 1:02d}"',
                f".1.3.6.1.2.1.2.2.1.7.{idx} = INTEGER: up(1)",
                f".1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: up(1)",
                f".1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 1000",
            ]
        )
        if idx <= 12:
            rows.extend(
                [
                    f".1.3.6.1.2.1.105.1.1.1.3.1.{idx} = INTEGER: auto(1)",
                    f".1.3.6.1.2.1.105.1.1.1.6.1.{idx} = INTEGER: deliveringPower(3)",
                    f".1.3.6.1.2.1.105.1.1.1.10.1.{idx} = INTEGER: class3(4)",
                ]
            )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def load_runtime_module(name: str, path: Path):
    runtime_text = str(RUNTIME)
    if runtime_text not in sys.path:
        sys.path.insert(0, runtime_text)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_support_diagnostics():
    return load_runtime_module("carry_support_diagnostics", SUPPORT_DIAGNOSTICS)


def load_support_web():
    return load_runtime_module("carry_support_web", SUPPORT_WEB)


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    devices = {row.get("model"): row for row in registry["devices"]}

    sr = devices["SR-S25G3420F"]
    assert sr["status"] == "experimental"
    assert sr["ports"]["rj45"] == 16
    assert sr["ports"]["ten_gigabit_sfp_plus"] == 4

    gs = devices["GS1915-24EP"]
    assert gs["status"] == "experimental"
    assert gs["ports"]["rj45"] == 24
    assert gs["ports"]["poe"] is True

    support_script = (RUNTIME / "support_my_switch.sh").read_text(encoding="utf-8")
    assert 'if [ "$STALE_TARGETED_WALK_COUNT" -gt 0 ]; then' in support_script
    assert 'EVIDENCE_QUALITY="degraded"' in support_script

    with tempfile.TemporaryDirectory(prefix="sv-carry-field-") as temp_name:
        temp = Path(temp_name)

        sr_walk = temp / "sr.walk"
        sirivision_walk(sr_walk)
        sr_yaml = generate(sr_walk, "swsr")
        assert "# Detected model: SR-S25G3420F" in sr_yaml
        assert "device_manufacturer: Sirivision" in sr_yaml
        assert "device_model: SR-S25G3420F" in sr_yaml
        assert "name: swsr Port 1 Status" in sr_yaml
        assert "name: swsr Port 16 Status" in sr_yaml
        assert "name: swsr SFP 10G 4 Status" in sr_yaml
        assert "name: swsr Uptime\n    source: sirivision_uptime" in sr_yaml
        assert "1.3.6.1.2.1.1.3.0" not in sr_yaml

        support_web = load_support_web()
        handoff_yaml = temp / "generated-snmp2mqtt.yaml"
        handoff_yaml.write_text(sr_yaml, encoding="utf-8")
        handoff_validation = support_web._validate_snmp2mqtt_yaml(handoff_yaml)
        assert handoff_validation["valid"] is True, handoff_validation
        assert (
            "template: \"{{ 'unknown' if (value | int) in [0, 1410] "
            "else ([value | int, 2500] | min) }}\""
        ) in sr_yaml

        gs_walk = temp / "gs.walk"
        gs1915_walk(gs_walk)
        gs_yaml = generate(gs_walk, "gs")
        for port in (1, 12):
            assert f"name: gs Port {port} PoE Admin Code" in gs_yaml
            assert f"name: gs Port {port} PoE Status Code" in gs_yaml
            assert f"name: gs Port {port} PoE Class Code" in gs_yaml
        assert "name: gs Port 13 PoE" not in gs_yaml
        assert "name: gs PoE Budget W" in gs_yaml

        diagnostics = load_support_diagnostics()
        root = temp / "support"
        walk_dir = root / "snmpwalks" / "test"
        walk_dir.mkdir(parents=True)
        targeted = walk_dir / "live-targeted-snmpwalk.txt"
        full = walk_dir / "live-full-snmpwalk.txt"
        targeted.write_text("targeted\n", encoding="utf-8")
        full.write_text("full\n", encoding="utf-8")
        now_ns = time.time_ns()
        os.utime(targeted, ns=(now_ns - 14 * 86400 * 1_000_000_000,) * 2)
        os.utime(full, ns=(now_ns,) * 2)
        stale = diagnostics.build_file_provenance(root)
        assert stale["schema_version"] == 2
        assert stale["walk_freshness"]["status"] == "stale_targeted_walks"
        assert stale["walk_freshness"]["stale_targeted_count"] == 1

        os.utime(targeted, ns=(now_ns,) * 2)
        current = diagnostics.build_file_provenance(root)
        assert current["walk_freshness"]["status"] == "ok"
        assert current["walk_freshness"]["stale_targeted_count"] == 0

    print("Discovery Carry field-hardening regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
