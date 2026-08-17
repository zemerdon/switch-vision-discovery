#!/usr/bin/env python3
"""Find likely vendor-specific sensor OIDs from a walk using curated vendor packs.

This scanner is observational. It does not install mappings automatically. Standard
MIB discovery remains the preferred path; vendor packs help narrow enterprise OIDs.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
from typing import Any

NUMERIC_LINE = re.compile(r"^\s*(?:iso\.|\.)?(?P<oid>[0-9.]+)\s*=\s*(?P<type>[^:]+):?\s*(?P<value>.*)$")
SYMBOLIC_LINE = re.compile(r"^\s*(?P<symbol>[A-Za-z][A-Za-z0-9_-]*(?:::[A-Za-z][A-Za-z0-9_-]*)?(?:\.[A-Za-z0-9_.-]+)?)\s*=\s*(?P<type>[^:]+):?\s*(?P<value>.*)$")
INT_RE = re.compile(r"-?\d+")


def clean(v: str) -> str:
    v=v.strip()
    return v[1:-1] if len(v)>=2 and v[0]==v[-1]=='"' else v

def numeric_value(v: str) -> int|None:
    m=INT_RE.search(v.replace(',',''))
    return int(m.group(0)) if m else None

def load_json(path: Path, default: Any) -> Any:
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,json.JSONDecodeError): return default

def parse_walk(path: Path) -> list[dict[str,Any]]:
    rows=[]
    for raw in path.read_text(encoding='utf-8',errors='ignore').splitlines():
        m=NUMERIC_LINE.match(raw)
        if m:
            rows.append({'oid':m.group('oid').lstrip('.'),'symbol':'','type':m.group('type').strip().upper(),'value':clean(m.group('value'))})
            continue
        m=SYMBOLIC_LINE.match(raw)
        if m:
            rows.append({'oid':'','symbol':m.group('symbol'),'type':m.group('type').strip().upper(),'value':clean(m.group('value'))})
    return rows

def detect_vendor(capabilities: dict[str,Any], db: Path) -> str:
    v=str(capabilities.get('device',{}).get('vendor','')).strip()
    if v and v not in {'generic','fallback'}: return v
    oid=str(capabilities.get('device',{}).get('sys_object_id','')).strip().lstrip('.')
    for d in sorted((db/'vendors').iterdir() if (db/'vendors').exists() else []):
        ident=load_json(d/'identity.json',{})
        for prefix in ident.get('detection',{}).get('sys_object_id_prefixes',[]):
            if oid.startswith(prefix): return d.name
        p=ident.get('detection',{}).get('sys_object_id_prefix')
        if p and oid.startswith(p): return d.name
    return 'generic'

def category_for(symbol: str, patterns: dict[str,list[str]]) -> str|None:
    for category, pats in patterns.items():
        for pat in pats:
            if re.search(pat, symbol, re.I): return category
    return None

def known_oid_for(oid: str, known: list[dict[str,Any]]) -> dict[str,Any]|None:
    if not oid:
        return None
    for item in known:
        exact=str(item.get('oid','')).strip().lstrip('.')
        prefix=str(item.get('oid_prefix','')).strip().lstrip('.')
        if exact and oid == exact:
            return item
        if prefix and (oid == prefix or oid.startswith(prefix + '.')):
            return item
    return None

def build(walk: Path, capabilities: dict[str,Any], db: Path) -> dict[str,Any]:
    vendor=detect_vendor(capabilities,db)
    pack_path=db/'vendors'/vendor/'sensors.json'
    pack=load_json(pack_path,{})
    if not pack:
        return {'schema_version':1,'vendor':vendor,'pack_loaded':False,'candidate_count':0,'counts_by_category':{},'candidates':[],
                'notes':['No vendor-specific sensor pack matched; standard MIB discovery remains active.']}
    rows=parse_walk(walk)
    patterns=pack.get('symbolic_name_patterns',{})
    roots=pack.get('enterprise_oids',[])
    known=pack.get('known_oids',[])
    policy=pack.get('numeric_candidate_policy',{})
    accepted={x.upper() for x in policy.get('accepted_types',[])}
    excluded={x.upper() for x in policy.get('exclude_types',[])}
    maximum=int(policy.get('maximum_candidates',120))
    out=[]; seen=set()

    # Pass 1: curated exact/prefix OIDs and symbolic-name matches are authoritative
    # review candidates. Always collect these before generic enterprise numerics so a
    # large vendor tree cannot exhaust the review cap before proven sensors appear.
    for row in rows:
        known_item=known_oid_for(row['oid'], known)
        category=category_for(row['symbol'],patterns) if row['symbol'] else None
        if known_item:
            known_category=str(known_item.get('category') or 'environment')
            key=(row['oid'],known_category)
            if key in seen: continue
            seen.add(key)
            out.append({'category':known_category,'source':'curated-known-oid','vendor':vendor,'oid':row['oid'] or None,
                        'symbolic_oid':row['symbol'] or None,'label':known_item.get('label'),
                        'unit':known_item.get('unit'),'value_type':row['type'],'raw_value':row['value'],
                        'numeric_value':numeric_value(row['value']),'confidence':known_item.get('confidence','high')})
        elif category:
            key=(row['symbol'] or row['oid'],category)
            if key in seen: continue
            seen.add(key)
            out.append({'category':category,'source':'symbolic-name','vendor':vendor,'oid':row['oid'] or None,
                        'symbolic_oid':row['symbol'] or None,'value_type':row['type'],'raw_value':row['value'],
                        'numeric_value':numeric_value(row['value']),'confidence':'high'})

    # Pass 2: fill only the remaining review budget with unclassified enterprise
    # numeric candidates. Curated/symbolic evidence is never displaced by this cap.
    for row in rows:
        if len(out)>=maximum: break
        if known_oid_for(row['oid'], known) or (row['symbol'] and category_for(row['symbol'],patterns)):
            continue
        enterprise=bool(row['oid'] and any(row['oid']==r or row['oid'].startswith(r+'.') for r in roots))
        if not enterprise or not policy.get('enabled',True) or row['type'] in excluded or (accepted and row['type'] not in accepted):
            continue
        n=numeric_value(row['value'])
        if n is None or abs(n)>1_000_000_000: continue
        key=(row['oid'],'vendor_numeric')
        if key in seen: continue
        seen.add(key)
        out.append({'category':'vendor_numeric','source':'enterprise-numeric','vendor':vendor,'oid':row['oid'],
                    'symbolic_oid':None,'value_type':row['type'],'raw_value':row['value'],'numeric_value':n,
                    'confidence':'review'})

    counts={}
    for item in out: counts[item['category']]=counts.get(item['category'],0)+1
    return {'schema_version':1,'vendor':vendor,'pack_loaded':True,'pack_file':str(pack_path),'candidate_count':len(out),
            'counts_by_category':counts,'candidates':out,
            'notes':['Standard MIB candidates should be reviewed first.','Curated and symbolic-name matches are prioritized ahead of capped numeric-only enterprise candidates.','Numeric-only enterprise candidates require review.','No vendor mapping is installed automatically.']}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--walk',type=Path,required=True); p.add_argument('--database',type=Path,default=Path('/opt/switch-vision/mib_database')); p.add_argument('--enrich',type=Path); p.add_argument('--output',type=Path); p.add_argument('--report',action='store_true'); a=p.parse_args()
    caps=load_json(a.enrich,{}) if a.enrich else {}
    payload=build(a.walk,caps,a.database)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(payload,indent=2)+'\n')
    if a.enrich:
        caps['vendor_sensor_discovery']=payload
        c=caps.setdefault('capabilities',{})
        counts=payload['counts_by_category']
        c['vendor_environment']=sum(counts.get(k,0) for k in ('temperature','fan','power','environment'))>0
        c['vendor_poe']=counts.get('poe',0)>0
        c['vendor_cpu']=counts.get('cpu',0)>0
        c['vendor_memory']=counts.get('memory',0)>0
        a.enrich.write_text(json.dumps(caps,indent=2)+'\n')
    if a.report:
        print('Vendor sensor discovery:')
        print(f"- Vendor pack: {payload['vendor']}")
        print(f"- Pack loaded: {'yes' if payload['pack_loaded'] else 'no'}")
        print(f"- Candidate sensors found: {payload['candidate_count']}")
        for k,v in sorted(payload['counts_by_category'].items()): print(f"- {k.replace('_',' ').title()} candidates: {v}")
        print('- Installation behaviour: review-only; no entities are installed automatically')
if __name__=='__main__': main()
