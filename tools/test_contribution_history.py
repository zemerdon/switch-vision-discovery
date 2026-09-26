#!/usr/bin/env python3
from pathlib import Path
import json
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
sys.path.insert(0, str(RUNTIME))

import support_web

source = (RUNTIME / "support_web.py").read_text(encoding="utf-8")
assert 'id="supportTab-history"' in source
assert 'id="contributionHistoryList"' in source
assert '"/api/contributions/history"' in source
assert "path.is_symlink()" in source
assert "Download ZIP" in source
assert "Download EML" in source
assert "Download Actions HTML" in source

with tempfile.TemporaryDirectory(prefix="sv-contribution-history-") as td:
    root = Path(td)
    archive = root / "Switch_Vision_Contribution_SV-2026-000099_20260925-010203.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(
            "Switch_Vision_Contribution_SV-2026-000099/MANIFEST.json",
            json.dumps({
                "contribution_id": "SV-2026-000099",
                "switch_vision_version": "3.0.6",
                "bundle_quality": "verified",
                "ready_to_send": True,
                "created_at": "2026-09-25T01:02:03Z",
                "contributor_value": "must-not-leak",
            }),
        )
        zf.writestr(
            "Switch_Vision_Contribution_SV-2026-000099/DEVICE_SUMMARY.json",
            json.dumps([
                {"model": "WS-C3850-12XS-E", "hostname": "private-switch-name"},
                {"model": "WS-C2960X-24PS-L"},
            ]),
        )
    archive.with_suffix(".eml").write_text("mail", encoding="utf-8")
    archive.with_name(archive.stem + "_Actions.html").write_text("<html></html>", encoding="utf-8")

    history = support_web._contribution_history(root)
    assert len(history) == 1
    item = history[0]
    assert item["contribution_id"] == "SV-2026-000099"
    assert item["version"] == "3.0.6"
    assert item["quality"] == "verified"
    assert item["ready_to_send"] is True
    assert item["device_count"] == 2
    assert item["models"] == ["WS-C3850-12XS-E", "WS-C2960X-24PS-L"]
    assert item["email"].endswith(".eml")
    assert item["actions"].endswith("_Actions.html")
    assert "contributor_value" not in item
    assert "hostname" not in json.dumps(item)

    outside = root / "Switch_Vision_Contribution_SV-2026-000100_20260925-010204.zip"
    target = root / "real.zip"
    with zipfile.ZipFile(target, "w") as zf:
        zf.writestr(
            "outside/MANIFEST.json",
            json.dumps({"contribution_id": "OUTSIDE", "switch_vision_version": "9.9.9"}),
        )
        zf.writestr("outside/DEVICE_SUMMARY.json", "[]")
    try:
        outside.symlink_to(target)
    except OSError:
        pass
    else:
        assert all(row["archive"] != outside.name for row in support_web._contribution_history(root))
        latest = support_web._latest_contribution(root)
        assert latest is not None
        assert latest["archive"] == archive.name
        assert latest["contribution_id"] == "SV-2026-000099"

        email_path = archive.with_suffix(".eml")
        actions_path = archive.with_name(archive.stem + "_Actions.html")
        email_path.unlink()
        actions_path.unlink()
        outside_email = root / "outside.eml"
        outside_actions = root / "outside.html"
        outside_email.write_text("external mail", encoding="utf-8")
        outside_actions.write_text("<html>external</html>", encoding="utf-8")
        email_path.symlink_to(outside_email)
        actions_path.symlink_to(outside_actions)
        latest = support_web._latest_contribution(root)
        assert latest is not None
        assert latest["email"] is None
        assert latest["actions"] is None

print("Discovery contribution history regression: PASS")
