#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
APP = ROOT / "switch_vision_discovery"
VERSION = "2.1.31"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8", newline="\n")


def replace_once(path: Path, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        raise SystemExit(f"Missing expected marker in {path}: {old!r}")
    write(path, text.replace(old, new, 1))


config = APP / "config.yaml"
replace_once(config, 'version: "2.1.30"', f'version: "{VERSION}"')
replace_once(config, 'panel_title: Support My Switch', 'panel_title: Switch Vision Hub')

for path in (RUNTIME / "run.sh", RUNTIME / "discovery_job.sh"):
    text = read(path)
    updated, count = re.subn(
        r'SWITCH_VISION_DISCOVERY_VERSION="2\.1\.30"',
        f'SWITCH_VISION_DISCOVERY_VERSION="{VERSION}"',
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"Current Discovery version marker missing in {path}")
    write(path, updated)

# Advance only current-version self-test expectations. Historical v2.1.28 and
# earlier regression fixtures intentionally retain their historical version text.
self_test = RUNTIME / "self-test.sh"
text = read(self_test)
text = text.replace('SWITCH_VISION_DISCOVERY_VERSION="2.1.30"', f'SWITCH_VISION_DISCOVERY_VERSION="{VERSION}"')
text = text.replace('version: "2.1.30"', f'version: "{VERSION}"')

regression = r'''

# v2.1.31 Hub/sidebar identity regression.
grep -Fq 'panel_title: Switch Vision Hub' "${ROOT_DIR}/../switch_vision_discovery/config.yaml"
if grep -Fq 'panel_title: Support My Switch' "${ROOT_DIR}/../switch_vision_discovery/config.yaml"; then
    echo "ERROR: Discovery app still exposes the old Support My Switch sidebar title"
    exit 1
fi
echo "Switch Vision Discovery v2.1.31 Hub sidebar identity regression: PASS"
'''
if 'v2.1.31 Hub/sidebar identity regression' not in text:
    text += regression
write(self_test, text)

changelog = APP / "CHANGELOG.md"
entry = '''## 2.1.31\n\n- Renames the Home Assistant ingress/sidebar panel from **Support My Switch** to **Switch Vision Hub**.\n- Keeps the app itself named **Switch Vision Discovery** in Settings → Apps.\n- Keeps Support My Switch as a feature inside the Hub rather than the identity of the entire management interface.\n- Preserves v2.1.30 progress-stage behavior, v2.1.29 Huawei defaults, atomic SNMP2MQTT YAML publication, mappings, telemetry and generated-card behavior.\n\n'''
current = read(changelog)
if not current.startswith("## 2.1.31"):
    write(changelog, entry + current)

print("Prepared Switch Vision Discovery v2.1.31 Hub sidebar identity release")
