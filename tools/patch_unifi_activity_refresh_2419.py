#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "runtime_src" / "unifi_dashboard_cards.py"
RELEASE_CHECK = ROOT / "tools" / "sv_release_check.py"
CHANGELOG = ROOT / "switch_vision_discovery" / "CHANGELOG.md"

text = GENERATOR.read_text(encoding="utf-8")
old = '"unifi_refresh_seconds": 30,'
new = '"unifi_refresh_seconds": 10,'
old_count = text.count(old)
if old_count:
    if old_count != 2:
        raise SystemExit(f"expected exactly two UniFi 30-second refresh defaults, found {old_count}")
    text = text.replace(old, new)
elif text.count(new) != 2:
    raise SystemExit("UniFi refresh defaults are neither old nor fully patched")
GENERATOR.write_text(text, encoding="utf-8", newline="\n")

release = RELEASE_CHECK.read_text(encoding="utf-8")
entry = '    "tools/test_unifi_activity_refresh_contract.py",\n'
anchor = '    "tools/test_faceplate_matrix_2419.py",\n'
if entry not in release:
    if anchor not in release:
        raise SystemExit("release-check faceplate regression anchor missing")
    release = release.replace(anchor, anchor + entry, 1)
RELEASE_CHECK.write_text(release, encoding="utf-8", newline="\n")

changelog = CHANGELOG.read_text(encoding="utf-8")
bullet = (
    "- Refresh native UniFi dashboard snapshots every 10 seconds so UniFi2MQTT 4.0 "
    "counter activity follows the controller telemetry cadence; keep the 12-second "
    "activity hold so sustained traffic remains visibly active between samples.\n"
)
anchor = (
    "- Add an exact-model regression so Discovery cannot silently drift from the approved "
    "faceplate/profile matrix again.\n"
)
if bullet not in changelog:
    if anchor not in changelog:
        raise SystemExit("Discovery 2.4.19 changelog anchor missing")
    changelog = changelog.replace(anchor, anchor + bullet, 1)
CHANGELOG.write_text(changelog, encoding="utf-8", newline="\n")

print("Discovery 2.4.19 UniFi activity refresh patch applied")
