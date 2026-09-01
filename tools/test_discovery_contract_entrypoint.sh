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
if run_entrypoint "$conflict" "$conflict/options.json" > "$conflict/stdout.txt" 2> "$conflict/stderr.txt"; then
  echo 'FAIL: topology conflict unexpectedly succeeded' >&2
  exit 1
fi
if ! grep -Fq 'Topology conflict' "$conflict/stdout.txt"; then
  echo 'FAIL: topology conflict did not surface its status marker' >&2
  cat "$conflict/stdout.txt" >&2 || true
  cat "$conflict/stderr.txt" >&2 || true
  exit 1
fi
[ ! -s "$conflict/generated.yaml" ] || {
  echo 'FAIL: topology conflict produced final YAML' >&2
  exit 1
}

echo 'entrypoint topology-conflict guard: PASS'

# Mixed current-run path: unresolved/non-switch targets are excluded while a
# resolved physical switch continues. All-unresolved runs still fail closed and
# a real resolver/topology exception remains fatal.
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
    ],
    "stack_member_prefixes": [
        {"switch_name": "supported", "member": "1"},
        {"switch_name": "unsupported", "member": "1"},
    ],
    "input_path": str(unsupported),
}
records = [
    {"walk": str(supported), "switch": "supported", "host": "192.0.2.21", "prefix": "GOOD", "community": "readonly"},
    {"walk": str(unsupported), "switch": "unsupported", "host": "192.0.2.22", "prefix": "SKIP", "community": "readonly"},
]

def resolved_prepare(source: Path, destination: Path, work: Path):
    if source.name == "unsupported.txt":
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return {
        "source": source,
        "destination": destination,
        "capability": work / "cap.json",
        "contract_path": work / "contract.json",
        "contract": {"status": "resolved"},
    }

module._prepare_walk = resolved_prepare
staged, ordered = module._stage_options(options, root / "work", records)
assert len(ordered) == 1, ordered
assert [row["switch_name"] for row in staged["switches"]] == ["supported"], staged["switches"]
assert [row["switch_name"] for row in staged["stack_member_prefixes"]] == ["supported"], staged["stack_member_prefixes"]
targets = Path(staged["targets_csv"]).read_text(encoding="utf-8")
assert "supported" in targets
assert "unsupported" not in targets
assert staged["input_path"].endswith("supported.txt"), staged["input_path"]

module._prepare_walk = lambda source, destination, work: None
try:
    module._stage_options(options, root / "all-unresolved", records)
except RuntimeError as exc:
    assert "did not produce any resolved physical switch contracts" in str(exc)
else:
    raise AssertionError("all-unresolved current-run staging unexpectedly succeeded")

def fatal_prepare(source: Path, destination: Path, work: Path):
    raise RuntimeError("synthetic topology conflict")

module._prepare_walk = fatal_prepare
try:
    module._stage_options(options, root / "fatal", records[:1])
except RuntimeError as exc:
    assert "synthetic topology conflict" in str(exc)
else:
    raise AssertionError("topology-conflict exception was swallowed")

print("entrypoint mixed current-run exclusion: PASS")
PY

echo 'Switch Vision Discovery physical-contract entrypoint: PASS'
