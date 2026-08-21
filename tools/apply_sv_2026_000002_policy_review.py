#!/usr/bin/env python3
"""Temporary review-only patch for Discovery's UniFi visual-policy regression."""
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "runtime_src" / "self-test.sh"
text = path.read_text(encoding="utf-8")
old = '''# Every known UniFi model must carry an explicit visual/profile assignment and
# must never fall through to Cisco-specific artwork/profile names.
for model, device in models.items():
    if device.get("vendor") != "Ubiquiti":
        continue
    faceplate = str(device.get("default_faceplate") or "")
    profile = str(device.get("calibration_profile") or "")
    visuals = device.get("visuals") if isinstance(device.get("visuals"), dict) else {}
    assert faceplate and profile, model
    assert visuals.get("recommended_faceplate") == faceplate, model
    assert visuals.get("calibration_profile") == profile, model
    assert "cisco" not in faceplate.lower(), (model, faceplate)
    assert not profile.lower().startswith("cisco_"), (model, profile)
print("Switch Vision Discovery v2.1.27 hardware/status/UniFi contract regression: PASS")'''
new = '''# UniFi models that claim dashboard support must carry an explicit visual/profile
# assignment. Detected hardware may intentionally remain visual-pending, but
# profile/faceplate state must stay paired and must never fall through to Cisco
# artwork/profile names.
for model, device in models.items():
    if device.get("vendor") != "Ubiquiti":
        continue
    faceplate = str(device.get("default_faceplate") or "")
    profile = str(device.get("calibration_profile") or "")
    visuals = device.get("visuals") if isinstance(device.get("visuals"), dict) else {}
    if device.get("dashboard_support") is True:
        assert faceplate and profile, model
    assert bool(faceplate) == bool(profile), model
    assert str(visuals.get("recommended_faceplate") or "") == faceplate, model
    assert str(visuals.get("calibration_profile") or "") == profile, model
    if faceplate:
        assert "cisco" not in faceplate.lower(), (model, faceplate)
        assert not profile.lower().startswith("cisco_"), (model, profile)
print("Switch Vision Discovery v2.1.27 hardware/status/UniFi contract regression: PASS")'''
if new not in text:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"UniFi visual-policy test target count={count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
print("Discovery UniFi visual-policy regression updated for detected-only models")
