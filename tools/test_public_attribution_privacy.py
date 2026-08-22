#!/usr/bin/env python3
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
OWNER = "zemerdon"
ALLOWED = {"", OWNER.casefold(), "community contributor", "anonymous"}
SUBMISSION_ID = re.compile(r"(?i)SV-[0-9]{4}-[0-9]+")
PACKAGE_NAME = re.compile(r"(?i)Switch[_ -]Vision[_ -]Contribution")


def main() -> None:
    registry = json.loads((ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json").read_text(encoding="utf-8"))
    for item in registry.get("devices", []):
        contributor = item.get("contributor") if isinstance(item, dict) else None
        if not isinstance(contributor, dict):
            continue
        name = str(contributor.get("display_name") or "").strip()
        if name.casefold() not in ALLOWED:
            raise SystemExit(f"Non-approved public contributor attribution remains for {item.get('model')}: {name!r}")
        if name.casefold() != OWNER.casefold() and contributor.get("public_credit") is True:
            raise SystemExit(f"Non-owner public credit remains enabled for {item.get('model')}")

    paths = [ROOT / "switch_vision_discovery/CHANGELOG.md"]
    paths += list((ROOT / "switch_vision_discovery/release-fragments").glob("*.md"))
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if SUBMISSION_ID.search(text):
            raise SystemExit(f"Submission identifier remains in public release text: {path}")
        if PACKAGE_NAME.search(text):
            raise SystemExit(f"Contribution package reference remains in public release text: {path}")

    print("Public attribution privacy policy: PASS")


if __name__ == "__main__":
    main()
