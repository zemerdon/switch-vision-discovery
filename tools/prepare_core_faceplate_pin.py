#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# This helper is routinely invoked directly during local candidate coordination.
# Keep it source-tree-clean even outside sv_release_check's -B/PYTHONDONTWRITEBYTECODE
# environment, because importing sibling contract helpers must never create
# __pycache__ that later trips the release hygiene gate.
sys.dont_write_bytecode = True

import check_component_contracts as contracts

ROOT = Path(__file__).resolve().parents[1]
PIN_PATH = ROOT / "contracts" / "core-faceplate-catalog.json"
REGISTRY_PATH = ROOT / "runtime_src" / "opt" / "switch-vision" / "devices" / "supported_devices.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def git_sha(root: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    value = (proc.stdout or "").strip().lower()
    if proc.returncode or SHA_RE.fullmatch(value) is None:
        raise SystemExit("exact Core source SHA is unavailable")
    dirty = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if dirty.returncode or (dirty.stdout or "").strip():
        raise SystemExit("Core source tree must be clean before binding the faceplate catalog pin")
    return value


def expected_pin(core_source_root: Path, core_source_sha: str) -> dict[str, str]:
    if SHA_RE.fullmatch(core_source_sha) is None:
        raise SystemExit(f"Core source SHA is invalid: {core_source_sha!r}")
    catalog_path = core_source_root / contracts.CORE_FACEPLATE_CATALOG_PATH
    if not catalog_path.is_file():
        raise SystemExit(f"Core faceplate catalog is missing: {catalog_path}")
    labels = contracts.parse_faceplate_catalog(json.loads(catalog_path.read_text(encoding="utf-8")))
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    errors = contracts.validate_default_faceplates(registry, labels)
    if errors:
        raise SystemExit("Discovery registry does not resolve against exact Core catalog: " + "; ".join(errors))
    return {
        "schema": contracts.FACEPLATE_PIN_SCHEMA,
        "repository": contracts.CORE_FACEPLATE_REPOSITORY,
        "commit_sha": core_source_sha,
        "path": contracts.CORE_FACEPLATE_CATALOG_PATH,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bind Discovery's published faceplate catalog pin to the exact Core source used for release validation."
    )
    parser.add_argument("--core-source-root", required=True, type=Path)
    parser.add_argument("--core-source-sha", default="")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    core_root = args.core_source_root.expanduser().resolve()
    sha = str(args.core_source_sha or "").strip().lower() or git_sha(core_root)
    expected = expected_pin(core_root, sha)

    if args.check:
        raw_current = json.loads(PIN_PATH.read_text(encoding="utf-8"))
        parsed_current = contracts.parse_faceplate_pin(raw_current)
        current = {"schema": raw_current.get("schema"), **parsed_current}
        if current != expected:
            raise SystemExit(
                "Discovery Core faceplate pin drift: "
                f"expected={json.dumps(expected, sort_keys=True)} "
                f"current={json.dumps(current, sort_keys=True)}"
            )
        print(f"Discovery Core faceplate pin: PASS ({sha})")
        return 0

    PIN_PATH.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    print(f"Discovery Core faceplate pin updated: {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
