#!/usr/bin/env python3
import importlib.util
from pathlib import Path
r=Path(__file__).resolve().parents[1]; s=importlib.util.spec_from_file_location("c",r/"tools/check_component_contracts.py")
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
labels=m.parse_faceplate_catalog({"schema":m.FACEPLATE_CATALOG_SCHEMA,"faceplates":[
{"filename":"unifi-24-rj45-2sfp-inline.png","display_name":"UniFi 24-Port · 2 × SFP · Inline"},
{"filename":"unifi-4-rj45-12sfp.png","display_name":"UniFi 4-Port · 12 × SFP"}]})
assert labels["unifi-24-rj45-2sfp-inline.png"].endswith("Inline")
assert not m.validate_default_faceplates({"devices":[{"model":"ok","default_faceplate":"faceplates/unifi-24-rj45-2sfp-inline.png"}]},labels)
assert m.validate_default_faceplates({"devices":[{"model":"bad","default_faceplate":"faceplates/missing.png"}]},labels)
try:m.parse_faceplate_pin({"schema":m.FACEPLATE_PIN_SCHEMA,"repository":m.CORE_FACEPLATE_REPOSITORY,"commit_sha":"main","path":m.CORE_FACEPLATE_CATALOG_PATH})
except RuntimeError:pass
else:raise SystemExit("non-SHA pin accepted")
import json,sys
registry=json.loads((r/"runtime_src/opt/switch-vision/devices/supported_devices.json").read_text(encoding="utf-8"))
rows={x["model"]:x for x in registry["devices"] if isinstance(x,dict) and x.get("model")}
expected={
"GS1900-8":("faceplates/24rj45-2sfp.png","stock_24rj45_2sfp",8,0),
"SR-S25G3420F":("faceplates/24rj45-4sfp.png","stock_24rj45_4sfp",16,4),
"US 16 PoE 150W":("faceplates/24rj45-2sfp.png","stock_24rj45_2sfp",16,2),
"GS1900-24E":("faceplates/24rj45-2sfp.png","stock_24rj45_2sfp",24,0),
"SG350-20":("faceplates/24rj45-4sfp.png","stock_24rj45_4sfp",16,4),
"HP J8693A Switch 3500yl-48G":("faceplates/48rj45-4sfp.png","stock_48rj45_4sfp",44,4),
"USW Flex 2.5G 5":("faceplates/unifi-5rj45.png","default_unifi_5_rj45",5,0),
"USW WAN":("faceplates/24rj45-4sfp.png","stock_24rj45_4sfp",1,3),
"USW Aggregation":("faceplates/unifi-32sfp.png","unifi_32sfp",0,8),
"USW Pro Aggregation":("faceplates/unifi-32sfp.png","unifi_32sfp",0,32),}
for model,(face,profile,rj,sfp) in expected.items():
 row=rows[model];assert row["dashboard_support"] is True,model;assert row["default_faceplate"]==face and row["calibration_profile"]==profile,model;assert row["ports"]["rj45"]==rj and row["ports"]["uplinks"]==sfp,model;assert row["visuals"]["recommended_faceplate"]==face and row["visuals"]["calibration_profile"]==profile,model
assert rows["USW Aggregation"]["unifi_api_port_map"]=={"rj45":[],"sfp":list(range(1,9))}
assert rows["USW Pro Aggregation"]["unifi_api_port_map"]=={"rj45":[],"sfp":list(range(1,33))}
assert rows["USW WAN"]["unifi_api_port_map"]=={"rj45":[4],"sfp":[1,2,3]}
u_spec=importlib.util.spec_from_file_location("sv_unifi_cards",r/"runtime_src/unifi_dashboard_cards.py");u=importlib.util.module_from_spec(u_spec);sys.modules[u_spec.name]=u;u_spec.loader.exec_module(u)
assert u.visual_geometry_matches("faceplates/24rj45-2sfp.png",8,0) and u.visual_geometry_matches("faceplates/24rj45-2sfp.png",16,2);assert not u.visual_geometry_matches("faceplates/24rj45-2sfp.png",24,4);assert u.generic_visual(8,0)[:2]==("stock_24rj45_2sfp","faceplates/24rj45-2sfp.png")
def ports(rj,sfp): return [{"idx":i,"connector":"RJ45"} for i in rj]+[{"idx":i,"connector":"SFP28" if i>=29 else "SFPPLUS"} for i in sfp]
for model,payload,rj,sfp,face in [("USW Aggregation",ports([],range(1,9)),0,8,"unifi-32sfp.png"),("USW Pro Aggregation",ports([],range(1,33)),0,32,"unifi-32sfp.png"),("US 16 PoE 150W",ports(range(1,17),range(17,19)),16,2,"24rj45-2sfp.png"),("USW WAN",ports([4],[1,2,3]),1,3,"24rj45-4sfp.png")]:
 rendered=u.render({"devices":[{"model":model,"id":"fixture","name":model,"ports":payload}]},registry);text,emitted=rendered[0],rendered[1];assert emitted==1,(model,rendered[1:]);assert f"port_count: {rj}" in text and f"sfp_port_count: {sfp}" in text,model;assert f"faceplate_file: {face}" in text,model
assert "sfp_port_count: 32" not in u.render({"devices":[{"model":"USW Aggregation","id":"agg","ports":ports([],range(1,9))}]},registry)[0]
print("Discovery faceplate catalog contract: PASS")
