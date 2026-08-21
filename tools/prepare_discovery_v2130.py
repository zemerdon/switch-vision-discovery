#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

support_path = ROOT / "runtime_src/support_web.py"
support = support_path.read_text(encoding="utf-8")
old = "function discoveryStage(state){if(!state.running)return state.success===true?5:-1;if((state.phase||'')==='preparing')return -1;const text=((state.log_tail||[]).join(' ')+' '+(state.message||'')+' '+(state.stage||'')).toLowerCase();if(text.includes('dashboard card')||text.includes('generated dashboard'))return 4;if(text.includes('generated yaml')||text.includes('snmp2mqtt')||text.includes('generator'))return 3;if(text.includes('model/platform')||text.includes('interface mapping')||text.includes('parser summary')||text.includes('exact models'))return 2;if(text.includes('snmp walk')||text.includes('walking')||text.includes('oid trees'))return 1;if(text.includes('configured switches')||text.includes('validating'))return 0;return 0}"
new = "function discoveryStage(state){if(!state.running)return state.success===true?5:-1;if((state.phase||'')==='preparing')return -1;const stage=String(state.stage||'').toLowerCase();if(stage.includes('generating snmp2mqtt yaml'))return 3;if(stage.includes('generating dashboard card yaml'))return 4;if(stage.includes('detecting exact models'))return 2;if(stage.includes('running snmp walks'))return 1;if(stage.includes('validating configured switches'))return 0;const text=((state.activity||'')+' '+(state.command||'')+' '+(state.message||'')+' '+(state.log_tail||[]).slice(-3).join(' ')).toLowerCase();if(text.includes('dashboard card')||text.includes('generated dashboard'))return 4;if(text.includes('generated yaml')||text.includes('snmp2mqtt')||text.includes('generator')||text.includes('write_generated_yaml'))return 3;if(text.includes('model/platform')||text.includes('interface mapping')||text.includes('parser summary')||text.includes('exact models'))return 2;if(text.includes('snmp walk')||text.includes('walking')||text.includes('oid trees'))return 1;if(text.includes('configured switches')||text.includes('validating'))return 0;return 0}"
if old not in support:
    raise SystemExit("ERROR: current Discovery progress-stage function not found")
support = support.replace(old, new, 1)
support_path.write_text(support, encoding="utf-8", newline="\n")

for rel in ("runtime_src/run.sh", "runtime_src/discovery_job.sh"):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    old_version = 'SWITCH_VISION_DISCOVERY_VERSION="2.1.29"'
    if old_version not in text:
        raise SystemExit(f"ERROR: {rel}: current 2.1.29 version not found")
    path.write_text(text.replace(old_version, 'SWITCH_VISION_DISCOVERY_VERSION="2.1.30"', 1), encoding="utf-8", newline="\n")

config_path = ROOT / "switch_vision_discovery/config.yaml"
config = config_path.read_text(encoding="utf-8")
config, count = re.subn(r'(?m)^version:\s*"2\.1\.29"\s*$', 'version: "2.1.30"', config, count=1)
if count != 1:
    raise SystemExit("ERROR: Discovery config version 2.1.29 not found exactly once")
config_path.write_text(config, encoding="utf-8", newline="\n")

self_test_path = ROOT / "runtime_src/self-test.sh"
self_test = self_test_path.read_text(encoding="utf-8")
self_test = self_test.replace('SWITCH_VISION_DISCOVERY_VERSION="2.1.29"', 'SWITCH_VISION_DISCOVERY_VERSION="2.1.30"')
regression = r'''
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
'''
if "v2.1.30 structured progress-stage regression" not in self_test:
    self_test += regression
self_test_path.write_text(self_test, encoding="utf-8", newline="\n")

changelog_path = ROOT / "switch_vision_discovery/CHANGELOG.md"
changelog = changelog_path.read_text(encoding="utf-8")
entry = """## 2.1.30\n\n- Keep the active blue Discovery progress highlight on `Generating SNMP2MQTT YAML` until the structured current stage actually advances to dashboard-card generation.\n- Prioritize the live structured `stage` value over stale historical log-tail text when selecting the progress step.\n- Limit log-tail fallback matching to the most recent lines and preserve all Discovery generation, Huawei visual defaults, atomic YAML publication, mappings, and telemetry unchanged.\n\n"""
if not changelog.startswith("# Changelog\n\n"):
    raise SystemExit("ERROR: unexpected Discovery changelog header")
changelog_path.write_text("# Changelog\n\n" + entry + changelog[len("# Changelog\n\n"):], encoding="utf-8", newline="\n")

print("Prepared Switch Vision Discovery v2.1.30 progress-stage hotfix")
