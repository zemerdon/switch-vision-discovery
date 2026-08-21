#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'runtime_src'
APP = ROOT / 'switch_vision_discovery'
OLD = '2.1.32'
NEW = '2.1.33'


def read(p: Path) -> str: return p.read_text(encoding='utf-8')
def write(p: Path, s: str) -> None: p.write_text(s.replace('\r\n','\n').replace('\r','\n'), encoding='utf-8', newline='\n')
def rep(p: Path, old: str, new: str) -> None:
    s=read(p)
    if old not in s: raise SystemExit(f'missing marker in {p}: {old[:120]!r}')
    write(p,s.replace(old,new,1))

# Versions.
rep(APP/'config.yaml', f'version: "{OLD}"', f'version: "{NEW}"')
for p in (RUNTIME/'run.sh', RUNTIME/'discovery_job.sh'):
    s=read(p)
    s2,n=re.subn(rf'SWITCH_VISION_DISCOVERY_VERSION="{re.escape(OLD)}"', f'SWITCH_VISION_DISCOVERY_VERSION="{NEW}"', s, count=1)
    if n != 1: raise SystemExit(f'version marker missing in {p}')
    write(p,s2)
selftest=RUNTIME/'self-test.sh'
s=read(selftest).replace(f'SWITCH_VISION_DISCOVERY_VERSION="{OLD}"',f'SWITCH_VISION_DISCOVERY_VERSION="{NEW}"')
s=s.replace(f'grep -Fq \'version: "{OLD}"\'',f'grep -Fq \'version: "{NEW}"\'')
write(selftest,s)

p=RUNTIME/'support_web.py'
s=read(p)

# Regeneration-only snapshot: saved Supervisor inventory + saved walks, no network walk.
marker='''def _configured_devices_snapshot(options_file: Path) -> dict[str, Any]:\n'''
helper='''def _write_snmp2mqtt_regeneration_options_snapshot(\n    destination: Path = Path("/tmp/switch_vision_regenerate_options.json"),\n) -> Path:\n    """Prepare a safe stored-walk-only snapshot for SNMP2MQTT YAML regeneration."""\n    options = _self_addon_options()\n    _validate_inventory_identities(options)\n    regenerated = dict(options)\n    rows = regenerated.get("switches")\n    has_inventory = isinstance(rows, list) and any(\n        isinstance(row, dict)\n        and (str(row.get("switch_name") or "").strip() or str(row.get("switch_host") or "").strip())\n        for row in rows\n    )\n    if has_inventory:\n        regenerated["enable_switch_list"] = True\n    regenerated["run_snmp_walks"] = False\n    regenerated["run_live_snmpwalk"] = False\n    regenerated["clean_output_before_walk"] = False\n    regenerated["parse_all_walks"] = True\n    regenerated["generate_snmp2mqtt"] = True\n    regenerated["report_path"] = "/tmp/switch_vision_regenerate_report.txt"\n    regenerated["last_run_summary_path"] = "/tmp/switch_vision_regenerate_summary.txt"\n    regenerated["generated_card_path"] = "/tmp/switch_vision_regenerate_dashboard.yaml"\n    destination.parent.mkdir(parents=True, exist_ok=True)\n    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")\n    try:\n        temporary.write_text(json.dumps(regenerated, indent=2) + "\\n", encoding="utf-8")\n        os.chmod(temporary, 0o600)\n        temporary.replace(destination)\n        os.chmod(destination, 0o600)\n    except OSError as exc:\n        try:\n            temporary.unlink(missing_ok=True)\n        except OSError:\n            pass\n        raise RuntimeError(f"Could not prepare SNMP2MQTT regeneration configuration: {exc}") from exc\n    return destination\n\n\n'''+marker
if marker not in s: raise SystemExit('configured devices marker missing')
s=s.replace(marker,helper,1)

# Generalize the existing Discovery runner so regeneration uses the identical parser/generator.
s=s.replace('def _run_discovery(discovery_script: Path) -> None:\n', 'def _run_discovery(discovery_script: Path, mode: str = "discovery") -> None:\n',1)
needle='''    generated_yaml_previous_topics = _remember_current_snmp2mqtt_topics() if generated_yaml_previous_mtime is not None else _load_snmp2mqtt_retirement_topics()\n    _set_discovery_state(\n'''
insert='''    generated_yaml_previous_topics = _remember_current_snmp2mqtt_topics() if generated_yaml_previous_mtime is not None else _load_snmp2mqtt_retirement_topics()\n    regenerate_only = mode == "regenerate_yaml"\n    operation_name = "SNMP2MQTT YAML regeneration" if regenerate_only else "Discovery"\n    preparing_message = "Preparing SNMP2MQTT YAML regeneration" if regenerate_only else "Preparing Discovery"\n    preparing_activity = "Loading saved Discovery data and SNMP walks" if regenerate_only else "Validating configured switches"\n    waiting_message = "Waiting for YAML regeneration to complete" if regenerate_only else "Waiting for Discovery to complete"\n    _set_discovery_state(\n'''
if needle not in s: raise SystemExit('runner setup marker missing')
s=s.replace(needle,insert,1)
s=s.replace('''        message="Preparing Discovery",\n        log_tail=[],\n        stage="Preparing Discovery",\n''','''        message=preparing_message,\n        log_tail=[],\n        stage=preparing_message,\n        mode=mode,\n''',1)
s=s.replace('''        activity="Validating configured switches",\n        phase="preparing",\n        snmp2mqtt={"status": "Waiting", "action": "none", "slug": None, "state": None, "message": "Waiting for Discovery to complete"},\n''','''        activity=preparing_activity,\n        phase="preparing",\n        snmp2mqtt={"status": "Waiting", "action": "none", "slug": None, "state": None, "message": waiting_message},\n''',1)
s=s.replace('''        options_snapshot = _write_authoritative_discovery_options_snapshot()\n        discovery_env = os.environ.copy()\n        discovery_env["SWITCH_VISION_OPTIONS_FILE"] = str(options_snapshot)\n        with log_path.open("a", encoding="utf-8") as log_file:\n            log_file.write(f"\\n=== Discovery started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\\n")\n            log_file.write("Discovery configuration: authoritative Supervisor snapshot\\n")\n''','''        options_snapshot = (\n            _write_snmp2mqtt_regeneration_options_snapshot()\n            if regenerate_only\n            else _write_authoritative_discovery_options_snapshot()\n        )\n        discovery_env = os.environ.copy()\n        discovery_env["SWITCH_VISION_OPTIONS_FILE"] = str(options_snapshot)\n        if regenerate_only:\n            discovery_env["SWITCH_VISION_CAPABILITIES_DIR"] = "/tmp/switch_vision_regenerate_capabilities"\n        with log_path.open("a", encoding="utf-8") as log_file:\n            action_label = "SNMP2MQTT YAML regeneration" if regenerate_only else "Discovery"\n            log_file.write(f"\\n=== {action_label} started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\\n")\n            log_file.write(\n                "Discovery configuration: stored-walk regeneration snapshot\\n"\n                if regenerate_only\n                else "Discovery configuration: authoritative Supervisor snapshot\\n"\n            )\n''',1)
s=s.replace('''            lines.append("Discovery stopped by user request.")\n            _set_discovery_state(\n                success=None,\n                message="Discovery stopped",\n                stage="Stopped",\n                activity="Discovery stopped by user",\n''','''            stopped_label = "YAML regeneration" if regenerate_only else "Discovery"\n            lines.append(f"{stopped_label} stopped by user request.")\n            _set_discovery_state(\n                success=None,\n                message=f"{stopped_label} stopped",\n                stage="Stopped",\n                activity=f"{stopped_label} stopped by user",\n''',1)
s=s.replace('raise RuntimeError(f"Discovery exited with code {return_code}.")','raise RuntimeError(f"{operation_name} exited with code {return_code}.")',1)
s=s.replace('auto_message = "Discovery complete"','auto_message = "SNMP2MQTT YAML regeneration complete" if regenerate_only else "Discovery complete"',1)
s=s.replace('_release_operation("Discovery")\n\n\n\n\n\ndef _read_supervisor_token', '_release_operation(operation_name)\n\n\n\n\n\ndef _read_supervisor_token',1)

# Route for the secondary action.
route='''        if path == "/api/discovery/start":\n'''
newroute='''        if path == "/api/discovery/regenerate-yaml":\n            operation_name = "SNMP2MQTT YAML regeneration"\n            try:\n                _claim_operation(operation_name)\n            except OperationConflict as exc:\n                self._json({"error": str(exc)}, HTTPStatus.CONFLICT)\n                return\n            _DISCOVERY_STOP_REQUESTED.clear()\n            _set_discovery_state(\n                running=True,\n                started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),\n                finished_at=None,\n                success=None,\n                message="Preparing SNMP2MQTT YAML regeneration",\n                log_tail=[],\n                stage="Preparing SNMP2MQTT YAML regeneration",\n                switch="",\n                target="",\n                command="",\n                activity="Loading saved Discovery data and SNMP walks",\n                phase="preparing",\n                mode="regenerate_yaml",\n                snmp2mqtt={"status": "Waiting", "action": "none", "slug": None, "state": None, "message": "Waiting for YAML regeneration to complete"},\n            )\n            thread = threading.Thread(\n                target=_run_discovery,\n                args=(self.app.discovery_script, "regenerate_yaml"),\n                daemon=True,\n            )\n            try:\n                thread.start()\n            except Exception:\n                _release_operation(operation_name)\n                raise\n            self._json({"started": True, "mode": "regenerate_yaml"}, HTTPStatus.ACCEPTED)\n            return\n        if path == "/api/discovery/start":\n'''
if route not in s: raise SystemExit('discovery start route missing')
s=s.replace(route,newroute,1)
# Normal route identifies its mode too.
s=s.replace('''                message="Preparing Discovery",\n                log_tail=[],\n                stage="Preparing Discovery",\n                switch="",\n''','''                message="Preparing Discovery",\n                log_tail=[],\n                stage="Preparing Discovery",\n                mode="discovery",\n                switch="",\n''',1)

# UI button + helper/status.
oldhtml='''<div class="actions"><button class="primary" id="runDiscoveryButton" type="button">Run Discovery</button><button id="stopDiscoveryButton" type="button" disabled>Stop Discovery</button><button id="viewResultsButton" type="button">View Results</button><button id="toggleDebugButton" type="button">Show Debug</button></div>\n'''
newhtml='''<div class="actions"><button class="primary" id="runDiscoveryButton" type="button">Run Discovery</button><button id="regenerateYamlButton" type="button">Regenerate SNMP2MQTT YAML</button><button id="stopDiscoveryButton" type="button" disabled>Stop Discovery</button><button id="viewResultsButton" type="button">View Results</button><button id="toggleDebugButton" type="button">Show Debug</button></div>\n<p class="muted">Regenerate SNMP2MQTT YAML uses the existing saved Discovery data and SNMP walks. No new SNMP walks are performed.</p>\n<p id="regenerateYamlStatus" class="muted"></p>\n'''
if oldhtml not in s: raise SystemExit('discovery actions html missing')
s=s.replace(oldhtml,newhtml,1)

# UI state: disable both start actions while either operation is running and label regeneration clearly.
oldshow="function showDiscovery(d){const state=d||{};lastDiscoveryState=state;const running=!!state.running;const phase=state.phase||(running?'running':(state.success===true?'complete':(state.success===false?'failed':'idle')));const preparing=running&&phase==='preparing';const stopping=running&&phase==='stopping';const active=running&&!preparing&&!stopping;const btn=$('runDiscoveryButton');const stopBtn=$('stopDiscoveryButton');btn.disabled=running;"
newshow="function showDiscovery(d){const state=d||{};lastDiscoveryState=state;const running=!!state.running;const regen=state.mode==='regenerate_yaml';const phase=state.phase||(running?'running':(state.success===true?'complete':(state.success===false?'failed':'idle')));const preparing=running&&phase==='preparing';const stopping=running&&phase==='stopping';const active=running&&!preparing&&!stopping;const btn=$('runDiscoveryButton');const regenBtn=$('regenerateYamlButton');const stopBtn=$('stopDiscoveryButton');btn.disabled=running;regenBtn.disabled=running;"
if oldshow not in s: raise SystemExit('showDiscovery start marker missing')
s=s.replace(oldshow,newshow,1)
# Preserve normal progress logic but replace user-facing labels when this is regeneration.
s=s.replace("btn.textContent=preparing?'Preparing…':(stopping?'Stopping…':(active?'Discovery Running…':'Run Discovery'));stopBtn.disabled", "btn.textContent=preparing&&!regen?'Preparing…':(stopping?'Stopping…':(active&&!regen?'Discovery Running…':'Run Discovery'));regenBtn.textContent=regen&&preparing?'Preparing…':(regen&&active?'Regenerating…':'Regenerate SNMP2MQTT YAML');stopBtn.disabled",1)
s=s.replace("if(preparing)label='Preparing Discovery';else if(stopping)label='Stopping Discovery';else if(active)label='Discovery running';else if(phase==='stopped')label='Discovery stopped';else if(state.success===true)label='Discovery complete';else if(state.success===false)label=`Discovery failed: ${state.message||'Unknown error'}`;", "if(preparing)label=regen?'Preparing SNMP2MQTT YAML regeneration':'Preparing Discovery';else if(stopping)label=regen?'Stopping YAML regeneration':'Stopping Discovery';else if(active)label=regen?'Regenerating SNMP2MQTT YAML':'Discovery running';else if(phase==='stopped')label=regen?'YAML regeneration stopped':'Discovery stopped';else if(state.success===true)label=regen?'SNMP2MQTT YAML regeneration complete':'Discovery complete';else if(state.success===false)label=`${regen?'YAML regeneration':'Discovery'} failed: ${state.message||'Unknown error'}`;",1)

oldjs="async function runDiscovery(){const btn=$('runDiscoveryButton');btn.disabled=true;$('discoveryStatus').textContent='Preparing Discovery';try{const r=await fetch(endpoint('api/discovery/start'),{method:'POST'});"
newjs="async function regenerateSnmp2mqttYaml(){const btn=$('regenerateYamlButton');const status=$('regenerateYamlStatus');btn.disabled=true;status.textContent='Preparing stored-walk YAML regeneration…';try{const r=await fetch(endpoint('api/discovery/regenerate-yaml'),{method:'POST'});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not start YAML regeneration');status.textContent='Regeneration started. Existing saved walks are being reprocessed; no SNMP walks will run.';await refresh()}catch(e){status.textContent=`Could not regenerate SNMP2MQTT YAML: ${e.message||e}`;btn.disabled=false}}\nasync function runDiscovery(){const btn=$('runDiscoveryButton');btn.disabled=true;$('discoveryStatus').textContent='Preparing Discovery';try{const r=await fetch(endpoint('api/discovery/start'),{method:'POST'});"
if oldjs not in s: raise SystemExit('runDiscovery JS marker missing')
s=s.replace(oldjs,newjs,1)
s=s.replace("$('runDiscoveryButton').addEventListener('click',runDiscovery);$('stopDiscoveryButton')", "$('runDiscoveryButton').addEventListener('click',runDiscovery);$('regenerateYamlButton').addEventListener('click',regenerateSnmp2mqttYaml);$('stopDiscoveryButton')",1)
write(p,s)

# Changelog.
ch=APP/'CHANGELOG.md'
body=read(ch)
entry='''# Changelog\n\n## 2.1.33\n\n- Add **Regenerate SNMP2MQTT YAML** beside Run Discovery in Switch Vision Hub.\n- Regeneration performs no new SNMP walks; it reuses the authoritative saved switch inventory and existing saved walk files.\n- Enabled switch folders remain authoritative, so disabled saved devices are not silently resurrected.\n- Reuse the normal v2.1.31 parser/generator, candidate validation and atomic publication path instead of introducing a second YAML generator.\n- Redirect regeneration-only report, capability and dashboard-card outputs to temporary files; only the configured SNMP2MQTT YAML may publish.\n- Apply/restart Switch Vision SNMP2MQTT only when a valid changed YAML is successfully published, preserving the previous known-good YAML on failure.\n\n'''
if body.startswith('# Changelog\n\n'):
    write(ch,entry+body[len('# Changelog\n\n'):])
else: raise SystemExit('changelog header missing')
print('Prepared Switch Vision Discovery v2.1.33 stored-walk YAML regeneration')
