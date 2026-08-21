#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"ERROR: {label} anchor not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


job_path = ROOT / "runtime_src/discovery_job.sh"
job = job_path.read_text(encoding="utf-8")

# Version and current-run authoritative metadata manifest.
job = job.replace('SWITCH_VISION_DISCOVERY_VERSION="2.1.30"', 'SWITCH_VISION_DISCOVERY_VERSION="2.1.31"', 1)
job = job.replace(
    'CURRENT_RUN_WALKS="/tmp/switch_vision_current_run_walks.txt"\n',
    'CURRENT_RUN_WALKS="/tmp/switch_vision_current_run_walks.txt"\n'
    'CURRENT_RUN_TARGETS="/tmp/switch_vision_current_run_targets.txt"\n',
    1,
)

manifest_helpers = r'''current_run_target_field_for_walk() {
  manifest_walk="$1"
  manifest_field="$2"
  [ -f "${CURRENT_RUN_TARGETS:-}" ] || return 1
  manifest_sep="$(printf '\034')"
  while IFS="$manifest_sep" read -r mf_walk mf_switch mf_host mf_prefix mf_community || [ -n "$mf_walk$mf_switch$mf_host$mf_prefix$mf_community" ]; do
    [ "$mf_walk" = "$manifest_walk" ] || continue
    case "$manifest_field" in
      switch) printf '%s' "$mf_switch" ;;
      host) printf '%s' "$mf_host" ;;
      prefix) printf '%s' "$mf_prefix" ;;
      community) printf '%s' "$mf_community" ;;
      *) return 1 ;;
    esac
    return 0
  done < "$CURRENT_RUN_TARGETS"
  return 1
}

record_current_run_target() {
  manifest_walk="$1"
  manifest_switch="$2"
  manifest_host="$3"
  manifest_prefix="$4"
  manifest_community="$5"
  [ -n "$manifest_walk" ] || return 1
  [ -n "$manifest_host" ] || return 1
  manifest_sep="$(printf '\034')"
  printf '%s%s%s%s%s%s%s%s%s\n' \
    "$manifest_walk" "$manifest_sep" \
    "$manifest_switch" "$manifest_sep" \
    "$manifest_host" "$manifest_sep" \
    "$manifest_prefix" "$manifest_sep" \
    "$manifest_community" >> "$CURRENT_RUN_TARGETS"
}

walk_header_target_for_walk() {
  walk_file="$1"
  [ -f "$walk_file" ] || return 1
  header_target=$(awk -F': ' '/^# Switch IP: / { print $2; exit }' "$walk_file" 2>/dev/null || true)
  case "$header_target" in
    ''|'not set'|'unknown') return 1 ;;
  esac
  printf '%s' "$header_target"
}

'''
if 'current_run_target_field_for_walk() {' not in job:
    marker = 'target_for_walk() {\n'
    if marker not in job:
        raise SystemExit("ERROR: target_for_walk anchor not found")
    job = job.replace(marker, manifest_helpers + marker, 1)

job = job.replace(
    'target_for_walk() {\n  walk_file="$1"\n\n  # Prefer explicit per-file mappings over default_host.',
    'target_for_walk() {\n  walk_file="$1"\n\n'
    '  # Current-run metadata is authoritative. The walk and its connection\n'
    '  # details are recorded together at collection time, so generation never\n'
    '  # has to rediscover a host from a filename or directory.\n'
    '  if current_host=$(current_run_target_field_for_walk "$walk_file" host 2>/dev/null) && [ -n "$current_host" ]; then\n'
    '    printf \'%s\' "$current_host"\n'
    '    return 0\n'
    '  fi\n\n'
    '  # Prefer explicit per-file mappings over default_host.',
    1,
)

job = job.replace(
    '  if [ -n "${DEFAULT_HOST:-}" ]; then\n    printf \'%s\' "$DEFAULT_HOST"\n    return 0\n  fi\n\n  printf \'unknown\'\n}\n',
    '  # A Switch Vision live walk also records its target in the walk header.\n'
    '  # This is a diagnostic recovery fallback only; current-run metadata and\n'
    '  # explicit mappings remain preferred.\n'
    '  if header_host=$(walk_header_target_for_walk "$walk_file" 2>/dev/null) && [ -n "$header_host" ]; then\n'
    '    printf \'%s\' "$header_host"\n'
    '    return 0\n'
    '  fi\n\n'
    '  if [ -n "${DEFAULT_HOST:-}" ]; then\n    printf \'%s\' "$DEFAULT_HOST"\n    return 0\n  fi\n\n  printf \'unknown\'\n}\n',
    1,
)

job = job.replace(
    'target_prefix_for_walk() {\n  walk_file="$1"\n  if [ -f "$TARGETS_CSV" ]; then',
    'target_prefix_for_walk() {\n  walk_file="$1"\n'
    '  if current_prefix=$(current_run_target_field_for_walk "$walk_file" prefix 2>/dev/null) && [ -n "$current_prefix" ]; then\n'
    '    printf \'%s\' "$current_prefix"\n'
    '    return 0\n'
    '  fi\n'
    '  if [ -f "$TARGETS_CSV" ]; then',
    1,
)

job = job.replace(
    'target_community_for_walk() {\n  walk_file="$1"\n  if [ -f "$TARGETS_CSV" ]; then',
    'target_community_for_walk() {\n  walk_file="$1"\n'
    '  if current_community=$(current_run_target_field_for_walk "$walk_file" community 2>/dev/null) && [ -n "$current_community" ]; then\n'
    '    printf \'%s\' "$current_community"\n'
    '    return 0\n'
    '  fi\n'
    '  if [ -f "$TARGETS_CSV" ]; then',
    1,
)

old_queue = '''  if [ -n "${CURRENT_RUN_WALKS:-}" ]; then
    printf '%s\n' "$LIVE_OUTPUT_PATH" >> "$CURRENT_RUN_WALKS"
    echo "Queued for current-run parse: $LIVE_OUTPUT_PATH" >> "$LIVE_LOG_PATH"
  fi
'''
new_queue = '''  if [ "$result" = "PASS" ] || [ "$result" = "WARN" ]; then
    if [ -n "${CURRENT_RUN_WALKS:-}" ]; then
      printf '%s\n' "$LIVE_OUTPUT_PATH" >> "$CURRENT_RUN_WALKS"
      echo "Queued for current-run parse: $LIVE_OUTPUT_PATH" >> "$LIVE_LOG_PATH"
    fi
    if [ -n "${CURRENT_RUN_TARGETS:-}" ]; then
      record_current_run_target \
        "$LIVE_OUTPUT_PATH" \
        "${SELECTED_SWITCH:-${LIVE_SWITCH_LABEL:-}}" \
        "$LIVE_SWITCH_IP" \
        "${DEFAULT_PREFIX:-${LIVE_SWITCH_LABEL:-SW}}" \
        "$LIVE_SNMP_COMMUNITY" || \
        echo "WARNING: current-run target metadata could not be recorded for $LIVE_OUTPUT_PATH" >> "$LIVE_LOG_PATH"
    fi
  else
    echo "Current-run parse skipped for failed walk: $LIVE_OUTPUT_PATH" >> "$LIVE_LOG_PATH"
  fi
'''
if old_queue not in job:
    raise SystemExit("ERROR: current-run queue anchor not found")
job = job.replace(old_queue, new_queue, 1)

old_reset = '''  rm -f /tmp/switch_vision_live_walk_summary.txt /tmp/switch_vision_live_walk_summary_all.txt "$CURRENT_RUN_WALKS"
  : > "$CURRENT_RUN_WALKS"
'''
new_reset = '''  rm -f /tmp/switch_vision_live_walk_summary.txt /tmp/switch_vision_live_walk_summary_all.txt "$CURRENT_RUN_WALKS" "$CURRENT_RUN_TARGETS"
  : > "$CURRENT_RUN_WALKS"
  : > "$CURRENT_RUN_TARGETS"
'''
if old_reset not in job:
    raise SystemExit("ERROR: current-run reset anchor not found")
job = job.replace(old_reset, new_reset, 1)

# Make generator parser/formatter failures explicit instead of allowing a
# successful final pipeline stage to hide an earlier AWK failure.
job = job.replace(
    '  source_name=$(basename "$walk_file")\n  if [ "$target_ip" = "unknown" ] || [ -z "$target_ip" ]; then',
    '  source_name=$(basename "$walk_file")\n'
    '  generator_raw_tmp="/tmp/switch_vision_generator_raw_$$.yaml"\n'
    '  rm -f "$generator_raw_tmp"\n'
    '  if [ "$target_ip" = "unknown" ] || [ -z "$target_ip" ]; then',
    1,
)

pipe_marker = "  ' \"$walk_file\" | awk '\n"
if pipe_marker not in job:
    raise SystemExit("ERROR: generator AWK pipeline anchor not found")
job = job.replace(
    pipe_marker,
    "  ' \"$walk_file\" > \"$generator_raw_tmp\" || {\n"
    "    rm -f \"$generator_raw_tmp\"\n"
    "    echo \"Generated YAML source parser failed for: $walk_file\" >> \"$LIVE_LOG_PATH\" 2>/dev/null || true\n"
    "    return 1\n"
    "  }\n"
    "  if ! awk '\n",
    1,
)

formatter_tail = "    END { flush_pending_empty() }\n  '\n}\n\ngenerator_has_unknown_targets() {"
if formatter_tail not in job:
    raise SystemExit("ERROR: generator formatter tail anchor not found")
job = job.replace(
    formatter_tail,
    "    END { flush_pending_empty() }\n"
    "  ' \"$generator_raw_tmp\"; then\n"
    "    rm -f \"$generator_raw_tmp\"\n"
    "    echo \"Generated YAML formatter failed for: $walk_file\" >> \"$LIVE_LOG_PATH\" 2>/dev/null || true\n"
    "    return 1\n"
    "  fi\n"
    "  rm -f \"$generator_raw_tmp\"\n"
    "}\n\n"
    "generator_has_unknown_targets() {",
    1,
)

publication_helpers = r'''quarantine_invalid_generated_live_yaml() {
  guard="$1"
  GENERATED_YAML_PREVIOUS_STATE="missing"
  [ -f "$GENERATED_YAML_PATH" ] || return 0
  if python3 "$guard" --validate "$GENERATED_YAML_PATH" >/dev/null 2>&1; then
    GENERATED_YAML_PREVIOUS_STATE="valid"
    return 0
  fi
  quarantine_path="${GENERATED_YAML_PATH}.invalid.$(date +%Y%m%dT%H%M%S)"
  if mv "$GENERATED_YAML_PATH" "$quarantine_path"; then
    GENERATED_YAML_PREVIOUS_STATE="quarantined_invalid"
    echo "Invalid previous generated YAML quarantined: $quarantine_path" >> "$LIVE_LOG_PATH" 2>/dev/null || true
  else
    GENERATED_YAML_PREVIOUS_STATE="invalid_quarantine_failed"
    echo "WARNING: invalid previous generated YAML could not be quarantined: $GENERATED_YAML_PATH" >> "$LIVE_LOG_PATH" 2>/dev/null || true
  fi
}

report_generated_yaml_failure_state() {
  case "${GENERATED_YAML_PREVIOUS_STATE:-unknown}" in
    valid) echo "- Previous valid generated YAML preserved unchanged." ;;
    quarantined_invalid) echo "- Previous invalid generated YAML was quarantined; no broken live handoff remains." ;;
    missing) echo "- No live generated YAML is available until a valid generation succeeds." ;;
    invalid_quarantine_failed) echo "- WARNING: previous invalid generated YAML could not be quarantined; review the Discovery log." ;;
    *) echo "- Previous generated YAML state could not be determined; review the Discovery log." ;;
  esac
}

'''
if 'quarantine_invalid_generated_live_yaml() {' not in job:
    marker = 'write_generated_yaml() {\n'
    if marker not in job:
        raise SystemExit("ERROR: write_generated_yaml anchor not found")
    job = job.replace(marker, publication_helpers + marker, 1)

job = job.replace(
    'write_generated_yaml() {\n  tmp_walks="$1"\n  GENERATED_YAML_PUBLISHED="false"\n',
    'write_generated_yaml() {\n  tmp_walks="$1"\n  GENERATED_YAML_PUBLISHED="false"\n'
    '  GENERATED_YAML_GENERATOR_FAILED="false"\n'
    '  GENERATED_YAML_PREVIOUS_STATE="unknown"\n',
    1,
)

old_generate_call = '''      write_generated_yaml_for_walk "$walk_file" "$target_ip" "$prefix" "$community" "$member_map"
'''
new_generate_call = '''      if ! write_generated_yaml_for_walk "$walk_file" "$target_ip" "$prefix" "$community" "$member_map"; then
        GENERATED_YAML_GENERATOR_FAILED="true"
        echo "Generated YAML target generation failed for: $walk_file" >> "$LIVE_LOG_PATH" 2>/dev/null || true
      fi
'''
if old_generate_call not in job:
    raise SystemExit("ERROR: generated target call anchor not found")
job = job.replace(old_generate_call, new_generate_call, 1)

pre_guard_anchor = '''  if [ ! -f "$guard" ]; then
    rm -f "$candidate_path"
'''
pre_guard_new = '''  if [ "$GENERATED_YAML_GENERATOR_FAILED" = "true" ]; then
    rm -f "$candidate_path"
    if [ -f "$guard" ]; then
      quarantine_invalid_generated_live_yaml "$guard"
    fi
    echo "Generated YAML candidate refused because one or more target generators failed." >> "$LIVE_LOG_PATH" 2>/dev/null || true
    return 0
  fi

  if [ ! -f "$guard" ]; then
    rm -f "$candidate_path"
'''
if pre_guard_anchor not in job:
    raise SystemExit("ERROR: generated guard anchor not found")
job = job.replace(pre_guard_anchor, pre_guard_new, 1)

old_guard_else = '''  else
    guard_status=$?
    rm -f "$candidate_path"
    echo "Generated YAML candidate refused (guard status $guard_status); previous live generated YAML was preserved." >> "$LIVE_LOG_PATH" 2>/dev/null || true
  fi
'''
new_guard_else = '''  else
    guard_status=$?
    rm -f "$candidate_path"
    quarantine_invalid_generated_live_yaml "$guard"
    echo "Generated YAML candidate refused (guard status $guard_status); previous live state: $GENERATED_YAML_PREVIOUS_STATE." >> "$LIVE_LOG_PATH" 2>/dev/null || true
  fi
'''
if old_guard_else not in job:
    raise SystemExit("ERROR: generated guard failure branch anchor not found")
job = job.replace(old_guard_else, new_guard_else, 1)

job = job.replace(
    '            echo "- Previous generated YAML preserved unchanged."\n',
    '            report_generated_yaml_failure_state\n',
)

job_path.write_text(job, encoding="utf-8", newline="\n")

# Bump runtime entrypoint.
run_path = ROOT / "runtime_src/run.sh"
run = run_path.read_text(encoding="utf-8")
if 'SWITCH_VISION_DISCOVERY_VERSION="2.1.30"' not in run:
    raise SystemExit("ERROR: run.sh 2.1.30 version not found")
run_path.write_text(run.replace('SWITCH_VISION_DISCOVERY_VERSION="2.1.30"', 'SWITCH_VISION_DISCOVERY_VERSION="2.1.31"', 1), encoding="utf-8", newline="\n")

# Bump Home Assistant app metadata.
config_path = ROOT / "switch_vision_discovery/config.yaml"
config = config_path.read_text(encoding="utf-8")
config, count = re.subn(r'(?m)^version:\s*"2\.1\.30"\s*$', 'version: "2.1.31"', config, count=1)
if count != 1:
    raise SystemExit("ERROR: Discovery config version 2.1.30 not found exactly once")
config_path.write_text(config, encoding="utf-8", newline="\n")

# Permanent regressions: exact current-run metadata, failed-walk exclusion,
# explicit generator stage failures, and invalid-live quarantine behavior.
self_test_path = ROOT / "runtime_src/self-test.sh"
self_test = self_test_path.read_text(encoding="utf-8")
self_test = self_test.replace('SWITCH_VISION_DISCOVERY_VERSION="2.1.30"', 'SWITCH_VISION_DISCOVERY_VERSION="2.1.31"')
regression = r'''

# v2.1.31 generated-YAML handoff regression. Current-run metadata captured at
# collection time must be authoritative, failed walks must not enter generation,
# parser/formatter failures must not be hidden by a shell pipeline, and an
# already-invalid live handoff must not survive another failed generation.
python3 - "$BASE_DIR/discovery_job.sh" <<'PYTEST_V2131_HANDOFF'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text(encoding="utf-8")
assert 'CURRENT_RUN_TARGETS="/tmp/switch_vision_current_run_targets.txt"' in text
assert 'record_current_run_target \\\n        "$LIVE_OUTPUT_PATH"' in text
assert 'current_run_target_field_for_walk "$walk_file" host' in text
assert 'current_run_target_field_for_walk "$walk_file" prefix' in text
assert 'current_run_target_field_for_walk "$walk_file" community' in text
assert text.index('current_run_target_field_for_walk "$walk_file" host') < text.index('if [ -f "$TARGETS_CSV" ]')
assert 'if [ "$result" = "PASS" ] || [ "$result" = "WARN" ]; then' in text
assert 'Current-run parse skipped for failed walk' in text
assert 'generator_raw_tmp="/tmp/switch_vision_generator_raw_$$.yaml"' in text
assert '\'$walk_file" | awk\'' not in text
assert 'Generated YAML source parser failed for:' in text
assert 'Generated YAML formatter failed for:' in text
assert 'quarantine_invalid_generated_live_yaml()' in text
assert 'python3 "$guard" --validate "$GENERATED_YAML_PATH"' in text
assert 'mv "$GENERATED_YAML_PATH" "$quarantine_path"' in text
assert 'Previous invalid generated YAML was quarantined; no broken live handoff remains.' in text
print("Switch Vision Discovery v2.1.31 generated-YAML handoff regression: PASS")
PYTEST_V2131_HANDOFF
'''
if "v2.1.31 generated-YAML handoff regression" not in self_test:
    self_test += regression
self_test_path.write_text(self_test, encoding="utf-8", newline="\n")

# Changelog.
changelog_path = ROOT / "switch_vision_discovery/CHANGELOG.md"
changelog = changelog_path.read_text(encoding="utf-8")
entry = """## 2.1.31\n\n- Make current-run walk metadata authoritative for SNMP2MQTT generation: each successful/warning walk is paired with its exact switch name, management host, prefix, and community at collection time instead of rediscovering those values later from filenames or directories.\n- Add the embedded `# Switch IP:` walk header as a diagnostic host fallback while keeping current-run metadata and explicit mappings preferred.\n- Exclude failed live walks from the current-run parser/generator set.\n- Split the YAML generator parser/formatter pipeline into explicit checked stages so an internal AWK failure can no longer collapse silently into a `targets:`-only candidate.\n- Quarantine an already-invalid live `generated-snmp2mqtt.yaml` when a new candidate also fails, while continuing to preserve a previously valid live handoff.\n- Add permanent regressions for authoritative current-run metadata, failed-walk exclusion, generator-stage failure visibility, and invalid-live quarantine.\n\n"""
if not changelog.startswith("# Changelog\n\n"):
    raise SystemExit("ERROR: unexpected Discovery changelog header")
changelog_path.write_text("# Changelog\n\n" + entry + changelog[len("# Changelog\n\n"):], encoding="utf-8", newline="\n")

print("Prepared Switch Vision Discovery v2.1.31 generated-YAML handoff rework")
