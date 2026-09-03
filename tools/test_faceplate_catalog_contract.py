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
print("Discovery faceplate catalog contract: PASS")
