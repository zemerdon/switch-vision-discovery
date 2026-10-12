#!/usr/bin/env python3
"""Vendor the exact Core Calibration stylesheet and style-rule generator for read-only Hub preview.

The pinned Core main is the only source. Never fetch private runtime/profile state.
Run during local product development before Discovery archive materialization.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT.parent / "core"  # override with --core-path when using a worktree
import argparse
import hashlib
import json
import re
from html import escape

def selection_button_fixture(script: str) -> bytes:
    """Derive the entire static Selection button inventory from Core."""
    start = script.index('data-cv-section="selection"')
    end = script.index("</div></details>", start)
    source = script[start:end]
    # Status Box quick controls are now two dropdowns, backed by the complete
    # 24-action Core contract rather than individually rendered buttons.
    quick_group_source = re.search(
        r"const SV_STATUS_BOX_QUICK_GROUPS = Object.freeze\((\[.*?\])\);", script, re.S
    )
    if not quick_group_source:
        raise ValueError("Core Status Box dropdown selection contract is missing")
    quick_groups = json.loads(quick_group_source.group(1))
    if len(quick_groups) != 2 or any(sum(len(actions) for _, actions in group) != 12 for group in quick_groups):
        raise ValueError("Core Status Box dropdown selection contract is incomplete")
    rows = []
    for css_class, content in re.findall(r'<div class="(cv-cal-tools-row[^"]+)">(.*?)</div>', source, re.S):
        tokens = []
        for match in re.finditer(
            r'<span class="cv-cal-quick-label"[^>]*>([^<]+)</span>'
            r'|<button[^>]*data-cv-action="([^"]+)"[^>]*>([^<]+)</button>', content, re.S
        ):
            if match.group(1) is not None:
                tokens.append(["label", match.group(1).strip()])
            else:
                tokens.append(["button", match.group(2), match.group(3).strip()])
        if "cv-cal-status-quick-row" in css_class:
            if content.count('data-cv-quick-group=') != 2:
                raise ValueError("Core Status Box quick dropdown markup is incomplete")
            tokens = [
                ["select", f"Status Box {i}", [
                    (heading + " · " + label) if heading != "Status Box" else label
                    for heading, entries in group for label, _target, _part in entries
                ]] for i, group in enumerate(quick_groups, 1)
            ]
        if any(token[0] in ("button", "select") for token in tokens):
            rows.append({"css": css_class, "tokens": tokens})
    count = sum(token[0] == "button" for row in rows for token in row["tokens"])
    selects = sum(token[0] == "select" for row in rows for token in row["tokens"])
    if count < 25 or selects != 2:
        raise ValueError("Core Selection button/dropdown inventory is incomplete")
    return ("window.SwitchVisionCalibrationSelectionButtons = " +
            json.dumps({"rows": rows, "count": count, "selects": selects}, ensure_ascii=False) + ";\n").encode()

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-path", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args()
    core = options.core_path.resolve()
    script = (core / "src/js/switch-vision.js").read_text(encoding="utf-8")
    start = script.index("const SV_CAL_THEME_SELECTORS = Object.freeze(")
    end = script.index("const SV_CALIBRATION_TRANSIENT_CONFIG_KEYS", start)
    fragment = script[start:end].strip()
    assert "function calibrationThemeCss(theme)" in fragment
    assert "function normalizeCalibrationTheme(theme)" in fragment
    out = (
        "/* Generated from Core Calibration theme code; do not hand-edit. */\n"
        "(() => {\n" + fragment +
        "\nwindow.SwitchVisionCalibrationThemeCoreCss = calibrationThemeCss;\n})();\n"
    )
    css = (core / "src/css/switch-vision.css").read_bytes()
    targets = {
        ROOT / "runtime_src/calibration_theme_core.css": css,
        ROOT / "runtime_src/calibration_theme_core_rules.js": out.encode("utf-8"),
        ROOT / "runtime_src/calibration_theme_selection_buttons.js": selection_button_fixture(script),
    }
    for target, payload in targets.items():
        if target.exists() and target.read_bytes() == payload:
            continue
        if options.check:
            raise SystemExit("Core preview asset drift: " + target.name)
        target.write_bytes(payload)
    print("CORE_CALIBRATION_PREVIEW_PARITY_PASS", *(f"{p.name}:{hashlib.sha256(b).hexdigest()}" for p,b in targets.items()))

if __name__ == "__main__":
    main()
