#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.1.28"


def write(path: Path, text: str) -> None:
    path.write_text(text.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8", newline="\n")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"ERROR: {label}: expected one occurrence, found {count}")
    return text.replace(old, new, 1)


# App/runtime versions.
config_path = ROOT / "switch_vision_discovery" / "config.yaml"
config = config_path.read_text(encoding="utf-8")
config = replace_once(config, 'version: "2.1.27"', f'version: "{VERSION}"', "config version")
write(config_path, config)

for rel in ("runtime_src/run.sh", "runtime_src/discovery_job.sh"):
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'SWITCH_VISION_DISCOVERY_VERSION="2.1.27"',
        f'SWITCH_VISION_DISCOVERY_VERSION="{VERSION}"',
        f"{rel} version",
    )
    write(path, text)

# Atomic generated-YAML publication. The generator writes a candidate beside
# the destination and a standalone semantic guard atomically replaces the live
# file only when the candidate contains a real Switch Vision target list.
job_path = ROOT / "runtime_src/discovery_job.sh"
job = job_path.read_text(encoding="utf-8")
start = job.index("write_generated_yaml() {")
end = job.index("\n\nwrite_report() {", start)
old_func = job[start:end]
if '} > "$GENERATED_YAML_PATH"' not in old_func:
    raise SystemExit("ERROR: expected direct generated-YAML redirection not found")
new_func = old_func.replace(
    'write_generated_yaml() {\n  tmp_walks="$1"\n  echo "Generating SNMP2MQTT YAML: $GENERATED_YAML_PATH" >> "$LIVE_LOG_PATH" 2>/dev/null || true\n  {',
    'write_generated_yaml() {\n  tmp_walks="$1"\n  GENERATED_YAML_PUBLISHED="false"\n  candidate_path="${GENERATED_YAML_PATH}.candidate.$$"\n  guard="/generated_yaml_guard.py"\n  [ -f "$guard" ] || guard="$(dirname "$0")/generated_yaml_guard.py"\n  echo "Generating SNMP2MQTT YAML candidate: $candidate_path" >> "$LIVE_LOG_PATH" 2>/dev/null || true\n  rm -f "$candidate_path"\n  {',
    1,
)
new_func = new_func.replace(
    '} > "$GENERATED_YAML_PATH"',
    '''} > "$candidate_path"

  if [ ! -f "$guard" ]; then
    rm -f "$candidate_path"
    echo "Generated YAML candidate refused: semantic guard is missing: $guard" >> "$LIVE_LOG_PATH" 2>/dev/null || true
    return 0
  fi

  if python3 "$guard" --publish "$candidate_path" "$GENERATED_YAML_PATH"; then
    GENERATED_YAML_PUBLISHED="true"
    echo "Generated YAML published atomically: $GENERATED_YAML_PATH" >> "$LIVE_LOG_PATH" 2>/dev/null || true
  else
    guard_status=$?
    rm -f "$candidate_path"
    echo "Generated YAML candidate refused (guard status $guard_status); previous live generated YAML was preserved." >> "$LIVE_LOG_PATH" 2>/dev/null || true
  fi''',
    1,
)
job = job[:start] + new_func + job[end:]

# Both report paths used to state that the file was generated regardless of
# whether its contents were usable. Make publication outcome explicit.
old_report = '''          write_generated_yaml "$tmp_walks"\n          echo "- Generated file: $GENERATED_YAML_PATH"\n          echo "- Review-only output; it has not been installed."'''
new_report = '''          write_generated_yaml "$tmp_walks"
          if [ "${GENERATED_YAML_PUBLISHED:-false}" = "true" ]; then
            echo "- Generated file: $GENERATED_YAML_PATH"
            echo "- Validation: PASS (non-empty target list); published atomically."
          else
            echo "- FAIL: generated YAML candidate did not contain a valid non-empty target list."
            echo "- Previous generated YAML preserved unchanged."
          fi
          echo "- Review-only output; it has not been installed."'''
count = job.count(old_report)
if count != 2:
    raise SystemExit(f"ERROR: expected two generated report blocks, found {count}")
job = job.replace(old_report, new_report)
write(job_path, job)

# The Discovery UI already validates before starting SNMP2MQTT. Update stale
# guidance so it describes current automatic application rather than asking a
# user to manually enable/restart the bridge after every run.
web_path = ROOT / "runtime_src" / "support_web.py"
web = web_path.read_text(encoding="utf-8")
web = replace_once(
    web,
    '"import_note": "Enable generated-YAML import in the Switch Vision SNMP2MQTT app and restart that app after regeneration.",',
    '"import_note": "A valid changed generated YAML is applied to Switch Vision SNMP2MQTT automatically when that app is available; invalid candidates are never published.",',
    "generated YAML status guidance",
)
write(web_path, web)

# Self-test version assertions and atomic-publication regression.
self_path = ROOT / "runtime_src" / "self-test.sh"
self_test = self_path.read_text(encoding="utf-8")
old_version = 'SWITCH_VISION_DISCOVERY_VERSION="2.1.27"'
if old_version in self_test:
    self_test = self_test.replace(old_version, f'SWITCH_VISION_DISCOVERY_VERSION="{VERSION}"')

regression = r'''

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
grep -Fq 'model == "S5720-12TP-LI-AC" && label ~ /^SFP 1G /' "$BASE_DIR/discovery_job.sh"
grep -Fq 'if (!(idx in ifname)) { ifname[idx]=val; ifname_source[idx]="ifDescr" }' "$BASE_DIR/discovery_job.sh"
printf '%s\n' "Switch Vision Discovery v2.1.28 S5720 generated-target prerequisites: PASS"
'''
if "v2.1.28 generated SNMP2MQTT YAML publication regression" not in self_test:
    self_test += regression
write(self_path, self_test)

# Changelog.
changelog_path = ROOT / "switch_vision_discovery" / "CHANGELOG.md"
changelog = changelog_path.read_text(encoding="utf-8")
entry = f'''# Changelog\n\n## v{VERSION} — Atomic generated-YAML handoff\n\n- Write SNMP2MQTT output to a candidate file and publish it atomically only after the candidate passes the Switch Vision header and non-empty target-list contract.\n- Preserve the previous live `generated-snmp2mqtt.yaml` unchanged when a generation attempt produces an empty, target-less, malformed, or otherwise invalid candidate.\n- Add a standalone generated-YAML semantic guard plus a permanent regression proving an invalid candidate cannot clobber a known-good live handoff.\n- Keep the Huawei S5720-12TP-LI-AC 8 RJ45 + 4 physical 1G SFP mapping and 1000 Mbps physical-cage speed cap from v2.1.27 unchanged.\n- Update Discovery UI guidance to reflect automatic SNMP2MQTT application of valid changed YAML.\n\n'''
if changelog.startswith("# Changelog\n\n"):
    changelog = entry + changelog[len("# Changelog\n\n"):]
else:
    raise SystemExit("ERROR: unexpected Discovery changelog header")
write(changelog_path, changelog)

print("Prepared Discovery 2.1.28 atomic generated-YAML handoff")
