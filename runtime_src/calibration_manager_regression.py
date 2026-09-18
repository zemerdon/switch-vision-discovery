#!/usr/bin/env python3
from pathlib import Path

base = Path(__file__).resolve().parent
profiles = (base / "calibration_profiles.js").read_text(encoding="utf-8")
manager = (base / "calibration_profiles_manager.js").read_text(encoding="utf-8")
web = (base / "support_web.py").read_text(encoding="utf-8")

for marker in (
    "const inactiveCount =",
    "`${inactiveCount} inactive`",
    "async function deleteAllUnused()",
    "item.active !== true",
    'item.scope !== "factory"',
    "await deleteSelected();",
    "deleteSelected,",
    "deleteAllUnused,",
):
    assert marker in profiles, marker
assert "SwitchVisionCalibrationProfiles" in manager
assert "?.deleteAllUnused?.();" in manager
assert "?.deleteSelected?.();" in manager
assert "switch_vision/delete_calibration" in web
delete_route = web.split('"/api/calibration-profiles/delete"', 1)[1].split("return", 1)[0]
assert "_home_assistant_ws(" in delete_route
assert "_home_assistant_service(" not in delete_route
handler = manager.split('$("svProfileManagerDeleteAllUnused")', 1)[1].split('function selectCard', 1)[0]
assert 'querySelectorAll' not in handler
assert 'dispatchEvent' not in handler
print("Switch Vision Calibration unused-profile manager regression: PASS")

assert ">Delete All Unused</button>" in manager
assert 'deleteButton.textContent = "Delete Selected";' in manager
assert "Delete All Inactive" not in manager
