#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
SUPPORT = RUNTIME / "support_web.py"
EXTERNAL = [
    RUNTIME / "maintenance.js",
    RUNTIME / "calibration_profiles.js",
    RUNTIME / "calibration_profiles_manager.js",
]


def extract_page() -> str:
    source = SUPPORT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "_PAGE" for t in node.targets):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value
    raise RuntimeError("_PAGE not found")


def attrs(tag: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for match in re.finditer(r'''([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(["'])(.*?)\2''', tag, re.S):
        result[match.group(1).casefold()] = match.group(3)
    return result


def main() -> int:
    page = extract_page()
    support_source = SUPPORT.read_text(encoding="utf-8")
    external_source = "\n".join(path.read_text(encoding="utf-8") for path in EXTERNAL)
    javascript = page + "\n" + external_source

    failures: list[str] = []
    warnings: list[str] = []
    static_buttons: list[tuple[str, dict[str, str]]] = []

    for match in re.finditer(r"<button\b([^>]*)>", page, flags=re.I | re.S):
        raw = match.group(1)
        properties = attrs(raw)
        button_id = properties.get("id", "").strip()
        if not button_id:
            # Anonymous buttons are acceptable only when they are form-submit
            # controls or are generated inside a delegated container.
            button_type = properties.get("type", "submit").casefold()
            if button_type != "submit" and "onclick" not in properties:
                warnings.append(f"anonymous non-submit button: <button{raw[:120]}>")
            continue
        static_buttons.append((button_id, properties))

    seen = set()
    for button_id, properties in static_buttons:
        if button_id in seen:
            failures.append(f"duplicate button id: {button_id}")
            continue
        seen.add(button_id)

        if "onclick" in properties:
            continue

        # Native submit buttons do not need a click listener when they live in a
        # form. Still require the control id to be referenced somewhere if it is
        # type=button, because otherwise it cannot perform an action.
        button_type = properties.get("type", "submit").casefold()
        quoted = re.compile(rf'''["']{re.escape(button_id)}["']''')
        references = len(quoted.findall(javascript))
        if button_type == "button" and references == 0:
            failures.append(f"{button_id}: type=button has no JavaScript reference")
            continue

        # For action buttons, accept direct event binding, assignment to a local
        # variable that is later bound, or a known delegated-action attribute.
        direct_patterns = [
            rf'''(?:getElementById|el)\(\s*["']{re.escape(button_id)}["']\s*\)[^\n;]{{0,180}}addEventListener''',
            rf'''querySelector\(\s*["']#{re.escape(button_id)}["']\s*\)[^\n;]{{0,180}}addEventListener''',
            rf'''["']{re.escape(button_id)}["'][^\n]{{0,220}}addEventListener''',
        ]
        directly_bound = any(re.search(pattern, javascript, flags=re.S) for pattern in direct_patterns)
        has_action_attr = any(key.startswith("data-") and "action" in key for key in properties)
        if button_type == "button" and not directly_bound and not has_action_attr:
            # Some shipped code stores the element in a variable first. If the
            # id is at least referenced by JS, flag as review warning rather than
            # a hard failure; the critical actions are separately hard-asserted.
            if references > 0:
                warnings.append(f"{button_id}: referenced by JavaScript but direct listener is indirect")
            else:
                failures.append(f"{button_id}: no action binding found")

    # Every static form input/select/textarea with an id should be referenced by
    # the page scripts, unless it is a browser-native file field or purely output.
    fields = []
    for match in re.finditer(r"<(input|select|textarea)\b([^>]*)>", page, flags=re.I | re.S):
        kind = match.group(1).casefold()
        properties = attrs(match.group(2))
        field_id = properties.get("id", "").strip()
        if not field_id:
            continue
        if properties.get("type", "").casefold() in {"hidden", "file"}:
            continue
        fields.append((kind, field_id, properties))

    unreferenced_fields = []
    for kind, field_id, properties in fields:
        if properties.get("readonly") is not None or properties.get("disabled") is not None:
            continue
        if not re.search(rf'''["']{re.escape(field_id)}["']''', javascript):
            unreferenced_fields.append(f"{kind}#{field_id}")
    if unreferenced_fields:
        failures.append("editable fields with no JavaScript reference: " + ", ".join(unreferenced_fields))

    print(f"Hub control inventory: {len(static_buttons)} static buttons, {len(fields)} editable/static fields checked")
    for item in warnings:
        print(f"WARN: {item}")
    for item in failures:
        print(f"FAIL: {item}")
    if failures:
        print(f"Hub static control inventory audit: FAIL ({len(failures)} issue(s))")
        return 1
    print("Hub static control inventory audit: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
