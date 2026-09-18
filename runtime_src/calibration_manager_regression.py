#!/usr/bin/env python3
from pathlib import Path

base = Path(__file__).resolve().parent
profiles = (base / "calibration_profiles.js").read_text(encoding="utf-8")
manager = (base / "calibration_profiles_manager.js").read_text(encoding="utf-8")

for marker in (
    "const inactiveCount =",
    "`${inactiveCount} inactive`",
    "async function deleteAllUnused()",
    "item.active !== true",
    'item.scope !== "factory"',
    "await deleteSelected();",
    "deleteAllUnused,",
):
    assert marker in profiles, marker
assert "SwitchVisionCalibrationProfiles" in manager
assert "?.deleteAllUnused?.();" in manager
handler = manager.split('$("svProfileManagerDeleteAllUnused")', 1)[1].split('function selectCard', 1)[0]
assert 'querySelectorAll' not in handler
assert 'dispatchEvent' not in handler
print("Switch Vision Calibration unused-profile manager regression: PASS")

assert ">Delete All Unused</button>" in manager
assert 'deleteButton.textContent = "Delete Selected";' in manager
assert "Delete All Inactive" not in manager
