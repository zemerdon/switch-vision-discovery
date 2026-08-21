#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "runtime_src/discovery_job.sh"
text = path.read_text(encoding="utf-8")
start_token = '  if [ -n "${CURRENT_RUN_WALKS:-}" ]; then'
needle = '    echo "Queued for current-run parse: $LIVE_OUTPUT_PATH" >> "$LIVE_LOG_PATH"'
needle_pos = text.index(needle)
start = text.rfind(start_token, 0, needle_pos)
if start < 0:
    raise SystemExit("ERROR: current-run queue start not found")
end = text.index('\n  fi', needle_pos) + len('\n  fi')
expected = '''  if [ -n "${CURRENT_RUN_WALKS:-}" ]; then
    printf '%s\n' "$LIVE_OUTPUT_PATH" >> "$CURRENT_RUN_WALKS"
    echo "Queued for current-run parse: $LIVE_OUTPUT_PATH" >> "$LIVE_LOG_PATH"
  fi'''
text = text[:start] + expected + text[end:]
path.write_text(text, encoding="utf-8", newline="\n")
print("Normalized Discovery current-run queue builder anchor")
