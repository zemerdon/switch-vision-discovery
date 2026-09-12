#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
registry=json.loads((ROOT/'runtime_src/opt/switch-vision/devices/supported_devices.json').read_text(encoding='utf-8'))
rows={row.get('model'):row for row in registry.get('devices',[]) if isinstance(row,dict)}
expected={
 'US-8-150W':('unifi_8_rj45_2sfp','faceplates/unifi-8-rj45-2sfp.png',8,2,True),
 'US 8 60W':('default_unifi_8_rj45','faceplates/unifi-8rj45.png',8,0,True),
}
for model,(profile,face,rj45,uplinks,poe) in expected.items():
    row=rows[model]
    assert row['status']=='experimental', model
    assert row['last_validated_version']=='2.4.11', model
    assert row['dashboard_support'] is True, model
    assert row['calibration_profile']==profile, model
    assert row['default_faceplate']==face, model
    assert row['visuals']['calibration_profile']==profile, model
    assert row['visuals']['recommended_faceplate']==face, model
    assert row['ports']['rj45']==rj45 and row['ports']['uplinks']==uplinks, model
    assert row['ports']['poe'] is poe, model
print('Ian UniFi exact visual mappings: PASS')
