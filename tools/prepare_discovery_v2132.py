#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
APP = ROOT / "switch_vision_discovery"
CURRENT = "2.1.31"
VERSION = "2.1.32"


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
replace_once(config, f'version: "{CURRENT}"', f'version: "{VERSION}"')
replace_once(config, 'panel_title: Support My Switch', 'panel_title: Switch Vision Hub')

for path in (RUNTIME / "run.sh", RUNTIME / "discovery_job.sh"):
    text = read(path)
    updated, count = re.subn(
        rf'SWITCH_VISION_DISCOVERY_VERSION="{re.escape(CURRENT)}"',
        f'SWITCH_VISION_DISCOVERY_VERSION="{VERSION}"',
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"Current Discovery version marker missing in {path}")
    write(path, updated)

# Advance only current-version self-test expectations. Historical fixtures keep
# their original release identifiers as part of their regression evidence.
self_test = RUNTIME / "self-test.sh"
text = read(self_test)
text = text.replace(
    f'SWITCH_VISION_DISCOVERY_VERSION="{CURRENT}"',
    f'SWITCH_VISION_DISCOVERY_VERSION="{VERSION}"',
)
text = text.replace(
    f'grep -Fq \'version: "{CURRENT}"\'',
    f'grep -Fq \'version: "{VERSION}"\'',
)

regression = r'''

# v2.1.32 Hub/sidebar identity regression.
grep -Fq 'panel_title: Switch Vision Hub' "${ROOT_DIR}/../switch_vision_discovery/config.yaml"
if grep -Fq 'panel_title: Support My Switch' "${ROOT_DIR}/../switch_vision_discovery/config.yaml"; then
    echo "ERROR: Discovery app still exposes the old Support My Switch sidebar title"
    exit 1
fi
echo "Switch Vision Discovery v2.1.32 Hub sidebar identity regression: PASS"
'''
if 'v2.1.32 Hub/sidebar identity regression' not in text:
    text += regression
write(self_test, text)

changelog = APP / "CHANGELOG.md"
entry = '''# Changelog\n\n## 2.1.32\n\n- Rename the Home Assistant ingress/sidebar panel from **Support My Switch** to **Switch Vision Hub**.\n- Keep the app itself named **Switch Vision Discovery** in Settings → Apps.\n- Keep Support My Switch as a feature inside the Hub rather than the identity of the entire management interface.\n- Preserve v2.1.31 authoritative generated-YAML handoff hardening, v2.1.30 structured progress highlighting, v2.1.29 Huawei defaults, mappings, telemetry and generated-card behavior.\n\n'''
current = read(changelog)
if current.startswith("# Changelog\n\n"):
    body = current[len("# Changelog\n\n"):]
    if not body.startswith("## 2.1.32"):
        write(changelog, entry + body)
else:
    raise SystemExit("Discovery changelog header is not in the expected format")

print("Prepared Switch Vision Discovery v2.1.32 Hub sidebar identity release")
