#!/usr/bin/env python3
"""Guarded TP-Link hardware admission from an offline walk; no network input."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "tools/review_snmp_walk_registration.py"
PREPARE = ROOT / "runtime_src/physical_contract_prepare.sh"
REGISTRY = ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"
spec = importlib.util.spec_from_file_location("walk_registration", REVIEW)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

DEVICES = [
 ("TL-SG2428P", "JetStream 28-Port Gigabit Smart Switch with 24-Port PoE+", "1.3.6.1.4.1.11863.5.98", 28, 24, 4),
 ("TL-SG2008P", "JetStream 8-Port Gigabit Smart Switch with 4-Port PoE+", "1.3.6.1.4.1.11863.5.94", 8, 8, 0),
]

def build_walk(descr, oid, count, *, plain=False):
    lines=[
      f".1.3.6.1.2.1.1.1.0 = STRING: {descr}",
      f".1.3.6.1.2.1.1.2.0 = OID: .{oid}",
      ".1.3.6.1.2.1.31.1.1.1.1.1 = STRING: Vlan-interface1",
    ]
    for n in range(1,count+1):
        idx=49152+n
        lines.extend([
          f".1.3.6.1.2.1.2.2.1.2.{idx} = STRING: gigabitEthernet 1/0/{n}",
          f".1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: gigabitEthernet 1/0/{n}",
          f".1.3.6.1.2.1.2.2.1.3.{idx} = INTEGER: ethernetCsmacd(6)",
          f".1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: up(1)",
          f".1.3.6.1.2.1.17.1.4.1.2.{idx} = INTEGER: {idx}",
          f".1.3.6.1.2.1.31.1.1.1.6.{idx} = Counter64: {n*3456}",
          f".1.3.6.1.2.1.31.1.1.1.10.{idx} = Counter64: {n*1234}",
        ])
    if not plain:lines.append("# Switch Vision SNMP walk result: pass")
    return ("\n".join(lines)+"\n").encode()

def run(*cmd,env=None):
    proc=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=45,env=env)
    assert proc.returncode==0,(cmd,proc.stdout[-1400:],proc.stderr[-1400:])
    return proc.stdout

def test():
    products=module._curated_products(module.KNOWLEDGE)
    assert len([p for p in products if p.get('vendor')=='tplink'])==2
    registry=json.loads(REGISTRY.read_text())['devices']
    for model,descr,oid,count,rj45,sfp in DEVICES:
        row=next(x for x in registry if x['model']==model)
        assert row['ports']['rj45']==rj45 and row['ports']['uplinks']==sfp
        assert row['status']=='experimental' and row['dashboard_support'] is True
        data=build_walk(descr,oid,count)
        verdict=module.inspect_walk(data,products,source='live-targeted-snmpwalk.txt')
        assert verdict['registration']=='experimental_candidate',verdict
        assert verdict['observed_physical_interfaces']==count and verdict['verified_port_contract']['sfp']==sfp,verdict
        # Plain net-snmp walks must be accepted, not only Switch Vision files.
        plain=module.inspect_walk(build_walk(descr,oid,count,plain=True),products,source='full.walk')
        assert plain['registration']=='experimental_candidate',plain
        assert module.inspect_walk(data.replace(b"walk result: pass",b"walk result: failed"),products,source='full.walk')['registration']!='experimental_candidate'
        assert module.inspect_walk(data.replace(oid.encode(),b"1.3.6.1.4.1.11863.5.500"),products,source='full.walk')['registration']!='experimental_candidate'
        tampered=data.replace(f"gigabitEthernet 1/0/{count}".encode(),b"Vlan-interface99")
        assert module.inspect_walk(tampered,products,source='full.walk')['registration']!='experimental_candidate'
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp)
            walk=work/'source.walk';normalized=work/'normalized.walk'
            capability=work/'capabilities.json';physical=work/'contract.json'
            walk.write_bytes(data)
            config=(ROOT/'switch_vision_discovery/config.yaml').read_text()
            import re
            m=re.search(r'^version: "([^"]+)"',config,re.M)
            assert m
            env=os.environ.copy();env['SWITCH_VISION_DISCOVERY_VERSION']=m.group(1)
            run(str(PREPARE),str(walk),str(normalized),str(capability),str(physical),env=env)
            cap=json.loads(capability.read_text());con=json.loads(physical.read_text())
            assert cap['device']['vendor']=='tplink',cap['device']
            assert cap['device']['model_text']==model,cap['device']
            assert cap['summary']['physical_count']==count,cap['summary']
            assert cap['summary']['rj45_count']==rj45,cap['summary']
            assert cap['summary']['uplink_count']==sfp,cap['summary']
            assert con['status']=='resolved',con
            assert con['device']['exact_registry_match'],con
            assert len(con['ports'])==count,con
            assert all(int(p['source']['if_index'])==49153+i for i,p in enumerate(con['ports'])),con['ports']
            assert all(p['media']=='rj45' for p in con['ports'][:rj45])
            assert all(p['media']=='sfp' for p in con['ports'][rj45:])
    # Wrong enterprise ID or a vague JetStream family name must not select a SKU.
    assert module.inspect_walk(build_walk(DEVICES[0][1],'1.3.6.1.4.1.11863.5.94',28),products,source='walk')['registration']!='experimental_candidate'
    print("TP_LINK_OFFLINE_FULL_WALK_AND_RUNTIME_CONTRACT_PASS")

if __name__=='__main__':
    test()
