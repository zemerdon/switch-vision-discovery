#!/usr/bin/env python3
"""Hub faceplate comparison against existing, saved Core Calibration profiles.

No new model-registration or Calibration state is created: Core owns saved
profile image identity, Discovery owns reviewed model default, and this helper
persists only per-offer "Keep Current" collapse preferences.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path("/share/switch_vision/faceplate-upgrade-offers.json")
SCHEMA = 1
_SHA = re.compile(r"^[0-9a-f]{64}$")
_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,140}\.(?:png|webp|jpg|jpeg)$", re.I)
_KEY = re.compile(r"^(?:snmp|unifi):[^\x00-\x1f\x7f]{1,300}$")


def filename(value: Any) -> str:
    value = str(value or "").strip()
    if value.startswith("faceplates/"):
        value = value[len("faceplates/"):]
    return value if _FILE.fullmatch(value) else ""


def installed_assets(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("faceplate_fingerprints"), dict):
        return {}
    images = {}
    for name, info in payload["faceplate_fingerprints"].items():
        digest = str(info.get("sha256") or "").lower() if isinstance(info, dict) else ""
        if filename(name) == name and _SHA.fullmatch(digest):
            images[name] = digest
    return images


def registry_defaults(registry: Any) -> dict[str, str]:
    rows = registry.get("devices") if isinstance(registry, dict) else None
    result = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not row.get("dashboard_support"):
            continue
        model = str(row.get("model") or "").strip()
        image = filename(row.get("default_faceplate"))
        if 0 < len(model) <= 128 and image:
            result[model] = image
    return result


def generated_exact_models(documents: Any, models: set[str]) -> dict[str, str]:
    """Only associate a registered switch with an unambiguous exact-model card."""
    matches: dict[str, str] = {}
    invalid = set()

    def walk(node: Any, depth: int = 0) -> None:
        if depth > 16:
            return
        if isinstance(node, list):
            for entry in node[:1024]:
                walk(entry, depth + 1)
        elif isinstance(node, dict):
            if node.get("type") == "custom:switch-vision-3650":
                key = str(node.get("discovery_selected_switch") or node.get("selected_switch") or "").strip()
                model = str(node.get("switch_model") or "").strip()
                if 0 < len(key) <= 120 and model in models:
                    if key in matches and matches[key] != model:
                        invalid.add(key)
                    else:
                        matches[key] = model
            for value in node.values():
                if isinstance(value, (list, dict)):
                    walk(value, depth + 1)
    walk(documents)
    for name in invalid:
        matches.pop(name, None)
    return matches


def _profile_base(switch_name: str) -> set[str]:
    key = re.sub(r"[^A-Za-z0-9_-]+", "_", switch_name.strip()).strip("_")[:96]
    return {f"native_{key}", f"custom_{key}"} if key else set()


def offers_from_saved(
    inventory: list[dict[str, str]],
    defaults: dict[str, str],
    assets: dict[str, str],
    profiles: Any,
    collapsed: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Only offer a changed stock image when the old saved image still exists.

    No saved profile => nothing needs resetting. Multiple saved scopes or
    missing/overwritten old imagery => fail closed rather than falsely
    previewing or resetting a different switch.
    """
    profiles = profiles if isinstance(profiles, list) else []
    collapsed = collapsed or {}
    offers = []
    seen = set()
    for device in inventory:
        key = str(device.get("device_key") or "")
        name = str(device.get("switch_name") or "")
        model = str(device.get("resolved_model") or "")
        if not _KEY.fullmatch(key) or not name or model not in defaults or key in seen:
            continue
        seen.add(key)
        new_file = defaults[model]
        new_hash = assets.get(new_file)
        if not new_hash:
            continue
        matching = [item for item in profiles if isinstance(item, dict) and
                    item.get("active") and item.get("base_profile") in _profile_base(name)]
        if len(matching) != 1:
            continue
        active = matching[0]
        source = str(active.get("faceplate_source") or "").strip().lower()
        selected = filename(active.get("faceplate"))
        old_file = selected if source == "custom" and selected else filename(active.get("saved_calibration_image"))
        if not old_file:
            continue
        # Retained stock artwork is content-addressed, not renamed. For an
        # in-place PNG correction Core proves the saved original's SHA and
        # immutable historical preview; a filename alone is never evidence.
        same_file = old_file == new_file
        preview = old_file
        if same_file:
            old_hash = str(active.get("saved_stock_sha256") or "").lower()
            preview = str(active.get("saved_stock_preview") or "")
            allowed = (f"faceplate-history/{old_hash}/{old_file}",
                       f"faceplate-history/legacy/{old_file}")
            if not _SHA.fullmatch(old_hash) or old_hash == new_hash or preview not in allowed:
                continue
        else:
            old_hash = assets.get(old_file)
        if not old_hash:
            continue
        offers.append({
            "device_key": key,
            "switch_name": name,
            "display_name": str(device.get("display_name") or "")[:120],
            "model": model,
            "base_profile": str(active["base_profile"]),
            "current_file": old_file,
            "current_sha256": old_hash,
            "current_preview": preview,
            "same_filename": same_file,
            "available_file": new_file,
            "available_sha256": new_hash,
            "collapsed": collapsed.get(key) == new_hash,
        })
    return offers


def load(path: Path | None = None) -> dict[str, str]:
    path = DEFAULT_PATH if path is None else path
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        return {}
    choices = value.get("collapsed")
    if not isinstance(choices, dict):
        return {}
    return {key: sha for key, sha in choices.items()
            if isinstance(key, str) and _KEY.fullmatch(key) and
            isinstance(sha, str) and _SHA.fullmatch(sha)}


def keep_current(key: str, sha: str, path: Path | None = None) -> None:
    if not _KEY.fullmatch(key) or not _SHA.fullmatch(sha):
        raise ValueError("Invalid faceplate offer identity")
    path = Path(DEFAULT_PATH if path is None else path)
    if path.is_symlink():
        raise ValueError("Unsafe faceplate preference location")
    choices = load(path)
    choices[key] = sha
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump({"schema": SCHEMA, "collapsed": choices}, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
