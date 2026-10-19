#!/usr/bin/env python3
"""Hub app links should reuse the installed list once per refresh."""
import support_web as web

web._unifi2mqtt_snapshot_status = lambda: {}
web._unifi2mqtt_diagnostics_status = lambda: {}
web._load_configuration_restore_pending = lambda: {}
calls = []
rows = [
    {"slug": "repo_switch_vision_discovery"},
    {"slug": "repo_switch_vision_snmp2mqtt"},
    {"slug": "repo_switch_vision_installer"},
    {"slug": "repo_switch_vision_unifi2mqtt", "state": "started"},
]
def supervisor(path, **_kwargs):
    calls.append(path)
    if path == "/addons":
        return {"data": {"addons": rows}}
    if path == "/store/addons":
        return {"data": {"addons": []}}
    if path.endswith("/info"):
        return {"data": {"state": "started", "options": {}}}
    raise AssertionError(path)

web._supervisor_json = supervisor
links = web._installed_switch_vision_app_links()
assert all(links[x]["found"] for x in ("discovery", "snmp2mqtt", "installer", "unifi2mqtt"))
assert calls.count("/addons") == 1, calls
assert calls.count("/store/addons") == 1, calls

# A separate refresh remains independent and queries the list afresh.
web._unifi2mqtt_settings_status()
assert calls.count("/addons") == 2
web._installed_switch_vision_app_links()
assert calls.count("/addons") == 3

# A store-only UniFi app remains available but is not installed.
calls.clear()
rows.pop()
store = [{"slug": "repo_switch_vision_unifi2mqtt", "name": "Switch Vision UniFi2MQTT",
          "installed": False}]
def uninstalled(path, **_kwargs):
    calls.append(path)
    if path == "/addons":
        return {"data": {"addons": rows}}
    if path == "/store/addons":
        return {"data": {"addons": store}}
    raise AssertionError(path)
web._supervisor_json = uninstalled
result = web._installed_switch_vision_app_links()
assert not result["unifi2mqtt"]["found"]
assert result["unifi2mqtt"]["available"]
assert calls.count("/addons") == 1

# A failed first list read must not be cached as an empty installed set:
# UniFi status retains its independent recovery attempt.
calls.clear()
rows.append({"slug": "repo_switch_vision_unifi2mqtt", "name": "Switch Vision UniFi2MQTT"})
def intermittent(path, **_kwargs):
    calls.append(path)
    if path == "/addons":
        if calls.count("/addons") == 1:
            raise RuntimeError("installed app query failed")
        return {"data": {"addons": rows}}
    if path == "/store/addons":
        return {"data": {"addons": []}}
    if path.endswith("/info"):
        return {"data": {"state": "started", "options": {}}}
    raise AssertionError(path)
web._supervisor_json = intermittent
result = web._installed_switch_vision_app_links()
assert result["error"] == "installed app query failed"
assert result["unifi2mqtt"]["found"] is True
assert calls.count("/addons") == 2

print("Hub app links shared installed-list refresh: PASS")
