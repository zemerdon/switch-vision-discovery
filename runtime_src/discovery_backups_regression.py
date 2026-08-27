#!/usr/bin/env python3
"""Permanent Discovery 2.3.0 backup-retention regression."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import tempfile

from discovery_backups import (
    DiscoveryBackupError,
    create_pre_mutation_backup,
    discovery_backup_status,
    enforce_retention,
    remove_discovery_backup,
    retention_settings,
)


def must_fail(callable_obj, *args, **kwargs) -> None:
    try:
        callable_obj(*args, **kwargs)
    except DiscoveryBackupError:
        return
    raise AssertionError(f"{callable_obj.__name__} unexpectedly accepted invalid input")


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    backup_dir = root / "share" / "switch_vision" / "backups" / "discovery"
    contributions = root / "share" / "switch_vision" / "contributions"
    contributions.mkdir(parents=True)
    private_submission = contributions / "Support_My_Switch_PRIVATE.zip"
    private_submission.write_bytes(b"private contribution bytes")
    outside = root / "share" / "switch_vision" / "outside-backup-scope.txt"
    outside.write_text("outside stays", encoding="utf-8")

    # Defaults are automatic retention on with five retained snapshots.
    assert retention_settings({}) == (True, 5)
    assert retention_settings(
        {"backup_retention_enabled": "true", "backup_retention_count": 1}
    ) == (True, 1)
    assert retention_settings(
        {"backup_retention_enabled": "true", "backup_retention_count": 10}
    ) == (True, 10)
    assert retention_settings(
        {"backup_retention_enabled": "false", "backup_retention_count": 10}
    ) == (False, 10)
    for invalid in (0, 11, -1, True, "0", "11", "five", 5.5, [], {}):
        must_fail(
            retention_settings,
            {"backup_retention_enabled": "true", "backup_retention_count": invalid},
        )

    secret = "SUPER-SECRET-SNMP-COMMUNITY"
    options = {
        "backup_retention_enabled": "true",
        "backup_retention_count": 3,
        "switches": [
            {
                "switch_name": "SW1",
                "switch_host": "192.0.2.10",
                "snmp_community": secret,
                "enabled": "enabled",
            }
        ],
    }
    start = datetime(2026, 8, 24, 5, 0, 0, tzinfo=timezone.utc)
    made = []
    for index in range(5):
        item = create_pre_mutation_backup(
            options,
            reason="device_state_update",
            directory=backup_dir,
            now=start + timedelta(seconds=index),
            nonce=f"{index + 1:08x}",
        )
        assert item is not None
        made.append(item["name"])

    # Oldest-first retention keeps only the newest three strict owned files.
    status = discovery_backup_status(options, directory=backup_dir)
    assert status["automatic_retention"] is True
    assert status["retained_limit"] == 3
    assert status["count"] == 3
    assert [row["name"] for row in reversed(status["backups"])] == made[-3:]
    assert secret not in repr(status)
    assert "options" not in repr(status)
    assert "configuration" not in repr(status)

    # The saved private payload really is complete, but it is file-only metadata
    # from the API/status contract.
    newest = backup_dir / made[-1]
    document = json.loads(newest.read_text(encoding="utf-8"))
    assert document["format"] == "switch-vision-discovery-backup-v1"
    assert document["options"]["switches"][0]["snmp_community"] == secret
    assert stat.S_IMODE(backup_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(newest.stat().st_mode) == 0o600
    assert not list(backup_dir.glob(".*.tmp"))

    # Unrelated files in the owned directory and Support My Switch contributions
    # are never listed, pruned, or removed.
    unrelated = backup_dir / "notes.txt"
    unrelated.write_text("keep me", encoding="utf-8")
    hand_edited = backup_dir / "switch-vision-discovery-backup-evil.json"
    hand_edited.write_text("keep me too", encoding="utf-8")
    enforce_retention(
        {"backup_retention_enabled": "true", "backup_retention_count": 1},
        directory=backup_dir,
    )
    assert unrelated.read_text(encoding="utf-8") == "keep me"
    assert hand_edited.read_text(encoding="utf-8") == "keep me too"
    assert private_submission.read_bytes() == b"private contribution bytes"
    assert outside.read_text(encoding="utf-8") == "outside stays"
    assert discovery_backup_status(
        {"backup_retention_enabled": "true", "backup_retention_count": 1},
        directory=backup_dir,
    )["count"] == 1

    # Automatic retention disabled means no automatic snapshot and no pruning.
    before = sorted(p.name for p in backup_dir.iterdir())
    disabled = {
        "backup_retention_enabled": "false",
        "backup_retention_count": 5,
        "switches": options["switches"],
    }
    assert create_pre_mutation_backup(
        disabled,
        reason="configuration_import",
        directory=backup_dir,
        now=start + timedelta(minutes=1),
        nonce="deadbeef",
    ) is None
    assert sorted(p.name for p in backup_dir.iterdir()) == before
    assert enforce_retention(disabled, directory=backup_dir) == []

    # Manual removal remains available when automatic retention is disabled.
    owned_name = discovery_backup_status(disabled, directory=backup_dir)["backups"][0]["name"]
    assert remove_discovery_backup(owned_name, directory=backup_dir) == owned_name
    assert not (backup_dir / owned_name).exists()
    assert unrelated.exists()
    assert hand_edited.exists()
    assert private_submission.exists()
    assert outside.read_text(encoding="utf-8") == "outside stays"

    # Normal Hub settings saves create the same protected pre-mutation snapshot.
    # This exact reason is used by the Hub settings save handler and must stay
    # synchronized with the backup validator.
    hub_save = create_pre_mutation_backup(
        options,
        reason="hub_settings_update",
        directory=backup_dir,
        now=start + timedelta(minutes=2),
        nonce="cafebabe",
    )
    assert hub_save is not None
    hub_document = json.loads((backup_dir / hub_save["name"]).read_text(encoding="utf-8"))
    assert hub_document["reason"] == "hub_settings_update"

    # Malicious/hand-edited names and traversal attempts fail closed.
    for invalid_name in (
        "../notes.txt",
        "notes.txt",
        "switch-vision-discovery-backup-evil.json",
        "switch-vision-discovery-backup-20260824T050000000000Z-DEADBEEF.json",
        "switch-vision-discovery-backup-20260824T050000000000Z-deadbeef.json/../notes.txt",
        "",
        None,
    ):
        must_fail(remove_discovery_backup, invalid_name, directory=backup_dir)
    assert unrelated.exists()
    assert hand_edited.exists()
    assert private_submission.exists()

    # Invalid retention options fail before a Hub-owned mutation can proceed.
    must_fail(
        create_pre_mutation_backup,
        {"backup_retention_enabled": "true", "backup_retention_count": 99},
        reason="configuration_import",
        directory=backup_dir,
    )
    must_fail(
        create_pre_mutation_backup,
        {"backup_retention_enabled": "true", "backup_retention_count": 5},
        reason="hand_edited_reason",
        directory=backup_dir,
    )

print("Switch Vision Discovery v2.3.0 backup retention regression: PASS")
