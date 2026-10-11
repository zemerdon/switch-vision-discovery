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
