#!/usr/bin/env python3
from pathlib import Path

base = Path(__file__).resolve().parent
profiles = (base / "calibration_profiles.js").read_text(encoding="utf-8")
manager = (base / "calibration_profiles_manager.js").read_text(encoding="utf-8")

for marker in (
    "const inactiveCount =",
    "`${inactiveCount} inactive`",
    "async function deleteAllInactive()",
    "item.active !== true",
    'item.scope !== "factory"',
    "await deleteSelected();",
    "deleteAllInactive,",
):
    assert marker in profiles, marker
assert "SwitchVisionCalibrationProfiles" in manager
assert "?.deleteAllInactive?.();" in manager
handler = manager.split('$("svProfileManagerDeleteAllUnused")', 1)[1].split('function selectCard', 1)[0]
assert 'querySelectorAll' not in handler
assert 'dispatchEvent' not in handler
print("Switch Vision Calibration inactive-profile manager regression: PASS")
