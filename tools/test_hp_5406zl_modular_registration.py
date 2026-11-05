from __future__ import annotations
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
MODEL = "HP J8697A Switch 5406zl"


def fixture(populated="ABDE", aliases=True):
    parts = {"A": (59,"J8702A"),"B": (60,"J8702A"),
             "D": (62,"J8707A"),"E": (63,"J8702A")}
    lines = [f'.1.3.6.1.2.1.1.1.0 = STRING: "{MODEL}"',
             '.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.11.2.3.7.11.50']
    for slot, (ent, sku) in parts.items():
        if slot in populated:
            lines.append(f'.1.3.6.1.2.1.47.1.1.1.1.13.{ent} = STRING: "HP {sku}"')
    for number, slot in enumerate("ABCDEF"):
        for port in range(1,25):
            idx=number*24+port
            lines.append(f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: "{slot}{port}"')
            if slot not in populated or (slot=="D" and port>4):continue
            ent, sku=parts[slot]
            ep=1000+idx
            lines.extend([
                f'.1.3.6.1.2.1.47.1.1.1.1.5.{ep} = INTEGER: port(10)',
                f'.1.3.6.1.2.1.47.1.1.1.1.4.{ep} = INTEGER: {ent}',
            ])
            if aliases:
                lines.append(f'.1.3.6.1.2.1.47.1.3.2.1.2.{ep}.0 = OID: .1.3.6.1.2.1.2.2.1.1.{idx}')
    return "\n".join(lines)+"\n"


def run(text):
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        src=root/"walk.txt"
        src.write_text(text)
        args=["sh",str(RUNTIME/"physical_contract_prepare.sh"),
              str(src),str(root/"norm.txt"),str(root/"caps.json"),str(root/"contract.json")]
        result=subprocess.run(args,capture_output=True,text=True,timeout=40)
        contract=json.loads((root/"contract.json").read_text())
        return result.returncode,contract,(root/"norm.txt").read_text()


def test_hp_5406zl_modules_and_empty_slot():
    code,contract,norm=run(fixture())
    assert code==0,contract
    assert contract["status"]=="resolved",contract["errors"]
    assert contract["observed"]["rj45"]==72
    assert contract["observed"]["sfp_plus"]==4
    ports={p["source"]["if_index"]:p for p in contract["ports"]}
    assert 49 not in ports and 72 not in ports
    assert ports[73]["compatibility_name"]=="Te1/1/1"
    assert ports[97]["compatibility_name"]=="Gi1/0/49"
    assert 'STRING: "Gi1/0/49"' in norm


def test_hp_5406zl_variable_modules_and_no_alias():
    code,contract,_=run(fixture(populated="AD"))
    assert code==0,contract
    assert contract["observed"]["physical"]==28
    assert contract["expected"]["physical"]==28
    code,contract,_=run(fixture(aliases=False))
    assert code!=0
    assert contract["status"]=="topology_conflict"


def test_hp_5406zl_generated_sensor_coverage():
    with tempfile.TemporaryDirectory(prefix="sv_hp5406_generator_") as td:
        root = Path(td)
        original = root / "walk.txt"
        original.write_text(fixture())
        norm = root / "normalized.txt"
        args = ["sh", str(RUNTIME / "physical_contract_prepare.sh"),
                str(original), str(norm), str(root / "cap.json"), str(root / "contract.json")]
        prep = subprocess.run(args, text=True, capture_output=True, timeout=40)
        assert prep.returncode == 0, prep.stderr
        shell = ("set -eu\n. " + str(RUNTIME / "discovery_yaml_stage.sh") +
                 "\nwrite_generated_yaml_for_walk " + str(norm) + " 10.0.0.1 TEST public\n")
        generated = subprocess.run(["sh"], input=shell, text=True,
                                   capture_output=True, timeout=40)
        assert generated.returncode == 0, generated.stderr
        yaml = generated.stdout
        assert "# Detected model: HP J8697A Switch 5406zl" in yaml
        assert "TEST Port 1 Status" in yaml
        assert "TEST Port 72 Status" in yaml
        assert "TEST SFP 10G 1 Status" in yaml
        assert "TEST SFP 10G 4 Status" in yaml
        assert "1.3.6.1.2.1.2.2.1.8.49" not in yaml  # empty C1
        assert "1.3.6.1.2.1.2.2.1.8.72" not in yaml  # empty C24
        assert "1.3.6.1.2.1.2.2.1.8.97" in yaml   # populated E1


def test_hp_5406zl_registry_status():
    d=json.loads((RUNTIME/"opt/switch-vision/devices/supported_devices.json").read_text())
    row=next(d for d in d["devices"] if d.get("model")==MODEL)
    assert row["status"]=="experimental"
    assert row["port_topology_mode"]=="entity_mib_modules"


if __name__ == "__main__":
    test_hp_5406zl_modules_and_empty_slot()
    test_hp_5406zl_variable_modules_and_no_alias()
    test_hp_5406zl_generated_sensor_coverage()
    test_hp_5406zl_registry_status()
    print("HP 5406zl modular registration tests passed")
