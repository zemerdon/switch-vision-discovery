#!/usr/bin/env python3
"""Migrate Switch Vision Discovery app options through Supervisor only."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


LEGACY_IMPORT_BACKUP = Path("/data/options.before-import.json")


def _remove_legacy_import_backup() -> bool:
    """Remove the obsolete secret-bearing pre-v2.1.13 import backup."""
    try:
        LEGACY_IMPORT_BACKUP.unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeError(f"could not remove legacy import backup: {exc}") from exc
    return not LEGACY_IMPORT_BACKUP.exists()


def _token() -> str:
    for name in ("SUPERVISOR_TOKEN", "HASSIO_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _request(path: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    token = _token()
    if not token:
        raise RuntimeError("Supervisor API token is unavailable")
    body = None if method == "GET" else json.dumps(payload or {}).encode("utf-8")
    req = Request(
        f"http://supervisor{path}",
        method=method,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=12.0) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supervisor API returned HTTP {exc.code}: {detail[:160]}") from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Supervisor API request failed: {exc}") from exc
    if isinstance(data, dict) and data.get("result") == "error":
        raise RuntimeError(str(data.get("message") or "Supervisor API reported an error"))
    return data if isinstance(data, dict) else {}


def _options() -> dict:
    payload = _request("/addons/self/info")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    options = data.get("options") if isinstance(data, dict) else None
    if not isinstance(options, dict):
        raise RuntimeError("Supervisor did not expose Discovery options")
    return dict(options)


def main() -> int:
    legacy_backup_existed = LEGACY_IMPORT_BACKUP.exists()
    _remove_legacy_import_backup()

    options = _options()
    migrated = dict(options)
    changes: list[str] = []

    if "show_card_header" in migrated:
        migrated.pop("show_card_header", None)
        changes.append("removed show_card_header")

    for key in ("switches", "multi_switch_walks"):
        rows = migrated.get(key)
        if not isinstance(rows, list):
            continue
        updated = []
        changed = False
        for row in rows:
            if isinstance(row, dict) and "enabled" not in row:
                copy = dict(row)
                copy["enabled"] = "enabled"
                updated.append(copy)
                changed = True
            else:
                updated.append(row)
        if changed:
            migrated[key] = updated
            changes.append(f"made {key} enabled state explicit")

    if not changes:
        suffix = "; removed legacy secret-bearing import backup" if legacy_backup_existed else ""
        print("Switch Vision Discovery options migration: no Supervisor changes required" + suffix)
        return 0

    _request("/addons/self/options", method="POST", payload={"options": migrated})
    confirmed = _options()
    if "show_card_header" in confirmed:
        raise RuntimeError("Supervisor did not remove show_card_header")
    for key in ("switches", "multi_switch_walks"):
        rows = confirmed.get(key)
        if isinstance(rows, list) and any(isinstance(row, dict) and "enabled" not in row for row in rows):
            raise RuntimeError(f"Supervisor did not confirm {key} enabled-state migration")

    if legacy_backup_existed:
        changes.append("removed legacy secret-bearing import backup")
    print("Switch Vision Discovery options migration: " + "; ".join(changes))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Switch Vision Discovery warning: authoritative options migration skipped: {exc}", file=sys.stderr)
        raise SystemExit(1)
