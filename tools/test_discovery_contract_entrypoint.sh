#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUNTIME="$ROOT/runtime_src"
REGISTRY="$RUNTIME/opt/switch-vision/devices/supported_devices.json"
ENTRYPOINT="$RUNTIME/discovery_contract_entrypoint.py"
PREPARE="$RUNTIME/physical_contract_prepare.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

make_dell_walk() {
  path=$1
  ports=$2
  {
    echo '.1.3.6.1.2.1.1.1.0 = STRING: "Dell Networking PowerConnect 5548P"'
    echo '.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.674.10895.3057'
    idx=1
    port=1
    while [ "$port" -le "$ports" ]; do
      printf '.1.3.6.1.2.1.31.1.1.1.1.%s = STRING: "gi1/0/%s"\n' "$idx" "$port"
      printf '.1.3.6.1.2.1.2.2.1.8.%s = INTEGER: up(1)\n' "$idx"
      idx=$((idx + 1)); port=$((port + 1))
    done
    if [ "$ports" -eq 48 ]; then
      port=1
      while [ "$port" -le 2 ]; do
        printf '.1.3.6.1.2.1.31.1.1.1.1.%s = STRING: "te1/0/%s"\n' "$idx" "$port"
        printf '.1.3.6.1.2.1.2.2.1.8.%s = INTEGER: up(1)\n' "$idx"
        idx=$((idx + 1)); port=$((port + 1))
      done
    fi
  } > "$path"
}

run_entrypoint() {
  case_dir=$1
  options=$2
  SWITCH_VISION_OPTIONS_FILE="$options" \
  SWITCH_VISION_LEGACY_DISCOVERY_SCRIPT="$RUNTIME/discovery_job.sh" \
  SWITCH_VISION_PHYSICAL_PREPARE="$PREPARE" \
  SWITCH_VISION_DEVICE_REGISTRY="$REGISTRY" \
  SWITCH_VISION_CAPABILITIES_DIR="$case_dir/published-capabilities" \
  SWITCH_VISION_SHARE_DIR="$case_dir/share" \
  SWITCH_VISION_RUNTIME_DIR="$RUNTIME" \
  "$ENTRYPOINT"
}

# Positive path: the exact Web-UI entrypoint must repair the production parser
# boundary and preserve the public report/YAML contract.
ok="$TMP/ok"
mkdir -p "$ok/walks" "$ok/live" "$ok/share"
walk="$ok/dell.txt"
make_dell_walk "$walk" 48
printf '%s,192.0.2.10,DELL,readonly,,Dell\n' "$(basename "$walk")" > "$ok/targets.csv"
cat > "$ok/options.json" <<EOF
{
  "input_path": "$walk",
  "snmpwalks_dir": "$ok/walks",
  "report_path": "$ok/report.txt",
  "run_snmp_walks": "false",
  "enable_switch_list": "false",
  "parse_all_walks": "true",
  "generate_snmp2mqtt": "true",
  "targets_csv": "$ok/targets.csv",
  "last_run_summary_path": "$ok/summary.txt",
  "generated_yaml_path": "$ok/generated.yaml",
  "generated_card_path": "$ok/card.yaml",
  "snmp_log_path": "$ok/discovery.log",
  "live_output_dir": "$ok/live",
  "live_output_path": "$ok/live/live-targeted-snmpwalk.txt",
  "generate_support_my_switch_bundle": "false"
}
EOF
if ! run_entrypoint "$ok" "$ok/options.json" > "$ok/stdout.txt" 2> "$ok/stderr.txt"; then
  echo 'FAIL: positive entrypoint path exited non-zero' >&2
  echo '--- entrypoint stdout ---' >&2
  cat "$ok/stdout.txt" >&2 || true
  echo '--- entrypoint stderr ---' >&2
  cat "$ok/stderr.txt" >&2 || true
  exit 1
fi
for assertion in \
  'Model/platform: PowerConnect 5548P' \
  '- Physical switch interfaces detected: 50' \
  '- Mapped physical interfaces: 50'; do
  if ! grep -Fq -- "$assertion" "$ok/report.txt"; then
    echo "FAIL: report missing: $assertion" >&2
    cat "$ok/report.txt" >&2 || true
    exit 1
  fi
done
if [ "$(grep -Ec '^  - oid: 1\.3\.6\.1\.2\.1\.2\.2\.1\.8\.[0-9]+$' "$ok/generated.yaml")" -ne 50 ]; then
  echo 'FAIL: generated YAML does not contain 50 status sensors' >&2
  sed -n '1,220p' "$ok/generated.yaml" >&2 || true
  exit 1
fi
grep -Fq '# Detected model: PowerConnect 5548P' "$ok/generated.yaml" || {
  echo 'FAIL: generated YAML model was not patched to exact registry model' >&2
  sed -n '1,120p' "$ok/generated.yaml" >&2 || true
  exit 1
}
find "$ok/published-capabilities" -name '*-physical-contract.json' -type f | grep -q . || {
  echo 'FAIL: physical contract was not published' >&2
  find "$ok" -maxdepth 3 -type f -print >&2 || true
  exit 1
}

echo 'entrypoint positive path: PASS'

# Mixed-device regression: a resolved HP 3500yl contract can legitimately
# use a fallback/generated card even when registry dashboard_support is false.
# It must still count toward generated SNMP card cardinality alongside two
# resolved Dell N2128PX-ON switches, or the Hub can falsely degrade the run
# and block the SNMP2MQTT restart/handoff.
python3 - "$ENTRYPOINT" <<'PY_MIXED_CARDINALITY'
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
entrypoint = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("sv_discovery_contract_entrypoint_mixed", entrypoint)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ordered = [
    {"contract": {"status": "resolved", "device": {"model": "HP J8693A Switch 3500yl-48G", "dashboard_support": False}, "observed": {"members": 1}}},
    {"contract": {"status": "resolved", "device": {"model": "N2128PX-ON", "dashboard_support": True}, "observed": {"members": 1}}},
    {"contract": {"status": "resolved", "device": {"model": "N2128PX-ON", "dashboard_support": True}, "observed": {"members": 1}}},
]
expected = module._expected_generated_snmp_cards(ordered)
assert expected == 3, f"Mixed HP + 2 Dell run must expect 3 cards, got {expected}"
PY_MIXED_CARDINALITY
echo 'entrypoint mixed HP + 2 Dell cardinality: PASS'

# Negative path: an exact registered model with incomplete physical evidence
# must fail closed rather than silently drawing a smaller switch.
conflict="$TMP/conflict"
mkdir -p "$conflict/walks" "$conflict/live" "$conflict/share"
conflict_walk="$conflict/dell-incomplete.txt"
make_dell_walk "$conflict_walk" 47
printf '%s,192.0.2.11,DELLBAD,readonly,,DellBad\n' "$(basename "$conflict_walk")" > "$conflict/targets.csv"
cat > "$conflict/options.json" <<EOF
{
  "input_path": "$conflict_walk",
  "snmpwalks_dir": "$conflict/walks",
  "report_path": "$conflict/report.txt",
  "run_snmp_walks": "false",
  "enable_switch_list": "false",
  "parse_all_walks": "true",
  "generate_snmp2mqtt": "true",
  "targets_csv": "$conflict/targets.csv",
  "last_run_summary_path": "$conflict/summary.txt",
  "generated_yaml_path": "$conflict/generated.yaml",
  "generated_card_path": "$conflict/card.yaml",
  "snmp_log_path": "$conflict/discovery.log",
  "live_output_dir": "$conflict/live",
  "live_output_path": "$conflict/live/live-targeted-snmpwalk.txt",
  "generate_support_my_switch_bundle": "false"
}
EOF
set +e
run_entrypoint "$conflict" "$conflict/options.json" > "$conflict/stdout.txt" 2> "$conflict/stderr.txt"
conflict_status=$?
set -e
if [ "$conflict_status" -ne 0 ]; then
  echo "FAIL: reachable registered topology conflict exited $conflict_status instead of fail-soft success" >&2
  cat "$conflict/stdout.txt" >&2 || true
  cat "$conflict/stderr.txt" >&2 || true
  exit 1
fi
grep -Fq 'Complete with warnings' "$conflict/stdout.txt" || {
  echo 'FAIL: topology conflict did not surface warning state' >&2
  exit 1
}
grep -Fq 'SV_RESULT|warnings=true|degraded=true' "$conflict/stdout.txt" || {
  echo 'FAIL: topology conflict did not mark display-only degraded success' >&2
  exit 1
}
[ ! -s "$conflict/generated.yaml" ] || {
  echo 'FAIL: topology conflict produced untrusted SNMP2MQTT YAML' >&2
  exit 1
}
grep -Fq 'type: custom:switch-vision-3650' "$conflict/card.yaml" || {
  echo 'FAIL: registered topology conflict did not keep a diagnosable card' >&2
  exit 1
}
grep -Fq 'Support My Switch' "$conflict/card.yaml" || {
  echo 'FAIL: registered topology conflict did not include contribution guidance' >&2
  exit 1
}

echo 'entrypoint registered-topology fail-soft display guard: PASS'

# Downstream/cardinality failure: validated physical evidence must survive and
# the executable entrypoint must return the reserved degraded exit code 10.
mismatch="$TMP/card-mismatch"
mkdir -p "$mismatch/walks" "$mismatch/published-capabilities"
cat > "$mismatch/walks/synthetic.txt" <<'EOF_MISMATCH_WALK'
.1.3.6.1.2.1.31.1.1.1.1.1 = STRING: "Gi1/0/1"
.1.3.6.1.2.1.2.2.1.8.1 = INTEGER: up(1)
EOF_MISMATCH_WALK
cat > "$mismatch/registry.json" <<'EOF_MISMATCH_REGISTRY'
{"devices":[]}
EOF_MISMATCH_REGISTRY
cat > "$mismatch/fake-prepare.sh" <<'EOF_MISMATCH_PREPARE'
#!/usr/bin/env sh
set -eu
source=$1
destination=$2
capability=$3
contract=$4
cp "$source" "$destination"
printf '{}\n' > "$capability"
cat > "$contract" <<'JSON'
{
  "status": "resolved",
  "device": {
    "model": "Synthetic Stack",
    "dashboard_support": true
  },
  "observed": {
    "physical": 1,
    "members": 2
  }
}
JSON
EOF_MISMATCH_PREPARE
chmod +x "$mismatch/fake-prepare.sh"
cat > "$mismatch/fake-legacy.sh" <<'EOF_MISMATCH_LEGACY'
#!/usr/bin/env sh
set -eu
python3 - "$SWITCH_VISION_OPTIONS_FILE" <<'PY_MISMATCH_LEGACY'
import json
import sys
from pathlib import Path
options = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
Path(options["report_path"]).write_text("Single walk: synthetic\n", encoding="utf-8")
Path(options["generated_yaml_path"]).write_text(
    "# Device source: synthetic\n# Detected model: Synthetic Stack\n",
    encoding="utf-8",
)
Path(options["generated_card_path"]).write_text(
    "- type: custom:switch-vision-3650\n  title: Synthetic member 1\n",
    encoding="utf-8",
)
PY_MISMATCH_LEGACY
EOF_MISMATCH_LEGACY
chmod +x "$mismatch/fake-legacy.sh"
cat > "$mismatch/options.json" <<EOF_MISMATCH_OPTIONS
{
  "input_path": "$mismatch/walks/synthetic.txt",
  "snmpwalks_dir": "$mismatch/walks",
  "report_path": "$mismatch/report.txt",
  "run_snmp_walks": "false",
  "parse_all_walks": "true",
  "generate_snmp2mqtt": "true",
  "generated_yaml_path": "$mismatch/generated.yaml",
  "generated_card_path": "$mismatch/card.yaml",
  "generate_support_my_switch_bundle": "false"
}
EOF_MISMATCH_OPTIONS
set +e
SWITCH_VISION_OPTIONS_FILE="$mismatch/options.json" \
SWITCH_VISION_LEGACY_DISCOVERY_SCRIPT="$mismatch/fake-legacy.sh" \
SWITCH_VISION_PHYSICAL_PREPARE="$mismatch/fake-prepare.sh" \
SWITCH_VISION_DEVICE_REGISTRY="$mismatch/registry.json" \
SWITCH_VISION_CAPABILITIES_DIR="$mismatch/published-capabilities" \
"$ENTRYPOINT" > "$mismatch/stdout.txt" 2> "$mismatch/stderr.txt"
mismatch_status=$?
set -e
if [ "$mismatch_status" -ne 10 ]; then
  echo "FAIL: card-count mismatch exited $mismatch_status instead of degraded code 10" >&2
  cat "$mismatch/stdout.txt" >&2 || true
  cat "$mismatch/stderr.txt" >&2 || true
  exit 1
fi
grep -Fq 'Generated SNMP card count mismatch: expected 2, found 1.' "$mismatch/stdout.txt" || {
  echo 'FAIL: card-count mismatch did not report the degraded cardinality reason' >&2
  cat "$mismatch/stdout.txt" >&2 || true
  exit 1
}
find "$mismatch/published-capabilities" -name '*-physical-contract.json' -type f | grep -q . || {
  echo 'FAIL: degraded card-count mismatch discarded validated physical evidence' >&2
  find "$mismatch" -maxdepth 3 -type f -print >&2 || true
  exit 1
}
echo 'entrypoint degraded cardinality/evidence contract: PASS'

# Mixed current-run staging keeps unresolved/non-switch targets out of exact
# telemetry generation while a resolved physical switch continues. Main runtime
# later turns reachable unsupported evidence into display-only fallback/CTA;
# genuine resolver exceptions remain software faults.
python3 - "$ENTRYPOINT" "$TMP" <<'PY'
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

entrypoint = Path(sys.argv[1])
root = Path(sys.argv[2]) / "mixed-current-run"
root.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("sv_discovery_contract_entrypoint", entrypoint)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

supported = root / "supported.txt"
unsupported = root / "unsupported.txt"
supported.write_text('.1.3.6.1.2.1.31.1.1.1.1.1 = STRING: "Gi1/0/1"\n', encoding="utf-8")
unsupported.write_text('.1.3.6.1.2.1.31.1.1.1.1.1 = STRING: "eth0"\n', encoding="utf-8")

options = {
    "switches": [
        {"switch_name": "supported", "output_dir": "/should/be/replaced"},
        {"switch_name": "unsupported", "output_dir": "/must/not/survive"},
        {"switch_name": "2960x-48p", "display_name": "SW7 2960X 48P", "sensor_prefix": "sw7", "switch_host": "192.0.2.23"},
    ],
    "stack_member_prefixes": [
        {"switch_name": "supported", "member": "1"},
        {"switch_name": "unsupported", "member": "1"},
        {"switch_name": "2960x-48p", "member": "1"},
    ],
    "input_path": str(unsupported),
}
records = [
    {"walk": str(supported), "switch": "supported", "host": "192.0.2.21", "prefix": "GOOD", "community": "readonly"},
    {"walk": str(unsupported), "switch": "unsupported", "host": "192.0.2.22", "prefix": "SKIP", "community": "readonly"},
]

def resolved_prepare(source: Path, destination: Path, work: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    if source.name == "unsupported.txt":
        return None
    return {
        "source": source,
        "destination": destination,
        "capability": work / "cap.json",
        "contract_path": work / "contract.json",
        "contract": {"status": "resolved"},
    }

module._prepare_walk = resolved_prepare
staged, ordered, accepted_evidence = module._stage_options(options, root / "work", records)
assert len(accepted_evidence) == 1, accepted_evidence
assert len(ordered) == 1, ordered
assert [row["switch_name"] for row in staged["switches"]] == ["supported"], staged["switches"]
assert [row["switch_name"] for row in staged["dashboard_switches"]] == ["supported", "2960x-48p"], staged["dashboard_switches"]
assert [row["switch_name"] for row in staged["stack_member_prefixes"]] == ["supported"], staged["stack_member_prefixes"]
assert [row["switch_name"] for row in staged["dashboard_stack_member_prefixes"]] == ["supported", "2960x-48p"], staged["dashboard_stack_member_prefixes"]
assert module._expected_generated_dashboard_cards(staged) == 2, staged
targets = Path(staged["targets_csv"]).read_text(encoding="utf-8")
assert "supported" in targets
assert "unsupported" not in targets
assert staged["input_path"].endswith("supported.txt"), staged["input_path"]
assert not (root / "work" / "snmpwalks" / "unsupported" / "unsupported.txt").exists()

module._prepare_walk = lambda source, destination, work: None
staged, ordered, accepted_evidence = module._stage_options(options, root / "all-unresolved", records)
assert not ordered, ordered
assert not accepted_evidence, accepted_evidence
assert staged["switches"] == [], staged["switches"]
assert [row["switch_name"] for row in staged["dashboard_switches"]] == ["2960x-48p"], staged["dashboard_switches"]

def fatal_prepare(source: Path, destination: Path, work: Path):
    raise RuntimeError("synthetic topology conflict")

module._prepare_walk = fatal_prepare
try:
    module._stage_options(options, root / "fatal", records[:1])
except RuntimeError as exc:
    assert "synthetic topology conflict" in str(exc)
else:
    raise AssertionError("topology-conflict exception was swallowed")

# Explicit unsupported-device best-fit contract: observed topology may select only
# a neutral stock visual, must preserve exact observed counts, and must tell the
# user how to contribute for exact support.
fallback_dir = root / "best-fit"
fallback_dir.mkdir(parents=True, exist_ok=True)
fallback_source = fallback_dir / "walks" / "unknown" / "live-targeted-snmpwalk.txt"
fallback_source.parent.mkdir(parents=True, exist_ok=True)
fallback_source.write_text('.1.3.6.1.2.1.31.1.1.1.1.1 = STRING: "ether1"\n', encoding="utf-8")
fallback_info = {
    "source": fallback_source,
    "contract": {
        "status": "unregistered",
        "device": {"model": "Example Unknown 8+2", "registry_match": False},
        "observed": {"physical": 10, "rj45": 8, "uplinks": 2, "members": 1},
        "ports": [
            *[{"physical_id": f"m1:rj45:{i}", "media": "rj45"} for i in range(1, 9)],
            *[{"physical_id": f"m1:uplink:{i}", "media": "sfp_plus"} for i in range(1, 3)],
        ],
    },
}
fallback_card = fallback_dir / "card.yaml"
fallback_options = {
    "switches": [{"switch_name": "unknown", "display_name": "Unknown Lab Switch", "switch_host": "192.0.2.60", "sensor_prefix": "UNKNOWN"}]
}
cards, notices = module._append_display_fallbacks(fallback_card, [fallback_info], fallback_options)
text = fallback_card.read_text(encoding="utf-8")
assert cards == 1 and notices == 1
assert "calibration_profile: \"stock_24rj45_2sfp\"" in text
assert "port_count: 8" in text and "sfp_port_count: 2" in text
assert "Support My Switch" in text
assert "Best-fit unsupported-model visual" in text
print("entrypoint unsupported best-fit + contribution CTA: PASS")

print("entrypoint mixed current-run exclusion: PASS")
PY

# Current-run partial regression at the full physical-contract wrapper boundary.
# A temporarily unreachable saved switch must stay in the generated Dashboard
# Card inventory, while SNMP2MQTT telemetry remains restricted to the switch
# with validated current-run evidence. This is the SW7 / 2960X-48P failure mode
# reported from a real contribution bundle.
retain="$TMP/dashboard-retain"
mkdir -p "$retain/bin" "$retain/walks" "$retain/share" "$retain/live"
make_dell_walk "$retain/dell.txt" 48
cat > "$retain/bin/snmpwalk" <<'EOF_RETAIN_SNMP'
#!/usr/bin/env sh
set -eu
host=""
for arg in "$@"; do
  case "$arg" in 192.0.2.*) host="$arg";; esac
done
[ "$host" = "192.0.2.71" ] || exit 1
cat "${SV_TEST_SNMP_SOURCE:?}"
EOF_RETAIN_SNMP
chmod +x "$retain/bin/snmpwalk"
cat > "$retain/options.json" <<EOF_RETAIN_OPTIONS
{
  "snmpwalks_dir": "$retain/walks",
  "report_path": "$retain/report.txt",
  "run_snmp_walks": "true",
  "enable_switch_list": "true",
  "parse_all_walks": "false",
  "generate_snmp2mqtt": "true",
  "switches": [
    {"switch_name":"working","display_name":"Working Switch","switch_host":"192.0.2.71","sensor_prefix":"GOOD","snmp_community":"readonly","enabled":"enabled","walk_mode":"targeted","switch_model":"auto","card_header_title":""},
    {"switch_name":"2960x-48p","display_name":"SW7 2960X 48P","switch_host":"192.0.2.72","sensor_prefix":"sw7","snmp_community":"readonly","enabled":"enabled","walk_mode":"targeted","switch_model":"auto","card_header_title":""}
  ],
  "stack_member_prefixes": [],
  "last_run_summary_path": "$retain/summary.txt",
  "generated_yaml_path": "$retain/generated.yaml",
  "generated_card_path": "$retain/card.yaml",
  "snmp_log_path": "$retain/discovery.log",
  "live_output_dir": "$retain/live",
  "live_output_path": "$retain/live/live-targeted-snmpwalk.txt",
  "minimum_valid_walk_lines": "1",
  "clean_output_before_walk": "false",
  "generate_support_my_switch_bundle": "false"
}
EOF_RETAIN_OPTIONS
if ! PATH="$retain/bin:$PATH" SV_TEST_SNMP_SOURCE="$retain/dell.txt" run_entrypoint "$retain" "$retain/options.json" > "$retain/stdout.txt" 2> "$retain/stderr.txt"; then
  echo 'FAIL: partial wrapper dashboard-retention path exited non-zero' >&2
  cat "$retain/stdout.txt" >&2 || true
  cat "$retain/stderr.txt" >&2 || true
  exit 1
fi
card_count=$(grep -c '^      - type: custom:switch-vision-3650$' "$retain/card.yaml" || true)
[ "$card_count" -eq 2 ] || {
  echo "FAIL: expected two saved Dashboard Card rows after partial SNMP run, found $card_count" >&2
  cat "$retain/card.yaml" >&2 || true
  exit 1
}
grep -Fq 'Working Switch' "$retain/card.yaml" || { echo 'FAIL: responding saved switch missing from Dashboard Card' >&2; cat "$retain/card.yaml" >&2; exit 1; }
grep -Fq 'SW7 2960X 48P' "$retain/card.yaml" || { echo 'FAIL: failed SW7 saved switch was dropped from Dashboard Card' >&2; cat "$retain/card.yaml" >&2; exit 1; }
grep -Fq 'sensor.sw7_model' "$retain/card.yaml" || { echo 'FAIL: retained SW7 card lost its configured sensor prefix' >&2; cat "$retain/card.yaml" >&2; exit 1; }
grep -Fq '192.0.2.71' "$retain/generated.yaml" || { echo 'FAIL: responding switch telemetry missing from generated YAML' >&2; cat "$retain/generated.yaml" >&2; exit 1; }
if grep -Fq '192.0.2.72' "$retain/generated.yaml" || grep -Fq '# Prefix: sw7' "$retain/generated.yaml"; then
  echo 'FAIL: failed SW7 target leaked into generated telemetry' >&2
  cat "$retain/generated.yaml" >&2 || true
  exit 1
fi
grep -Fq 'SV_RESULT|warnings=true|degraded=false' "$retain/stdout.txt" || {
  echo 'FAIL: partial wrapper run did not complete fail-soft with warnings' >&2
  cat "$retain/stdout.txt" >&2 || true
  exit 1
}
echo 'entrypoint partial run retains saved Dashboard Card inventory but filters telemetry: PASS'

# Live partial/all-fail regression uses the real legacy runtime with a fake
# snmpwalk. Stale full-walk files remain physically present while current
# targeted attempts run, proving only CURRENT_RUN_WALKS is consumed.
live="$TMP/live-exit"
mkdir -p "$live/bin"
make_dell_walk "$live/dell.txt" 48
cat > "$live/bin/snmpwalk" <<'EOF_SNMP'
#!/usr/bin/env sh
set -eu
host=""
for arg in "$@"; do
  case "$arg" in 192.0.2.*) host="$arg";; esac
done
[ "$host" = "192.0.2.31" ] || exit 1
cat "${SV_TEST_SNMP_SOURCE:?}"
EOF_SNMP
chmod +x "$live/bin/snmpwalk"

run_live_case() {
  name=$1; good=$2
  case_dir="$live/$name"
  mkdir -p "$case_dir/walks/one" "$case_dir/walks/two" "$case_dir/caps" "$case_dir/share"
  for sw in one two; do
    cat > "$case_dir/walks/$sw/live-full-snmpwalk.txt" <<'EOF_STALE'
# STALE_HISTORICAL_WALK_MUST_NOT_PARSE
.1.3.6.1.2.1.31.1.1.1.1.99 = STRING: "Gi9/9/9"
EOF_STALE
  done
  if [ "$good" = yes ]; then h1=192.0.2.31; h2=192.0.2.32; else h1=192.0.2.41; h2=192.0.2.42; fi
  cat > "$case_dir/options.json" <<EOF_OPTIONS
{"snmpwalks_dir":"$case_dir/walks","report_path":"$case_dir/report.txt","run_snmp_walks":"true","enable_switch_list":"true","parse_all_walks":"false","generate_snmp2mqtt":"false","switches":[{"switch_name":"one","switch_host":"$h1","sensor_prefix":"ONE","snmp_community":"readonly","enabled":true},{"switch_name":"two","switch_host":"$h2","sensor_prefix":"TWO","snmp_community":"readonly","enabled":true}],"last_run_summary_path":"$case_dir/summary.txt","generated_yaml_path":"$case_dir/generated.yaml","generated_card_path":"$case_dir/card.yaml","snmp_log_path":"$case_dir/discovery.log","minimum_valid_walk_lines":"1","clean_output_before_walk":"false","generate_support_my_switch_bundle":"false"}
EOF_OPTIONS
  set +e
  PATH="$live/bin:$PATH" SV_TEST_SNMP_SOURCE="$live/dell.txt" SWITCH_VISION_OPTIONS_FILE="$case_dir/options.json" SWITCH_VISION_CAPABILITIES_DIR="$case_dir/caps" SWITCH_VISION_SHARE_DIR="$case_dir/share" "$RUNTIME/discovery_job.sh" >"$case_dir/stdout" 2>"$case_dir/stderr"
  status=$?
  set -e
  if [ "$good" = yes ]; then
    [ "$status" -eq 11 ] || {
      echo "FAIL: mixed live rc=$status" >&2
      echo '--- live stdout ---' >&2
      cat "$case_dir/stdout" >&2 || true
      echo '--- live stderr ---' >&2
      cat "$case_dir/stderr" >&2 || true
      echo '--- live report ---' >&2
      cat "$case_dir/report.txt" >&2 || true
      echo '--- live log ---' >&2
      cat "$case_dir/discovery.log" >&2 || true
      exit 1
    }
    grep -Fq 'Switch-list SNMP walk result: PARTIAL' "$case_dir/report.txt"
    [ "$(grep -c '^File: ' "$case_dir/report.txt" || true)" -eq 1 ]
    grep -Fq "File: $case_dir/walks/one/live-targeted-snmpwalk.txt" "$case_dir/report.txt"
  else
    [ "$status" -eq 2 ] || { echo "FAIL: all-fail live rc=$status" >&2; exit 1; }
    [ "$(grep -c '^File: ' "$case_dir/report.txt" || true)" -eq 0 ]
    grep -Fq 'Switch-list SNMP walk result: FAILED' "$case_dir/report.txt"
    grep -Fq 'Historical SNMP walks were ignored.' "$case_dir/report.txt"
  fi
  ! grep -Fq 'STALE_HISTORICAL_WALK_MUST_NOT_PARSE' "$case_dir/report.txt"
  test -f "$case_dir/walks/two/live-full-snmpwalk.txt"
}
run_live_case mixed yes
run_live_case all-fail no
echo 'entrypoint live PARTIAL/all-fail stale-walk contract: PASS'

# Physical-contract collection classification: legacy 11 is accepted as a warning, legacy 10
# remains a degraded software classification, and unexpected non-zero remains fatal.
python3 - "$ENTRYPOINT" "$TMP" <<'PY_LIVE_CODES'
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys

entrypoint = Path(sys.argv[1])
root = Path(sys.argv[2]) / "live-codes"
root.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location("sv_live_codes", entrypoint)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
options = {"run_snmp_walks": True}
record = {"walk": str(root/"ok.txt"), "switch":"ok", "host":"192.0.2.51", "prefix":"OK", "community":"readonly"}
Path(record["walk"]).write_text('.1.3.6.1.2.1.31.1.1.1.1.1 = STRING: "Gi1/0/1"\n', encoding="utf-8")

m._read_current_run_records = lambda *args, **kwargs: [record]
for code, expected_partial in ((0, False), (11, True)):
    m._stream_legacy = lambda *a, _code=code, **k: _code
    work = root/f"stage-{code}"
    work.mkdir(parents=True, exist_ok=True)
    rows, partial = m._stage_live_collection(options, work)
    assert rows == [record] and partial is expected_partial

m._stream_legacy = lambda *a, **k: 11
m._read_current_run_records = lambda *args, **kwargs: []
work = root/"empty-partial"
work.mkdir(parents=True, exist_ok=True)
try:
    m._stage_live_collection(options, work)
except RuntimeError as exc:
    assert "PARTIAL without any successful current-run walk" in str(exc)
else:
    raise AssertionError("empty PARTIAL was accepted")

m._stream_legacy = lambda *a, **k: 10
work = root/"degraded"
work.mkdir(parents=True, exist_ok=True)
try:
    m._stage_live_collection(options, work)
except m.DegradedDiscoveryError as exc:
    assert "useful evidence" in str(exc)
else:
    raise AssertionError("exit 10 lost degraded classification")

m._stream_legacy = lambda *a, **k: 7
work = root/"fatal"
work.mkdir(parents=True, exist_ok=True)
try:
    m._stage_live_collection(options, work)
except RuntimeError as exc:
    assert "code 7" in str(exc)
else:
    raise AssertionError("unexpected non-zero was accepted")

# Main path converts a reachable live PARTIAL into successful Discovery with warnings.
m.LEGACY = root/"legacy"; m.PREPARE = root/"prepare"; m.REGISTRY = root/"registry"
for path in (m.LEGACY, m.PREPARE, m.REGISTRY): path.write_text("x", encoding="utf-8")
m.DEFAULT_OPTIONS = root/"options.json"; m.DEFAULT_OPTIONS.write_text("{}", encoding="utf-8")
m.DEFAULT_CAPABILITIES = root/"caps"
m._stage_live_collection = lambda options, work: ([record], True)
contract = {"status":"resolved","device":{"model":"Synthetic"},"observed":{"physical":1,"members":1}}
def stage(options, work, current):
    cap=work/"cap"; con=work/"con"; dst=work/"ok.txt"
    for p in (cap, con, dst): p.write_text("x", encoding="utf-8")
    info={"source":Path(record["walk"]),"destination":dst,"capability":cap,"contract_path":con,"contract":contract}
    return options, [info], [info]
m._stage_options = stage
m._publish_contracts = lambda *a, **k: None
m._stream_legacy = lambda *a, **k: 0
m._expected_generated_dashboard_cards = lambda staged: 1
m._generated_snmp_card_count = lambda path: 1
m._patch_report = lambda *a: None
m._patch_yaml = lambda *a: None
assert m.main() == 0
print("entrypoint live fail-soft classification/carry: PASS")
PY_LIVE_CODES

echo 'Switch Vision Discovery physical-contract entrypoint: PASS'
