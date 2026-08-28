#!/usr/bin/env sh
set -eu

# v2.1.15 Copy Debug Info regression checks
SV_COPY_DEBUG_TEST_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

grep -Fq 'id="copyDebugButton"' \
    "$SV_COPY_DEBUG_TEST_DIR/support_web.py"

grep -Fq 'id="copyDebugStatus"' \
    "$SV_COPY_DEBUG_TEST_DIR/support_web.py"

grep -Fq 'function sanitizeDebugText(text)' \
    "$SV_COPY_DEBUG_TEST_DIR/support_web.py"

grep -Fq 'async function copyDebugInfo()' \
    "$SV_COPY_DEBUG_TEST_DIR/support_web.py"

grep -Fq "\$('copyDebugButton').addEventListener('click',copyDebugInfo)" \
    "$SV_COPY_DEBUG_TEST_DIR/support_web.py"

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# v2.3.20 Credits animation / test-content presentation regression.
grep -Fq 'id="creditsMatrix"' "$BASE_DIR/support_web.py"
grep -Fq 'function startCreditsAnimation()' "$BASE_DIR/support_web.py"
grep -Fq 'credits-matrix-active' "$BASE_DIR/support_web.py"
grep -Fq 'credits-settled' "$BASE_DIR/support_web.py"
grep -Fq '@media(prefers-reduced-motion:reduce)' "$BASE_DIR/support_web.py"
grep -Fq 'TEST ENTRIES — NOT REAL CONTRIBUTORS' "$BASE_DIR/support_web.py"
grep -Fq 'DemoAlias-01' "$BASE_DIR/support_web.py"
grep -Fq "openCreditsButton').addEventListener('click',()=>{setView('credits');startCreditsAnimation()})" "$BASE_DIR/support_web.py"
echo 'Switch Vision Discovery v2.3.20 Credits animation regression: PASS'

# v2.3.21 Credits card home-navigation order regression.
python3 - "$BASE_DIR/support_web.py" <<'PY_CREDITS_ORDER'
from pathlib import Path
import sys
text = Path(sys.argv[1]).read_text(encoding="utf-8")
settings = text.index('id="openIntegrationSettingsButton"')
unifi = text.index('id="openUnifi2mqttSettingsButton"')
credits = text.index('id="openCreditsButton"')
assert settings < unifi < credits, "Credits must be the final Hub navigation card"
PY_CREDITS_ORDER
echo 'Switch Vision Discovery v2.3.21 Credits home-navigation order: PASS'

# v2.3.11 HP J8693A / 3500yl numeric-interface regression.
# Exact hardware contract: 44 fixed copper logical ports plus four
# dual-personality copper/mini-GBIC logical ports (45-48).  No private
# contribution values are embedded in this regression.
HP_TEST_WALK=$(mktemp)
HP_TEST_CAP=$(mktemp)
trap 'rm -f "$HP_TEST_WALK" "$HP_TEST_CAP"' EXIT HUP INT TERM
{
  echo '.1.3.6.1.2.1.1.1.0 = STRING: HP J8693A Switch 3500yl-48G'
  i=1
  while [ "$i" -le 48 ]; do
    echo ".1.3.6.1.2.1.31.1.1.1.1.$i = STRING: \"$i\""
    i=$((i + 1))
  done
} > "$HP_TEST_WALK"
CV_MIB_DATABASE_DIR="$BASE_DIR/opt/switch-vision/mib_database"
CV_VENDOR_DIR="$BASE_DIR/opt/switch-vision/vendors"
. "$CV_VENDOR_DIR/base.sh"
. "$CV_VENDOR_DIR/generic.sh"
. "$CV_VENDOR_DIR/cisco.sh"
. "$CV_VENDOR_DIR/known_vendor.sh"
. "$CV_VENDOR_DIR/interface.sh"
. "$CV_VENDOR_DIR/loader.sh"
CV_ID_VENDOR="hp_aruba"
CV_ID_VENDOR_NAME="HP / Aruba"
CV_ID_FAMILY="3500yl"
CV_ID_SUPPORT_STATUS="detected"
CV_ID_SYS_OBJECT_ID="1.3.6.1.4.1.11.2.3.7.11.59"
CV_ID_SYS_DESCR="HP J8693A Switch 3500yl-48G"
cv_write_capabilities_json "$HP_TEST_WALK" "$HP_TEST_CAP" ""
jq -e '
  (.device.model_text | contains("J8693A"))
  and ([.interfaces[] | select(.physical == true)] | length == 48)
  and ([.interfaces[] | select(.media == "rj45")] | length == 44)
  and ([.interfaces[] | select(.media == "uplink")] | length == 4)
  and (any(.interfaces[]; .name == "44" and .media == "rj45" and .physical == true))
  and (any(.interfaces[]; .name == "45" and .media == "uplink" and .physical == true))
  and (any(.interfaces[]; .name == "48" and .media == "uplink" and .physical == true))
' "$HP_TEST_CAP" >/dev/null
grep -Fq 'hp_3500yl_model = "HP J8693A Switch 3500yl-48G"' "$BASE_DIR/discovery_job.sh"
grep -Fq 'hp_3500yl_model="HP J8693A Switch 3500yl-48G"' "$BASE_DIR/discovery_job.sh"
grep -Fq 'model == "HP J8693A Switch 3500yl-48G" && name ~ /^([1-9]|[1-3][0-9]|4[0-8])$/' "$BASE_DIR/discovery_job.sh"
echo 'Switch Vision Discovery v2.3.11 HP 3500yl numeric interface contract: PASS'

# v2.3.16 Hub header / calibration-profile single-line summary regression
grep -Fq 'class="sv-profile-meta-actions"' "$BASE_DIR/calibration_profiles.js"
grep -Fq 'class="sv-profile-top-meta"' "$BASE_DIR/calibration_profiles.js"
! grep -Fq 'class="sv-profile-internal"' "$BASE_DIR/calibration_profiles.js"
grep -Fq 'class="sv-profiles-stats"' "$BASE_DIR/calibration_profiles.js"
grep -Fq 'grid-area:actions' "$BASE_DIR/calibration_profiles.js"
grep -Fq 'data-profile-export=' "$BASE_DIR/calibration_profiles.js"
grep -Fq 'data-profile-import=' "$BASE_DIR/calibration_profiles.js"
grep -Fq 'data-profile-copy=' "$BASE_DIR/calibration_profiles.js"
grep -Fq 'data-profile-delete=' "$BASE_DIR/calibration_profiles.js"
! grep -Fq 'Active — Protected' "$BASE_DIR/calibration_profiles.js"
! grep -Fq 'Factory — Protected' "$BASE_DIR/calibration_profiles.js"
grep -Fq 'text-overflow:ellipsis' "$BASE_DIR/calibration_profiles.js"
grep -Fq 'white-space:nowrap' "$BASE_DIR/calibration_profiles.js"
! grep -Fq '<b>Base profile:</b>' "$BASE_DIR/calibration_profiles.js"
! grep -Fq '<b>Faceplate exists:</b>' "$BASE_DIR/calibration_profiles.js"
! grep -Fq '<b>SHA-256:</b>' "$BASE_DIR/calibration_profiles.js"
grep -Fq 'duplicate_faceplate_content' "$BASE_DIR/calibration_profiles.js"
grep -Fq '.hub-toggle-grid{display:grid;grid-template-columns:repeat(2,minmax(240px,300px));column-gap:10px;justify-content:start;align-items:start}' "$BASE_DIR/support_web.py"
grep -Fq '.hub-settings-actions{position:sticky;bottom:6px;display:flex;gap:8px' "$BASE_DIR/support_web.py"
grep -Fq 'border:1px solid var(--line-soft);padding:8px 10px;margin:10px 0 0' "$BASE_DIR/support_web.py"
grep -Fq '.hub-settings-status{margin:0 0 0 auto;line-height:1.2}' "$BASE_DIR/support_web.py"
grep -Fq "className='device-meta-line'" "$BASE_DIR/support_web.py"
grep -Fq "['Registry',d.registry_match?'Yes':'No']" "$BASE_DIR/support_web.py"
grep -Fq "['Validated',d.registry_last_validated_version" "$BASE_DIR/support_web.py"
grep -Fq 'row.className = "device-card installer-backup-row"' "$BASE_DIR/maintenance.js"
grep -Fq 'line.className = "installer-backup-line"' "$BASE_DIR/maintenance.js"
! grep -Fq 'backup.contents.join' "$BASE_DIR/maintenance.js"
grep -Fq 'restore_backup' "$BASE_DIR/maintenance.js"
grep -Fq 'validate_backup' "$BASE_DIR/maintenance.js"
grep -Fq '.validation-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:4px;margin-top:7px}' "$BASE_DIR/support_web.py"
grep -Fq '.validation-item{display:flex;justify-content:space-between;align-items:center;gap:6px;border-top:1px solid var(--line);padding:4px 5px 2px}' "$BASE_DIR/support_web.py"
! grep -Fq 'id="hubComponent-core" class="hub-component" open' "$BASE_DIR/support_web.py"
! grep -Fq 'class="yaml-manager generated-card-manager" open' "$BASE_DIR/support_web.py"
! grep -Fq 'class="yaml-manager" open' "$BASE_DIR/support_web.py"

# v2.3.17 grouped Calibration Profiles manager regression
grep -Fq 'svProfileManagerActions' "$BASE_DIR/calibration_profiles_manager.js"
grep -Fq 'svProfileManagerExport' "$BASE_DIR/calibration_profiles_manager.js"
grep -Fq 'svProfileManagerImport' "$BASE_DIR/calibration_profiles_manager.js"
grep -Fq 'svProfileManagerCopyTarget' "$BASE_DIR/calibration_profiles_manager.js"
grep -Fq 'svProfileManagerDelete' "$BASE_DIR/calibration_profiles_manager.js"
grep -Fq 'ACTIVE PROFILES' "$BASE_DIR/calibration_profiles_manager.js"
grep -Fq 'UNUSED PROFILES' "$BASE_DIR/calibration_profiles_manager.js"
grep -Fq 'manager-selected' "$BASE_DIR/calibration_profiles_manager.js"
grep -Fq 'max-width:clamp(90px,30vw,420px)!important' "$BASE_DIR/calibration_profiles_manager.js"
grep -Fq 'max-width:clamp(88px,30vw,210px)!important' "$BASE_DIR/calibration_profiles_manager.js"
grep -Fq 'summary.title = text;' "$BASE_DIR/calibration_profiles_manager.js"
grep -Fq 'showTooltip(text);' "$BASE_DIR/calibration_profiles_manager.js"
grep -Fq 'new MutationObserver' "$BASE_DIR/calibration_profiles_manager.js"
grep -Fq 'opacity:.42;' "$BASE_DIR/calibration_profiles_manager.js"
grep -Fq 'filter:saturate(.15);' "$BASE_DIR/calibration_profiles_manager.js"
grep -Fq 'calibration_profiles_manager.js' "$BASE_DIR/support_web.py"

# v2.3.4 Hub-owned settings UX / authoritative-store / privacy regressions
grep -Fq 'id="settingsCard"' "$BASE_DIR/support_web.py"
grep -Fq 'id="hubSettingsSave"' "$BASE_DIR/support_web.py"
grep -Fq '/api/settings/core' "$BASE_DIR/support_web.py"
grep -Fq '/api/settings/snmp2mqtt' "$BASE_DIR/support_web.py"
grep -Fq '/api/settings/discovery' "$BASE_DIR/support_web.py"
grep -Fq "SwitchVisionHubSettings?.open('core')" "$BASE_DIR/support_web.py"
grep -Fq 'id="hubComponent-snmp2mqtt"' "$BASE_DIR/support_web.py"
grep -Fq 'id="hubComponent-discovery"' "$BASE_DIR/support_web.py"
# v2.3.7 explicit font range + shared Hub component geometry regression
PYTHONPATH="$BASE_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 "$BASE_DIR/hub_density_regression.py"
# v2.3.6 themed visual hierarchy / elegance regression
grep -Fq -- '--heading:#69c8ff;--heading-strong:#a6e3ff;--heading-line:#2787c7' "$BASE_DIR/support_web.py"
grep -Fq -- '--heading:#4fc3e8;--heading-strong:#86dcf3;--heading-line:#049fd9' "$BASE_DIR/support_web.py"
grep -Fq -- '--heading:#79d7f5;--heading-strong:#ace9fb;--heading-line:#42b4e6' "$BASE_DIR/support_web.py"
grep -Fq -- '--heading:#005ed8;--heading-strong:#003f9e;--heading-line:#6aa7ff' "$BASE_DIR/support_web.py"
grep -Fq 'h2{font-size:var(--sv-font-section-title);line-height:1.25;color:var(--heading)}' "$BASE_DIR/support_web.py"
grep -Fq '.hub-settings-section h3::before{content:"";position:absolute;left:0;top:.12em;width:3px;height:1.05em' "$BASE_DIR/support_web.py"
grep -Fq '.hub-component>summary{cursor:pointer;font-size:1rem;font-weight:750;color:var(--heading)' "$BASE_DIR/support_web.py"
grep -Fq 'box-shadow:0 0 0 3px var(--accent-soft)' "$BASE_DIR/support_web.py"
grep -Fq '.nav-card::before{content:"";position:absolute;left:0;top:0;right:0;height:2px' "$BASE_DIR/support_web.py"
PYTHONPATH="$BASE_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY_HUB_SETTINGS'
import copy
import support_web

# Core uses only its admin WebSocket contract.
ws=[]
def fake_ws(command):
    ws.append(copy.deepcopy(command))
    return {"schema_version":1,"settings":{"sidebar":{"show_panel_in_sidebar":True}},"defaults":{}}
support_web._home_assistant_ws=fake_ws
assert support_web._core_settings_status()["settings"]
support_web._save_core_settings({"settings":{"sidebar":{"show_panel_in_sidebar":False}}})
assert ws[-1]["type"]=="switch_vision/set_settings"

# SNMP2MQTT secrets never return; blank preserves; required HA discovery is fail-closed.
snmp={"mqtt":{"host":"core-mosquitto","port":1883,"username":"u","password":"PRIVATE_MQTT_PASSWORD"},"targets_path":"/config/app_configs/switch_vision_snmp2mqtt/targets.yaml","use_switch_vision_generated_yaml":True,"switch_vision_generated_yaml_path":"/share/switch_vision/generated-snmp2mqtt.yaml","imported_targets_path":"/config/app_configs/switch_vision_snmp2mqtt/imported/generated-snmp2mqtt.yaml","backup_existing_config":False,"homeassistant":{"discovery":False,"prefix":"old"},"future":"keep"}
support_web._find_snmp2mqtt_addon=lambda:{"slug":"switch_vision_snmp2mqtt","state":"started"}
def sup(path,method="GET",timeout=12.0,payload=None):
    if path.endswith('/info'): return {"data":{"state":"started","options":copy.deepcopy(snmp)}}
    if path.endswith('/options'):
        snmp.clear();snmp.update(copy.deepcopy(payload["options"]));return {"result":"ok"}
    if path.endswith('/restart'): return {"result":"ok"}
    raise AssertionError(path)
support_web._supervisor_json=sup
st=support_web._snmp2mqtt_settings_status();assert st["password_configured"] and "PRIVATE_MQTT_PASSWORD" not in repr(st)
r=copy.deepcopy(st["settings"]);r["mqtt"]["host"]="mqtt.local"
saved=support_web._save_snmp2mqtt_settings({"settings":r})
assert snmp["mqtt"]["password"]=="PRIVATE_MQTT_PASSWORD" and snmp["future"]=="keep"
assert snmp["homeassistant"]=={"discovery":True,"prefix":"homeassistant"} and "PRIVATE_MQTT_PASSWORD" not in repr(saved)
bad=copy.deepcopy(r);bad["homeassistant"]={"discovery":False,"prefix":"wrong"}
try: support_web._save_snmp2mqtt_settings({"settings":bad})
except ValueError: pass
else: raise AssertionError('noncanonical SNMP2MQTT HA discovery accepted')

# Discovery SNMP community and contributor identity are write-only; blank preserves both.
disc={"input_path":"/share/switch_vision/snmpwalk.txt","snmpwalks_dir":"/share/switch_vision/snmpwalks","report_path":"/share/switch_vision/discovery-report.txt","run_snmp_walks":"true","enable_switch_list":"true","switches":[{"switch_name":"SW1","display_name":"Lab","switch_host":"192.0.2.10","sensor_prefix":"sw1","snmp_community":"PRIVATE_SNMP_COMMUNITY","enabled":"enabled","walk_mode":"targeted","switch_model":"auto","card_header_title":""}],"stack_member_prefixes":[],"parse_all_walks":"false","generate_snmp2mqtt":"true","clean_output_before_walk":"false","targets_csv":"/share/switch_vision/discovery-targets.csv","last_run_summary_path":"/share/switch_vision/last-discovery-run.txt","generated_yaml_path":"/share/switch_vision/generated-snmp2mqtt.yaml","generated_card_path":"/share/switch_vision/generated-dashboard-card.yaml","snmp_timeout":"3","snmp_retries":"1","snmp_log_path":"/share/switch_vision/snmpwalk.log","minimum_valid_walk_lines":"100","backup_retention_enabled":"true","backup_retention_count":5,"generate_support_my_switch_bundle":"true","support_mask_management_ips":"true","support_mask_mac_addresses":"true","support_mask_hostnames":"true","support_mask_vlan_names":"true","support_mask_interface_descriptions":"true","support_contributor_type":"forum","support_contributor_value":"PRIVATE_CONTRIBUTOR","future":"keep-too"}
def dsup(path,method="GET",timeout=12.0,payload=None):
    if path=='/addons/self/info': return {"data":{"options":copy.deepcopy(disc)}}
    if path=='/addons/self/options': disc.clear();disc.update(copy.deepcopy(payload["options"]));return {"result":"ok"}
    raise AssertionError(path)
support_web._supervisor_json=dsup
support_web._manual_snmp_override_models=lambda:{"WS-C3650-48PD-E"}
support_web.create_pre_mutation_backup=lambda *a,**k:None
support_web.enforce_retention=lambda *a,**k:None
st=support_web._discovery_settings_status();assert "PRIVATE_SNMP_COMMUNITY" not in repr(st) and "PRIVATE_CONTRIBUTOR" not in repr(st)
r=copy.deepcopy(st["settings"]);r["snmp_timeout"]="4"
saved=support_web._save_discovery_settings({"settings":r})
assert disc["switches"][0]["snmp_community"]=="PRIVATE_SNMP_COMMUNITY" and disc["support_contributor_value"]=="PRIVATE_CONTRIBUTOR" and disc["future"]=="keep-too"
assert "PRIVATE_SNMP_COMMUNITY" not in repr(saved) and "PRIVATE_CONTRIBUTOR" not in repr(saved)
print('Switch Vision Discovery v2.3.4 Hub settings ownership/privacy: PASS')
PY_HUB_SETTINGS

# v2.3.1 Supervisor ingress source gate regression
PYTHONPATH="$BASE_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY_INGRESS_GATE'
from http import HTTPStatus
from support_web import SUPERVISOR_INGRESS_IP, SupportHandler


def make_handler(source_ip: str):
    handler = SupportHandler.__new__(SupportHandler)
    handler.client_address = (source_ip, 12345)
    errors = []
    handler.send_error = lambda status, *args, **kwargs: errors.append(status)
    return handler, errors


allowed, allowed_errors = make_handler(SUPERVISOR_INGRESS_IP)
assert allowed._allow_ingress_request() is True
assert allowed_errors == []

for method, path in (("do_GET", "/api/status"), ("do_POST", "/api/create")):
    denied, denied_errors = make_handler("172.30.33.8")
    denied.path = path
    getattr(denied, method)()
    assert denied_errors == [HTTPStatus.FORBIDDEN], (method, denied_errors)

print("Switch Vision Discovery v2.3.1 Supervisor ingress source gate: PASS")
PY_INGRESS_GATE

# v2.2.0 Maintenance Hub MQTT ownership/reconciliation regression
python3 -m py_compile "$BASE_DIR/discovery_backups.py" "$BASE_DIR/discovery_backups_regression.py" "$BASE_DIR/mqtt_maintenance.py" "$BASE_DIR/mqtt_maintenance_runtime.py" "$BASE_DIR/support_diagnostics.py" "$BASE_DIR/supervisor_runtime.py" "$BASE_DIR/walk_correlation.py"
grep -Fq 'id="openMaintenanceButton"' "$BASE_DIR/support_web.py"
grep -Fq '<span>Manage backups</span>' "$BASE_DIR/support_web.py"
grep -Fq 'id="maintenanceCard"' "$BASE_DIR/support_web.py"
grep -Fq '/api/maintenance/mqtt/scan' "$BASE_DIR/support_web.py"
grep -Fq '/api/maintenance/mqtt/repair' "$BASE_DIR/support_web.py"
grep -Fq 'REPAIR STALE MQTT ENTITIES' "$BASE_DIR/maintenance.js"
grep -Fq 'id="exportMqttResultsButton"' "$BASE_DIR/support_web.py"
grep -Fq 'Stale Switch Vision MQTT entities (' "$BASE_DIR/maintenance.js"
grep -Fq 'switch-vision-mqtt-maintenance-scan-v1' "$BASE_DIR/maintenance.js"

# v2.3.0 Discovery configuration backup backend/privacy regressions remain.
# v2.3.10 removes the duplicate Discovery backup manager from Maintenance UI.
! grep -Fq 'id="discoveryBackupSummary"' "$BASE_DIR/support_web.py"
! grep -Fq 'id="refreshDiscoveryBackupsButton"' "$BASE_DIR/support_web.py"
grep -Fq '/api/maintenance/discovery-backups' "$BASE_DIR/support_web.py"
grep -Fq '/api/maintenance/discovery-backups/remove' "$BASE_DIR/support_web.py"
grep -Fq 'reason="configuration_import"' "$BASE_DIR/support_web.py"
grep -Fq 'reason="device_state_update"' "$BASE_DIR/support_web.py"
! grep -Fq 'api/maintenance/discovery-backups' "$BASE_DIR/maintenance.js"
PYTHONPATH="$BASE_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 "$BASE_DIR/discovery_backups_regression.py"

# v2.3.3 Installer recovery backup Maintenance bridge/UI regression
grep -Fq 'id="installerBackupSummary"' "$BASE_DIR/support_web.py"
grep -Fq '/api/maintenance/installer-backups' "$BASE_DIR/support_web.py"
grep -Fq 'switch-vision-installer-maintenance-v1' "$BASE_DIR/support_web.py"
grep -Fq 'installerBackupAutomaticRetention' "$BASE_DIR/maintenance.js"
grep -Fq 'retention_count: retention' "$BASE_DIR/maintenance.js"
PYTHONPATH="$BASE_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY_INSTALLER_BACKUPS'
import json
from pathlib import Path
import tempfile

import support_web


with tempfile.TemporaryDirectory() as tmp:
    response_path = Path(tmp) / "installer-maintenance-response.json"
    calls = []

    support_web._installed_switch_vision_app_links = lambda: {
        "installer": {
            "found": True,
            "slug": "switch_vision_installer",
            "ingress_url": "/api/hassio_ingress/example/",
        }
    }

    def supervisor(path, *, method="GET", timeout=12.0, payload=None):
        calls.append((path, method, payload))
        if path.endswith("/info"):
            info_calls = len([call for call in calls if call[0].endswith("/info")])
            return {
                "data": {
                    "stdin": True,
                    "state": "stopped" if info_calls == 1 else "started",
                }
            }
        if path.endswith("/start"):
            return {"result": "ok"}
        if path.endswith("/stdin"):
            response_path.write_text(
                json.dumps(
                    {
                        "schema": support_web.INSTALLER_MAINTENANCE_SCHEMA,
                        "request_id": payload["request_id"],
                        "ok": True,
                        "automatic_retention": True,
                        "retention_count": 4,
                        "backups": [
                            {
                                "name": "switch-vision-test",
                                "created_at": "2026-08-25T00:00:00+00:00",
                                "version": "2.6.0",
                                "contents": ["Custom component"],
                            }
                        ],
                        "operation": {
                            "active": False,
                            "kind": None,
                            "message": "Ready.",
                            "percent": 0,
                            "result": None,
                            "error": None,
                        },
                    }
                ),
                encoding="utf-8",
            )
            return {"result": "ok"}
        raise AssertionError(path)

    support_web._supervisor_json = supervisor
    result = support_web._installer_maintenance_request(
        "status", response_path=response_path
    )
    assert result["retention_count"] == 4
    assert result["backups"][0]["name"] == "switch-vision-test"
    start_calls = [call for call in calls if call[0].endswith("/start")]
    assert len(start_calls) == 1
    stdin_call = [call for call in calls if call[0].endswith("/stdin")][0]
    assert calls.index(start_calls[0]) < calls.index(stdin_call)
    command = stdin_call[2]
    assert command["schema"] == "switch-vision-installer-maintenance-v1"
    assert command["action"] == "status"
    assert command["request_id"].startswith("maintenance-")
    assert "/data/switch-vision-backups" not in repr(result)

try:
    support_web._installer_maintenance_browser_request(
        {
            "action": "set_policy",
            "automatic_retention": True,
            "retention_count": 11,
        }
    )
except ValueError:
    pass
else:
    raise AssertionError("Installer retention count above 10 was accepted")

try:
    support_web._installer_maintenance_browser_request({"action": "shell"})
except ValueError:
    pass
else:
    raise AssertionError("Unapproved Installer Maintenance action was accepted")

print("Switch Vision Discovery v2.3.3 Installer backup Maintenance bridge: PASS")
PY_INSTALLER_BACKUPS

PYTHONPATH="$BASE_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY_SUPPORT_DIAGNOSTICS'
from support_diagnostics import build_port_pipeline

generated = {"targets": [{"name": "SW1", "sensors": [{"object_id": "sw1_port_1_status", "oid": ".1.3.6.1.2.1.2.2.1.8.1"}]}]}
states = [{"entity_id": "sensor.sw1_port_1_status_2", "state": "up", "attributes": {"secret": "MUST_NOT_LEAK"}, "last_updated": "2026-08-24T00:00:00+00:00"}]
result = build_port_pipeline(generated, states, {"1.3.6.1.2.1.2.2.1.8.1": "up(1)"})
assert result["summary"]["status_rows"] == 1
assert result["summary"]["walk_up_but_exact_not_up"] == 1
assert result["ports"][0]["suffix_alternatives"][0]["entity_id"] == "sensor.sw1_port_1_status_2"
assert result["summary"]["ha_state_status"] == "available"
assert result["summary"]["walk_up_count"] == 1
assert "MUST_NOT_LEAK" not in repr(result)

unavailable = build_port_pipeline(
    generated,
    [],
    {"1.3.6.1.2.1.2.2.1.8.1": "up(1)"},
    ha_available=False,
)
assert unavailable["summary"]["ha_state_status"] == "unavailable"
assert unavailable["summary"]["walk_up_count"] == 1
assert unavailable["summary"]["walk_up_but_exact_not_up"] is None
assert unavailable["summary"]["suffix_alternative_count"] is None
assert unavailable["ports"][0]["exact_present"] is None
assert unavailable["anomalies"] == []
print("Switch Vision Discovery v2.2.3 support diagnostics availability regression: PASS")
PY_SUPPORT_DIAGNOSTICS

PYTHONPATH="$BASE_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY_CONFIGURATION_SNAPSHOT'
import json
from pathlib import Path
import tempfile

from support_diagnostics import (
    _configuration_from_documents,
    _safe_discovery_options,
    _safe_installer_options,
    _safe_snmp2mqtt_options,
    _safe_unifi2mqtt_options,
)

private_values = {
    "switch_host": "10.20.30.40",
    "community": "PRIVATE_COMMUNITY",
    "mqtt_password": "PRIVATE_MQTT_PASSWORD",
    "api_key": "PRIVATE_API_KEY",
    "controller": "https://private-controller.example",
    "contributor": "Private Person",
    "custom_prefix": "private/homeassistant/prefix",
}
discovery = _safe_discovery_options({
    "run_snmp_walks": "true",
    "generate_snmp2mqtt": "true",
    "snmp_timeout": "3",
    "support_contributor_type": "full_name",
    "support_contributor_value": private_values["contributor"],
    "switches": [{
        "switch_name": "PRIVATE_SWITCH",
        "switch_host": private_values["switch_host"],
        "sensor_prefix": "private_sensor",
        "snmp_community": private_values["community"],
        "enabled": "enabled",
        "walk_mode": "targeted",
        "switch_model": "N2128PX-ON",
        "display_name": "Private Rack Switch",
    }],
})
assert discovery["run_snmp_walks"] is True
assert discovery["generate_snmp2mqtt"] is True
assert discovery["switches"][0]["switch_host_configured"] is True
assert discovery["switches"][0]["snmp_community_configured"] is True
assert discovery["switches"][0]["switch_model"] == "N2128PX-ON"

snmp = _safe_snmp2mqtt_options({
    "mqtt": {
        "host": "private-broker.example",
        "port": 1883,
        "username": "private-user",
        "password": private_values["mqtt_password"],
        "base_topic": "private/base/topic",
    },
    "targets_path": "/private/custom-targets.yaml",
    "use_switch_vision_generated_yaml": False,
    "homeassistant": {"discovery": False, "prefix": private_values["custom_prefix"]},
})
assert snmp["generated_yaml_import"] is False
assert snmp["homeassistant"]["discovery_requested"] is False
assert snmp["homeassistant"]["prefix_mode"] == "custom"
assert snmp["mqtt"]["host_mode"] == "custom"
assert snmp["mqtt"]["password_configured"] is True

unifi = _safe_unifi2mqtt_options({
    "controller_url": private_values["controller"],
    "site_id": "private-site",
    "api_key": private_values["api_key"],
    "verify_ssl": "true",
    "poll_interval": "30",
    "mqtt_discovery_prefix": private_values["custom_prefix"],
})
assert unifi["controller"]["transport"] == "https"
assert unifi["controller"]["api_key_configured"] is True
assert unifi["controller"]["site_mode"] == "custom"
assert unifi["mqtt"]["discovery_prefix_mode"] == "custom"

installer = _safe_installer_options({
    "release_api_url": "https://private-release.example/api",
    "allow_custom_release_source": True,
    "backup_retention": 7,
})
assert installer["release_source_mode"] == "custom"
assert installer["allow_custom_release_source"] is True

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    diag = root / "diagnostics"
    diag.mkdir()
    (diag / "snmp2mqtt-runtime.json").write_text(json.dumps({
        "app_version": "0.9.18",
        "configuration_source": "switch_vision_generated_yaml",
        "generated_yaml_import_requested": "false",
        "generated_yaml_import_effective": True,
        "generated_target_count": 1,
        "generated_sensor_count": 60,
        "generated_yaml_sha256": "a" * 64,
        "homeassistant_discovery_requested": "false",
        "homeassistant_discovery_effective": True,
        "homeassistant_prefix_requested_mode": "custom",
        "homeassistant_prefix_effective": "homeassistant",
        "homeassistant_prefix_requested": private_values["custom_prefix"],
    }), encoding="utf-8")
    snapshot = _configuration_from_documents(root, {
        "discovery": {"version": "2.3.2", "state": "started", "options": {}},
        "snmp2mqtt": {"version": "0.9.18", "state": "started", "options": {}},
        "unifi2mqtt": {"version": "2.0.50", "state": "started", "options": {}},
        "installer": {"version": "2.1.30", "state": "stopped", "options": {}},
    })
    assert snapshot["effective_snmp2mqtt"]["homeassistant_discovery_requested"] is False
    assert snapshot["effective_snmp2mqtt"]["homeassistant_discovery_effective"] is True
    assert snapshot["effective_snmp2mqtt"]["homeassistant_prefix_requested_mode"] == "custom"
    assert snapshot["effective_snmp2mqtt"]["homeassistant_prefix_effective"] == "homeassistant"
    rendered = repr(snapshot) + repr(discovery) + repr(snmp) + repr(unifi) + repr(installer)
    for value in private_values.values():
        assert value not in rendered, value
    assert "PRIVATE_SWITCH" not in rendered
    assert "private-broker.example" not in rendered
    assert "private/base/topic" not in rendered
    assert "private-user" not in rendered
    assert "/private/custom-targets.yaml" not in rendered

print("Switch Vision Discovery v2.3.2 privacy-safe configuration snapshot regression: PASS")
PY_CONFIGURATION_SNAPSHOT


PYTHONPATH="$BASE_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY_DIAGNOSTIC_CORRELATION'
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile

from walk_correlation import build_port_pipeline
from mqtt_maintenance_runtime import _retained_receive_timeout

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    a = root / "snmpwalks" / "Switch_A"
    b = root / "snmpwalks" / "Switch_B"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    walk_a = a / "live-targeted-snmpwalk.txt"
    walk_b = b / "live-targeted-snmpwalk.txt"
    walk_a.write_text(".1.3.6.1.2.1.2.2.1.8.1 = INTEGER: up(1)\n", encoding="utf-8")
    walk_b.write_text(".1.3.6.1.2.1.2.2.1.8.1 = INTEGER: down(2)\n", encoding="utf-8")
    now = datetime.now(timezone.utc)
    os.utime(walk_a, (now.timestamp(), now.timestamp()))
    os.utime(walk_b, (now.timestamp(), now.timestamp()))

    generated = {"targets": [
        {"name": "Switch Vision sw1 Status", "sensors": [
            {"object_id": "sw1_port_1_status", "oid": ".1.3.6.1.2.1.2.2.1.8.1"}
        ]},
        {"name": "Switch Vision sw2 Status", "sensors": [
            {"object_id": "sw2_port_1_status", "oid": ".1.3.6.1.2.1.2.2.1.8.1"}
        ]},
    ]}
    cards = {"cards": [
        {"selected_switch": "SW1", "discovery_selected_switch": "Switch A", "status_entity_prefix": "sensor.sw1_port_"},
        {"selected_switch": "SW2", "discovery_selected_switch": "Switch B", "status_entity_prefix": "sensor.sw2_port_"},
    ]}
    states = [
        {"entity_id": "sensor.sw1_port_1_status", "state": "1"},
        {"entity_id": "sensor.sw2_port_1_status", "state": "2"},
    ]

    fresh = build_port_pipeline(root, generated, states, cards, now=now)
    by_id = {row["object_id"]: row for row in fresh["ports"]}
    assert by_id["sw1_port_1_status"]["walk_if_oper_status"] == "up(1)"
    assert by_id["sw2_port_1_status"]["walk_if_oper_status"] == "down(2)"
    assert by_id["sw1_port_1_status"]["walk_source"] != by_id["sw2_port_1_status"]["walk_source"]
    assert fresh["summary"]["walk_state_status"] == "fresh"
    assert fresh["summary"]["walk_up_but_exact_not_up"] == 0

    old = (now - timedelta(hours=2)).timestamp()
    os.utime(walk_a, (old, old))
    os.utime(walk_b, (old, old))
    stale = build_port_pipeline(root, generated, states, cards, now=now)
    assert stale["summary"]["walk_state_status"] == "stale"
    assert stale["summary"]["walk_up_but_exact_not_up"] is None
    assert stale["anomalies"] == []
    assert stale["summary"]["stale_walk_status_rows"] == 2

assert _retained_receive_timeout(False, 0, 99.0) == 12.0
assert _retained_receive_timeout(True, 0, 99.0) == 5.0
assert _retained_receive_timeout(True, 1, 99.0) == 1.0
print("Switch Vision Discovery v2.2.4 diagnostic correlation/timing regression: PASS")
PY_DIAGNOSTIC_CORRELATION

# v2.2.2: run the real contribution packaging path and inspect the ZIP.
# This catches runtime filename/wrapper drift that unit-testing support_diagnostics.py
# alone cannot detect.
grep -Fq 'SANITIZER_SCRIPT="${SUPPORT_SANITIZER_SCRIPT:-/ha_entity_snapshot_sanitizer.py}"' "$BASE_DIR/support_my_switch.sh"
grep -Fq 'BASE_SANITIZER_SCRIPT="${SUPPORT_BASE_SANITIZER_SCRIPT:-/sanitize_support_bundle.py}"' "$BASE_DIR/support_my_switch.sh"
grep -Fq 'BASE_SANITIZER = Path(os.environ.get("SWITCH_VISION_BASE_SANITIZER", "/sanitize_support_bundle.py"))' "$BASE_DIR/ha_entity_snapshot_sanitizer.py"

support_test_dir=$(mktemp -d)
mkdir -p "$support_test_dir/switch_vision/snmpwalks/test" "$support_test_dir/out"
cat > "$support_test_dir/switch_vision/generated-snmp2mqtt.yaml" <<'YAML_SUPPORT_E2E'
mqtt:
  discovery_prefix: homeassistant
  topic_prefix: snmp2mqtt
targets:
  - name: TEST
    host: 198.51.100.10
    sensors:
      - name: test_port_1_status
        object_id: test_port_1_status
        oid: .1.3.6.1.2.1.2.2.1.8.1
YAML_SUPPORT_E2E
cat > "$support_test_dir/switch_vision/generated-dashboard-card.yaml" <<'YAML_SUPPORT_CARD'
- type: custom:switch-vision-3650
  title: Integration Test
  selected_switch: TEST
  sensor_prefix: test
  status_entity_prefix: sensor.test_port_
  status_entity_suffix: _status
YAML_SUPPORT_CARD
cat > "$support_test_dir/switch_vision/snmpwalks/test/live-targeted-snmpwalk.txt" <<'WALK_SUPPORT_E2E'
.1.3.6.1.2.1.2.2.1.8.1 = INTEGER: up(1)
WALK_SUPPORT_E2E

SUPERVISOR_TOKEN="" \
SWITCH_VISION_DISCOVERY_VERSION="integration-test" \
SWITCH_VISION_ROOT="$support_test_dir/switch_vision" \
CONTRIBUTIONS_DIR="$support_test_dir/out" \
SUPPORT_SANITIZER_SCRIPT="$BASE_DIR/ha_entity_snapshot_sanitizer.py" \
SUPPORT_BASE_SANITIZER_SCRIPT="$BASE_DIR/sanitize_support_bundle.py" \
SWITCH_VISION_BASE_SANITIZER="$BASE_DIR/sanitize_support_bundle.py" \
SUPPORT_EMAIL_BUILDER_SCRIPT="$BASE_DIR/make_support_email.py" \
SUPPORT_REGISTRY_LOOKUP_SCRIPT="$BASE_DIR/registry_lookup.py" \
SUPPORT_REGISTRY_FILE="$support_test_dir/missing-registry.json" \
SUPPORT_MASK_MANAGEMENT_IPS=true \
SUPPORT_MASK_MAC_ADDRESSES=true \
SUPPORT_MASK_HOSTNAMES=true \
SUPPORT_MASK_VLAN_NAMES=true \
SUPPORT_MASK_INTERFACE_DESCRIPTIONS=true \
sh "$BASE_DIR/support_my_switch.sh" > "$support_test_dir/run.log"

support_bundle=$(find "$support_test_dir/out" -maxdepth 1 -type f -name '*.zip' | head -n 1)
[ -n "$support_bundle" ] && [ -s "$support_bundle" ]
python3 - "$support_bundle" <<'PY_SUPPORT_ZIP'
import json
import sys
import zipfile

path = sys.argv[1]
expected = (
    "home-assistant-entity-resolution.json",
    "mqtt-maintenance-scan.json",
    "port-pipeline.json",
    "model-provenance.json",
    "card-entity-bindings.json",
    "generated-file-provenance.json",
    "runtime-versions.json",
    "configuration-snapshot.json",
    "diagnostic-summary.json",
)
with zipfile.ZipFile(path) as archive:
    names = archive.namelist()
    roots = {name.split("/", 1)[0] for name in names if "/" in name}
    assert len(roots) == 1, roots
    root = next(iter(roots))
    for filename in expected:
        wanted = f"{root}/switch_vision/diagnostics/{filename}"
        assert names.count(wanted) == 1, (wanted, names.count(wanted))
    assert not any(name.startswith(f"{root}/diagnostics/") for name in names), "duplicate top-level diagnostics"
    manifest = json.loads(archive.read(f"{root}/MANIFEST.json"))
    assert manifest["bundle_version"] == 12
    summary = json.loads(archive.read(f"{root}/switch_vision/diagnostics/diagnostic-summary.json"))
    assert summary["privacy"] == {
        "credentials_included": False,
        "home_assistant_attributes_included": False,
        "raw_mqtt_discovery_payloads_included": False,
        "unrelated_home_assistant_entities_included": False,
    }
print("Switch Vision Discovery v2.2.2 Support My Switch packaged diagnostics integration: PASS")
PY_SUPPORT_ZIP
rm -rf "$support_test_dir"


PYTHONPATH="$BASE_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY_MQTT_MAINTENANCE'
import json

from mqtt_maintenance import (
    build_repair_plan,
    classify_owned_retained_config,
    discovery_subscription_filter,
    public_repair_plan,
)

prefix = "homeassistant"
base = "snmp2mqtt"
topic = "homeassistant/sensor/snmp2mqtt/sw1_port_1_status/config"
payload = json.dumps(
    {
        "origin": {
            "name": "Switch Vision SNMP2MQTT",
            "url": "https://github.com/zemerdon/switch-vision-snmp2mqtt",
        },
        "object_id": "sw1_port_1_status",
        "default_entity_id": "sensor.sw1_port_1_status",
        "unique_id": "sw1_port_1_status",
        "state_topic": "snmp2mqtt/sw1/port_1_status/value",
    }
)
assert discovery_subscription_filter(prefix) == "homeassistant/+/snmp2mqtt/+/config"
owned = classify_owned_retained_config(topic, payload, True, prefix, base)
assert owned and owned["entity_id"] == "sensor.sw1_port_1_status"
assert classify_owned_retained_config(topic, payload, False, prefix, base) is None

wrong_origin = json.loads(payload)
wrong_origin["origin"] = {"name": "Something Else"}
assert classify_owned_retained_config(topic, json.dumps(wrong_origin), True, prefix, base) is None

wrong_url = json.loads(payload)
wrong_url["origin"]["url"] = "https://example.invalid/not-switch-vision"
assert classify_owned_retained_config(topic, json.dumps(wrong_url), True, prefix, base) is None

wrong_state = json.loads(payload)
wrong_state["state_topic"] = "zigbee2mqtt/sw1/value"
assert classify_owned_retained_config(topic, json.dumps(wrong_state), True, prefix, base) is None

wrong_unique = json.loads(payload)
wrong_unique["unique_id"] = "different"
assert classify_owned_retained_config(topic, json.dumps(wrong_unique), True, prefix, base) is None

unrelated_topic = "homeassistant/sensor/other_app/sw1_port_1_status/config"
assert classify_owned_retained_config(unrelated_topic, payload, True, prefix, base) is None

stale_topic = "homeassistant/sensor/snmp2mqtt/old_sw_port_1_status/config"
stale_payload = json.dumps(
    {
        "origin": {"name": "Switch Vision SNMP2MQTT"},
        "object_id": "old_sw_port_1_status",
        "default_entity_id": "sensor.old_sw_port_1_status",
        "unique_id": "old_sw_port_1_status",
        "state_topic": "snmp2mqtt/old_sw/port_1_status/value",
    }
)
stale = classify_owned_retained_config(stale_topic, stale_payload, True, prefix, base)
assert stale

plan = build_repair_plan([topic], [owned, stale])
assert plan["owned_retained_count"] == 2
assert plan["current_retained_count"] == 1
assert plan["stale_count"] == 1
assert plan["stale_entries"] == [
    {
        "component": "sensor",
        "object_id": "old_sw_port_1_status",
        "entity_id": "sensor.old_sw_port_1_status",
    }
]
assert "_stale_topics" not in public_repair_plan(plan)
assert public_repair_plan(plan)["plan_token"] == public_repair_plan(
    build_repair_plan([topic], [stale, owned])
)["plan_token"]

clean = build_repair_plan([topic], [owned])
assert clean["stale_count"] == 0
print("Switch Vision Discovery v2.2.0 MQTT maintenance ownership regression: PASS")
PY_MQTT_MAINTENANCE

# v2.1.47: targeted walks must retain DOT3-MAU-MIB. This is diagnostic
# evidence for dual-personality media selection; it does not classify or
# render any connector by itself.
mau_live_oid_count="$(
  python3 - "$BASE_DIR/discovery_job.sh" <<PY_MAU
from pathlib import Path
import sys

inside = False
count = 0
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not inside and line == 'LIVE_OIDS="':
        inside = True
        continue
    if inside and line == '"':
        break
    if inside and line == "1.3.6.1.2.1.26":
        count += 1
print(count)
PY_MAU
)"
[ "$mau_live_oid_count" -eq 1 ]
echo "Switch Vision Discovery v2.1.47 DOT3-MAU targeted-walk regression: PASS"

# Calibration Profile Manager relocation checks
grep -Fq 'id="openCalibrationProfilesButton"'     "$BASE_DIR/support_web.py"

grep -Fq 'id="calibrationProfilesCard"'     "$BASE_DIR/support_web.py"

grep -Fq 'switch_vision/list_calibrations'     "$BASE_DIR/support_web.py"

grep -Fq 'switch_vision/get_calibration'     "$BASE_DIR/support_web.py"

grep -Fq 'SwitchVisionCalibrationProfiles'     "$BASE_DIR/calibration_profiles.js"

if [ -d "$BASE_DIR/mib_database" ]; then
  RUNTIME_DATA_DIR="$BASE_DIR"
elif [ -d "$BASE_DIR/opt/switch-vision/mib_database" ]; then
  RUNTIME_DATA_DIR="$BASE_DIR/opt/switch-vision"
elif [ -d /opt/switch-vision/mib_database ]; then
  RUNTIME_DATA_DIR=/opt/switch-vision
else
  echo "ERROR: Switch Vision runtime data directory is missing." >&2
  exit 1
fi
export CV_MIB_DATABASE_DIR="$RUNTIME_DATA_DIR/mib_database"
export CV_VENDOR_DIR="$RUNTIME_DATA_DIR/vendors"
RUNTIME_REGISTRY="$RUNTIME_DATA_DIR/devices/supported_devices.json"
[ -f "$RUNTIME_REGISTRY" ]
. "$CV_VENDOR_DIR/base.sh"
. "$CV_VENDOR_DIR/generic.sh"
. "$CV_VENDOR_DIR/cisco.sh"
. "$CV_VENDOR_DIR/known_vendor.sh"
. "$CV_VENDOR_DIR/interface.sh"
. "$CV_VENDOR_DIR/loader.sh"
cv_vendor_database_self_test

tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT
walk="$tmp_dir/test-walk.txt"
cat > "$walk" <<'WALK'
.1.3.6.1.2.1.1.1.0 = STRING: "Cisco IOS Software, C3650 Software"
.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.9.1.2066
.1.3.6.1.2.1.1.5.0 = STRING: "SW5"
.1.3.6.1.2.1.31.1.1.1.1.1 = STRING: "GigabitEthernet1/0/1"
.1.3.6.1.2.1.31.1.1.1.1.49 = STRING: "TenGigabitEthernet1/1/1"
.1.3.6.1.2.1.31.1.1.1.1.10101 = STRING: "Vlan1"
WALK
cv_detect_vendor_identity "$walk"
[ "$CV_ID_VENDOR" = "cisco" ]
[ "$CV_ID_FAMILY" = "Catalyst 3650" ]
[ "$CV_ID_PRODUCT_MATCH" = "exact" ]
cv_write_capabilities_json "$walk" "$tmp_dir/capabilities.json" "$tmp_dir/latest.json"
jq -e '(.device.vendor == "cisco") and (.summary.interface_count == 3) and (.summary.physical_count == 2) and (.summary.rj45_count == 1) and (.summary.sfp_plus_count == 1)' "$tmp_dir/capabilities.json" >/dev/null

# Catalyst uplink normalization: 48FPD Gi aliases represent the same two
# physical SFP+ cages as Te1/0/1-2; 24PS has four genuine 1G SFP ports.
c2960_fpd="$tmp_dir/c2960-fpd.txt"
cat > "$c2960_fpd" <<'WALK'
.1.3.6.1.2.1.1.1.0 = STRING: "Cisco IOS Software, C2960X Software"
.1.3.6.1.2.1.47.1.1.1.1.13.1 = STRING: "WS-C2960X-48FPD-L"
.1.3.6.1.2.1.31.1.1.1.1.1 = STRING: "Gi1/0/1"
.1.3.6.1.2.1.31.1.1.1.1.49 = STRING: "Gi1/0/49"
.1.3.6.1.2.1.31.1.1.1.1.50 = STRING: "Gi1/0/50"
.1.3.6.1.2.1.31.1.1.1.1.201 = STRING: "Te1/0/1"
.1.3.6.1.2.1.31.1.1.1.1.202 = STRING: "Te1/0/2"
WALK
cv_write_capabilities_json "$c2960_fpd" "$tmp_dir/c2960-fpd-capabilities.json" ""
jq -e '(.summary.rj45_count == 1) and (.summary.sfp_count == 0) and (.summary.sfp_plus_count == 2) and (.summary.physical_count == 3)' "$tmp_dir/c2960-fpd-capabilities.json" >/dev/null

c2960_24ps="$tmp_dir/c2960-24ps.txt"
cat > "$c2960_24ps" <<'WALK'
.1.3.6.1.2.1.1.1.0 = STRING: "Cisco IOS Software, C2960X Software"
.1.3.6.1.2.1.47.1.1.1.1.13.1 = STRING: "WS-C2960X-24PS-L"
.1.3.6.1.2.1.31.1.1.1.1.1 = STRING: "Gi1/0/1"
.1.3.6.1.2.1.31.1.1.1.1.25 = STRING: "Gi1/0/25"
.1.3.6.1.2.1.31.1.1.1.1.26 = STRING: "Gi1/0/26"
.1.3.6.1.2.1.31.1.1.1.1.27 = STRING: "Gi1/0/27"
.1.3.6.1.2.1.31.1.1.1.1.28 = STRING: "Gi1/0/28"
WALK
cv_write_capabilities_json "$c2960_24ps" "$tmp_dir/c2960-24ps-capabilities.json" ""
jq -e '(.summary.rj45_count == 1) and (.summary.sfp_count == 4) and (.summary.sfp_plus_count == 0) and (.summary.physical_count == 5)' "$tmp_dir/c2960-24ps-capabilities.json" >/dev/null

cat >> "$walk" <<'WALK'
.1.3.6.1.2.1.47.1.1.1.1.7.1001 = STRING: "Chassis inlet temperature"
.1.3.6.1.2.1.99.1.1.1.1.1001 = INTEGER: 8
.1.3.6.1.2.1.99.1.1.1.2.1001 = INTEGER: 9
.1.3.6.1.2.1.99.1.1.1.3.1001 = INTEGER: 0
.1.3.6.1.2.1.99.1.1.1.4.1001 = INTEGER: 42
.1.3.6.1.2.1.99.1.1.1.5.1001 = INTEGER: 1
.1.3.6.1.2.1.105.1.3.1.1.2.1 = Gauge32: 740
.1.3.6.1.2.1.105.1.3.1.1.4.1 = Gauge32: 120
WALK
python3 "$BASE_DIR/standard_sensor_scan.py" --walk "$walk" --enrich "$tmp_dir/capabilities.json"
jq -e '(.standard_sensor_discovery.candidate_count == 3) and (.capabilities.environment == true) and (.capabilities.poe == true)' "$tmp_dir/capabilities.json" >/dev/null


juniper_walk="$tmp_dir/juniper-walk.txt"
cat > "$juniper_walk" <<'WALK'
.1.3.6.1.2.1.1.1.0 = STRING: "Juniper Networks, Inc. ex4300-48p"
.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.2636.1.1.1.2.63
.1.3.6.1.2.1.1.5.0 = STRING: "edge-juniper"
JUNIPER-MIB::jnxOperatingTemp.1 = INTEGER: 42
JUNIPER-MIB::jnxOperatingCPU.1 = INTEGER: 17
WALK
cv_detect_vendor_identity "$juniper_walk"
[ "$CV_ID_VENDOR" = "juniper" ]
cv_write_capabilities_json "$juniper_walk" "$tmp_dir/juniper-capabilities.json" ""
python3 "$BASE_DIR/vendor_sensor_scan.py" --walk "$juniper_walk" --database "$CV_MIB_DATABASE_DIR" --enrich "$tmp_dir/juniper-capabilities.json"
jq -e '(.device.vendor == "juniper") and (.vendor_sensor_discovery.pack_loaded == true) and (.vendor_sensor_discovery.counts_by_category.temperature == 1) and (.vendor_sensor_discovery.counts_by_category.cpu == 1)' "$tmp_dir/juniper-capabilities.json" >/dev/null

huawei_walk="$tmp_dir/huawei-walk.txt"
cat > "$huawei_walk" <<'WALK'
.1.3.6.1.2.1.1.1.0 = STRING: "Huawei S5735-L8P4X-A1"
.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.2011.2.23.849
.1.3.6.1.2.1.1.5.0 = STRING: "huawei-test"
.1.3.6.1.2.1.31.1.1.1.1.6 = STRING: "GigabitEthernet0/0/1"
.1.3.6.1.2.1.31.1.1.1.1.14 = STRING: "XGigabitEthernet0/0/1"
.1.3.6.1.2.1.31.1.1.1.1.15 = STRING: "XGigabitEthernet0/0/2"
.1.3.6.1.2.1.31.1.1.1.1.16 = STRING: "XGigabitEthernet0/0/3"
.1.3.6.1.2.1.31.1.1.1.1.17 = STRING: "XGigabitEthernet0/0/4"
WALK
cv_detect_vendor_identity "$huawei_walk"
[ "$CV_ID_VENDOR" = "huawei" ]
cv_write_capabilities_json "$huawei_walk" "$tmp_dir/huawei-capabilities.json" ""
jq -e '(.device.vendor == "huawei") and (.summary.physical_count == 5) and (.summary.rj45_count == 1) and (.summary.sfp_plus_count == 4)' "$tmp_dir/huawei-capabilities.json" >/dev/null

s5720_walk="$tmp_dir/s5720-walk.txt"
cat > "$s5720_walk" <<'WALK'
.1.3.6.1.2.1.1.1.0 = STRING: "Huawei S5720-12TP-LI-AC "
.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.2011.2.23.394
.1.3.6.1.2.1.1.5.0 = STRING: "huawei-s5720-test"
.1.3.6.1.2.1.2.2.1.2.1 = STRING: "InLoopBack0"
.1.3.6.1.2.1.2.2.1.2.2 = STRING: "NULL0"
.1.3.6.1.2.1.2.2.1.2.5 = STRING: "GigabitEthernet0/0/1"
.1.3.6.1.2.1.2.2.1.2.6 = STRING: "GigabitEthernet0/0/2"
.1.3.6.1.2.1.2.2.1.2.7 = STRING: "GigabitEthernet0/0/3"
.1.3.6.1.2.1.2.2.1.2.8 = STRING: "GigabitEthernet0/0/4"
.1.3.6.1.2.1.2.2.1.2.9 = STRING: "GigabitEthernet0/0/5"
.1.3.6.1.2.1.2.2.1.2.10 = STRING: "GigabitEthernet0/0/6"
.1.3.6.1.2.1.2.2.1.2.11 = STRING: "GigabitEthernet0/0/7"
.1.3.6.1.2.1.2.2.1.2.12 = STRING: "GigabitEthernet0/0/8"
.1.3.6.1.2.1.2.2.1.2.13 = STRING: "GigabitEthernet0/0/9"
.1.3.6.1.2.1.2.2.1.2.14 = STRING: "GigabitEthernet0/0/10"
.1.3.6.1.2.1.2.2.1.2.15 = STRING: "GigabitEthernet0/0/11"
.1.3.6.1.2.1.2.2.1.2.16 = STRING: "GigabitEthernet0/0/12"
WALK
cv_detect_vendor_identity "$s5720_walk"
[ "$CV_ID_VENDOR" = "huawei" ]
cv_write_capabilities_json "$s5720_walk" "$tmp_dir/s5720-capabilities.json" ""
jq -e '
  (.device.model_text == "S5720-12TP-LI-AC")
  and (.summary.physical_count == 12)
  and (.summary.rj45_count == 8)
  and (.summary.sfp_count == 4)
  and (.summary.sfp_plus_count == 0)
  and (.summary.uplink_count == 4)
  and ([.interfaces[] | select(.physical) | .name] | length == 12)
' "$tmp_dir/s5720-capabilities.json" >/dev/null


zyxel_walk="$tmp_dir/zyxel-walk.txt"
cat > "$zyxel_walk" <<'WALK'
.1.3.6.1.2.1.1.1.0 = STRING: "XS1930-10"
.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.890.1.15
.1.3.6.1.2.1.1.5.0 = STRING: "zyxel-test"
.1.3.6.1.2.1.31.1.1.1.1.1 = STRING: "swp00"
.1.3.6.1.2.1.31.1.1.1.1.2 = STRING: "swp01"
.1.3.6.1.2.1.31.1.1.1.1.3 = STRING: "swp02"
.1.3.6.1.2.1.31.1.1.1.1.4 = STRING: "swp03"
.1.3.6.1.2.1.31.1.1.1.1.5 = STRING: "swp04"
.1.3.6.1.2.1.31.1.1.1.1.6 = STRING: "swp05"
.1.3.6.1.2.1.31.1.1.1.1.7 = STRING: "swp06"
.1.3.6.1.2.1.31.1.1.1.1.8 = STRING: "swp07"
.1.3.6.1.2.1.31.1.1.1.1.9 = STRING: "swp08"
.1.3.6.1.2.1.31.1.1.1.1.10 = STRING: "swp09"
.1.3.6.1.4.1.890.1.15.3.2.4.0 = INTEGER: 12
.1.3.6.1.4.1.890.1.15.3.2.5.0 = INTEGER: 34
.1.3.6.1.4.1.890.1.15.3.2.7.0 = INTEGER: 13
.1.3.6.1.4.1.890.1.15.3.2.8.0 = INTEGER: 11
.1.3.6.1.4.1.890.1.15.3.2.9.0 = INTEGER: 9
WALK
# Put more than the vendor review cap of generic enterprise numerics before the
# late fan/temperature rows. Curated OIDs must still be retained by the scanner.
i=1
while [ "$i" -le 130 ]; do
  printf '.1.3.6.1.4.1.890.1.15.99.1.%s = INTEGER: %s\n' "$i" "$i" >> "$zyxel_walk"
  i=$((i + 1))
done
cat >> "$zyxel_walk" <<'WALK'
.1.3.6.1.4.1.890.1.15.3.26.1.1.1.3.1 = INTEGER: 3500
.1.3.6.1.4.1.890.1.15.3.26.1.1.1.7.1 = STRING: "Normal"
.1.3.6.1.4.1.890.1.15.3.26.1.2.1.3.2 = INTEGER: 51
.1.3.6.1.4.1.890.1.15.3.26.1.2.1.7.2 = STRING: "NORMAL"
WALK
cv_detect_vendor_identity "$zyxel_walk"
[ "$CV_ID_VENDOR" = "zyxel" ]
[ "$CV_ID_FAMILY" = "XS1930" ]
[ "$CV_ID_MODEL_HINT" = "XS1930-10" ]
[ "$CV_ID_SUPPORT_STATUS" = "experimental" ]
cv_write_capabilities_json "$zyxel_walk" "$tmp_dir/zyxel-capabilities.json" ""
python3 "$BASE_DIR/vendor_sensor_scan.py" --walk "$zyxel_walk" --database "$CV_MIB_DATABASE_DIR" --enrich "$tmp_dir/zyxel-capabilities.json"
jq -e '
  (.device.vendor == "zyxel")
  and (.device.model_text == "XS1930-10")
  and (.summary.physical_count == 10)
  and (.summary.rj45_count == 8)
  and (.summary.sfp_plus_count == 2)
  and (.vendor_sensor_discovery.pack_loaded == true)
  and (.vendor_sensor_discovery.counts_by_category.cpu == 4)
  and (.vendor_sensor_discovery.counts_by_category.memory == 1)
  and (.vendor_sensor_discovery.counts_by_category.fan == 2)
  and (.vendor_sensor_discovery.counts_by_category.temperature == 2)
  and ([.vendor_sensor_discovery.candidates[] | select(.source == "curated-known-oid")] | length == 9)
  and ([.vendor_sensor_discovery.candidates[] | select(.oid == "1.3.6.1.4.1.890.1.15.3.26.1.1.1.3.1")] | length == 1)
  and ([.vendor_sensor_discovery.candidates[] | select(.oid == "1.3.6.1.4.1.890.1.15.3.26.1.2.1.3.2")] | length == 1)
' "$tmp_dir/zyxel-capabilities.json" >/dev/null
python3 "$BASE_DIR/registry_lookup.py" --registry "$RUNTIME_REGISTRY" --model "Unknown Zyxel XS1930-10" --report > "$tmp_dir/zyxel-registry-report.txt"
grep -q -- '- Registry match: yes' "$tmp_dir/zyxel-registry-report.txt"
grep -q -- '- Registry status: experimental' "$tmp_dir/zyxel-registry-report.txt"
grep -q -- '- Mapping profile: zyxel-xs1930-10' "$tmp_dir/zyxel-registry-report.txt"

sg500_walk="$tmp_dir/sg500-walk.txt"
cat > "$sg500_walk" <<'WALK'
.1.3.6.1.2.1.1.1.0 = STRING: "SG500X-24 24-Port Gigabit with 4-Port 10-Gigabit Stackable Managed Switch"
.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.9.6.1.85.24.1
.1.3.6.1.2.1.1.5.0 = STRING: "sg500-test"
.1.3.6.1.2.1.31.1.1.1.1.49 = STRING: "gi1/1"
.1.3.6.1.2.1.31.1.1.1.1.72 = STRING: "gi1/24"
.1.3.6.1.2.1.31.1.1.1.1.107 = STRING: "te1/1"
.1.3.6.1.2.1.31.1.1.1.1.110 = STRING: "te1/4"
WALK
cv_detect_vendor_identity "$sg500_walk"
[ "$CV_ID_VENDOR" = "cisco" ]
cv_write_capabilities_json "$sg500_walk" "$tmp_dir/sg500-capabilities.json" ""
jq -e '(.device.model_text == "SG500X-24") and (.summary.physical_count == 4) and (.summary.rj45_count == 2) and (.summary.sfp_plus_count == 2)' "$tmp_dir/sg500-capabilities.json" >/dev/null

registry_report="$tmp_dir/registry-report.txt"
python3 "$BASE_DIR/registry_lookup.py" --registry "$RUNTIME_REGISTRY" --model "WS-C3650-48PD-E" --report > "$registry_report"
grep -q -- '- Registry match: yes' "$registry_report"
grep -q -- '- Registry status: confirmed' "$registry_report"
grep -q -- '- Mapping profile: cisco-3650-48p-2x10g' "$registry_report"

unifi_snapshot="$tmp_dir/unifi-devices.json"
unifi_registry="$tmp_dir/unifi-registry.json"
python3 - "$unifi_snapshot" "$unifi_registry" <<'PYTEST'
import json, sys
snapshot, registry = sys.argv[1:3]
pro_ports = [{"idx": i, "state": "UP", "connector": "RJ45", "speed_mbps": 1000} for i in range(1, 25)]
pro_ports += [{"idx": 25, "state": "UP", "connector": "SFPPLUS", "speed_mbps": 10000}, {"idx": 26, "state": "UP", "connector": "SFPPLUS", "speed_mbps": 10000}]
lite_ports = [{"idx": i, "state": "UP", "connector": "RJ45", "speed_mbps": 1000} for i in range(1, 17)]
us48_ports = [{"idx": i, "state": "UP", "connector": "RJ45", "speed_mbps": 1000} for i in range(1, 49)]
us48_ports += [
    {"idx": 49, "state": "UP", "connector": "SFP", "speed_mbps": 1000},
    {"idx": 50, "state": "UP", "connector": "SFP", "speed_mbps": 1000},
    {"idx": 51, "state": "UP", "connector": "SFPPLUS", "speed_mbps": 10000},
    {"idx": 52, "state": "UP", "connector": "SFPPLUS", "speed_mbps": 10000},
]
json.dump({"schema_version": 1, "devices": [
    {"id": "api-pro24", "name": "Core", "model": "USW Pro 24 PoE", "ports": pro_ports},
    {"id": "api-lite16", "name": "Garage", "model": "USW Lite 16 PoE", "ports": lite_ports},
    {
        "id": "api-us48",
        "name": "Legacy 48",
        "model": "US 48 PoE 500W",
        "ports": us48_ports,
        "api_capabilities": {
            "port_detail": True,
            "per_port_traffic": False,
        },
    },
    {
        "id": "api-ups",
        "name": "Managed UPS",
        "model": "UPS 2U",
        "ports": [
            {
                "idx": 1,
                "state": "UP",
                "connector": "RJ45",
                "speed_mbps": 100,
            }
        ],
    },
]}, open(snapshot, "w"))
json.dump({"devices": [
    {"model": "USW-Pro-24-PoE", "status": "experimental", "dashboard_support": True, "calibration_profile": "cisco_2960x_24p", "default_faceplate": "faceplates/24rj45-2sfp.png"},
    {"model": "USW Lite 16 PoE", "status": "experimental", "dashboard_support": True, "calibration_profile": "cisco_2960x_24p", "default_faceplate": "faceplates/24rj45-4sfp.png"},
    {"model": "US 48 PoE 500W", "status": "experimental", "dashboard_support": True, "calibration_profile": "default_cisco_48_port", "default_faceplate": "faceplates/48rj45-4sfp.png"},
]}, open(registry, "w"))
PYTEST
python3 "$BASE_DIR/unifi_dashboard_cards.py" --snapshot "$unifi_snapshot" --registry "$unifi_registry" --indent 0 > "$tmp_dir/unifi-cards.yaml"
grep -q 'data_source: unifi_api' "$tmp_dir/unifi-cards.yaml"
grep -q 'switch_model: USW Pro 24 PoE' "$tmp_dir/unifi-cards.yaml"
grep -q 'switch_model: USW Lite 16 PoE' "$tmp_dir/unifi-cards.yaml"
grep -q 'faceplate_file: 48rj45-4sfp.png' "$tmp_dir/unifi-cards.yaml"
grep -q 'port_count: 16' "$tmp_dir/unifi-cards.yaml"
grep -q 'switch_model: US 48 PoE 500W' "$tmp_dir/unifi-cards.yaml"
grep -q 'port_count: 48' "$tmp_dir/unifi-cards.yaml"
grep -q 'sfp_port_count: 4' "$tmp_dir/unifi-cards.yaml"
grep -q 'unifi_port_detail: true' "$tmp_dir/unifi-cards.yaml"
grep -q 'unifi_per_port_traffic: false' "$tmp_dir/unifi-cards.yaml"
! grep -q 'switch_model: UPS 2U' "$tmp_dir/unifi-cards.yaml"
! grep -q 'waiting for a matching generic faceplate/calibration profile' "$tmp_dir/unifi-cards.yaml"

contrib_snapshot="$tmp_dir/unifi-community-fixture-a.json"

python3 - "$contrib_snapshot" <<'PYTEST'
import json
import sys

path = sys.argv[1]

def rj45(count, speed=1000):
    return [
        {
            "idx": i,
            "state": "UP",
            "connector": "RJ45",
            "max_speed_mbps": speed,
            "speed_mbps": speed,
            "poe": {
                "available": False
            },
        }
        for i in range(1, count + 1)
    ]

usw24 = rj45(24)
usw24 += [
    {
        "idx": 25,
        "state": "DOWN",
        "connector": "SFP",
        "max_speed_mbps": 1000,
        "speed_mbps": None,
    },
    {
        "idx": 26,
        "state": "DOWN",
        "connector": "SFP",
        "max_speed_mbps": 1000,
        "speed_mbps": None,
    },
]

usw16 = rj45(16)
usw16 += [
    {
        "idx": 17,
        "state": "DOWN",
        "connector": "SFP",
        "max_speed_mbps": 1000,
        "speed_mbps": None,
    },
    {
        "idx": 18,
        "state": "DOWN",
        "connector": "SFP",
        "max_speed_mbps": 1000,
        "speed_mbps": None,
    },
]

lite8 = rj45(8)

flex25 = rj45(8, 2500)
flex25 += [
    {
        "idx": 9,
        "state": "DOWN",
        "connector": "RJ45",
        "max_speed_mbps": 10000,
        "speed_mbps": None,
    },
    {
        "idx": 10,
        "state": "DOWN",
        "connector": "SFPPLUS",
        "max_speed_mbps": 10000,
        "speed_mbps": None,
    },
]

flex = rj45(5)

devices = [
    {
        "id": "contrib-usw24",
        "name": "USW24",
        "model": "USW-24-PoE",
        "ports": usw24,
        "api_capabilities": {
            "port_detail": True,
            "per_port_traffic": False,
        },
    },
    {
        "id": "contrib-usw16",
        "name": "USW16",
        "model": "USW-16-PoE",
        "ports": usw16,
        "api_capabilities": {
            "port_detail": True,
            "per_port_traffic": False,
        },
    },
    {
        "id": "contrib-lite8",
        "name": "Lite8",
        "model": "USW-Lite-8-PoE",
        "ports": lite8,
        "api_capabilities": {
            "port_detail": True,
            "per_port_traffic": False,
        },
    },
    {
        "id": "contrib-flex25",
        "name": "Flex25",
        "model": "USW Flex 2.5G 8 PoE",
        "ports": flex25,
        "api_capabilities": {
            "port_detail": True,
            "per_port_traffic": False,
        },
    },
    {
        "id": "contrib-flex",
        "name": "Flex",
        "model": "USW Flex",
        "ports": flex,
        "api_capabilities": {
            "port_detail": True,
            "per_port_traffic": False,
        },
    },
]

json.dump(
    {
        "schema_version": 1,
        "devices": devices,
    },
    open(path, "w"),
)
PYTEST

python3 \
  "$BASE_DIR/unifi_dashboard_cards.py" \
  --snapshot "$contrib_snapshot" \
  --registry "$RUNTIME_REGISTRY" \
  --indent 0 \
  > "$tmp_dir/unifi-community-fixture-a-cards.yaml"

grep -q \
  'switch_model: USW-24-PoE' \
  "$tmp_dir/unifi-community-fixture-a-cards.yaml"

grep -q \
  'switch_model: USW-16-PoE' \
  "$tmp_dir/unifi-community-fixture-a-cards.yaml"

grep -q \
  'switch_model: USW-Lite-8-PoE' \
  "$tmp_dir/unifi-community-fixture-a-cards.yaml"

grep -q \
  'switch_model: USW Flex 2.5G 8 PoE' \
  "$tmp_dir/unifi-community-fixture-a-cards.yaml"

grep -q \
  'switch_model: USW Flex' \
  "$tmp_dir/unifi-community-fixture-a-cards.yaml"

grep -q \
  'port_count: 24' \
  "$tmp_dir/unifi-community-fixture-a-cards.yaml"

grep -q \
  'port_count: 16' \
  "$tmp_dir/unifi-community-fixture-a-cards.yaml"

grep -q \
  'port_count: 8' \
  "$tmp_dir/unifi-community-fixture-a-cards.yaml"

grep -q \
  'port_count: 9' \
  "$tmp_dir/unifi-community-fixture-a-cards.yaml"

grep -q \
  'port_count: 5' \
  "$tmp_dir/unifi-community-fixture-a-cards.yaml"

grep -q \
  'sfp_port_count: 2' \
  "$tmp_dir/unifi-community-fixture-a-cards.yaml"

grep -q \
  'sfp_port_count: 1' \
  "$tmp_dir/unifi-community-fixture-a-cards.yaml"

grep -q \
  'unifi_per_port_traffic: false' \
  "$tmp_dir/unifi-community-fixture-a-cards.yaml"

! grep -q \
  'no exact Switch Vision registry entry' \
  "$tmp_dir/unifi-community-fixture-a-cards.yaml"

echo \
  "Switch Vision UniFi contribution community-validation regression: PASS"

privacy_root="$tmp_dir/privacy"
mkdir -p "$privacy_root/unifi"
cat > "$privacy_root/unifi/devices.json" <<'JSON'
{"devices":[{"id":"device-uuid-123","name":"Private Core","model":"USW Pro 24 PoE","ports":[]}]}
JSON
cat > "$privacy_root/unifi/diagnostics.json" <<'JSON'
{
  "schema_version": 1,
  "product": "Switch Vision UniFi2MQTT",
  "version": "2.0.43",
  "status": "success",
  "stage": "complete",
  "adopted_devices": 3,
  "switching_devices": 2,
  "rejected_devices": 1,
  "empty_switch_polls": 0,
  "device_classification": [
    {
      "model": "USW 24 Pro",
      "features": ["switching"],
      "accepted": true,
      "reason": "unifi_switch_model"
    }
  ],
  "api_key": "DO_NOT_KEEP_API_KEY",
  "device_name": "Private Diagnostic Switch",
  "controller_url": "https://192.168.50.1"
}
JSON
cat > "$privacy_root/generated-dashboard-card.yaml" <<'YAML'
views:
  - title: Switch Vision
    cards:
      - type: custom:switch-vision-3650
        title: Private Core
        member: unifi_deviceuuid123
        selected_switch: unifi_deviceuuid123
        switch_model: USW Pro 24 PoE
        data_source: unifi_api
        unifi_device_id: device-uuid-123
      # UniFi "Private Garage" (USW Lite 16 PoE) detected; waiting for visuals.
YAML
python3 "$BASE_DIR/sanitize_support_bundle.py" "$privacy_root" "$privacy_root/report.json" --mask-hostnames true >/dev/null
jq -e '(.devices[0].id | startswith("masked-device-")) and (.devices[0].name == "masked-switch") and (.devices[0].model == "USW Pro 24 PoE")' "$privacy_root/unifi/devices.json" >/dev/null
jq -e '
  (.version == "2.0.43")
  and (.status == "success")
  and (.stage == "complete")
  and (.adopted_devices == 3)
  and (.switching_devices == 2)
  and (.rejected_devices == 1)
  and (.device_classification[0].model == "USW 24 Pro")
  and (.device_classification[0].accepted == true)
  and (has("api_key") | not)
  and (has("device_name") | not)
  and (has("controller_url") | not)
' "$privacy_root/unifi/diagnostics.json" >/dev/null
! grep -q 'DO_NOT_KEEP_API_KEY\|Private Diagnostic Switch\|192.168.50.1' "$privacy_root/unifi/diagnostics.json"
grep -q '^        title: masked-switch$' "$privacy_root/generated-dashboard-card.yaml"
grep -q '^        unifi_device_id: masked-device-' "$privacy_root/generated-dashboard-card.yaml"
grep -q '^        member: unifi_masked_' "$privacy_root/generated-dashboard-card.yaml"
grep -q '^        selected_switch: unifi_masked_' "$privacy_root/generated-dashboard-card.yaml"
grep -q '# UniFi "masked-switch" (USW Lite 16 PoE)' "$privacy_root/generated-dashboard-card.yaml"
! grep -q 'Private Core\|Private Garage\|device-uuid-123\|unifi_deviceuuid123' "$privacy_root/generated-dashboard-card.yaml"
jq -e '(.sanitization_version >= 12) and (.residual_audit.unifi_device_ids_remaining == 0) and (.residual_audit.unifi_device_names_remaining == 0) and (.residual_audit.unifi_dashboard_ids_remaining == 0) and (.residual_audit.unifi_dashboard_names_remaining == 0) and (.enabled_category_leaks_found == false)' "$privacy_root/report.json" >/dev/null

privacy_hard_root="$tmp_dir/privacy-hardening"
mkdir -p "$privacy_hard_root"
cat > "$privacy_hard_root/leaks.txt" <<'TEXT'
snmp_community: privateCommunity
mqtt_password=superSecret
endpoint: mqtt://user:pass@example.invalid
command: snmpwalk -On -v2c -c walkSecret 192.0.2.10 1.3.6.1.2.1.1
Authorization: Bearer bearerSecret
serial: FOC1234ABCD
.1.3.6.1.2.1.47.1.1.1.1.11.1001 = STRING: "JN1234567890"
.1.3.6.1.2.1.47.1.2.1.1.4.1 = STRING: "entityCommunity"
.1.3.6.1.2.1.47.1.2.1.1.4.2 = STRING: "entityCommunity@10"
ENTITY-MIB::entLogicalCommunity.3 = STRING: "symbolicCommunity@30"
loose_mac: 0:1:2:3:4:5
local_mac: 02:11:22:33:44:55
cisco_mac: aabb.ccdd.eeff
TEXT
cat > "$privacy_hard_root/discovery-targets.csv" <<'CSV'
switch name,switch host,sensor prefix,switch snmp community,output_dir,display name
SW1,192.0.2.10,sw1,csvPrivate,/share/switch_vision/snmpwalks/SW1,Private Switch
CSV
python3 "$BASE_DIR/sanitize_support_bundle.py" "$privacy_hard_root" "$privacy_hard_root/report.json" >/dev/null
! grep -q 'privateCommunity\|superSecret\|user:pass\|walkSecret\|bearerSecret\|FOC1234ABCD\|JN1234567890\|entityCommunity\|symbolicCommunity\|0:1:2:3:4:5\|02:11:22:33:44:55\|aabb.ccdd.eeff\|csvPrivate' "$privacy_hard_root/leaks.txt" "$privacy_hard_root/discovery-targets.csv"
grep -q 'masked-serial-' "$privacy_hard_root/leaks.txt"
grep -q 'masked-mac-' "$privacy_hard_root/leaks.txt"
python3 - "$privacy_hard_root/discovery-targets.csv" "$privacy_hard_root/report.json" <<'PYTEST'
import csv
import json
import sys

with open(sys.argv[1], newline="", encoding="utf-8") as handle:
    rows = list(csv.reader(handle))
assert rows[1][3] == "<REDACTED>", rows

with open(sys.argv[2], encoding="utf-8") as handle:
    report = json.load(handle)
assert report["sanitization_version"] >= 13, report
assert report["serial_numbers_always_masked"] is True, report
assert report["audit_categories"]["credentials"] == {"enforced": True, "remaining": 0}, report
assert report["audit_categories"]["serial_numbers"] == {"enforced": True, "remaining": 0}, report
assert report["audit_categories"]["mac_addresses"]["remaining"] == 0, report
assert report["enabled_category_leaks_found"] is False, report
assert report["counts"]["csv_community_values_removed"] >= 1, report
assert report["counts"]["entity_logical_communities_removed"] >= 3, report
assert report["counts"]["serial_numbers_masked"] >= 2, report
assert report["counts"]["mac_addresses_masked"] >= 3, report
PYTEST

printf '%s\n' "Switch Vision privacy hardening regression: PASS"

python3 - "$BASE_DIR" <<'PYTEST'
import sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import support_web

with tempfile.TemporaryDirectory() as tmp:
    generated = Path(tmp) / "generated-snmp2mqtt.yaml"
    generated.write_text("""targets:\n- host: 192.0.2.10\n  name: SW1\n  sensors:\n  - oid: 1.3.6.1.2.1.1.3.0\n    name: SW1 Uptime\n  - oid: 1.3.6.1.2.1.2.2.1.8.1\n    name: SW1 Port 1 Status\n    binary_sensor: true\n  - oid: 1.3.6.1.2.1.2.2.1.10.1\n    name: ignored-name\n    object_id: sw1_port_1_rx_bytes\n""", encoding="utf-8")
    topics = support_web._snmp2mqtt_discovery_topics(generated, "homeassistant")
    assert topics == [
        "homeassistant/binary_sensor/snmp2mqtt/sw1_port_1_status/config",
        "homeassistant/sensor/snmp2mqtt/sw1_port_1_rx_bytes/config",
        "homeassistant/sensor/snmp2mqtt/sw1_uptime/config",
    ], topics
    assert support_web._snmp2mqtt_slug("SW1 SFP 10G 1 RX Bytes") == "sw1_sfp_10g_1_rx_bytes"

print("Switch Vision SNMP2MQTT retirement topic self-test: PASS")
PYTEST


python3 - "$BASE_DIR" <<'PYTEST'
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, sys.argv[1])
import support_web

def validate(text):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "generated-snmp2mqtt.yaml"
        path.write_text(text, encoding="utf-8")
        return support_web._validate_snmp2mqtt_yaml(path)

valid_juniper = """targets:
- host: 192.0.2.10
  sensors:
  - name: SW10 Port 0 VLAN Mode
    source: juniper_ex_vlan
    interface: ge-0/0/0
    attribute: mode
"""
assert validate(valid_juniper)["valid"] is True

valid_juniper_candidates = """targets:
- host: 192.0.2.10
  sensors:
  - name: SW10 SFP 10G 1 VLAN Mode
    source: juniper_ex_vlan
    interfaces:
      - xe-0/1/0
      - ge-0/1/0
    attribute: mode
"""
assert validate(valid_juniper_candidates)["valid"] is True

valid_live_interface = """targets:
- host: 192.0.2.10
  sensors:
  - name: SW10 SFP 10G 1 Status
    source: interface
    interfaces:
      - xe-0/1/0
      - ge-0/1/0
    attribute: oper_status
"""
assert validate(valid_live_interface)["valid"] is True

for attribute in ("oper_status", "admin_status", "speed_mbps", "rx_bytes", "tx_bytes", "alias"):
    result = validate(f"""targets:
- host: 192.0.2.10
  sensors:
  - name: SW10 live interface helper
    source: interface
    interfaces:
      - xe-0/1/0
      - ge-0/1/0
    attribute: {attribute}
""")
    assert result["valid"] is True, (attribute, result)

for attribute in ("mode", "native_vlan", "vlans", "tagged_vlans", "untagged_vlans", "summary"):
    result = validate(f"""targets:
- host: 192.0.2.10
  sensors:
  - name: SW10 VLAN helper
    source: juniper_ex_vlan
    interface: ge-0/0/0
    attribute: {attribute}
""")
    assert result["valid"] is True, (attribute, result)

normal_missing_oid = """targets:
- host: 192.0.2.10
  sensors:
  - name: Broken normal sensor
"""
result = validate(normal_missing_oid)
assert result["valid"] is False and "has no OID" in result["error"], result

missing_interface = """targets:
- host: 192.0.2.10
  sensors:
  - name: Broken Juniper helper
    source: juniper_ex_vlan
    attribute: mode
"""
result = validate(missing_interface)
assert result["valid"] is False and "has no interface" in result["error"], result

missing_attribute = """targets:
- host: 192.0.2.10
  sensors:
  - name: Broken Juniper helper
    source: juniper_ex_vlan
    interface: ge-0/0/0
"""
result = validate(missing_attribute)
assert result["valid"] is False and "has no attribute" in result["error"], result

unsupported_attribute = """targets:
- host: 192.0.2.10
  sensors:
  - name: Broken Juniper helper
    source: juniper_ex_vlan
    interface: ge-0/0/0
    attribute: definitely_not_supported
"""
result = validate(unsupported_attribute)
assert result["valid"] is False and "unsupported attribute" in result["error"], result

unknown_source = """targets:
- host: 192.0.2.10
  sensors:
  - name: Broken derived sensor
    source: mystery_source
    interface: ge-0/0/0
    attribute: mode
"""
result = validate(unknown_source)
assert result["valid"] is False and "unsupported OID-less source" in result["error"], result

print("Switch Vision source-aware generated-YAML validation self-test: PASS")
PYTEST

printf '%s\n' "Switch Vision vendor/interface/privacy self-test: PASS"

# Hub UniFi visibility/status UX regression checks.
grep -q 'id="openUnifi2mqttSettingsButton"' "$BASE_DIR/support_web.py"
grep -q 'unifi-unavailable' "$BASE_DIR/support_web.py"
grep -q 'UniFi2MQTT is not installed. Install it from Switch Vision Installer first.' "$BASE_DIR/support_web.py"
grep -q 'UniFi2MQTT is installed but not configured. Open settings to complete setup.' "$BASE_DIR/support_web.py"
grep -q 'show_unifi_integration' "$BASE_DIR/support_web.py"
grep -q "openResolvedApp('discovery')" "$BASE_DIR/support_web.py"
! grep -q '/config/app/local_switch_vision_discovery/config' "$BASE_DIR/support_web.py"
! grep -q 'Install/copy the bundled local app' "$BASE_DIR/support_web.py"
grep -q '_configured_switch_count' "$BASE_DIR/support_web.py"


# Blank/default switch-row regression.
# A fresh Home Assistant install contains one visual placeholder row, but that
# row must not count as a configured SNMP target. Empty fields must also remain
# in their original positions when switch rows are decoded.
sh -n "$BASE_DIR/discovery_job.sh"
grep -q 'SWITCH_VISION_DISCOVERY_VERSION="2.3.25"' "$BASE_DIR/discovery_job.sh"
grep -q 'SWITCH_VISION_DISCOVERY_VERSION="2.3.25"' "$BASE_DIR/run.sh"

# v2.1.24 Cisco trunk-status diagnostic contract.
# The early diagnostic must match the parser: only an indexed Cisco
# vlanTrunkPortDynamicStatus row with an INTEGER value counts as present.
grep -Fq '14\.[0-9]+ = INTEGER:' "$BASE_DIR/discovery_job.sh"

trunk_bad_unindexed="$tmp_dir/trunk-bad-unindexed.txt"
trunk_bad_type="$tmp_dir/trunk-bad-type.txt"
trunk_good_numeric="$tmp_dir/trunk-good-numeric.txt"
trunk_good_iso="$tmp_dir/trunk-good-iso.txt"

printf '%s\n'   '1.3.6.1.4.1.9.9.46.1.6.1.1.14 = INTEGER: 1'   > "$trunk_bad_unindexed"

printf '%s\n'   '1.3.6.1.4.1.9.9.46.1.6.1.1.14.101 = STRING: "1"'   > "$trunk_bad_type"

printf '%s\n'   '1.3.6.1.4.1.9.9.46.1.6.1.1.14.101 = INTEGER: 1'   > "$trunk_good_numeric"

printf '%s\n'   'iso.3.6.1.4.1.9.9.46.1.6.1.1.14.102 = INTEGER: 2'   > "$trunk_good_iso"

trunk_status_present() {
  awk '/\.3\.6\.1\.4\.1\.9\.9\.46\.1\.6\.1\.1\.14\.[0-9]+ = INTEGER:/ { found=1 } END { exit(found ? 0 : 1) }' "$1"
}

! trunk_status_present "$trunk_bad_unindexed"
! trunk_status_present "$trunk_bad_type"
trunk_status_present "$trunk_good_numeric"
trunk_status_present "$trunk_good_iso"

echo "Switch Vision Discovery v2.1.24 Cisco trunk-status diagnostic regression: PASS"

blank_switch_cfg="$tmp_dir/blank-switch-row.json"
real_switch_cfg="$tmp_dir/real-switch-row.json"

printf "%s\n" \
'{"switches":[{"switch_name":"","switch_host":"","sensor_prefix":"","snmp_community":"readonly","walk_mode":"targeted","switch_model":"auto"}]}' \
> "$blank_switch_cfg"

printf "%s\n" \
'{"switches":[{"switch_name":"SW10","switch_host":"192.168.1.108","sensor_prefix":"sw10","snmp_community":"readonly","walk_mode":"targeted","switch_model":"EX3300-48P"}]}' \
> "$real_switch_cfg"

if jq -e '
  (.switches // .multi_switch_walks // []) as $rows |
  ($rows | type == "array") and
  any($rows[]?;
    ((.switch_name // .switch // .selected_switch // .name // "")
     | tostring | length) > 0
  )
' "$blank_switch_cfg" >/dev/null; then
  echo "ERROR: blank starter switch row counted as configured" >&2
  exit 1
fi

jq -e '
  (.switches // .multi_switch_walks // []) as $rows |
  ($rows | type == "array") and
  any($rows[]?;
    ((.switch_name // .switch // .selected_switch // .name // "")
     | tostring | length) > 0
  )
' "$real_switch_cfg" >/dev/null

sv_row_separator="$(printf "\\034")"

blank_parsed=$(
  jq -r '
    (.switches // .multi_switch_walks // [])[]? | [
      (.switch_name // .switch // .selected_switch // .name // ""),
      (.switch_host // .host // .manual_switch_host // ""),
      (.switch_name // .switch // .selected_switch // .name // ""),
      (.sensor_prefix // .entity_prefix // .prefix // ""),
      (.snmp_community // .community // ""),
      (.walk_mode // .mode // "targeted"),
      (.output_dir // ""),
      (.display_name // .card_title // ""),
      (.switch_model // .model_override // "auto")
    ] | map(tostring) | join("\u001c")
  ' "$blank_switch_cfg" |
  while IFS="$sv_row_separator" read -r sw host label prefix community mode out display model; do
    printf "%s|%s|%s|%s|%s|%s" \
      "$sw" "$host" "$prefix" "$community" "$mode" "$model"
  done
)

[ "$blank_parsed" = "|||readonly|targeted|auto" ]

real_parsed=$(
  jq -r '
    (.switches // .multi_switch_walks // [])[]? | [
      (.switch_name // .switch // .selected_switch // .name // ""),
      (.switch_host // .host // .manual_switch_host // ""),
      (.switch_name // .switch // .selected_switch // .name // ""),
      (.sensor_prefix // .entity_prefix // .prefix // ""),
      (.snmp_community // .community // ""),
      (.walk_mode // .mode // "targeted"),
      (.output_dir // ""),
      (.display_name // .card_title // ""),
      (.switch_model // .model_override // "auto")
    ] | map(tostring) | join("\u001c")
  ' "$real_switch_cfg" |
  while IFS="$sv_row_separator" read -r sw host label prefix community mode out display model; do
    printf "%s|%s|%s|%s|%s|%s" \
      "$sw" "$host" "$prefix" "$community" "$mode" "$model"
  done
)

[ "$real_parsed" = "SW10|192.168.1.108|sw10|readonly|targeted|EX3300-48P" ]

printf "%s\n" "Switch Vision blank switch-row regression: PASS"


# Persistent switch enable/disable regression.
# Missing enabled defaults to true; explicit false rows must be excluded from
# walking/generation and from historical parse_all_walks source selection.
enabled_switch_cfg="$tmp_dir/enabled-switch-row.json"
disabled_switch_cfg="$tmp_dir/disabled-switch-row.json"
legacy_switch_cfg="$tmp_dir/legacy-switch-row.json"

printf "%s\n" \
'{"switches":[{"switch_name":"SW10","switch_host":"192.168.1.108","sensor_prefix":"sw10","snmp_community":"readonly","enabled":"enabled","walk_mode":"targeted","switch_model":"EX3300-48P"}]}' \
> "$enabled_switch_cfg"
printf "%s\n" \
'{"switches":[{"switch_name":"SW10","switch_host":"192.168.1.108","sensor_prefix":"sw10","snmp_community":"readonly","enabled":"disabled","walk_mode":"targeted","switch_model":"EX3300-48P"}]}' \
> "$disabled_switch_cfg"
printf "%s\n" \
'{"switches":[{"switch_name":"SW10","switch_host":"192.168.1.108","sensor_prefix":"sw10","snmp_community":"readonly","walk_mode":"targeted","switch_model":"EX3300-48P"}]}' \
> "$legacy_switch_cfg"

enabled_jq='def enabled($sw): (($sw.enabled // "enabled") as $value | if ($value | type) == "boolean" then $value elif ($value | type) == "string" then (($value | ascii_downcase) as $state | ($state != "false" and $state != "disabled" and $state != "disable" and $state != "off" and $state != "no" and $state != "0")) else true end); (.switches // .multi_switch_walks // [])[]? | select(enabled(.)) | (.switch_name // "")'
[ "$(jq -r "$enabled_jq" "$enabled_switch_cfg")" = "SW10" ]
[ -z "$(jq -r "$enabled_jq" "$disabled_switch_cfg")" ]
[ "$(jq -r "$enabled_jq" "$legacy_switch_cfg")" = "SW10" ]
grep -q 'row\["enabled"\] = _switch_enabled_state(row.get("enabled", "enabled")' "$BASE_DIR/support_web.py"
grep -q 'select(enabled(.))' "$BASE_DIR/discovery_job.sh"
grep -q 'json_has_configured_switch_rows()' "$BASE_DIR/discovery_job.sh"
grep -q 'json_has_enabled_switch_rows()' "$BASE_DIR/discovery_job.sh"
grep -q 'legacy_single_walk_allowed()' "$BASE_DIR/discovery_job.sh"
grep -q 'scanning enabled switch folders only' "$BASE_DIR/discovery_job.sh"
grep -q 'json_has_configured_switch_rows &&' "$BASE_DIR/discovery_job.sh"
grep -q 'python3 /migrate_options.py' "$BASE_DIR/run.sh"
grep -q '/addons/self/options' "$BASE_DIR/migrate_options.py"
! grep -q 'options.before-import' "$BASE_DIR/support_web.py"

# Configuration export v2 is intentionally not accepted by v2.1.7, preventing
# a downgrade from silently ignoring disabled rows. v2.1.8 still imports v1.
python3 - "$BASE_DIR/support_web.py" "$tmp_dir" <<'PY_CONFIG_FORMAT'
import importlib.util
import json
import sys
from pathlib import Path

module_path = Path(sys.argv[1])
tmp = Path(sys.argv[2])
sys.path.insert(0, str(module_path.parent))
spec = importlib.util.spec_from_file_location("sv_support_web_test", module_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

options = tmp / "export-options.json"
options.write_text(json.dumps({
    "switches": [{
        "switch_name": "SW10",
        "switch_host": "192.0.2.10",
        "sensor_prefix": "sw10",
        "snmp_community": "readonly",
        "walk_mode": "targeted",
        "switch_model": "auto",
    }]
}), encoding="utf-8")
module._self_addon_options = lambda: json.loads(options.read_text(encoding="utf-8"))
exported = module._discovery_export(options, "2.1.14")
assert exported["format"] == "switch-vision-discovery-config-v2", exported
assert exported["configuration"]["switches"][0]["enabled"] == "enabled", exported

v1 = {
    "format": "switch-vision-discovery-config-v1",
    "configuration": exported["configuration"],
}
v1["configuration"]["switches"][0].pop("enabled", None)
validated_v1 = module._validate_discovery_import(v1)
assert validated_v1["switches"][0]["enabled"] == "enabled", validated_v1

v2 = {
    "format": "switch-vision-discovery-config-v2",
    "configuration": validated_v1,
}
v2["configuration"]["switches"][0]["enabled"] = "disabled"
validated_v2 = module._validate_discovery_import(v2)
assert validated_v2["switches"][0]["enabled"] == "disabled", validated_v2

try:
    module._validate_discovery_import({"format": "switch-vision-discovery-config-v3", "configuration": {}})
except ValueError:
    pass
else:
    raise AssertionError("unknown future export format must be rejected")
PY_CONFIG_FORMAT

printf "%s\n" "Switch Vision persistent switch enable/disable regression: PASS"


# Hub quick enable/disable controls must use Supervisor as the authoritative
# configuration source, preserve unrelated settings/secrets, and never expose
# the SNMP community to the browser-safe device snapshot.
python3 - "$BASE_DIR/support_web.py" "$tmp_dir" <<'PY_HUB_DEVICE_TOGGLE'
import copy
import importlib.util
import json
import sys
from pathlib import Path

module_path = Path(sys.argv[1])
tmp = Path(sys.argv[2])
sys.path.insert(0, str(module_path.parent))
spec = importlib.util.spec_from_file_location("sv_support_web_hub_toggle_test", module_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

stored = {
    "enable_switch_list": "true",
    "support_mask_management_ips": "true",
    "switches": [
        {
            "switch_name": "SW10",
            "display_name": "Juniper EX3300 48P",
            "switch_host": "192.0.2.10",
            "sensor_prefix": "sw10",
            "snmp_community": "do-not-expose",
            "enabled": "enabled",
            "walk_mode": "targeted",
            "switch_model": "EX3300-48P",
        },
        {
            "switch_name": "",
            "switch_host": "",
            "sensor_prefix": "",
            "snmp_community": "readonly",
            "enabled": "enabled",
            "walk_mode": "targeted",
            "switch_model": "auto",
        },
    ],
}
posts = []
backup_calls = []

def fake_supervisor(path, *, method="GET", timeout=12.0, payload=None):
    if path == "/addons/self/info" and method == "GET":
        return {"data": {"options": copy.deepcopy(stored)}}
    if path == "/addons/self/options" and method == "POST":
        assert backup_calls, "pre-mutation backup must run before the Supervisor options POST"
        assert isinstance(payload, dict) and isinstance(payload.get("options"), dict), payload
        posts.append(copy.deepcopy(payload))
        stored.clear()
        stored.update(copy.deepcopy(payload["options"]))
        return {"result": "ok", "data": {}}
    raise AssertionError((path, method, payload))

real_create_backup = module.create_pre_mutation_backup
def create_test_backup(options, *, reason):
    backup_calls.append(reason)
    return real_create_backup(
        options,
        reason=reason,
        directory=tmp / "discovery-backups",
    )

module.create_pre_mutation_backup = create_test_backup
module._supervisor_json = fake_supervisor
fallback = tmp / "hub-toggle-options.json"
fallback.write_text("{}", encoding="utf-8")

snapshot = module._configured_devices_snapshot(fallback)
assert snapshot["writable"] is True, snapshot
assert snapshot["count"] == 1, snapshot
assert snapshot["devices"][0]["enabled"] == "enabled", snapshot
assert snapshot["devices"][0]["display_name"] == "Juniper EX3300 48P", snapshot
assert "snmp_community" not in snapshot["devices"][0], snapshot

updated = module._set_configured_device_state(fallback, {
    "index": 0,
    "switch_name": "SW10",
    "enabled": "disabled",
})
assert posts, "Supervisor options endpoint was not called"
assert stored["switches"][0]["enabled"] == "disabled", stored
assert stored["switches"][0]["snmp_community"] == "do-not-expose", stored
assert stored["support_mask_management_ips"] == "true", stored
assert updated["devices"][0]["enabled"] == "disabled", updated

try:
    module._set_configured_device_state(fallback, {"index": 0, "switch_name": "WRONG", "enabled": "enabled"})
except ValueError:
    pass
else:
    raise AssertionError("stale/mismatched switch identity must be rejected")
PY_HUB_DEVICE_TOGGLE

grep -q 'Enable / Disable Devices' "$BASE_DIR/support_web.py"
grep -q '/addons/self/options' "$BASE_DIR/support_web.py"
grep -q '/api/configured-devices/state' "$BASE_DIR/support_web.py"
printf "%s\n" "Switch Vision Hub device-state controls regression: PASS"

# A Discovery run must not trust a stale /data/options.json after a Hub/native
# state change. Capture the authoritative Supervisor options immediately before
# starting the child process and pass that exact snapshot to discovery_job.sh.
python3 - "$BASE_DIR/support_web.py" "$tmp_dir" <<'PY_AUTHORITATIVE_RUN_OPTIONS'
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

module_path = Path(sys.argv[1])
tmp = Path(sys.argv[2])
sys.path.insert(0, str(module_path.parent))
spec = importlib.util.spec_from_file_location("sv_support_web_authoritative_options_test", module_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

authoritative = {
    "enable_switch_list": "true",
    "generate_support_my_switch_bundle": True,
    "switches": [
        {
            "switch_name": "SW_DISABLED",
            "switch_host": "192.0.2.20",
            "sensor_prefix": "sw_disabled",
            "snmp_community": "secret-disabled",
            "enabled": "disabled",
            "walk_mode": "full",
            "switch_model": "auto",
        },
        {
            "switch_name": "SW_ENABLED",
            "switch_host": "192.0.2.21",
            "sensor_prefix": "sw_enabled",
            "snmp_community": "secret-enabled",
            "enabled": "enabled",
            "walk_mode": "targeted",
            "switch_model": "auto",
        },
    ],
}
module._self_addon_options = lambda: authoritative
snapshot = tmp / "authoritative-run-options.json"
result = module._write_authoritative_discovery_options_snapshot(snapshot)
assert result == snapshot
loaded = json.loads(snapshot.read_text(encoding="utf-8"))
expected_snapshot = dict(authoritative)
expected_snapshot["generate_support_my_switch_bundle"] = False
assert loaded == expected_snapshot
assert authoritative["generate_support_my_switch_bundle"] is True
assert stat.S_IMODE(snapshot.stat().st_mode) == 0o600, oct(stat.S_IMODE(snapshot.stat().st_mode))
assert loaded["switches"][0]["enabled"] == "disabled"
assert loaded["switches"][1]["enabled"] == "enabled"
assert loaded["switches"][0]["snmp_community"] == "secret-disabled"
PY_AUTHORITATIVE_RUN_OPTIONS

grep -Fq 'CONFIG_FILE="${SWITCH_VISION_OPTIONS_FILE:-/data/options.json}"' "$BASE_DIR/discovery_job.sh"
grep -Fq '_write_authoritative_discovery_options_snapshot(' "$BASE_DIR/support_web.py"
grep -q 'discovery_env\["SWITCH_VISION_OPTIONS_FILE"\]' "$BASE_DIR/support_web.py"
grep -q 'Discovery configuration: authoritative Supervisor snapshot' "$BASE_DIR/support_web.py"
printf "%s\n" "Switch Vision authoritative run-options regression: PASS"

# Generated dashboard rows must obey the same enabled-state predicate as the
# walk/parser/generator path. Exercise the exact jq program embedded in the
# production dashboard-card writer so a disabled saved switch cannot render a
# stale/offline card, while legacy rows without explicit state remain enabled.
card_rows_jq="$tmp_dir/generated-card-rows.jq"
awk '
  /SWITCH_VISION_GENERATED_CARD_ROWS_JQ_BEGIN/ { capture=1; next }
  /SWITCH_VISION_GENERATED_CARD_ROWS_JQ_END/ { capture=0; next }
  capture { print }
' "$BASE_DIR/discovery_job.sh" > "$card_rows_jq"
[ -s "$card_rows_jq" ] || { echo "ERROR: generated-card jq program was not found" >&2; exit 1; }

card_fixture="$tmp_dir/generated-card-enabled-filter.json"
cat > "$card_fixture" <<'JSON_CARD_ENABLED_FILTER'
{
  "switches": [
    {
      "switch_name": "STACK_ENABLED",
      "switch_host": "192.0.2.31",
      "sensor_prefix": "sw1",
      "display_name": "Enabled Stack",
      "enabled": "enabled"
    },
    {
      "switch_name": "SW_DISABLED",
      "switch_host": "192.0.2.32",
      "sensor_prefix": "sw_disabled",
      "display_name": "Disabled Switch",
      "enabled": "disabled"
    },
    {
      "switch_name": "SW_LEGACY",
      "switch_host": "192.0.2.33",
      "sensor_prefix": "sw_legacy",
      "display_name": "Legacy Enabled"
    }
  ],
  "stack_member_prefixes": [
    {"switch_name": "STACK_ENABLED", "member": "1", "sensor_prefix": "sw1", "display_name": "STACK 1"},
    {"switch_name": "STACK_ENABLED", "member": "2", "sensor_prefix": "sw2", "display_name": "STACK 2"},
    {"switch_name": "SW_DISABLED", "member": "1", "sensor_prefix": "sw_disabled", "display_name": "SHOULD NOT RENDER"}
  ]
}
JSON_CARD_ENABLED_FILTER

card_rows="$tmp_dir/generated-card-enabled-filter.rows"
jq -r -f "$card_rows_jq" "$card_fixture" > "$card_rows"
[ "$(wc -l < "$card_rows" | tr -d ' ')" = "3" ] || {
  echo "ERROR: expected two enabled stack cards plus one legacy card" >&2
  cat "$card_rows" >&2
  exit 1
}
grep -q 'STACK_ENABLED' "$card_rows"
grep -q 'SW_LEGACY' "$card_rows"
! grep -q 'SW_DISABLED' "$card_rows"
! grep -q 'SHOULD NOT RENDER' "$card_rows"
printf "%s\n" "Switch Vision generated-card enabled-state regression: PASS"

# Zyxel XS1930-10 contribution / registry / generator reconciliation regression.
grep -q 'if (model == "XS1930-10") return "experimental"' "$BASE_DIR/discovery_job.sh"
grep -q 'profile = "zyxel-xs1930-10"' "$BASE_DIR/discovery_job.sh"
grep -q 'model == "XS1930-10" && if_total > 0 && rj45 == 8 && ten == 2' "$BASE_DIR/discovery_job.sh"
grep -q 'RJ45 swp00-swp07 ports' "$BASE_DIR/discovery_job.sh"
grep -q '10G SFP+ swp08-swp09 uplinks' "$BASE_DIR/discovery_job.sh"
grep -q '1.3.6.1.4.1.890.1.15.3.2.4.0' "$BASE_DIR/discovery_job.sh"
grep -q '1.3.6.1.4.1.890.1.15.3.2.5.0' "$BASE_DIR/discovery_job.sh"
grep -q 'Q-BRIDGE-MIB PVID' "$BASE_DIR/discovery_job.sh"

awk '
  /^  zyxel-xs1930-10:/ { in_zyxel=1; next }
  in_zyxel && /^  [A-Za-z0-9_-]+:/ { exit }
  in_zyxel && /^    status: experimental$/ { found=1 }
  END { exit(found ? 0 : 1) }
' "$BASE_DIR/profiles/switch-vision-profiles.yaml"

printf '%s\n' "Switch Vision Zyxel XS1930-10 contribution regression self-test: PASS"

# Full-walk correctness / authoritative-status regression.
grep -q 'Running split Juniper full SNMP walk' "$BASE_DIR/discovery_job.sh"
grep -q '1.3.6.1.4.1.2636' "$BASE_DIR/discovery_job.sh"
grep -q '# Switch Vision SNMP walk result: warning' "$BASE_DIR/discovery_job.sh"
grep -q 'registry_status == "confirmed"' "$BASE_DIR/discovery_job.sh"
grep -q '.device.support_status=(.registry.status' "$BASE_DIR/discovery_job.sh"
printf '%s\n' "Switch Vision full-walk/status reconciliation regression: PASS"

# Juniper EX3300 legacy-parser / registry reconciliation regression.
grep -q 'if (model == "Juniper EX3300-48P") return "supported"' "$BASE_DIR/discovery_job.sh"
grep -q 'profile = "juniper-ex3300-48p"' "$BASE_DIR/discovery_job.sh"
grep -q 'model == "Juniper EX3300-48P" && if_total > 0 && rj45 == 48' "$BASE_DIR/discovery_job.sh"
grep -q 'RJ45 ge-0/0/0-47 ports' "$BASE_DIR/discovery_job.sh"
grep -q 'SFP/SFP+ uplink cage' "$BASE_DIR/discovery_job.sh"
grep -q 'Virtual Chassis support: not validated' "$BASE_DIR/discovery_job.sh"

awk '
  /^  juniper-ex3300-48p:/ { in_ex=1; next }
  in_ex && /^  [A-Za-z0-9_-]+:/ { exit }
  in_ex && /^    status: supported$/ { found=1 }
  END { exit(found ? 0 : 1) }
' "$BASE_DIR/profiles/switch-vision-profiles.yaml"

awk '
  /CV_ID_FAMILY="EX3300"/ { in_ex=1 }
  in_ex && /CV_ID_SUPPORT_STATUS="supported"/ { found=1 }
  in_ex && /^[[:space:]]*;;[[:space:]]*$/ { exit }
  END { exit(found ? 0 : 1) }
' "$CV_VENDOR_DIR/known_vendor.sh"

printf '%s\n' "Switch Vision Juniper legacy-parser/registry reconciliation self-test: PASS"

# EX3300 live SFP/SFP+ generation regression.
grep -q 'function yaml_interface_sensor' "$BASE_DIR/discovery_job.sh"
grep -q 'function yaml_juniper_vlan_candidates_sensor' "$BASE_DIR/discovery_job.sh"
grep -q 'primary="xe-0/1/" cage' "$BASE_DIR/discovery_job.sh"
grep -q 'secondary="ge-0/1/" cage' "$BASE_DIR/discovery_job.sh"
grep -q 'label " Status", "oper_status"' "$BASE_DIR/discovery_job.sh"
grep -q 'label " RX Bytes", "rx_bytes"' "$BASE_DIR/discovery_job.sh"
grep -q 'label " TX Bytes", "tx_bytes"' "$BASE_DIR/discovery_job.sh"
grep -q 'label " Admin Status", "admin_status"' "$BASE_DIR/discovery_job.sh"
grep -q 'label " Speed Mbps", "speed_mbps"' "$BASE_DIR/discovery_job.sh"
grep -q 'label " Alias", "alias"' "$BASE_DIR/discovery_job.sh"
grep -q 'sensor_source in {"juniper_ex_vlan", "interface"}' "$BASE_DIR/support_web.py"
printf '%s\n' "Switch Vision EX3300 live-interface generation regression: PASS"

# v2.1.18 placeholder and UniFi diagnostics regressions.
python3 - "$BASE_DIR" <<'PYTEST_V217'
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

base = Path(sys.argv[1])
sys.path.insert(0, str(base))

spec = importlib.util.spec_from_file_location(
    "switch_vision_support_web_v217",
    base / "support_web.py",
)
assert spec and spec.loader
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)

placeholder = {
    "switch_name": "",
    "switch_host": "",
    "sensor_prefix": "stale_placeholder",
    "snmp_community": "readonly",
    "enabled": "enabled",
    "walk_mode": "targeted",
    "switch_model": "auto",
}

validated = web._validate_switch_row(
    placeholder,
    1,
)

assert validated["switch_name"] == ""
assert validated["switch_host"] == ""
assert validated["sensor_prefix"] == ""

web._validate_inventory_identities(
    {
        "switches": [
            placeholder,
        ],
        "stack_member_prefixes": [],
    }
)

assert web._configured_switch_count(
    [placeholder]
) == 0

bad = dict(placeholder)
bad["switch_host"] = "192.0.2.55"

try:
    web._validate_inventory_identities(
        {
            "switches": [bad],
            "stack_member_prefixes": [],
        }
    )
except ValueError:
    pass
else:
    raise AssertionError(
        "real incomplete switch row was accepted"
    )

with tempfile.TemporaryDirectory() as td:
    path = Path(td) / "diagnostics.json"

    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "product":
                    "Switch Vision UniFi2MQTT",
                "version": "2.0.43",
                "status": "error",
                "stage": "list_devices",
                "adopted_devices": 0,
                "switching_devices": 0,
                "rejected_devices": 0,
                "empty_switch_polls": 0,
                "error_type": "RuntimeError",
                "device_classification": [],
                "api_key": "must-not-surface",
            }
        ),
        encoding="utf-8",
    )

    old_path = web.DEFAULT_UNIFI_DIAGNOSTICS

    try:
        web.DEFAULT_UNIFI_DIAGNOSTICS = path

        status = (
            web._unifi2mqtt_diagnostics_status()
        )

        assert status["found"] is True
        assert status["valid"] is True
        assert status["version"] == "2.0.43"
        assert status["status"] == "error"
        assert status["stage"] == "list_devices"
        assert (
            status["error_type"]
            == "RuntimeError"
        )
        assert "api_key" not in status
    finally:
        web.DEFAULT_UNIFI_DIAGNOSTICS = (
            old_path
        )

print(
    "Switch Vision Discovery v2.1.20 "
    "UniFi diagnostics regressions: PASS"
)
PYTEST_V217

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
assert store["switches"][0]["enabled"] == "enabled"
assert store["switches"][0]["snmp_community"] == "keep-secret"
assert store["unrelated_secret"] == "also-keep-secret"

posts.clear()
assert migration.main() == 0
assert not posts, "no-op migration unexpectedly rewrote Supervisor options"
print("Switch Vision Discovery v2.1.14 Supervisor migration: PASS")
PY_MIGRATION

# v2.1.19 community-validation UniFi profile regression.
v219_community_snapshot="$tmp_dir/unifi-community-fixture-b.json"
python3 - "$v219_community_snapshot" <<'PYTEST_V219_COMMUNITY'
import json, sys
path = sys.argv[1]

def port(idx, connector="RJ45", max_speed=1000, poe=False, standard=None):
    return {
        "idx": idx,
        "state": "UP",
        "connector": connector,
        "speed_mbps": max_speed,
        "max_speed_mbps": max_speed,
        "poe": {
            "available": bool(poe),
            "enabled": bool(poe),
            "state": "UP" if poe else "DOWN",
            "standard": standard,
        },
    }

mini = [port(i) for i in range(1, 6)]
pro24 = [port(i) for i in range(1, 25)] + [
    port(25, "SFPPLUS", 10000), port(26, "SFPPLUS", 10000)
]
us8 = [
    port(i, poe=(5 <= i <= 8), standard="802.3af" if 5 <= i <= 8 else None)
    for i in range(1, 9)
]
us8[6]["poe"]["state"] = "DOWN"
udm = [port(i, poe=True, standard="802.3at") for i in range(1, 9)]
udm += [port(9, "RJ45", 2500), port(10, "SFPPLUS", 10000), port(11, "SFPPLUS", 10000)]
usw24 = [
    port(i, poe=(i <= 16), standard="802.3at" if i <= 16 else None)
    for i in range(1, 25)
] + [port(25, "SFP", 1000), port(26, "SFP", 1000)]

devices = []
for n in range(1, 4):
    devices.append({
        "id": f"sv57-mini-{n}",
        "name": f"Flex Mini {n}",
        "model": "USW Flex Mini",
        "ports": mini,
        "api_capabilities": {"port_detail": True, "per_port_traffic": False},
    })
devices += [
    {"id":"sv57-pro24","name":"Pro24","model":"USW Pro 24","ports":pro24,
     "api_capabilities":{"port_detail":True,"per_port_traffic":False}},
    {"id":"sv57-us8","name":"US8","model":"US 8 60W","ports":us8,
     "api_capabilities":{"port_detail":True,"per_port_traffic":False}},
    {"id":"sv57-udm","name":"UDM SE","model":"UniFi Dream Machine PRO SE","ports":udm,
     "api_capabilities":{"port_detail":True,"per_port_traffic":False}},
    {"id":"sv57-usw24","name":"USW24","model":"USW-24-PoE","ports":usw24,
     "api_capabilities":{"port_detail":True,"per_port_traffic":False}},
]
json.dump({"schema_version":1,"devices":devices}, open(path,"w"))
PYTEST_V219_COMMUNITY

python3 "$BASE_DIR/unifi_dashboard_cards.py" \
  --snapshot "$v219_community_snapshot" \
  --registry "$RUNTIME_REGISTRY" \
  --indent 0 \
  > "$tmp_dir/unifi-community-fixture-b-cards.yaml"

for model in "USW Flex Mini" "USW Pro 24" "US 8 60W" "UniFi Dream Machine PRO SE" "USW-24-PoE"; do
  grep -q "switch_model: $model" "$tmp_dir/unifi-community-fixture-b-cards.yaml"
done

[ "$(grep -c 'switch_model: USW Flex Mini' "$tmp_dir/unifi-community-fixture-b-cards.yaml")" -eq 3 ]

python3 - "$RUNTIME_REGISTRY" "$BASE_DIR/profiles/switch-vision-profiles.yaml" <<'PYTEST_V219_REGISTRY'
import json, sys
from pathlib import Path
import yaml
reg=json.loads(Path(sys.argv[1]).read_text())
prof=yaml.safe_load(Path(sys.argv[2]).read_text())
profiles=prof.get("profiles", prof)
devices={d["model"]:d for d in reg["devices"]}

assert devices["USW-24-PoE"]["ports"]["gigabit_sfp"] == 2
assert devices["USW-24-PoE"]["ports"]["ten_gigabit_sfp_plus"] == 0
assert devices["USW Pro 24"]["ports"]["gigabit_sfp"] == 0
assert devices["USW Pro 24"]["ports"]["ten_gigabit_sfp_plus"] == 2
assert devices["US 8 60W"]["validation"]["poe"] == "live_api_confirmed_ports_5_8_802_3af"
assert devices["UniFi Dream Machine PRO SE"]["validation"]["poe"] == "live_api_confirmed_ports_1_8"
assert devices["USW Flex Mini"]["validation"]["exact_model_detection"] == "live_api_confirmed_three_devices"
assert profiles["ubiquiti-usw-pro-24-api"]["layout"]["sfp_10g_ports"] == 2
assert profiles["ubiquiti-usw-24-poe-api"]["layout"]["sfp_1g_ports"] == 2
print("Switch Vision Discovery v2.1.19 community-validation profile regression: PASS")
PYTEST_V219_REGISTRY

# v2.1.20 Dell EMC Networking N2128PX-ON contribution regression.
dell_walk="$tmp_dir/dell-n2128px-on.txt"
cat > "$dell_walk" <<'EOF_DELL_N2128PX'
.1.3.6.1.2.1.1.1.0 = STRING: Dell EMC Networking N2128PX-ON, 6.7.1.27, Linux 4.14.174, v1.0.9
.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.674.10895.3077
.1.3.6.1.2.1.31.1.1.1.1.1 = STRING: Gi1/0/1
.1.3.6.1.2.1.31.1.1.1.1.28 = STRING: Gi1/0/28
.1.3.6.1.2.1.31.1.1.1.1.29 = STRING: Te1/0/1
.1.3.6.1.2.1.31.1.1.1.1.30 = STRING: Te1/0/2
.1.3.6.1.2.1.31.1.1.1.1.54 = STRING: Gi2/0/1
.1.3.6.1.2.1.31.1.1.1.1.81 = STRING: Gi2/0/28
.1.3.6.1.2.1.31.1.1.1.1.82 = STRING: Te2/0/1
.1.3.6.1.2.1.31.1.1.1.1.83 = STRING: Te2/0/2
EOF_DELL_N2128PX

(
  . "$BASE_DIR/opt/switch-vision/vendors/interface.sh"
  cv_cap_set_front_panel_profile "$dell_walk"
  [ "$CV_CAP_MODEL_TEXT" = "N2128PX-ON" ]
  [ "$CV_CAP_PLATFORM" = "dell_n2128px_on" ]
  [ "$CV_CAP_RJ45_LIMIT" = "28" ]
  [ "$(cv_interface_class_for_name Gi1/0/1)" = "rj45" ]
  [ "$(cv_interface_class_for_name Gi2/0/28)" = "rj45" ]
  [ "$(cv_interface_class_for_name Te1/0/1)" = "sfp_plus" ]
  [ "$(cv_interface_class_for_name Te2/0/2)" = "sfp_plus" ]
  [ "$(cv_interface_class_for_name Gi1/0/29)" = "other" ]
  [ "$(cv_interface_class_for_name Te1/0/3)" = "other" ]
)

python3 "$BASE_DIR/registry_lookup.py" --registry "$RUNTIME_REGISTRY" --model "N2128PX-ON" --report > "$tmp_dir/dell-registry-report.txt"
grep -q -- '- Registry match: yes' "$tmp_dir/dell-registry-report.txt"
grep -q -- '- Registry status: experimental' "$tmp_dir/dell-registry-report.txt"

python3 - "$RUNTIME_REGISTRY" "$BASE_DIR/profiles/switch-vision-profiles.yaml" <<'PYTEST_V2120_DELL'
import json, sys
from pathlib import Path
import yaml
reg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
prof = yaml.safe_load(Path(sys.argv[2]).read_text(encoding="utf-8"))
profiles = prof.get("profiles", prof)
devices = {d["model"]: d for d in reg["devices"]}
d = devices["N2128PX-ON"]
assert d["status"] == "experimental"
assert d["ports"]["rj45"] == 28
assert d["ports"]["uplinks"] == 2
assert d["ports"]["ten_gigabit_sfp_plus"] == 2
assert d["stack_support"] is True
assert d["tested_firmware"] == ["6.7.1.27", "6.6.0.7"]
assert d["mapping_profile"] == "dell-n2128px-on"
p = profiles["dell-n2128px-on"]
assert p["sys_object_ids"] == ["1.3.6.1.4.1.674.10895.3077"]
assert p["layout"]["rj45_ports"] == 28
assert p["layout"]["sfp_10g_ports"] == 2
assert "Gi{member}/0/{port}" in p["interface_patterns"]["rj45"]
assert "Te{member}/0/1" in p["interface_patterns"]["sfp_10g"]
job = (Path(sys.argv[2]).parents[1] / "discovery_job.sh").read_text(encoding="utf-8")
for required in ('model == "N2128PX-ON"', 'profile = "dell-n2128px-on"', '10G SFP+ uplink', 'manufacturer = "Dell"'):
    assert required in job, required
print("Switch Vision Discovery v2.1.20 Dell N2128PX-ON regression: PASS")
PYTEST_V2120_DELL


# v2.1.21 Support My Switch privacy-default contract.
# The Home Assistant app config lives outside runtime.tar.gz, so this regression
# protects the runtime-side expectation that both controls remain supported and
# are read as normal boolean contribution options.
grep -q 'support_mask_vlan_names' "$BASE_DIR/discovery_job.sh"
grep -q 'support_mask_interface_descriptions' "$BASE_DIR/discovery_job.sh"
echo "Switch Vision Discovery v2.1.21 privacy-default contract regression: PASS"


# v2.1.27 hardware-validation and speed-contract regressions.
python3 - "$RUNTIME_REGISTRY" "$BASE_DIR/profiles/switch-vision-profiles.yaml" "$BASE_DIR/discovery_job.sh" <<'PYTEST_V2127_HARDWARE'
import json
import sys
from pathlib import Path
import yaml

registry = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
profiles_doc = yaml.safe_load(Path(sys.argv[2]).read_text(encoding="utf-8")) or {}
profiles = profiles_doc.get("profiles", profiles_doc)
job = Path(sys.argv[3]).read_text(encoding="utf-8")
models = {d["model"]: d for d in registry["devices"] if isinstance(d, dict)}
community_validated = {
    "SG500X-24",
    "S5735-L8P4X-A1",
    "S5720-12TP-LI-AC",
}
for model in community_validated:
    assert models[model]["status"] == "community_validated", model

pending_experimental = {
    "WS-C2960X-24TS-L",
    "WS-C3560CG-8PC-S",
}
for model in pending_experimental:
    assert models[model]["status"] == "experimental", model

p3560 = next(p for p in profiles.values() if "WS-C3560CG-8PC-S" in (p.get("model_patterns") or []))
assert p3560["layout"]["rj45_ports"] == 8
assert p3560["layout"]["sfp_1g_ports"] == 2
assert p3560["interface_patterns"]["sfp_1g"] == ["Gi0/9", "Gi0/10", "GigabitEthernet0/9", "GigabitEthernet0/10"]

s5720 = next(p for p in profiles.values() if "S5720-12TP-LI-AC" in (p.get("model_patterns") or []))
assert s5720["layout"]["rj45_ports"] == 8
assert s5720["layout"]["sfp_1g_ports"] == 4
assert s5720["layout"]["sfp_10g_ports"] == 0
assert s5720["physical_speed_caps_mbps"]["sfp_1g"] == 1000
assert 'physical_speed_cap_mbps(model, label)' in job
assert 'model == "S5720-12TP-LI-AC" && label ~ /(^| )SFP 1G /' in job
# Source ordering is the contract: ifHighSpeed must win whenever available.
helper = job[job.index('function yaml_speed_sensor'):job.index('function yaml_interface_sensor')]
assert helper.index('if (has_highspeed)') < helper.index('else if (has_ifspeed)')
assert '1.3.6.1.2.1.31.1.1.1.15.' in helper
assert '1.3.6.1.2.1.2.2.1.5.' in helper

# UniFi models that claim dashboard support must carry an explicit visual/profile
# assignment. Detected hardware may intentionally remain visual-pending, but
# profile/faceplate state must stay paired and must never fall through to Cisco
# artwork/profile names.
for model, device in models.items():
    if device.get("vendor") != "Ubiquiti":
        continue
    faceplate = str(device.get("default_faceplate") or "")
    profile = str(device.get("calibration_profile") or "")
    visuals = device.get("visuals") if isinstance(device.get("visuals"), dict) else {}
    if device.get("dashboard_support") is True:
        assert faceplate and profile, model
    assert bool(faceplate) == bool(profile), model
    assert str(visuals.get("recommended_faceplate") or "") == faceplate, model
    assert str(visuals.get("calibration_profile") or "") == profile, model
    if faceplate:
        assert "cisco" not in faceplate.lower(), (model, faceplate)
        assert not profile.lower().startswith("cisco_"), (model, profile)
print("Switch Vision Discovery v2.1.27 hardware/status/UniFi contract regression: PASS")
PYTEST_V2127_HARDWARE

# Dell N2128PX-ON physical-front-panel safeguards. Interfaces 29/30 are the
# two physical 10G SFP+ cages. 31/32 can exist in IF-MIB but are not present
# front-panel ports and must stay excluded.
dell_v2127="$tmp_dir/dell-v2127.txt"
cat > "$dell_v2127" <<'EOF_DELL_V2127'
.1.3.6.1.2.1.1.1.0 = STRING: Dell EMC Networking N2128PX-ON, 6.7.1.27
.1.3.6.1.2.1.31.1.1.1.1.25 = STRING: Gi1/0/25
.1.3.6.1.2.1.31.1.1.1.1.26 = STRING: Gi1/0/26
.1.3.6.1.2.1.31.1.1.1.1.29 = STRING: Te1/0/1
.1.3.6.1.2.1.31.1.1.1.1.30 = STRING: Te1/0/2
.1.3.6.1.2.1.31.1.1.1.1.31 = STRING: Te1/0/3
.1.3.6.1.2.1.31.1.1.1.1.32 = STRING: Te1/0/4
.1.3.6.1.2.1.2.2.1.8.31 = INTEGER: notPresent(6)
.1.3.6.1.2.1.2.2.1.8.32 = INTEGER: notPresent(6)
.1.3.6.1.2.1.2.2.1.5.25 = Gauge32: 4294967295
.1.3.6.1.2.1.2.2.1.5.26 = Gauge32: 4294967295
.1.3.6.1.2.1.2.2.1.5.29 = Gauge32: 4294967295
.1.3.6.1.2.1.2.2.1.5.30 = Gauge32: 4294967295
.1.3.6.1.2.1.31.1.1.1.15.25 = Gauge32: 2500
.1.3.6.1.2.1.31.1.1.1.15.26 = Gauge32: 2500
.1.3.6.1.2.1.31.1.1.1.15.29 = Gauge32: 10000
.1.3.6.1.2.1.31.1.1.1.15.30 = Gauge32: 10000
.1.3.6.1.2.1.31.1.1.1.15.31 = Gauge32: 20000
.1.3.6.1.2.1.31.1.1.1.15.32 = Gauge32: 20000
EOF_DELL_V2127
cv_write_capabilities_json "$dell_v2127" "$tmp_dir/dell-v2127-capabilities.json" ""
jq -e '
  ([.interfaces[] | select(.if_index == 29 or .if_index == 30) | select(.media == "sfp_plus" and .physical == true)] | length == 2)
  and ([.interfaces[] | select(.if_index == 31 or .if_index == 32) | select(.physical == true)] | length == 0)
' "$tmp_dir/dell-v2127-capabilities.json" >/dev/null

echo "Switch Vision Discovery v2.1.27 Dell physical/speed safeguard regression: PASS"


# v2.1.28 generated SNMP2MQTT YAML publication regression. An invalid/empty
# target candidate must never replace an already-valid live handoff file.
yaml_guard="$BASE_DIR/generated_yaml_guard.py"
[ -f "$yaml_guard" ]
valid_yaml="$tmp_dir/generated-valid.yaml"
invalid_yaml="$tmp_dir/generated-invalid.yaml"
live_yaml="$tmp_dir/generated-live.yaml"
cat > "$valid_yaml" <<'YAML_VALID_V2128'
# Switch Vision generated SNMP2MQTT YAML
# Source: Switch Vision Discovery v2.1.28
targets:
  - host: 192.0.2.128
    name: Switch Vision Regression
    version: 2c
    community: public
    sensors:
      - oid: 1.3.6.1.2.1.1.3.0
        name: Regression Uptime
YAML_VALID_V2128
cat > "$invalid_yaml" <<'YAML_INVALID_V2128'
# Switch Vision generated SNMP2MQTT YAML
# Source: Switch Vision Discovery v2.1.28
targets:
YAML_INVALID_V2128
cp "$valid_yaml" "$live_yaml"
valid_sha_before=$(sha256sum "$live_yaml" | awk '{print $1}')
if python3 "$yaml_guard" --publish "$invalid_yaml" "$live_yaml"; then
  echo "ERROR: target-less generated YAML candidate was accepted" >&2
  exit 1
fi
valid_sha_after=$(sha256sum "$live_yaml" | awk '{print $1}')
[ "$valid_sha_before" = "$valid_sha_after" ] || {
  echo "ERROR: invalid generated YAML replaced the live handoff" >&2
  exit 1
}
cp "$valid_yaml" "$tmp_dir/generated-valid-candidate.yaml"
python3 "$yaml_guard" --publish "$tmp_dir/generated-valid-candidate.yaml" "$live_yaml"
grep -Eq '^[[:space:]]*-[[:space:]]+host:[[:space:]]+192\.0\.2\.128$' "$live_yaml"
[ ! -e "$tmp_dir/generated-valid-candidate.yaml" ]
grep -Fq 'candidate_path="${GENERATED_YAML_PATH}.candidate.$$"' "$BASE_DIR/discovery_job.sh"
grep -Fq 'python3 "$guard" --publish "$candidate_path" "$GENERATED_YAML_PATH"' "$BASE_DIR/discovery_job.sh"
! grep -Fq '} > "$GENERATED_YAML_PATH"' "$BASE_DIR/discovery_job.sh"
printf '%s\n' "Switch Vision Discovery v2.1.28 atomic generated-YAML publication: PASS"

# S5720 generator contract: its fallback ifDescr names must still create target
# output and its four physical 1G SFP cages retain the v2.1.27 speed cap.
grep -Fq 'model == "S5720-12TP-LI-AC" && label ~ /(^| )SFP 1G /' "$BASE_DIR/discovery_job.sh"
grep -Fq 'if (!(idx in ifname)) { ifname[idx]=val; ifname_source[idx]="ifDescr" }' "$BASE_DIR/discovery_job.sh"
printf '%s\n' "Switch Vision Discovery v2.1.28 S5720 generated-target prerequisites: PASS"

# v2.1.30 Discovery progress-stage regression. Structured current stage must
# beat stale/historical log-tail text so the blue highlight stays on the task
# that is actually running.
python3 - "$BASE_DIR/support_web.py" <<'PYTEST_V2130_PROGRESS'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
start = text.index("function discoveryStage(state)")
end = text.index("function updateSteps(state)", start)
fn = text[start:end]
assert "const stage=String(state.stage||'').toLowerCase()" in fn
assert "if(stage.includes('generating snmp2mqtt yaml'))return 3" in fn
assert "if(stage.includes('generating dashboard card yaml'))return 4" in fn
assert fn.index("const stage=") < fn.index("const text=")
assert fn.index("generating snmp2mqtt yaml") < fn.index("dashboard card')||text.includes")
assert ".slice(-3).join(' ')" in fn
print("Switch Vision Discovery v2.1.30 structured progress-stage regression: PASS")
PYTEST_V2130_PROGRESS


# v2.1.31 generated-YAML handoff regression. Current-run metadata captured at
# collection time must be authoritative, failed walks must not enter generation,
# parser/formatter failures must not be hidden by a shell pipeline, and an
# already-invalid live handoff must not survive another failed generation.
python3 - "$BASE_DIR/discovery_job.sh" <<'PYTEST_V2131_HANDOFF'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
assert 'CURRENT_RUN_TARGETS="/tmp/switch_vision_current_run_targets.txt"' in text
assert 'record_current_run_target' in text
assert 'current_run_target_field_for_walk "$walk_file" host' in text
assert 'current_run_target_field_for_walk "$walk_file" prefix' in text
assert 'current_run_target_field_for_walk "$walk_file" community' in text
assert text.index('current_run_target_field_for_walk "$walk_file" host') < text.index('if [ -f "$TARGETS_CSV" ]')
assert 'if [ "$result" = "PASS" ] || [ "$result" = "WARN" ]; then' in text
assert 'Current-run parse skipped for failed walk' in text
assert 'generator_raw_tmp="/tmp/switch_vision_generator_raw_$$.yaml"' in text
assert '"$walk_file" | awk' not in text
assert 'Generated YAML source parser failed for:' in text
assert 'Generated YAML formatter failed for:' in text
assert 'quarantine_invalid_generated_live_yaml()' in text
assert 'python3 "$guard" --validate "$GENERATED_YAML_PATH"' in text
assert 'mv "$GENERATED_YAML_PATH" "$quarantine_path"' in text
assert 'Previous invalid generated YAML was quarantined; no broken live handoff remains.' in text
print("Switch Vision Discovery v2.1.31 generated-YAML handoff regression: PASS")
PYTEST_V2131_HANDOFF


# v2.1.31 end-to-end current-run handoff regression. Run the real Discovery
# engine against deterministic fake Dell N2128PX-ON and Huawei S5720 agents.
# This exercises switch-list walking, current-run metadata capture, the actual
# AWK generator, S5720 ifDescr fallback + 1G speed cap, semantic validation,
# and atomic publication as one flow.
v2131_e2e="$tmp_dir/v2131-e2e"
mkdir -p "$v2131_e2e/bin" "$v2131_e2e/snmpwalks" "$v2131_e2e/capabilities" "$v2131_e2e/share"
cat > "$v2131_e2e/bin/snmpwalk" <<'FAKE_SNMPWALK_V2131'
#!/usr/bin/env sh
case " $* " in
  *" 192.0.2.32 "*)
    cat <<'HUAWEI_WALK_V2131'
.1.3.6.1.2.1.1.1.0 = STRING: Huawei S5720-12TP-LI-AC V200R022C00SPC500
.1.3.6.1.2.1.1.3.0 = Timeticks: (654321) 1:49:03.21
.1.3.6.1.2.1.2.2.1.2.5 = STRING: GigabitEthernet0/0/1
.1.3.6.1.2.1.2.2.1.2.13 = STRING: GigabitEthernet0/0/9
.1.3.6.1.2.1.2.2.1.2.14 = STRING: GigabitEthernet0/0/10
.1.3.6.1.2.1.2.2.1.2.15 = STRING: GigabitEthernet0/0/11
.1.3.6.1.2.1.2.2.1.2.16 = STRING: GigabitEthernet0/0/12
.1.3.6.1.2.1.2.2.1.8.5 = INTEGER: 1
.1.3.6.1.2.1.2.2.1.8.13 = INTEGER: 1
.1.3.6.1.2.1.2.2.1.8.14 = INTEGER: 2
.1.3.6.1.2.1.2.2.1.8.15 = INTEGER: 1
.1.3.6.1.2.1.2.2.1.8.16 = INTEGER: 2
.1.3.6.1.2.1.31.1.1.1.15.5 = Gauge32: 1000
.1.3.6.1.2.1.31.1.1.1.15.13 = Gauge32: 10000
.1.3.6.1.2.1.31.1.1.1.15.14 = Gauge32: 10000
.1.3.6.1.2.1.31.1.1.1.15.15 = Gauge32: 10000
.1.3.6.1.2.1.31.1.1.1.15.16 = Gauge32: 10000
HUAWEI_WALK_V2131
    ;;
  *)
    cat <<'DELL_WALK_V2131'
.1.3.6.1.2.1.1.1.0 = STRING: Dell EMC Networking N2128PX-ON, 6.7.1.27, Linux 4.14.174, v1.0.9
.1.3.6.1.2.1.1.3.0 = Timeticks: (123456) 0:20:34.56
.1.3.6.1.2.1.31.1.1.1.1.1 = STRING: Gi1/0/1
.1.3.6.1.2.1.31.1.1.1.1.28 = STRING: Gi1/0/28
.1.3.6.1.2.1.31.1.1.1.1.29 = STRING: Te1/0/1
.1.3.6.1.2.1.31.1.1.1.1.30 = STRING: Te1/0/2
.1.3.6.1.2.1.2.2.1.8.1 = INTEGER: 1
.1.3.6.1.2.1.2.2.1.8.28 = INTEGER: 2
.1.3.6.1.2.1.2.2.1.8.29 = INTEGER: 1
.1.3.6.1.2.1.2.2.1.8.30 = INTEGER: 2
.1.3.6.1.2.1.31.1.1.1.15.1 = Gauge32: 1000
.1.3.6.1.2.1.31.1.1.1.15.28 = Gauge32: 2500
.1.3.6.1.2.1.31.1.1.1.15.29 = Gauge32: 10000
.1.3.6.1.2.1.31.1.1.1.15.30 = Gauge32: 10000
DELL_WALK_V2131
    ;;
esac
FAKE_SNMPWALK_V2131
chmod +x "$v2131_e2e/bin/snmpwalk"

cat > "$v2131_e2e/options.json" <<JSON_V2131
{
  "input_path": "$v2131_e2e/legacy-unused.txt",
  "snmpwalks_dir": "$v2131_e2e/snmpwalks",
  "report_path": "$v2131_e2e/discovery-report.txt",
  "run_snmp_walks": "true",
  "enable_switch_list": "true",
  "switches": [
    {
      "switch_name": "DELL-REGRESSION",
      "display_name": "Dell Regression",
      "switch_host": "192.0.2.31",
      "sensor_prefix": "dellreg",
      "snmp_community": "public",
      "enabled": "enabled",
      "walk_mode": "targeted",
      "switch_model": "N2128PX-ON"
    },
    {
      "switch_name": "S5720-REGRESSION",
      "display_name": "S5720 Regression",
      "switch_host": "192.0.2.32",
      "sensor_prefix": "huaweireg",
      "snmp_community": "public",
      "enabled": "enabled",
      "walk_mode": "targeted",
      "switch_model": "S5720-12TP-LI-AC"
    }
  ],
  "stack_member_prefixes": [],
  "parse_all_walks": "false",
  "generate_snmp2mqtt": "true",
  "clean_output_before_walk": "false",
  "targets_csv": "$v2131_e2e/no-import.csv",
  "last_run_summary_path": "$v2131_e2e/last-run.txt",
  "generated_yaml_path": "$v2131_e2e/generated-snmp2mqtt.yaml",
  "generated_card_path": "$v2131_e2e/generated-dashboard-card.yaml",
  "snmp_timeout": "1",
  "snmp_retries": "0",
  "snmp_log_path": "$v2131_e2e/snmpwalk.log",
  "minimum_valid_walk_lines": "1"
}
JSON_V2131

rm -f /tmp/switch_vision_current_run_walks.txt /tmp/switch_vision_current_run_targets.txt
if ! PATH="$v2131_e2e/bin:$PATH" \
  SWITCH_VISION_OPTIONS_FILE="$v2131_e2e/options.json" \
  SWITCH_VISION_SHARE_DIR="$v2131_e2e/share" \
  SWITCH_VISION_CAPABILITIES_DIR="$v2131_e2e/capabilities" \
  CV_MIB_DATABASE_DIR="$RUNTIME_DATA_DIR/mib_database" \
  CV_VENDOR_DIR="$RUNTIME_DATA_DIR/vendors" \
  sh "$BASE_DIR/discovery_job.sh" > "$v2131_e2e/run-output.txt" 2>&1; then
  echo "ERROR: v2.1.31 end-to-end Discovery process failed" >&2
  cat "$v2131_e2e/run-output.txt" >&2 || true
  cat "$v2131_e2e/snmpwalk.log" >&2 || true
  exit 1
fi

if ! python3 "$BASE_DIR/generated_yaml_guard.py" --validate "$v2131_e2e/generated-snmp2mqtt.yaml"; then
  echo "ERROR: v2.1.31 end-to-end generated YAML validation failed" >&2
  cat "$v2131_e2e/run-output.txt" >&2 || true
  cat "$v2131_e2e/snmpwalk.log" >&2 || true
  cat "$v2131_e2e/generated-snmp2mqtt.yaml" >&2 || true
  exit 1
fi
grep -Eq '^- host: 192\.0\.2\.31$' "$v2131_e2e/generated-snmp2mqtt.yaml"
grep -Eq '^- host: 192\.0\.2\.32$' "$v2131_e2e/generated-snmp2mqtt.yaml"
grep -Fq 'template: "{{ [value | int, 1000] | min }}"' "$v2131_e2e/generated-snmp2mqtt.yaml"
grep -Fq 'DELL-REGRESSION/live-targeted-snmpwalk.txt' /tmp/switch_vision_current_run_targets.txt
grep -Fq 'S5720-REGRESSION/live-targeted-snmpwalk.txt' /tmp/switch_vision_current_run_targets.txt
grep -Fq '192.0.2.31' /tmp/switch_vision_current_run_targets.txt
grep -Fq '192.0.2.32' /tmp/switch_vision_current_run_targets.txt
grep -Fq 'dellreg' /tmp/switch_vision_current_run_targets.txt
grep -Fq 'huaweireg' /tmp/switch_vision_current_run_targets.txt
grep -Fq 'Generated YAML published atomically:' "$v2131_e2e/snmpwalk.log"
! grep -Fq 'Generated YAML source parser failed' "$v2131_e2e/snmpwalk.log"
! grep -Fq 'no target host entries' "$v2131_e2e/run-output.txt"
rm -f /tmp/switch_vision_current_run_walks.txt /tmp/switch_vision_current_run_targets.txt
printf '%s\n' "Switch Vision Discovery v2.1.31 end-to-end Dell + S5720 current-run handoff: PASS"

# community-validation UniFi exact-model/API mapping regression.
python3 - "$RUNTIME_REGISTRY" "$BASE_DIR/profiles/switch-vision-profiles.yaml" <<'PYTEST_community_validation'
import json
import sys
from pathlib import Path
import yaml

registry = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
profiles_doc = yaml.safe_load(Path(sys.argv[2]).read_text(encoding="utf-8")) or {}
profiles = profiles_doc.get("profiles", profiles_doc)
models = {d["model"]: d for d in registry["devices"] if isinstance(d, dict)}

us48 = models["US 48"]
assert us48["status"] == "experimental"
assert us48["ports"]["rj45"] == 48
assert us48["ports"]["gigabit_sfp"] == 2
assert us48["ports"]["ten_gigabit_sfp_plus"] == 2
assert "unifi_api_port_map" not in us48

xg16 = models["US XG 16"]
assert xg16["status"] == "detected"
assert xg16["dashboard_support"] is False
assert xg16["unifi_api_port_map"]["sfp"] == list(range(1, 13))
assert xg16["unifi_api_port_map"]["rj45"] == [13, 14, 15, 16]

agg = models["USW Pro Aggregation"]
assert agg["status"] == "detected"
assert agg["dashboard_support"] is False
assert agg["ports"]["rj45"] == 0
assert agg["ports"]["ten_gigabit_sfp_plus"] == 28
assert agg["ports"]["twenty_five_gigabit_sfp28"] == 4
assert agg["unifi_api_port_map"]["sfp"] == list(range(1, 33))

p48 = profiles["ubiquiti-us-48-api"]
assert p48["layout"] == {"members": 1, "rj45_ports": 48, "sfp_1g_ports": 2, "sfp_10g_ports": 2}
assert p48["interface_patterns"]["sfp_10g"] == ["api-port-49", "api-port-50"]
assert p48["interface_patterns"]["sfp_1g"] == ["api-port-51", "api-port-52"]
pxg = profiles["ubiquiti-us-xg-16-api"]
assert pxg["interface_patterns"]["rj45"] == ["api-port-13", "api-port-14", "api-port-15", "api-port-16"]
assert pxg["interface_patterns"]["sfp_10g"] == [f"api-port-{n}" for n in range(1, 13)]
pagg = profiles["ubiquiti-usw-pro-aggregation-api"]
assert pagg["layout"]["rj45_ports"] == 0
assert pagg["layout"]["sfp_10g_ports"] == 28
assert pagg["layout"]["sfp_25g_ports"] == 4
assert pagg["interface_patterns"]["sfp_25g"] == [f"api-port-{n}" for n in range(29, 33)]
print("Switch Vision Discovery community-validation UniFi contract regression: PASS")
PYTEST_community_validation

python3 - "$tmp_dir/community-validation-unifi.json" <<'PYTEST_community_validation_SNAPSHOT'
import json
import sys
from pathlib import Path

def ports(items):
    return [{"idx": idx, "connector": connector} for idx, connector in items]

snapshot = {
    "devices": [
        {
            "id": "us48-test",
            "name": "US 48 test",
            "model": "US 48",
            "api_capabilities": {"port_detail": True, "per_port_traffic": False},
            "ports": ports([(n, "RJ45") for n in range(1, 49)] + [(49, "SFPPLUS"), (50, "SFPPLUS"), (51, "SFP"), (52, "SFP")]),
        },
        {
            "id": "xg16-test",
            "name": "US XG 16 test",
            "model": "US XG 16",
            "api_capabilities": {"port_detail": True, "per_port_traffic": False},
            "ports": ports([(n, "SFPPLUS") for n in range(1, 13)] + [(n, "RJ45") for n in range(13, 17)]),
        },
        {
            "id": "aggregation-test",
            "name": "Pro Aggregation test",
            "model": "USW Pro Aggregation",
            "api_capabilities": {"port_detail": True, "per_port_traffic": False},
            "ports": ports([(n, "SFPPLUS") for n in range(1, 29)] + [(n, "SFP28") for n in range(29, 33)]),
        },
    ]
}
Path(sys.argv[1]).write_text(json.dumps(snapshot), encoding="utf-8")
PYTEST_community_validation_SNAPSHOT
python3 "$BASE_DIR/unifi_dashboard_cards.py" \
    --snapshot "$tmp_dir/community-validation-unifi.json" \
    --registry "$RUNTIME_REGISTRY" \
    --summary > "$tmp_dir/community-validation-cards.yaml"
grep -q 'switch_model: US 48' "$tmp_dir/community-validation-cards.yaml"
grep -q 'unifi_sfp_port_offset: 48' "$tmp_dir/community-validation-cards.yaml"
! grep -q 'switch_model: US XG 16' "$tmp_dir/community-validation-cards.yaml"
! grep -q 'switch_model: USW Pro Aggregation' "$tmp_dir/community-validation-cards.yaml"
grep -q 'US XG 16.*dashboard support is pending verified visuals' "$tmp_dir/community-validation-cards.yaml"
grep -q 'USW Pro Aggregation.*dashboard support is pending verified visuals' "$tmp_dir/community-validation-cards.yaml"
grep -q 'UniFi cards emitted: 1; waiting for visuals/registry: 2' "$tmp_dir/community-validation-cards.yaml"
echo "Switch Vision Discovery community-validation generated-card regression: PASS"
# v2.1.36 UniFi-only SNMP2MQTT status regression.
PYTHONPATH="$BASE_DIR" python3 - <<'PYTEST_V2136_UNIFI_ONLY'
import tempfile
from pathlib import Path
import support_web as web

tmp = tempfile.TemporaryDirectory()
web.DEFAULT_GENERATED_SNMP2MQTT = Path(tmp.name) / "generated-snmp2mqtt.yaml"

web._self_addon_options = lambda: {
    "generate_snmp2mqtt": "true",
    "parse_all_walks": "false",
    "switches": [],
}
status = web._generated_yaml_status()
assert status["applicable"] is False
assert status["validation"]["valid"] is None
assert "UniFi2MQTT-only" in status["reason"]

source = Path(web.__file__).read_text(encoding="utf-8")
assert 'if not generated_yaml["found"] and snmp2mqtt_applicability["applicable"]:' in source
assert '"snmp2mqtt_applicability": snmp2mqtt_applicability' in source
assert 'if snmp2mqtt_applicability["applicable"]:' in source
assert 'stale_candidates.insert(0, ("SNMP2MQTT YAML"' in source
assert 'id="generatedYamlDescription"' in web._PAGE
assert 'id="generatedYamlActions"' in web._PAGE
assert 'id="regenerateYamlHelp"' in web._PAGE
assert "d.applicable!==false" in web._PAGE
assert "regen.hidden=true" in web._PAGE
assert "Not in use · no enabled SNMP targets" in web._PAGE

web._self_addon_options = lambda: {
    "generate_snmp2mqtt": "true",
    "parse_all_walks": "false",
    "switches": [{
        "switch_name": "SW1",
        "switch_host": "192.0.2.10",
        "enabled": "enabled",
    }],
}
status = web._generated_yaml_status()
assert status["applicable"] is True
assert status["validation"]["valid"] is False
assert "not found" in status["validation"]["error"].lower()

web._self_addon_options = lambda: {
    "generate_snmp2mqtt": "false",
    "parse_all_walks": "false",
    "switches": [{
        "switch_name": "SW1",
        "switch_host": "192.0.2.10",
        "enabled": "enabled",
    }],
}
status = web._generated_yaml_status()
assert status["applicable"] is False
assert "disabled" in status["reason"].lower()
print("Switch Vision Discovery v2.1.36 UniFi-only SNMP2MQTT status regression: PASS")
PYTEST_V2136_UNIFI_ONLY

# community-hardware Community UniFi exact-model contract regression.
python3 - "$RUNTIME_REGISTRY" "$BASE_DIR/profiles/switch-vision-profiles.yaml" <<'PYTEST_BRENDAN_UNIFI'
import json
import sys
from pathlib import Path
import yaml

registry = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
profiles_doc = yaml.safe_load(Path(sys.argv[2]).read_text(encoding="utf-8")) or {}
profiles = profiles_doc.get("profiles", profiles_doc)
models = {d["model"]: d for d in registry["devices"] if isinstance(d, dict)}

expected = {
    "UCG Ultra": (5, 0, False, True, "ubiquiti-ucg-ultra-api"),
    "US 16 PoE 150W": (16, 2, True, False, "ubiquiti-us-16-poe-150w-api"),
    "USW Pro Max 24": (24, 2, False, True, "ubiquiti-usw-pro-max-24-api"),
    "USW Ultra": (8, 0, True, True, "ubiquiti-usw-ultra-api"),
}
for model, (rj45, uplinks, poe, dashboard, profile) in expected.items():
    item = models[model]
    expected_status = "experimental"
    assert item["status"] == expected_status, model
    assert item["ports"]["rj45"] == rj45, model
    assert item["ports"]["uplinks"] == uplinks, model
    assert item["ports"]["poe"] is poe, model
    assert item["dashboard_support"] is dashboard, model
    assert item["mapping_profile"] == profile, model
    assert [c["id"] for c in item["contributions"]] == ["community-validation-1", "community-validation-2"], model
    assert item["contributions"][0]["contributor"]["public_credit"] is False, model
    assert item["contributions"][1]["contributor"]["display_name"] == "community contributor", model
    assert all(c["api_capabilities"]["per_port_traffic"] is False for c in item["contributions"]), model
    assert profile in profiles, profile
    assert profiles[profile]["status"] == "experimental", model

promax = models["USW Pro Max 24"]
assert promax["calibration_profile"] == "unifi_24p_rj45_2sfp"
assert promax["default_faceplate"] == "faceplates/unifi-24p-rj45-2sfp.png"
ucg = models["UCG Ultra"]
assert ucg["calibration_profile"] == "default_unifi_5_rj45"
assert ucg["default_faceplate"] == "faceplates/unifi-5rj45.png"
ultra = models["USW Ultra"]
assert ultra["calibration_profile"] == "default_unifi_8_rj45"
assert ultra["default_faceplate"] == "faceplates/unifi-8rj45.png"
assert profiles["ubiquiti-usw-pro-max-24-api"]["interface_patterns"]["sfp_10g"] == ["api-port-25", "api-port-26"]
assert profiles["ubiquiti-us-16-poe-150w-api"]["interface_patterns"]["sfp_1g"] == ["api-port-17", "api-port-18"]
assert "ports_1_7_only" in models["USW Ultra"]["validation"]["poe"]
assert "2p5g_capable" in promax["validation"]["rj45_mapping"]
print("Switch Vision Discovery Community registry/profile contract: PASS")
PYTEST_BRENDAN_UNIFI

python3 - "$tmp_dir/community-unifi.json" <<'PYTEST_BRENDAN_SNAPSHOT'
import json
import sys
from pathlib import Path

def ports(rj45, sfp=0):
    rows = [{"idx": n, "connector": "RJ45", "max_speed_mbps": 1000} for n in range(1, rj45 + 1)]
    rows += [{"idx": rj45 + n, "connector": "SFPPLUS", "max_speed_mbps": 10000} for n in range(1, sfp + 1)]
    return rows

snapshot = {"devices": [
    {"id": "community-ucg", "name": "UCG Ultra", "model": "UCG Ultra", "api_capabilities": {"port_detail": True, "per_port_traffic": False}, "ports": ports(5)},
    {"id": "community-us16", "name": "US 16 PoE 150W", "model": "US 16 PoE 150W", "api_capabilities": {"port_detail": True, "per_port_traffic": False}, "ports": ports(16, 2)},
    {"id": "community-promax24", "name": "USW Pro Max 24", "model": "USW Pro Max 24", "api_capabilities": {"port_detail": True, "per_port_traffic": False}, "ports": ports(24, 2)},
    {"id": "community-ultra", "name": "USW Ultra", "model": "USW Ultra", "api_capabilities": {"port_detail": True, "per_port_traffic": False}, "ports": ports(8)},
]}
Path(sys.argv[1]).write_text(json.dumps(snapshot), encoding="utf-8")
PYTEST_BRENDAN_SNAPSHOT

python3 "$BASE_DIR/unifi_dashboard_cards.py" \
    --snapshot "$tmp_dir/community-unifi.json" \
    --registry "$RUNTIME_REGISTRY" \
    --summary > "$tmp_dir/community-unifi-cards.yaml"
grep -q 'switch_model: UCG Ultra' "$tmp_dir/community-unifi-cards.yaml"
grep -q 'switch_model: US 16 PoE 150W' "$tmp_dir/community-unifi-cards.yaml"
grep -q 'switch_model: USW Pro Max 24' "$tmp_dir/community-unifi-cards.yaml"
grep -q 'switch_model: USW Ultra' "$tmp_dir/community-unifi-cards.yaml"
test "$(grep -c 'generic_faceplate: true' "$tmp_dir/community-unifi-cards.yaml")" -eq 1
test "$(grep -c 'generic_faceplate: false' "$tmp_dir/community-unifi-cards.yaml")" -eq 3
grep -q 'UniFi cards emitted: 4; exact cards: 3; generic fallbacks: 1; exact support pending: 1; issues: 0' "$tmp_dir/community-unifi-cards.yaml"
echo "Switch Vision Discovery community-hardware generated-card regression: PASS"

# v2.2.5 generated-config activation and transaction-aware walk freshness regression.
PYTHONPATH="$BASE_DIR" python3 - "$tmp_dir" <<'PYTEST_V225_HANDOFF'
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import tempfile
import yaml

import support_web as web
import walk_correlation as correlation

tmp = Path(sys.argv[1]) / "v225-handoff"
tmp.mkdir(parents=True, exist_ok=True)
generated = tmp / "generated-snmp2mqtt.yaml"
generated.write_text(
    yaml.safe_dump(
        {
            "targets": [
                {
                    "host": "192.0.2.40",
                    "name": "Regression target",
                    "sensors": [
                        {
                            "oid": "1.3.6.1.2.1.2.2.1.8.1",
                            "name": "SW1 Port 1 Status",
                            "object_id": "sw1_port_1_status",
                        }
                    ],
                }
            ]
        },
        sort_keys=False,
    ),
    encoding="utf-8",
)
web.DEFAULT_GENERATED_SNMP2MQTT = generated
web.time.sleep = lambda _seconds: None

base_runtime = {
    "installed": True,
    "slug": "test_switch_vision_snmp2mqtt",
    "state": "started",
    "options_readable": True,
    "homeassistant_prefix": "homeassistant",
    "base_topic": "snmp2mqtt",
    "host_name_as_target": False,
    "wrapper_options_readable": True,
    "use_switch_vision_generated_yaml": True,
    "switch_vision_generated_yaml_path": str(generated),
}

# Explicit manual-target mode must fail closed without restarting the app.
manual_runtime = dict(base_runtime)
manual_runtime["use_switch_vision_generated_yaml"] = False
web._snmp2mqtt_runtime_info = lambda: dict(manual_runtime)
unexpected_actions = []
web._supervisor_json = lambda *args, **kwargs: unexpected_actions.append((args, kwargs)) or {}
manual_result = web._ensure_snmp2mqtt_running([], 0.0, [])
assert manual_result["handoff_failed"] is True
assert manual_result["configuration_mode"] == "manual"
assert manual_result["action"] == "blocked_configuration"
assert unexpected_actions == []

# A configured generated path that does not match Discovery output must also
# fail before any restart.
path_runtime = dict(base_runtime)
path_runtime["switch_vision_generated_yaml_path"] = str(tmp / "different.yaml")
web._snmp2mqtt_runtime_info = lambda: dict(path_runtime)
unexpected_actions.clear()
path_result = web._ensure_snmp2mqtt_running([], 0.0, [])
assert path_result["handoff_failed"] is True
assert path_result["configuration_mode"] == "generated_path_mismatch"
assert unexpected_actions == []

# Successful restart: an initially missing retained identity may arrive later.
events = []
web._snmp2mqtt_runtime_info = lambda: dict(base_runtime)
def supervisor(path, *, method="GET", timeout=12.0, payload=None):
    events.append(("supervisor", method, path))
    if path.endswith("/info"):
        return {"data": {"state": "started"}}
    return {"result": "ok"}
web._supervisor_json = supervisor
scans = [
    {
        "current_expected_count": 1,
        "current_retained_count": 0,
        "current_missing_retained_count": 1,
        "stale_count": 1,
    },
    {
        "current_expected_count": 1,
        "current_retained_count": 1,
        "current_missing_retained_count": 0,
        "stale_count": 1,
    },
]
def scan_success():
    value = scans.pop(0)
    events.append(("scan", value["current_retained_count"]))
    return value
web.scan_mqtt_entities = scan_success
clears = []
def clear_topics(topics):
    events.append(("clear", len(topics)))
    clears.append(list(topics))
    return len(topics), []
web._clear_retained_snmp2mqtt_discovery = clear_topics
web._save_snmp2mqtt_retirement_topics = lambda topics: events.append(("save", len(topics)))
old_topic = "homeassistant/sensor/snmp2mqtt/old_identity/config"
success = web._ensure_snmp2mqtt_running([], 0.0, [old_topic])
assert success["handoff_failed"] is False
assert success["activation_verified"] is True
assert success["mqtt_current_retained"] == 1
assert clears == [[old_topic]]
assert events.index(("scan", 1)) < events.index(("clear", 1))

# If the replacement identity set never appears, old retained identities must
# stay untouched and the Discovery handoff must fail.
events.clear()
clears.clear()
web.scan_mqtt_entities = lambda: {
    "current_expected_count": 1,
    "current_retained_count": 0,
    "current_missing_retained_count": 1,
    "stale_count": 1,
}
failed = web._ensure_snmp2mqtt_running([], 0.0, [old_topic])
assert failed["handoff_failed"] is True
assert failed["activation_verified"] is False
assert clears == []

source = Path(web.__file__).read_text(encoding="utf-8")
assert 'if snmp2mqtt_result.get("handoff_failed"):' in source
assert 'stage="SNMP2MQTT handoff not verified"' in source

# A long multi-switch Discovery run must not age out its own early walk.
root = tmp / "walk-freshness"
walk_dir = root / "snmpwalks" / "SW1"
walk_dir.mkdir(parents=True, exist_ok=True)
walk = walk_dir / "live-full-snmpwalk.txt"
walk.write_text(
    ".1.3.6.1.2.1.2.2.1.8.1 = INTEGER: 1\n",
    encoding="utf-8",
)
now = datetime(2026, 8, 24, 4, 30, 0, tzinfo=timezone.utc)
captured = now - timedelta(minutes=20)
os.utime(walk, (captured.timestamp(), captured.timestamp()))
(root / "last-discovery-run.txt").write_text(
    "Switch Vision Discovery last run\n"
    f"Discovery app loaded: {(now - timedelta(minutes=22)).isoformat()}\n"
    f"Generated: {(now - timedelta(minutes=4)).isoformat()}\n",
    encoding="utf-8",
)
generated_doc = {
    "targets": [
        {
            "name": "SW1",
            "sensors": [
                {
                    "object_id": "sw1_port_1_status",
                    "oid": "1.3.6.1.2.1.2.2.1.8.1",
                }
            ],
        }
    ]
}
bindings = {
    "cards": [
        {
            "discovery_selected_switch": "SW1",
            "sensor_prefix": "sw1",
        }
    ]
}
same_run = correlation.build_port_pipeline(
    root,
    generated_doc,
    [],
    bindings,
    ha_available=False,
    now=now,
)
assert same_run["summary"]["fresh_walk_status_rows"] == 1
assert same_run["summary"]["current_run_walk_status_rows"] == 1
assert same_run["ports"][0]["walk_source_status"] == "fresh"
assert same_run["ports"][0]["walk_current_discovery_run"] is True
assert same_run["ports"][0]["walk_freshness_reason"] == "current_discovery_run"

# The same 20-minute-old walk must remain stale when it predates the recorded
# run window, and malformed run metadata must safely fall back to age.
(root / "last-discovery-run.txt").write_text(
    "Switch Vision Discovery last run\n"
    f"Discovery app loaded: {(now - timedelta(minutes=10)).isoformat()}\n"
    f"Generated: {(now - timedelta(minutes=4)).isoformat()}\n",
    encoding="utf-8",
)
old_walk = correlation.build_port_pipeline(
    root,
    generated_doc,
    [],
    bindings,
    ha_available=False,
    now=now,
)
assert old_walk["summary"]["fresh_walk_status_rows"] == 0
assert old_walk["summary"]["stale_walk_status_rows"] == 1
assert old_walk["ports"][0]["walk_current_discovery_run"] is False
assert old_walk["ports"][0]["walk_freshness_reason"] == "stale"

(root / "last-discovery-run.txt").write_text(
    "Switch Vision Discovery last run\nDiscovery app loaded: not-a-time\nGenerated: also-not-a-time\n",
    encoding="utf-8",
)
malformed = correlation.build_port_pipeline(
    root,
    generated_doc,
    [],
    bindings,
    ha_available=False,
    now=now,
)
assert malformed["summary"]["stale_walk_status_rows"] == 1
assert malformed["ports"][0]["walk_freshness_reason"] == "stale"

print("Switch Vision Discovery v2.2.5 verified handoff + walk freshness regression: PASS")
PYTEST_V225_HANDOFF

# v2.2.5 automatic Support My Switch ordering regression. The shell Discovery
# stage must never build the automatic contribution before the Hub has checked
# the SNMP2MQTT handoff.
PYTHONPATH="$BASE_DIR" python3 - "$tmp_dir" <<'PYTEST_V225_BUNDLE_ORDER'
import json
import os
from pathlib import Path
import stat
import sys

import support_web as web

tmp = Path(sys.argv[1]) / "v225-bundle-order"
tmp.mkdir(parents=True, exist_ok=True)

options = {
    "switches": [],
    "stack_member_prefixes": [],
    "generate_support_my_switch_bundle": True,
    "support_mask_management_ips": True,
    "support_mask_mac_addresses": True,
    "support_mask_hostnames": True,
    "support_mask_vlan_names": False,
    "support_mask_interface_descriptions": False,
    "support_contributor_type": "anonymous",
    "support_contributor_value": "",
}

# A normal Hub run suppresses shell-side automatic capture in the temporary
# snapshot without changing the authoritative saved option.
normal_snapshot = tmp / "normal-options.json"
web._write_authoritative_discovery_options_snapshot(
    normal_snapshot,
    options=options,
)
normal_doc = json.loads(normal_snapshot.read_text(encoding="utf-8"))
assert normal_doc["generate_support_my_switch_bundle"] is False
assert options["generate_support_my_switch_bundle"] is True

# Regeneration is never a contribution-capture action.
web._self_addon_options = lambda: dict(options)
regen_snapshot = tmp / "regen-options.json"
web._write_snmp2mqtt_regeneration_options_snapshot(regen_snapshot)
regen_doc = json.loads(regen_snapshot.read_text(encoding="utf-8"))
assert regen_doc["generate_support_my_switch_bundle"] is False

settings = web._support_settings_from_options(options)
assert settings["mask_management_ips"] is True
assert settings["mask_vlan_names"] is False
assert settings["contributor_type"] == "anonymous"

# The Hub-owned automatic helper preserves only the Support My Switch settings,
# invokes the local support backend, and exposes no backend stdout/private IDs.
support = tmp / "support.sh"
support.write_text(
    "#!/bin/sh\n"
    'printf "%s|%s\n" "$SUPPORT_MASK_MANAGEMENT_IPS" "$SUPPORT_CONTRIBUTOR_TYPE" '
    '>"$CONTRIBUTIONS_DIR/helper-marker.txt"\n',
    encoding="utf-8",
)
support.chmod(support.stat().st_mode | stat.S_IXUSR)
contributions = tmp / "contributions"
web.DEFAULT_SUPPORT_SCRIPT = support
web.DEFAULT_CONTRIBUTIONS_DIR = contributions
os.environ["SWITCH_VISION_DISCOVERY_VERSION"] = "2.2.5"
lines = []
assert web._generate_automatic_support_bundle(settings, lines) is True
assert (contributions / "helper-marker.txt").read_text(encoding="utf-8").strip() == "true|anonymous"
assert any("after the SNMP2MQTT handoff check" in line for line in lines)

source = Path(web.__file__).read_text(encoding="utf-8")
start = source.index("def _run_discovery(")
end = source.index("\ndef _read_supervisor_token(", start)
run_source = source[start:end]
assert run_source.index("_ensure_snmp2mqtt_running(") < run_source.index(
    "_generate_automatic_support_bundle("
)
assert 'snapshot_options["generate_support_my_switch_bundle"] = False' in source
assert 'regenerated["generate_support_my_switch_bundle"] = False' in source

print("Switch Vision Discovery v2.2.5 post-handoff bundle ordering regression: PASS")
PYTEST_V225_BUNDLE_ORDER
