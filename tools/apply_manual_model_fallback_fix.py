#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "runtime_src/support_web.py"

old = '''    return models or {\n        "WS-C3650-48PD-E", "WS-C3650-48PD-L", "WS-C2960X-48FPD-L",\n        "WS-C2960X-24PS-L", "WS-C2960X-24TS-L", "WS-C2960S-48FPD-L",\n        "WS-C3560CG-8PC-S", "EX3300-48P", "SG500X-24",\n        "S5720-12TP-LI-AC", "S5735-L8P4X-A1",\n    }\n'''
new = '''    return models or {\n        "WS-C3650-48PD-E", "WS-C3650-48PD-L", "WS-C2960X-48FPD-L",\n        "WS-C2960X-24PS-L", "WS-C2960X-24TS-L", "WS-C2960S-48FPD-L",\n        "WS-C3560CG-8PC-S", "WS-C3750-48P", "WS-C3750X-48P",\n        "EX3300-48P", "SG500X-24", "S5720-12TP-LI-AC",\n        "S5735-L8P4X-A1", "CRS328-24P-4S+RM", "XS1930-10",\n        "N2128PX-ON", "PowerConnect 5548P",\n    }\n'''

text = TARGET.read_text(encoding="utf-8")
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected one stale fallback block, found {count}")
TARGET.write_text(text.replace(old, new, 1), encoding="utf-8")
