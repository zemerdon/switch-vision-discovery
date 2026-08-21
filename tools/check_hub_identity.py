#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "switch_vision_discovery" / "config.yaml"
text = CONFIG.read_text(encoding="utf-8")

required = [
    'name: Switch Vision Discovery',
    'ingress: true',
    'panel_title: Switch Vision Hub',
]
missing = [token for token in required if token not in text]
if missing:
    raise SystemExit("Discovery Hub identity contract failed: missing " + ", ".join(missing))
if 'panel_title: Support My Switch' in text:
    raise SystemExit("Discovery Hub identity contract failed: legacy Support My Switch panel title returned")

print("Discovery Hub identity contract: PASS")
