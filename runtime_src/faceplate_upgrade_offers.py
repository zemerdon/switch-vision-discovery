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



def offers_from_choices(
    inventory: list[dict[str, str]],
    defaults: dict[str, str],
    assets: dict[str, str],
    choices: Any,
    collapsed: dict[str, str] | None = None,
    revisions: dict[str, list[dict[str, str]]] | None = None,
) -> list[dict[str, str]]:
    """Compare the actual approved per-switch image, independent of geometry.

    Core alone supplies verified stock revisions and retained historical
    preview paths. We never infer prior pixels from a matching filename,
    and we never offer a reset of a switch's saved Calibration.
    """
    choices = choices if isinstance(choices, dict) else {}
    collapsed = collapsed or {}
    revisions = revisions or {}
    offers: list[dict[str, str]] = []
    seen: set[str] = set()
    for device in inventory:
        key = str(device.get("device_key") or "")
        name = str(device.get("switch_name") or "")
        model = str(device.get("resolved_model") or "")
        if not _KEY.fullmatch(key) or not name or model not in defaults or key in seen:
            continue
        seen.add(key)
        target_file = defaults[model]
        target_sha = assets.get(target_file)
        if not target_sha:
            continue
        scope_choices = [
            (base, choices.get(base))
            for base in sorted(_profile_base(name))
            if isinstance(choices.get(base), dict)
        ]
        # Each scope owns an independent selection. Show the first pending
        # scope, then offer the other after approval, without cross-switch
        # or cross-scope mutation.
        # When both dashboards need an upgrade, Native is the visible
        # generated dashboard and must be offered first. Approval remains
        # strictly one scope at a time; the other scope is re-evaluated on
        # the next Hub refresh rather than silently resetting its Calibration.
        scope_choices.sort(key=lambda item: (0 if item[0].startswith("native_") else 1, item[0]))
        for base, current in scope_choices:
            old_file = filename(current.get("filename"))
            old_sha = str(current.get("sha256") or "").lower()
            old_path = str(current.get("path") or "")
            old_unavailable = bool(current.get("unavailable"))
            if not old_file or not _SHA.fullmatch(old_sha) or (not old_path and not old_unavailable):
                continue
            available_versions = revisions.get(target_file, [])
            if not isinstance(available_versions, list):
                available_versions = []
            valid_versions = [row for row in available_versions[:64]
                              if isinstance(row, dict) and row.get('filename') == target_file
                              and _SHA.fullmatch(str(row.get('sha256', '')))
                              and _SHA.fullmatch(str(row.get('geometry_sha256', '')))
                              and isinstance(row.get('path'), str)]
            current_version = str(current.get("version") or "")
            current_geometry = str(current.get("geometry_sha256") or "")
            latest = next((row for row in valid_versions
                           if row.get("path") == f"faceplates/{target_file}"), {})
            latest_version = str(latest.get("version") or "")
            latest_geometry = str(latest.get("geometry_sha256") or "")
            # A current Native/Custom scope is never an upgrade offer just
            # because the catalogue contains older selectable revisions.
            # Otherwise an already-current Custom pin masks a genuinely
            # outdated Native pin for the same switch.
            # Same-PNG geometry-only changes still count as upgrades.
            if old_file == target_file and old_sha == target_sha:
                if ((current_version and current_version == latest_version)
                        or (current_geometry and current_geometry == latest_geometry)
                        or not latest_version):
                    continue
            if old_file == target_file:
                allowed_paths = {f"faceplate-history/{old_sha}/{old_file}"}
                allowed_paths.update(row["path"] for row in valid_versions if row["sha256"] == old_sha)
                if old_sha != target_sha and old_path not in allowed_paths and not old_unavailable:
                    continue
            elif (old_path != f"faceplates/{old_file}"
                  and old_path != f"faceplate-history/{old_sha}/{old_file}" and not old_unavailable):
                continue
            choice_key = f"{key}@{base}"
            offers.append({
                "device_key": key,
                "switch_name": name,
                "display_name": str(device.get("display_name") or "")[:120],
                "model": model,
                "base_profile": base,
                "current_file": old_file,
                "current_sha256": old_sha,
                "current_preview": old_path if old_path.startswith(("faceplate-history/", "faceplates-old/")) else "",
                "old_preview_unavailable": old_unavailable,
                "same_filename": old_file == target_file,
                "available_file": target_file,
                "available_sha256": target_sha,
                "collapsed": collapsed.get(choice_key) == (latest_geometry or target_sha)
                    or (old_file == target_file and old_sha == target_sha
                        and current_version == latest_version
                        and bool(latest_version)),
                "current_version": current_version,
                "available_version": latest_version,
                "available_geometry_sha256": latest_geometry,
                "versions": valid_versions,
            })
            break
    return offers


def selectable_for_devices(
    inventory: list[dict[str, str]],
    defaults: dict[str, str],
    assets: dict[str, str],
    choices: Any,
    revisions: Any,
) -> list[dict[str, Any]]:
    """Always-available model-scoped selection for verified installed pairs.

    Unlike one-time offers, keep dismissals cannot hide these options. All
    images and revisions originate from Core's verified catalogue, and only
    the affected native/custom profile is ever returned.
    """
    if not isinstance(choices, dict) or not isinstance(revisions, dict):
        return []
    result = []
    seen = set()
    for device in inventory[:256]:
        key = str(device.get("device_key") or "")
        name = str(device.get("switch_name") or "")
        model = str(device.get("resolved_model") or "")
        if not _KEY.fullmatch(key) or not name or key in seen:
            continue
        seen.add(key)
        recommended = defaults.get(model, "")
        if recommended not in assets:
            recommended = ""
        found_current = False
        for base in sorted(_profile_base(name)):
            current = choices.get(base)
            if not isinstance(current, dict):
                continue
            old_file = filename(current.get("filename"))
            sha = str(current.get("sha256") or "")
            path = str(current.get("path") or "")
            if (not old_file or not _SHA.fullmatch(sha) or not path
                    or current.get("unavailable")):
                continue
            # Core supplies only verified, server-owned selected paths. A
            # missing/tampered choice is never represented as active artwork.
            if not (path == "faceplates/" + old_file
                    or re.fullmatch(
                        r"faceplate-history/revisions/sha/[a-f0-9]{64}/"
                        + re.escape(old_file), path)
                    or re.fullmatch(
                        r"faceplates-old/\d+\.\d+\.\d+/"
                        + re.escape(old_file), path)
                    or re.fullmatch(
                        r"faceplate-history/(?:legacy|[a-f0-9]{64})/"
                        + re.escape(old_file), path)):
                continue
            found_current = True
            options = []
            identities = set()
            # Once upgraded, previously chosen generic artwork remains
            # available for this switch only. Core owns the remembered,
            # server-approved set; unrelated models cannot be added by Hub.
            historical_names = current.get("eligible_faceplates", [])
            if not isinstance(historical_names, list):
                historical_names = []
            eligible = [old_file, recommended, *historical_names[:16]]
            for image in dict.fromkeys(eligible):
                if not filename(image) or image not in assets:
                    continue
                for row in revisions.get(image, [])[:64] if isinstance(revisions.get(image), list) else []:
                    if (not isinstance(row, dict) or row.get("filename") != image
                            or not _SHA.fullmatch(str(row.get("sha256") or ""))
                            or not _SHA.fullmatch(str(row.get("geometry_sha256") or ""))):
                        continue
                    version = str(row.get("version") or "")
                    asset_path = str(row.get("path") or "")
                    if not version or not asset_path or not (
                        asset_path == "faceplates/" + image
                        or re.fullmatch(
                            r"faceplate-history/revisions/sha/[a-f0-9]{64}/"
                            + re.escape(image), asset_path)
                        or re.fullmatch(
                            r"faceplates-old/\d+\.\d+\.\d+/"
                            + re.escape(image), asset_path)
                    ):
                        continue
                    identity = (image, row["sha256"], row["geometry_sha256"], version)
                    if identity in identities:
                        continue
                    identities.add(identity)
                    options.append({k: row[k] for k in (
                        "filename", "sha256", "geometry_sha256", "version", "path"
                    )})
            selected_version = str(current.get("version") or "")
            selected_geo = str(current.get("geometry_sha256") or "")
            selected = any(
                o["filename"] == old_file and o["sha256"] == sha
                and (not selected_version or o["version"] == selected_version)
                and (not selected_geo or o["geometry_sha256"] == selected_geo)
                for o in options
            )
            # Do not suggest an unverified current selection; fail closed
            # rather than silently present a new model's image as current.
            result.append({
                "verified_current": True,
                "current_in_catalog": selected,
                "current_path": path,
                "device_key": key, "switch_name": name,
                "display_name": str(device.get("display_name") or "")[:120],
                "model": model, "base_profile": base,
                "current_file": old_file, "current_sha256": sha,
                "current_version": selected_version,
                "current_geometry_sha256": selected_geo,
                "available_file": recommended,
                "options": options,
            })
        if not found_current:
            # Visibility and mutation authority are independent: every
            # configured SNMP switch appears in Device Overview even when a
            # verified stock pin/profile is not available yet.
            result.append({
                "verified_current": False, "device_key": key,
                "switch_name": name,
                "display_name": str(device.get("display_name") or "")[:120],
                "model": model, "base_profile": "",
                "current_file": "", "current_sha256": "",
                "current_version": "", "current_geometry_sha256": "",
                "current_path": "", "available_file": recommended,
                "options": [],
            })
    return result
