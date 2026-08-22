#!/usr/bin/env python3
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
OWNER = "zemerdon"
ALLOWED = {"", OWNER.casefold(), "community contributor", "anonymous"}
SUBMISSION_ID = re.compile(r"(?i)SV[-_]20\d{2}[-_]\d+")
PACKAGE_NAME = re.compile(r"(?i)Switch[_ -]Vision[_ -]Contribution")


def check_structured(value: object, path: Path) -> None:
    if isinstance(value, dict):
        if "display_name" in value and "public_credit" in value:
            name = str(value.get("display_name") or "").strip()
            if name.casefold() not in ALLOWED:
                raise SystemExit(f"Non-approved public attribution remains in {path}: {name!r}")
            if name.casefold() != OWNER.casefold() and value.get("public_credit") is True:
                raise SystemExit(f"Non-owner public credit remains enabled in {path}")
        for child in value.values():
            check_structured(child, path)
    elif isinstance(value, list):
        for child in value:
            check_structured(child, path)
    elif isinstance(value, str):
        if SUBMISSION_ID.search(value):
            raise SystemExit(f"Submission identifier remains in structured public metadata: {path}")
        if PACKAGE_NAME.search(value):
            raise SystemExit(f"Contribution package reference remains in structured public metadata: {path}")


def main() -> None:
    registries = [
        path
        for path in ROOT.rglob("supported_devices.json")
        if path.is_file() and "devices" in path.parts
    ]
    if not registries:
        raise SystemExit("No public supported-device registry found")
    for path in registries:
        check_structured(json.loads(path.read_text(encoding="utf-8")), path)

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
