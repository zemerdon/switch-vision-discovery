#!/usr/bin/env python3
"""UniFi settings saves must not re-fetch presentation state before mutation."""
import copy
import support_web as web

calls = []
status_calls = []
pending_calls = []
current_state = {"state": "started", "options": {"local_api_key": "fixture-secret", "mqtt_topic_prefix": "sv/test"}}
selected = {"slug": "repo_switch_vision_unifi2mqtt", "_source": "addons", "installed": True}

def addon_lookup(*, include_store=True, **kwargs):
    calls.append(("lookup", include_store))
    return selected

def supervisor(path, *, method="GET", timeout=None, payload=None):
    calls.append((method, path))
    if path.endswith("/info"):
        return {"data": copy.deepcopy(current_state)}
    if path.endswith("/options"):
        assert payload is not None
        assert payload["options"]["local_api_key"] == "fixture-secret"
        assert payload["options"]["mqtt_topic_prefix"] == "sv/updated"
        return {"data": {}}
    if path.endswith("/restart") or path.endswith("/start"):
        return {"data": {}}
    raise AssertionError(path)

def validate(data, current):
    calls.append(("validate", None))
    assert current["local_api_key"] == "fixture-secret"
    assert data == {"mqtt_topic_prefix": "sv/updated"}
    merged = dict(current)
    merged.update(data)
    return merged

def final_status():
    status_calls.append("status")
    return {"installed": True, "slug": selected["slug"], "state": current_state["state"],
            "options": {"mqtt_topic_prefix": "sv/updated", "local_api_key_configured": True}}

web._find_unifi2mqtt_addon = addon_lookup
web._supervisor_json = supervisor
web._validate_unifi2mqtt_options = validate
web._unifi2mqtt_settings_status = final_status
web._clear_configuration_restore_pending = lambda section: pending_calls.append(section)
# The old path read these before the first write; post-save status already owns them.
web._unifi2mqtt_snapshot_status = lambda: (_ for _ in ()).throw(AssertionError("unnecessary snapshot"))
web._unifi2mqtt_diagnostics_status = lambda: (_ for _ in ()).throw(AssertionError("unnecessary diagnostics"))
web._load_configuration_restore_pending = lambda: (_ for _ in ()).throw(AssertionError("unnecessary pending read"))

for mode, action in [("started", "restart"), ("running", "restart"), ("stopped", "start"),
                     ("unknown", None)]:
    calls.clear()
    status_calls.clear()
    pending_calls.clear()
    current_state["state"] = mode
    result = web._save_unifi2mqtt_settings({"mqtt_topic_prefix": "sv/updated"})
    assert calls.count(("lookup", True)) == 1, calls
    assert calls.count(("GET", "/addons/repo_switch_vision_unifi2mqtt/info")) == 1, calls
    assert calls.count(("POST", "/addons/repo_switch_vision_unifi2mqtt/options")) == 1, calls
    assert calls.count(("validate", None)) == 1
    lifecycle = [item for item in calls if isinstance(item[1], str) and item[1].endswith(("/restart", "/start"))]
    assert lifecycle == ([("POST", f"/addons/repo_switch_vision_unifi2mqtt/{action}")] if action else [])
    assert status_calls == ["status"]  # Fresh presentation response only AFTER successful save.
    assert pending_calls == ["unifi_controllers"]
    assert result["saved"] and result["restarted"] == (action == "restart")
    assert result["started"] == (action == "start")
    assert "fixture-secret" not in str(result)

# Store-only, missing slug and absent apps must fail before requesting options.
for found in [None, {"slug": "", "_source": "addons"},
              {"slug": "repo_switch_vision_unifi2mqtt", "_source": "store", "installed": False}]:
    selected = found
    calls.clear()
    status_calls.clear()
    pending_calls.clear()
    try:
        web._save_unifi2mqtt_settings({"mqtt_topic_prefix": "sv/updated"})
    except RuntimeError as exc:
        assert "not installed" in str(exc).lower()
    else:
        raise AssertionError("Unavailable add-on did not fail closed")
    assert calls == [("lookup", True)], calls
    assert not status_calls and not pending_calls

selected = {"slug": "repo_switch_vision_unifi2mqtt", "_source": "addons"}
# Missing complete options must not overwrite stored secrets with defaults.
current_state["options"] = None
calls.clear()
status_calls.clear()
pending_calls.clear()
try:
    web._save_unifi2mqtt_settings({"mqtt_topic_prefix": "sv/updated"})
except RuntimeError as exc:
    assert "protect stored secrets" in str(exc)
else:
    raise AssertionError("Unreadable options should not permit a save")
assert ("POST", "/addons/repo_switch_vision_unifi2mqtt/options") not in calls
assert not status_calls and not pending_calls

print("Hub UniFi settings one-read save, lifecycle, privacy and fail-closed regression: PASS")
