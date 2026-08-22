#!/usr/bin/env python3
"""Sanitize public attribution metadata before release publication."""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re

TEXT_SUFFIXES = {
    ".md", ".bbcode", ".txt", ".json", ".yaml", ".yml", ".py", ".js",
    ".sh", ".html", ".css", ".xml", ".toml", ".ini", ".cfg", ".csv",
}
SUBMISSION_ID_RE = re.compile(r"(?i)SV-[0-9]{4}-[0-9]+")
PACKAGE_RE = re.compile(r"(?i)Switch[_ -]Vision[_ -]Contribution[^\s`\"']*")


def collect_private_identities(registry: Path, owner: str) -> set[str]:
    data = json.loads(registry.read_text(encoding="utf-8"))
    generic = {"", owner.casefold(), "community contributor", "anonymous"}
    identities: set[str] = set()
    for item in data.get("devices", []):
        contributor = item.get("contributor") if isinstance(item, dict) else None
        if not isinstance(contributor, dict):
            continue
        name = str(contributor.get("display_name") or "").strip()
        if name.casefold() in generic:
            continue
        identities.add(name)
        for token in re.findall(r"[A-Za-z0-9_.@+-]+", name):
            if len(token) >= 4 and token.casefold() not in generic:
                identities.add(token)
    return identities


def sanitize_text(text: str, identities: set[str]) -> str:
    for identity in sorted(identities, key=len, reverse=True):
        text = re.sub(re.escape(identity), "community contributor", text, flags=re.I)
    text = PACKAGE_RE.sub("community submission", text)
    text = SUBMISSION_ID_RE.sub("community validation", text)
    text = re.sub(r"(?i)community contributor['’]s", "community-provided", text)
    return text


def scrub_tree(root: Path, identities: set[str]) -> None:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = sanitize_text(text, identities)
        if updated != text:
            path.write_text(updated, encoding="utf-8", newline="\n")


def neutralize_registry(registry: Path, owner: str) -> None:
    data = json.loads(registry.read_text(encoding="utf-8"))
    for item in data.get("devices", []):
        contributor = item.get("contributor") if isinstance(item, dict) else None
        if not isinstance(contributor, dict):
            continue
        name = str(contributor.get("display_name") or "").strip()
        if name.casefold() != owner.casefold():
            contributor["display_name"] = "Community contributor"
            contributor["public_credit"] = False
    registry.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_release_text(root: Path, version: str, identities: set[str]) -> None:
    changelog = root / "switch_vision_discovery/CHANGELOG.md"
    old = sanitize_text(changelog.read_text(encoding="utf-8"), identities)
    old = re.sub(rf"^## {re.escape(version)}.*?(?=^## |\Z)", "", old, flags=re.M | re.S).lstrip()
    entry = f"""# Changelog

## {version}

- Apply a general public-attribution privacy policy to Discovery release history and structured public contributor metadata.
- Remove contributor and tester identities unless explicitly approved by the project owner.
- Remove submission identifiers, contribution package names, and submission filenames from public release/history text.
- Preserve technical validation facts using neutral **Community contributor** wording.
- Add permanent regression coverage preventing non-approved attribution or private submission references from returning.
- No device mapping, generated YAML, telemetry, dashboard-card, or runtime behaviour changes.

"""
    if old.startswith("# Changelog"):
        old = old[len("# Changelog"):].lstrip()
    changelog.write_text(entry + old, encoding="utf-8", newline="\n")

    fragment = root / f"switch_vision_discovery/release-fragments/{version}.md"
    fragment.write_text(f"""## {version}

- Apply a general public-attribution privacy policy to public Discovery release metadata.
- Remove non-approved contributor/tester identities, submission identifiers, contribution package names, and submission filenames.
- Preserve technical validation facts with neutral community wording.
- Add permanent privacy regression coverage.
- No runtime behaviour changes.
""", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--owner", default="zemerdon")
    parser.add_argument("--version")
    args = parser.parse_args()

    root = args.root.resolve()
    registry = root / "runtime_src/opt/switch-vision/devices/supported_devices.json"
    identities = collect_private_identities(registry, args.owner)
    scrub_tree(root, identities)
    neutralize_registry(registry, args.owner)
    if args.version:
        write_release_text(root, args.version, identities)
    print(f"Sanitized public attribution metadata; neutralized {len(identities)} identity token(s).")


if __name__ == "__main__":
    main()
