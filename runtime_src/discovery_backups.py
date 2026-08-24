#!/usr/bin/env python3
"""Private retained configuration snapshots for Switch Vision Discovery.

Only Switch Vision Discovery-owned backup filenames inside the dedicated backup
directory are ever listed, pruned, or removed. Backup contents may contain
secrets and are intentionally never returned by the maintenance metadata API.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any

DEFAULT_BACKUP_DIR = Path("/share/switch_vision/backups/discovery")
BACKUP_FORMAT = "switch-vision-discovery-backup-v1"
BACKUP_PREFIX = "switch-vision-discovery-backup-"
BACKUP_FILENAME_RE = re.compile(
    r"^switch-vision-discovery-backup-(\d{8}T\d{12}Z)-([0-9a-f]{8})\.json$"
)
RETENTION_ENABLED_KEY = "backup_retention_enabled"
RETENTION_COUNT_KEY = "backup_retention_count"
DEFAULT_RETENTION_ENABLED = True
DEFAULT_RETENTION_COUNT = 5
MIN_RETENTION_COUNT = 1
MAX_RETENTION_COUNT = 10
_ALLOWED_REASONS = {"configuration_import", "device_state_update"}


class DiscoveryBackupError(RuntimeError):
    """Fail-closed Discovery backup contract error."""


def _strict_bool(value: Any, field: str, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes", "on", "enabled"}:
            return True
        if normalized in {"false", "0", "no", "off", "disabled"}:
            return False
    raise DiscoveryBackupError(f"{field} must be true or false.")


def _strict_retention_count(value: Any) -> int:
    if value is None:
        return DEFAULT_RETENTION_COUNT
    if isinstance(value, bool):
        raise DiscoveryBackupError(
            f"{RETENTION_COUNT_KEY} must be between "
            f"{MIN_RETENTION_COUNT} and {MAX_RETENTION_COUNT}."
        )
    if isinstance(value, int):
        count = value
    elif isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
        count = int(value.strip())
    else:
        raise DiscoveryBackupError(
            f"{RETENTION_COUNT_KEY} must be between "
            f"{MIN_RETENTION_COUNT} and {MAX_RETENTION_COUNT}."
        )
    if count < MIN_RETENTION_COUNT or count > MAX_RETENTION_COUNT:
        raise DiscoveryBackupError(
            f"{RETENTION_COUNT_KEY} must be between "
            f"{MIN_RETENTION_COUNT} and {MAX_RETENTION_COUNT}."
        )
    return count


def retention_settings(options: dict[str, Any]) -> tuple[bool, int]:
    """Return validated automatic-retention settings or fail closed."""
    if not isinstance(options, dict):
        raise DiscoveryBackupError("Discovery options must be a JSON object.")
    enabled = _strict_bool(
        options.get(RETENTION_ENABLED_KEY),
        RETENTION_ENABLED_KEY,
        DEFAULT_RETENTION_ENABLED,
    )
    count = _strict_retention_count(options.get(RETENTION_COUNT_KEY))
    return enabled, count


def _ensure_backup_dir(directory: Path) -> Path:
    directory = Path(directory)
    try:
        if directory.exists() or directory.is_symlink():
            mode = directory.lstat().st_mode
            if not stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
                raise DiscoveryBackupError(
                    f"Discovery backup path is not a private directory: {directory}"
                )
        else:
            directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        os.chmod(directory, 0o700)
    except OSError as exc:
        raise DiscoveryBackupError(
            f"Could not prepare the Discovery backup directory: {exc}"
        ) from exc
    return directory


def _parse_owned_name(name: Any) -> tuple[str, datetime]:
    if not isinstance(name, str):
        raise DiscoveryBackupError("Discovery backup name is invalid.")
    match = BACKUP_FILENAME_RE.fullmatch(name)
    if not match:
        raise DiscoveryBackupError("Discovery backup name is invalid.")
    stamp = match.group(1)
    try:
        created = datetime.strptime(stamp, "%Y%m%dT%H%M%S%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise DiscoveryBackupError("Discovery backup name is invalid.") from exc
    return name, created


def _owned_entries(directory: Path) -> list[tuple[datetime, str, Path, int]]:
    root = _ensure_backup_dir(directory)
    result: list[tuple[datetime, str, Path, int]] = []
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        raise DiscoveryBackupError(
            f"Could not read the Discovery backup directory: {exc}"
        ) from exc
    for path in entries:
        try:
            name, created = _parse_owned_name(path.name)
        except DiscoveryBackupError:
            continue
        try:
            info = path.stat(follow_symlinks=False)
        except OSError:
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        result.append((created, name, path, int(info.st_size)))
    result.sort(key=lambda row: (row[0], row[1]))
    return result


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _new_owned_name(
    directory: Path,
    *,
    now: datetime | None = None,
    nonce: str | None = None,
) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    stamp = current.strftime("%Y%m%dT%H%M%S%fZ")

    if nonce is not None:
        candidate_nonce = str(nonce).strip().casefold()
        if not re.fullmatch(r"[0-9a-f]{8}", candidate_nonce):
            raise DiscoveryBackupError("Discovery backup nonce is invalid.")
        candidate = f"{BACKUP_PREFIX}{stamp}-{candidate_nonce}.json"
        if (directory / candidate).exists():
            raise DiscoveryBackupError("Discovery backup filename collision.")
        return candidate

    for _ in range(32):
        candidate = f"{BACKUP_PREFIX}{stamp}-{secrets.token_hex(4)}.json"
        if not (directory / candidate).exists():
            return candidate
    raise DiscoveryBackupError("Could not allocate a unique Discovery backup name.")


def prune_discovery_backups(
    retention_count: Any,
    *,
    directory: Path = DEFAULT_BACKUP_DIR,
) -> list[str]:
    """Prune oldest owned backups only, retaining the requested exact count."""
    count = _strict_retention_count(retention_count)
    entries = _owned_entries(directory)
    remove_count = max(0, len(entries) - count)
    removed: list[str] = []
    for _created, name, path, _size in entries[:remove_count]:
        try:
            mode = path.stat(follow_symlinks=False).st_mode
            if not stat.S_ISREG(mode):
                raise DiscoveryBackupError(
                    f"Refusing to prune non-regular Discovery backup: {name}"
                )
            path.unlink()
        except OSError as exc:
            raise DiscoveryBackupError(
                f"Could not prune Discovery backup {name}: {exc}"
            ) from exc
        removed.append(name)
    if removed:
        _fsync_directory(Path(directory))
    return removed


def enforce_retention(
    options: dict[str, Any],
    *,
    directory: Path = DEFAULT_BACKUP_DIR,
) -> list[str]:
    """Apply automatic retention only when the validated option is enabled."""
    enabled, count = retention_settings(options)
    _ensure_backup_dir(directory)
    if not enabled:
        return []
    return prune_discovery_backups(count, directory=directory)


def create_pre_mutation_backup(
    options: dict[str, Any],
    *,
    reason: str,
    directory: Path = DEFAULT_BACKUP_DIR,
    now: datetime | None = None,
    nonce: str | None = None,
) -> dict[str, Any] | None:
    """Atomically snapshot authoritative options before a Hub-owned mutation."""
    enabled, retention_count = retention_settings(options)
    root = _ensure_backup_dir(directory)
    if not enabled:
        return None
    if reason not in _ALLOWED_REASONS:
        raise DiscoveryBackupError("Discovery backup reason is invalid.")

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    name = _new_owned_name(root, now=current, nonce=nonce)
    destination = root / name
    temporary = root / f".{name}.{os.getpid()}.tmp"
    payload = {
        "format": BACKUP_FORMAT,
        "created_at": (
            current.isoformat(timespec="microseconds").replace("+00:00", "Z")
        ),
        "reason": reason,
        "options": options,
    }
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")

    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = None
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
        _fsync_directory(root)
    except (OSError, TypeError, ValueError) as exc:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise DiscoveryBackupError(
            f"Could not create the pre-mutation Discovery backup: {exc}"
        ) from exc

    prune_discovery_backups(retention_count, directory=root)
    return _metadata_for_path(destination)


def _metadata_for_path(path: Path) -> dict[str, Any]:
    name, created = _parse_owned_name(path.name)
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise DiscoveryBackupError(
            f"Could not read Discovery backup metadata: {exc}"
        ) from exc
    if not stat.S_ISREG(info.st_mode):
        raise DiscoveryBackupError("Discovery backup is not a regular file.")
    return {
        "name": name,
        "time": created.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "size": int(info.st_size),
    }


def discovery_backup_status(
    options: dict[str, Any],
    *,
    directory: Path = DEFAULT_BACKUP_DIR,
) -> dict[str, Any]:
    """Return safe metadata only; never read or expose saved configuration."""
    enabled, retention_count = retention_settings(options)
    entries = _owned_entries(directory)
    backups = [
        {
            "name": name,
            "time": created.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "size": size,
        }
        for created, name, _path, size in reversed(entries)
    ]
    return {
        "automatic_retention": enabled,
        "retained_limit": retention_count,
        "count": len(backups),
        "backups": backups,
    }


def remove_discovery_backup(
    name: Any,
    *,
    directory: Path = DEFAULT_BACKUP_DIR,
) -> str:
    """Remove exactly one strict owned backup name; unrelated files are untouched."""
    clean_name, _created = _parse_owned_name(name)
    root = _ensure_backup_dir(directory)
    path = root / clean_name
    try:
        info = path.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        raise DiscoveryBackupError("Discovery backup was not found.") from exc
    except OSError as exc:
        raise DiscoveryBackupError(f"Could not inspect Discovery backup: {exc}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise DiscoveryBackupError("Discovery backup is not a regular file.")
    try:
        path.unlink()
        _fsync_directory(root)
    except OSError as exc:
        raise DiscoveryBackupError(f"Could not remove Discovery backup: {exc}") from exc
    return clean_name
