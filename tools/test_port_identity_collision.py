#!/usr/bin/env python3
"""Replay the raw-vs-contract 3850 collision and global publication guard."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
sys.path.insert(0, str(RUNTIME))
import generated_yaml_guard as guard

def run_case(work: Path, contracted: bool, juniper: bool = False) -> dict:
    walkdir = work / "walks" / "switch"
    walkdir.mkdir(parents=True)
    walk = walkdir / "live-targeted-snmpwalk.txt"
    lines = [
        '.1.3.6.1.2.1.1.1.0 = STRING: "Cisco IOS Software, Catalyst 3850"',
        '.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.9.1.1745',
        '.1.3.6.1.2.1.47.1.1.1.1.13.1001 = STRING: "WS-C3850-12XS-E"',
    ]
    for idx in range(8, 24):
        slot, port = (0, idx - 7) if idx < 20 else (1, idx - 19)
        lines += [
            f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: "Te1/{slot}/{port}"',
            f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: {1 if slot == 0 else 2}',
            f'.1.3.6.1.2.1.31.1.1.1.6.{idx} = Counter64: {1000 if slot == 0 else 0}',
            f'.1.3.6.1.2.1.31.1.1.1.10.{idx} = Counter64: {2000 if slot == 0 else 0}',
        ]
    # Chassis and member ENTITY-MIB rows must not compete for one Model entity.
    lines.append('.1.3.6.1.2.1.47.1.1.1.1.13.1 = STRING: "WS-C3850-12XS-E"')
    if juniper:
        lines = [
            '.1.3.6.1.2.1.1.1.0 = STRING: "Juniper EX3300-48P Ethernet Switch"',
            '.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.2636.1.1.1.2.66',
        ]
        for port in range(48):
            lines += [
                f'.1.3.6.1.2.1.31.1.1.1.1.{port+1} = STRING: "ge-0/0/{port}"',
                f'.1.3.6.1.2.1.2.2.1.8.{port+1} = INTEGER: 1',
            ]
        lines += [
            '.1.3.6.1.2.1.31.1.1.1.1.605 = STRING: "xe-0/1/0"',
            '.1.3.6.1.2.1.2.2.1.8.605 = INTEGER: 1',
            '.1.3.6.1.2.1.31.1.1.1.6.605 = Counter64: 1000',
            '.1.3.6.1.2.1.31.1.1.1.10.605 = Counter64: 2000',
        ]
        for fan in (1, 2):
            lines += [
                f'.1.3.6.1.4.1.2636.3.1.13.1.5.4.1.1.{fan} = STRING: "Fan {fan}"',
                f'.1.3.6.1.4.1.2636.3.1.13.1.6.4.1.1.{fan} = INTEGER: 2',
            ]
    walk.write_text("\n".join(lines) + "\n")
    targets = work / "targets.csv"
    targets.write_text(f"{walk.name},192.0.2.10,SW2,readonly,,switch\n")
    generated = work / "generated.yaml"
    previous = guard.HEADER + "\n" + guard.SOURCE_HEADER + "\ntargets:\n- host: 192.0.2.10\n  sensors:\n  - name: SW2 Prior Status\n    oid: 1.3.6.1.2.1.2.2.1.8.8\n"
    generated.write_text(previous)
    options = dict(
        input_path=str(walk), snmpwalks_dir=str(work / "walks"),
        report_path=str(work / "report.txt"), run_snmp_walks=False,
        enable_switch_list=False, parse_all_walks=True, generate_snmp2mqtt=True,
        targets_csv=str(targets), last_run_summary_path=str(work / "summary.txt"),
        generated_yaml_path=str(generated), generated_card_path=str(work / "card.yaml"),
        snmp_log_path=str(work / "snmp.log"), live_output_dir=str(work / "live"),
        live_output_path=str(work / "live" / "live-targeted-snmpwalk.txt"),
        generate_support_my_switch_bundle=False,
    )
    optionfile = work / "options.json"
    optionfile.write_text(json.dumps(options))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
        SWITCH_VISION_OPTIONS_FILE=str(optionfile),
        SWITCH_VISION_RUNTIME_DIR=str(RUNTIME),
        SWITCH_VISION_LEGACY_DISCOVERY_SCRIPT=str(RUNTIME / "discovery_job.sh"),
        SWITCH_VISION_PHYSICAL_PREPARE=str(RUNTIME / "physical_contract_prepare.sh"),
        SWITCH_VISION_DEVICE_REGISTRY=str(RUNTIME / "opt/switch-vision/devices/supported_devices.json"),
        CV_VENDOR_DIR=str(RUNTIME / "opt/switch-vision/vendors"),
        CV_MIB_DATABASE_DIR=str(RUNTIME / "opt/switch-vision/mib_database"),
        SWITCH_VISION_CAPABILITIES_DIR=str(work / "caps"),
        SWITCH_VISION_SHARE_DIR=str(work / "share"))
    command = [sys.executable, str(RUNTIME / "discovery_contract_entrypoint.py")] if contracted else ["sh", str(RUNTIME / "discovery_job.sh")]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=90)
    if not contracted:
        assert generated.read_text() == previous, result.stdout + result.stderr
        assert "duplicate sensor identity" in result.stdout + result.stderr
        print("raw 3850 bypass: collision refused; previous output preserved")
        return {}
    assert result.returncode == 0, result.stdout + result.stderr
    document = yaml.safe_load(generated.read_text())
    sensors = [s for target in document["targets"] for s in target.get("sensors", [])]
    if juniper:
        for suffix in ("Status", "RX Bytes", "TX Bytes"):
            rows = [s for s in sensors if s["name"] == f"SW2 SFP 10G 1 {suffix}"]
            assert len(rows) == 1 and rows[0].get("source") == "interface", rows
            assert rows[0]["interfaces"] == ["xe-0/1/0", "ge-0/1/0"], rows
        assert any(s["name"] == "SW2 Port 0 Status" for s in sensors)
        fans = [s for s in sensors if s["name"].startswith("SW2 Fan ")]
        assert len(fans) == 2 and len({s["name"] for s in fans}) == 2, fans
        assert guard.validate(generated)[0]
        print("Juniper native copper/cage identity and separate fan sensors: PASS")
        return document
    assert len([s for s in sensors if s["name"] == "SW2 Model"]) == 1
    for port in range(1, 13):
        for suffix, oid in [("Status", "1.3.6.1.2.1.2.2.1.8"), ("RX Bytes", "1.3.6.1.2.1.31.1.1.1.6"), ("TX Bytes", "1.3.6.1.2.1.31.1.1.1.10")]:
            rows = [s for s in sensors if s["name"] == f"SW2 SFP 10G {port} {suffix}"]
            assert len(rows) == 1, (port, suffix, rows)
            assert rows[0]["oid"] == f"{oid}.{port + 7}", rows
    assert guard.validate(generated)[0]
    print("contract 3850 path: all 12 status/RX/TX bindings exact and unique")
    return document

with tempfile.TemporaryDirectory(prefix="sv-port-identity-") as td:
    root = Path(td)
    run_case(root / "raw", False)
    run_case(root / "contract", True)
    run_case(root / "juniper", True, juniper=True)
    candidate = root / "candidate.yaml"
    destination = root / "retained.yaml"
    destination.write_text("keep")
    def check(sensors, expected, hosts=("192.0.2.1", "192.0.2.2")):
        targets = [{"host": hosts[i], "sensors": [sensor]} for i, sensor in enumerate(sensors)]
        candidate.write_text(guard.HEADER + "\n" + guard.SOURCE_HEADER + "\n" + yaml.safe_dump({"targets": targets}))
        ok, reason = guard.validate(candidate)
        assert ok == expected, reason
        if not expected:
            assert "duplicate sensor identity" in reason, reason
            assert not guard.publish(candidate, destination)[0]
            assert destination.read_text() == "keep"
    check([{"name": "SW2 SFP 10G 1 Status", "oid": "1.2.8"}, {"name": "sw2_sfp_10g_1_status", "oid": "1.2.20"}], False)
    check([{"name": "a", "object_id": "same", "oid": "1.2.8"}, {"name": "b", "object_id": "same", "oid": "1.2.20"}], False)
    check([{"name": "a", "oid": "1.2.8"}, {"name": "a", "oid": "1.2.8"}], False)
    check([{"name": "SW1 Port 1", "oid": "1.2.8"}, {"name": "SW2 Port 1", "oid": "1.2.8"}], True)
    check([{"name": "a", "object_id": "first", "oid": "1.2.8"}, {"name": "a", "object_id": "second", "oid": "1.2.20"}], True)
print("port identity collision regression: PASS")

# Exercise the actual HTTP handler dispatch without network or configuration writes.
import io
from types import SimpleNamespace
from unittest.mock import patch
import support_web as web

body = json.dumps({"device_key": "snmp:test", "enabled": False}).encode()
selected = Path("/test/runtime/discovery_contract_entrypoint.py")
responses = []
handler = SimpleNamespace(
    path="/api/configured-devices/state",
    headers={"Content-Length": str(len(body))},
    rfile=io.BytesIO(body),
    app=SimpleNamespace(options_file=Path("/unused/options.json"), discovery_script=selected),
    _allow_ingress_request=lambda: True,
    _json=lambda payload, *args: responses.append(payload),
)
with patch.object(web, "_set_configured_device_state", return_value={}), \
     patch.object(web, "_apply_saved_device_order_to_dashboard", return_value={"updated": True}), \
     patch.object(web, "_start_device_state_application", return_value={"started": True}) as queue:
    web.SupportHandler.do_POST(handler)
    queue.assert_called_once_with(selected)
    assert responses[0]["polling_refresh_started"] is True, responses
assert web.DEFAULT_DISCOVERY_SCRIPT == Path("/discovery_contract_entrypoint.py")
print("device-state HTTP handler preserves configured contract entrypoint: PASS")
