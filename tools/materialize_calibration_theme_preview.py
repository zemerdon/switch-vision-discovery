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
        if any(token[0] == "button" for token in tokens):
            rows.append({"css": css_class, "tokens": tokens})
    count = sum(token[0] == "button" for row in rows for token in row["tokens"])
    if count < 40:
        raise ValueError("Core Selection button inventory is incomplete")
    return ("window.SwitchVisionCalibrationSelectionButtons = " +
            json.dumps({"rows": rows, "count": count}, ensure_ascii=False) + ";\n").encode()

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
