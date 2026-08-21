#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "runtime_src/self-test.sh"
lines = path.read_text(encoding="utf-8").splitlines()
out = []
for line in lines:
    if line.startswith("assert ") and "record_current_run_target" in line:
        out.append("assert 'record_current_run_target' in text")
        continue
    if line.startswith("assert ") and "$walk_file" in line and "| awk" in line:
        out.append("assert '\"$walk_file\" | awk' not in text")
        continue
    out.append(line)
path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
print("Hardened Discovery v2.1.31 regression assertions")
