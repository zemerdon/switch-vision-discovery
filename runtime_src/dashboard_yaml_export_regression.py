#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import tempfile

import yaml

import support_web as web

SAMPLE = """# generated native source
views:
  - title: Switch Vision
    path: switch-vision
    type: custom:vertical-layout
    layout:
      width: 800
      max_cols: 1
    cards:
      - type: markdown
        content: '## Switch Vision'
      - type: custom:switch-vision-3650
        title: Lab Switch
        selected_switch: sw1
"""

with tempfile.TemporaryDirectory() as tmpdir:
    path = Path(tmpdir) / "generated-dashboard-card.yaml"
    path.write_text(SAMPLE, encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    dashboard = web._generated_dashboard_export(path)
    assert dashboard["valid"] is True, dashboard
    assert dashboard["mode"] == "dashboard"
    assert dashboard["sha256"]
    assert "custom:vertical-layout" not in dashboard["text"]
    assert "No third-party Layout Card view dependency is required." in dashboard["text"]
    dashboard_doc = yaml.safe_load(dashboard["text"])
    assert isinstance(dashboard_doc, dict)
    assert len(dashboard_doc["views"]) == 1
    view = dashboard_doc["views"][0]
    assert "type" not in view
    assert "layout" not in view
    assert view["title"] == "Switch Vision"
    assert view["path"] == "switch-vision"
    assert [card["type"] for card in view["cards"]] == ["markdown", "custom:switch-vision-3650"]
    assert view["cards"][1]["selected_switch"] == "sw1"

    cards = web._generated_dashboard_export(path, cards_only=True)
    assert cards["valid"] is True, cards
    assert cards["mode"] == "cards"
    assert "beneath an existing Home Assistant view's cards: key" in cards["text"]
    card_list = yaml.safe_load(cards["text"])
    assert isinstance(card_list, list)
    assert [card["type"] for card in card_list] == ["markdown", "custom:switch-vision-3650"]
    assert card_list[1]["title"] == "Lab Switch"

    # Export is derived; the Native generated source must never be rewritten.
    assert path.read_text(encoding="utf-8") == before

    unknown = SAMPLE.replace("custom:vertical-layout", "custom:future-layout")
    path.write_text(unknown, encoding="utf-8")
    blocked = web._generated_dashboard_export(path)
    assert blocked["valid"] is False
    assert "unknown custom view dependency" in blocked["error"]

    two_views = SAMPLE + "\n  - title: Second\n    cards:\n      - type: markdown\n        content: second\n"
    path.write_text(two_views, encoding="utf-8")
    blocked_cards = web._generated_dashboard_export(path, cards_only=True)
    assert blocked_cards["valid"] is False
    assert "exactly one view" in blocked_cards["error"]

source = Path(web.__file__).read_text(encoding="utf-8")
for marker in (
    'id="previewGeneratedDashboardYamlButton"',
    'id="copyGeneratedDashboardYamlButton"',
    'id="copyGeneratedCardsOnlyButton"',
    'id="downloadGeneratedDashboardYamlButton"',
    '/api/generated-card-yaml/dashboard-export',
    '/api/generated-card-yaml/cards-export',
    '/download/switch-vision-dashboard.yaml',
    "fetchGeneratedDashboardExport('dashboard')",
    "fetchGeneratedDashboardExport('cards')",
):
    assert marker in source, marker

print("Switch Vision Discovery dashboard YAML manual-export regression: PASS")
