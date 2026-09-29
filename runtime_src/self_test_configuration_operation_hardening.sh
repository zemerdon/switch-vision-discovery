# Switch Vision Discovery self-test configuration/operation hardening module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# v2.1.14 configuration/operation hardening regressions.
PYTHONPATH="$BASE_DIR" python3 - "$tmp_dir" <<'PYTEST'
import json
import sys
from pathlib import Path
import support_web as web

tmp = Path(sys.argv[1])

def switch(name, host, prefix, enabled="enabled"):
    return {
        "switch_name": name,
        "switch_host": host,
        "sensor_prefix": prefix,
        "snmp_community": "private-test-community",
        "enabled": enabled,
        "walk_mode": "targeted",
        "switch_model": "auto",
    }

def exported(rows, stack=None):
    return {
        "format": web.DISCOVERY_EXPORT_FORMAT,
        "configuration": {
            "switches": rows,
            "stack_member_prefixes": stack or [],
        },
    }

# Disabled rows still reserve identities and cannot collide on switch_name.
try:
    web._validate_discovery_import(exported([
        switch("SW1", "192.0.2.1", "sw1"),
        switch("sw1", "192.0.2.2", "sw2", "disabled"),
    ]))
except ValueError:
    pass
else:
    raise SystemExit("duplicate switch_name was accepted")

# HA-equivalent hyphen/underscore prefixes collide even across disabled rows.
try:
    web._validate_discovery_import(exported([
        switch("A", "192.0.2.1", "rack_1"),
        switch("B", "192.0.2.2", "rack-1", "disabled"),
    ]))
except ValueError:
    pass
else:
    raise SystemExit("duplicate sensor_prefix identity was accepted")

# Stack-member prefixes share the same global entity namespace.
try:
    web._validate_discovery_import(exported(
        [switch("STACK", "192.0.2.3", "stack_1")],
        [{"switch_name": "STACK", "member": "2", "sensor_prefix": "stack-1"}],
    ))
except ValueError:
    pass
else:
    raise SystemExit("duplicate stack-member sensor_prefix was accepted")

# Member 1 may intentionally reuse its own management-target/base prefix.
web._validate_discovery_import(exported(
    [switch("STACK", "192.0.2.3", "sw1")],
    [{"switch_name": "STACK", "member": "1", "sensor_prefix": "SW1"}],
))

# The operation coordinator must fail closed on overlapping operations.
web._claim_operation("Discovery")
try:
    try:
        web._claim_operation("Support My Switch")
    except web.OperationConflict:
        pass
    else:
        raise SystemExit("overlapping operation was accepted")
finally:
    web._release_operation("Discovery")
web._claim_operation("Support My Switch")
web._release_operation("Support My Switch")

# Import writes the full merged authoritative option set through Supervisor,
# preserves unrelated secrets, and confirms the saved result.
store = {
    "switches": [switch("SW1", "192.0.2.1", "sw1")],
    "stack_member_prefixes": [],
    "run_snmp_walks": "true",
    "unrelated_secret": "keep-me",
}
posts = []
backup_calls = []
retention_calls = []
backup_dir = tmp / "import-backups"

def get_options():
    return dict(store)

def supervisor(path, *, method="GET", timeout=12.0, payload=None):
    if path == "/addons/self/options" and method == "POST":
        assert backup_calls == ["configuration_import"], (
            "pre-mutation backup must run before the Supervisor options POST",
            backup_calls,
        )
        store.clear()
        store.update(payload["options"])
        posts.append(dict(store))
        return {"result": "ok"}
    raise AssertionError((path, method))

real_create_backup = web.create_pre_mutation_backup
real_enforce_retention = web.enforce_retention

def create_test_backup(options, *, reason):
    backup_calls.append(reason)
    return real_create_backup(options, reason=reason, directory=backup_dir)

def enforce_test_retention(options):
    retention_calls.append(True)
    return real_enforce_retention(options, directory=backup_dir)

web.create_pre_mutation_backup = create_test_backup
web.enforce_retention = enforce_test_retention
web._self_addon_options = get_options
web._supervisor_json = supervisor
web._import_discovery_options({
    "switches": [switch("SW1", "192.0.2.1", "sw1")],
    "stack_member_prefixes": [],
    "run_snmp_walks": "false",
})
assert posts and store["unrelated_secret"] == "keep-me" and store["run_snmp_walks"] == "false"
assert retention_calls == [True], retention_calls
assert len(list(backup_dir.glob("switch-vision-discovery-backup-*.json"))) == 1

# Export must read Supervisor, not a stale /data-style local copy.
stale = tmp / "options.json"
stale.write_text(json.dumps({"run_snmp_walks": "stale"}), encoding="utf-8")
payload = web._discovery_export(stale, "2.1.14")
assert payload["configuration"]["run_snmp_walks"] == "false"

# A run snapshot validates identities before any configuration is written.
web._self_addon_options = lambda: {
    "switches": [
        switch("A", "192.0.2.1", "dup"),
        switch("B", "192.0.2.2", "DUP", "disabled"),
    ],
    "stack_member_prefixes": [],
}
snapshot = tmp / "authoritative-options.json"
try:
    web._write_authoritative_discovery_options_snapshot(snapshot)
except ValueError:
    pass
else:
    raise SystemExit("duplicate identities reached Discovery snapshot")
assert not snapshot.exists()

print("Switch Vision Discovery v2.1.14 configuration hardening: PASS")
PYTEST

# Startup option migration must preserve unrelated options/secrets and write
# only through the authoritative Supervisor API.
PYTHONPATH="$BASE_DIR" python3 - <<'PY_MIGRATION'
import copy
import tempfile
from pathlib import Path
import migrate_options as migration

legacy_dir = tempfile.TemporaryDirectory()
migration.LEGACY_IMPORT_BACKUP = Path(legacy_dir.name) / "options.before-import.json"
migration.LEGACY_IMPORT_BACKUP.write_text('{"snmp_community":"legacy-secret"}\n', encoding="utf-8")

store = {
    "show_card_header": True,
    "switches": [{
        "switch_name": "SW1",
        "switch_host": "192.0.2.1",
        "sensor_prefix": "sw1",
        "snmp_community": "keep-secret",
    }],
    "unrelated_secret": "also-keep-secret",
}
posts = []

def options():
    return copy.deepcopy(store)

def request(path, *, method="GET", payload=None):
    assert path == "/addons/self/options" and method == "POST", (path, method)
    assert isinstance(payload, dict) and isinstance(payload.get("options"), dict)
    store.clear()
    store.update(copy.deepcopy(payload["options"]))
    posts.append(copy.deepcopy(store))
    return {"result": "ok"}

migration._options = options
migration._request = request
assert migration.main() == 0
assert posts, "migration did not use Supervisor options POST"
assert not migration.LEGACY_IMPORT_BACKUP.exists(), "legacy secret-bearing backup was not removed"
assert "show_card_header" not in store
assert store["autodiscover_networks"] == [], store
assert store["switches"][0]["enabled"] == "enabled"
assert store["switches"][0]["snmp_community"] == "keep-secret"
assert store["unrelated_secret"] == "also-keep-secret"

posts.clear()
assert migration.main() == 0
assert not posts, "no-op migration unexpectedly rewrote Supervisor options"
print("Switch Vision Discovery v3.0.2 Supervisor upgrade migration: PASS")
PY_MIGRATION
