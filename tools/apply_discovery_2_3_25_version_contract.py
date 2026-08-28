#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

changes = {
    ROOT / "runtime_src/discovery_job.sh": (
        'SWITCH_VISION_DISCOVERY_VERSION="2.3.24"',
        'SWITCH_VISION_DISCOVERY_VERSION="2.3.25"',
        1,
    ),
    ROOT / "runtime_src/self-test.sh": (
        'SWITCH_VISION_DISCOVERY_VERSION="2.3.24"',
        'SWITCH_VISION_DISCOVERY_VERSION="2.3.25"',
        2,
    ),
}

for path, (old, new, expected) in changes.items():
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"{path}: expected {expected} occurrences of {old!r}, found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    print(f"updated {path.relative_to(ROOT)} ({count} occurrence(s))")
