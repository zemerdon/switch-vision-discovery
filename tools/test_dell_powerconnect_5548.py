#!/usr/bin/env python3
"""Exact Dell PowerConnect 5548 vs 5548P and bounded read-only health contract."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/"runtime_src"
REGISTRY=RUNTIME/"opt/switch-vision/devices/supported_devices.json"

def run(args,env):
    p=subprocess.run(args,cwd=ROOT,env=env,text=True,capture_output=True,timeout=90)
    if p.returncode:
        raise AssertionError(f"{args} rc={p.returncode}\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")

def fixture(root,model_oid,readings):
    walkdir=root/"walks"/"DELL5548"
    walkdir.mkdir(parents=True)
    walk=walkdir/"live-full-snmpwalk.txt"
    rows=[
        '.1.3.6.1.2.1.1.1.0 = STRING: "Dell Technologies 48G Ethernet Switch"',
        f".1.3.6.1.2.1.1.2.0 = OID: .{model_oid}",
    ]
    for i in range(1,49):
        rows.append(f'.1.3.6.1.2.1.31.1.1.1.1.{i} = STRING: "gi1/0/{i}"')
    for i in range(49,51):
        rows.append(f'.1.3.6.1.2.1.31.1.1.1.1.{i} = STRING: "te1/0/{i-48}"')
    for oid,val in readings.items():
        rows.append(f".{oid} = INTEGER: {val}")
    walk.write_text("\n".join(rows)+"\n")
    opts=root/"options.json"
    targets=root/"targets.csv"
    targets.write_text(f"DELL5548,192.0.2.56,DELL5548,readonly,{walkdir},DELL5548\n")
    opts.write_text(json.dumps({
        "input_path":str(walk),
        "snmpwalks_dir":str(root/"walks"),
        "report_path":str(root/"report.txt"),
        "run_snmp_walks":"false",
        "enable_switch_list":"false",
        "parse_all_walks":"true",
        "generate_snmp2mqtt":"true",
        "targets_csv":str(targets),
        "last_run_summary_path":str(root/"summary.txt"),
        "generated_yaml_path":str(root/"generated.yaml"),
        "generated_card_path":str(root/"card.yaml"),
        "snmp_log_path":str(root/"log.txt"),
        "live_output_dir":str(root/"live"),
        "generate_support_my_switch_bundle":"false",
    }))
    env=os.environ.copy()
    env.update({
        "SWITCH_VISION_DISCOVERY_VERSION":"3.1.26",
        "SWITCH_VISION_OPTIONS_FILE":str(opts),
        "SWITCH_VISION_CAPABILITIES_DIR":str(root),
        "SWITCH_VISION_DEVICE_REGISTRY":str(REGISTRY),
        "SWITCH_VISION_REGISTRY_LOOKUP":str(RUNTIME/"registry_lookup.py"),
        "SWITCH_VISION_RUNTIME_DIR":str(RUNTIME),
        "SWITCH_VISION_SHARE_DIR":str(root/"share"),
    })
    run([str(RUNTIME/"discovery_job.sh")],env)
    return (root/"generated.yaml").read_text()

cpu={
    "1.3.6.1.4.1.89.1.7.0":78,
    "1.3.6.1.4.1.89.1.8.0":83,
    "1.3.6.1.4.1.89.1.9.0":81,
    "1.3.6.1.4.1.89.53.15.1.9.1":41,
}
with tempfile.TemporaryDirectory(prefix="sv-powerconnect-5548-") as tmp:
    root=Path(tmp)
    y=fixture(root/"nonpoe","1.3.6.1.4.1.674.10895.3031",cpu)
    assert "# Detected model: PowerConnect 5548" in y
    for label in ("CPU 1s","CPU 60s","CPU 300s","Chassis Temperature"):
        assert label in y, (label,y[:2000])
    for oid in cpu:
        assert oid in y,oid
    assert "Optical Power" not in y
    assert "PoE Power" not in y

    y=fixture(root/"invalid","1.3.6.1.4.1.674.10895.3031",{
        "1.3.6.1.4.1.89.1.7.0":101,    # documented unmeasured sentinel
        "1.3.6.1.4.1.89.53.15.1.9.1":500,
    })
    assert "# Detected model: PowerConnect 5548" in y
    assert "CPU 1s" not in y
    assert "Chassis Temperature" not in y

    y=fixture(root/"poe","1.3.6.1.4.1.674.10895.3033",cpu)
    assert "# Detected model: PowerConnect 5548P" in y
    assert "PowerConnect 5548 Chassis" not in y
    assert "CPU 1s" not in y
    assert "Chassis Temperature" not in y

# Verify real Dell product IDs, not the unrelated N3024 OID formerly used
# by the synthetic PowerConnect 5548P test fixtures.
d=json.loads(REGISTRY.read_text())
models={entry["model"]:entry for entry in d["devices"]}
assert models["PowerConnect 5548"]["ports"]["poe"] is False
assert models["PowerConnect 5548P"]["ports"]["poe"] is True
assert models["PowerConnect 5548"]["ports"]["rj45"]==48
assert models["PowerConnect 5548"]["ports"]["ten_gigabit_sfp_plus"]==2
print("Dell 5548/5548P identity, bounded CPU/temp and negative model telemetry: PASS")
