#!/usr/bin/env python3
"""Browser-side Dashboard YAML export layout and indentation regression."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

PAGE = Path(__file__).resolve().parents[1] / "runtime_src" / "support_web.html"


def run_node(source: str) -> str:
    result = subprocess.run(
        ["node", "-e", source],
        text=True, capture_output=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def main() -> int:
    page = PAGE.read_text(encoding="utf-8")
    assert page.count('class="generated-yaml-export-group"') == 2
    new = page.index("<strong>New dashboard</strong>")
    existing = page.index("<strong>Existing dashboard · Cards Only</strong>")
    assert new < page.index('id="generatedDashboardExportMode"') < existing
    for control in (
        "previewGeneratedDashboardYamlButton",
        "copyGeneratedDashboardYamlButton",
        "downloadGeneratedDashboardYamlButton",
    ):
        assert new < page.index(f'id="{control}"') < existing
    for control in (
        "decreaseGeneratedCardsIndentButton",
        "generatedCardsIndentValue",
        "increaseGeneratedCardsIndentButton",
        "previewGeneratedCardsOnlyButton",
        "copyGeneratedCardsOnlyButton",
    ):
        assert page.index(f'id="{control}"') > existing
    assert ".generated-yaml-export-controls{display:flex" in page
    assert "@media(max-width:640px){.generated-yaml-export-format" in page
    assert "changeGeneratedCardsLeadingSpaces(-1)" in page
    assert "changeGeneratedCardsLeadingSpaces(1)" in page

    # Syntax-check the real classic browser scripts, not a reconstructed helper.
    for source in re.findall(r"<script(?:\s+[^>]*)?>(.*?)</script>", page, re.DOTALL):
        if source.strip():
            checked = subprocess.run(
                ["node", "--check", "-"], input=source, text=True,
                capture_output=True, check=False, timeout=30,
            )
            assert checked.returncode == 0, checked.stdout + checked.stderr

    start = page.index("let generatedCardsLeadingSpaces=0;")
    end = page.index("async function loadGeneratedYamlStatus()", start)
    real_handlers = page[start:end]
    harness = r"""
const assert = require('node:assert/strict');
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    textContent: '', value: 'custom-dashboard', disabled: false, href: '',
    classList: {
      hidden: true,
      contains(name) { return name === 'hidden' && this.hidden; },
      add(name) { if (name === 'hidden') this.hidden = true; },
      remove(name) { if (name === 'hidden') this.hidden = false; }
    }
  });
  return elements.get(id);
}
const $ = element;
const endpoint = path => path;
const cards = "# Switch Vision cards-only export\n- type: markdown\n  content: |-\n    first line\n    second line\n\n- type: custom:switch-vision-3650\n  title: Lab Switch\n";
const full = "# complete dashboard\nviews:\n  - title: Switch Vision\n";
const requests = [];
const fetch = async path => {
  requests.push(path);
  return {ok: true, json: async () => ({text: path.includes('cards-export') ? cards : full})};
};
let clipboard = '';
const copyTextWithFallback = async text => { clipboard = text; return true; };
"""
    exercise = r"""
(async () => {
  assert.equal(generatedCardsLeadingSpaces, 0);
  assert.equal(indentGeneratedCardsYaml(cards, 0), cards);
  assert.equal(indentGeneratedCardsYaml(cards, -5), cards);
  assert.equal(indentGeneratedCardsYaml(cards, 999), indentGeneratedCardsYaml(cards, 12));
  await previewGeneratedCardsOnly();
  assert.equal($('generatedCardYamlPreview').textContent, cards);
  changeGeneratedCardsLeadingSpaces(1);
  const expected = cards.split('\n').map(line => line.trim() ? ' ' + line : line).join('\n');
  assert.equal(generatedCardsLeadingSpaces, 1);
  assert.equal($('generatedCardYamlPreview').textContent, expected);
  await copyGeneratedCardsOnly();
  assert.equal(clipboard, expected);
  assert.equal($('generatedCardYamlPreview').textContent, clipboard);
  const copiedCards = clipboard;
  assert.equal($('decreaseGeneratedCardsIndentButton').disabled, false);
  changeGeneratedCardsLeadingSpaces(11);
  assert.equal(generatedCardsLeadingSpaces, 12);
  assert.equal($('increaseGeneratedCardsIndentButton').disabled, true);
  changeGeneratedCardsLeadingSpaces(1);
  assert.equal(generatedCardsLeadingSpaces, 12);
  changeGeneratedCardsLeadingSpaces(-20);
  assert.equal(generatedCardsLeadingSpaces, 0);
  assert.equal($('decreaseGeneratedCardsIndentButton').disabled, true);
  syncGeneratedDashboardExportMode();
  assert.equal($('downloadGeneratedDashboardYamlButton').href, 'download/switch-vision-custom-dashboard.yaml');
  await previewGeneratedDashboardYaml();
  assert.equal($('generatedCardYamlPreview').textContent, full);
  $('generatedDashboardExportMode').value = 'dashboard';
  syncGeneratedDashboardExportMode();
  assert.equal($('downloadGeneratedDashboardYamlButton').href, 'download/switch-vision-dashboard.yaml');
  await copyGeneratedDashboardYaml();
  assert.equal(clipboard, full);
  assert.equal($('generatedCardYamlPreview').textContent, full);
  assert.equal(generatedDashboardPreviewMode, 'dashboard');
  assert(requests.includes('api/generated-card-yaml/cards-export'));
  assert(requests.includes('api/generated-card-yaml/dashboard-export'));
  console.log(JSON.stringify({copiedCards}));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = json.loads(run_node(harness + "\n" + real_handlers + "\n" + exercise))
    # Exactly the user's case: one extra space beneath an existing cards: key.
    parsed = yaml.safe_load("cards:\n" + result["copiedCards"])
    assert [card["type"] for card in parsed["cards"]] == [
        "markdown", "custom:switch-vision-3650",
    ]
    assert parsed["cards"][0]["content"] == "first line\nsecond line"
    assert parsed["cards"][1]["title"] == "Lab Switch"
    print("Discovery dashboard export UI: PASS (responsive groups, preview/copy parity, indentation, YAML nesting)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
