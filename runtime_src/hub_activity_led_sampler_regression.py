#!/usr/bin/env python3
from pathlib import Path

source = Path(__file__).with_name("support_web.py").read_text(encoding="utf-8")

required = {
    "saved snapshot state": "savedCoreActivity:null",
    "authoritative snapshot clone": "state.savedCoreActivity=state.core?.settings?.activity_leds?clone(state.core.settings.activity_leds):null",
    "saved period source": "const value=Number(state.savedCoreActivity?.[key]);",
    "allowed minimum": "ACTIVITY_SAMPLE_MIN_MS=120",
    "allowed maximum": "ACTIVITY_SAMPLE_MAX_MS=2000",
    "slow row": "activitySampleRow('Slow traffic','activity_slow_period_ms')",
    "medium row": "activitySampleRow('Medium traffic','activity_medium_period_ms')",
    "fast row": "activitySampleRow('Fast traffic','activity_fast_period_ms')",
    "saved rate display": "rate.textContent=`Saved: ${period} ms`",
    "sample button": "button.textContent='Sample'",
    "reduced motion": "prefers-reduced-motion: reduce",
    "temporary stop": "activitySampleStopTimer=setTimeout(stopActivitySample",
    "tab cleanup": "if(selected!=='core')stopActivitySample()",
    "small preview led": ".hub-activity-sample-led{width:12px;height:12px",
    "Core dwell helper": "function activitySampleDurationMs(key,on)",
    "Slow ON dwell": "Math.max(120,Math.round(cadence*(0.22+(a*0.20))))",
    "Slow OFF dwell": "Math.max(140,Math.round(cadence*(0.70+(a*1.15)+(b*0.35))))",
    "Medium ON dwell": "Math.max(120,Math.round(cadence*(0.45+(a*0.30))))",
    "Medium OFF dwell": "Math.max(100,Math.round(cadence*(0.35+(a*0.70)+(b*0.20))))",
    "Fast ON dwell": "Math.max(90,Math.round(cadence*(1.04+(a*0.13))))",
    "Fast OFF dwell": "Math.max(25,Math.round(cadence*(0.24+(a*0.06)+(b*0.03))))",
    "dwell-driven sample loop": "setTimeout(toggle,activitySampleDurationMs(key,on))",
}

for label, literal in required.items():
    assert literal in source, f"missing {label}: {literal}"

# The saved snapshot must refresh only from authoritative load/save/reset paths.
assert source.count("captureSavedCoreActivity()") == 4, "unexpected saved snapshot capture count"
assert "s.activity_leds[k]=Number(x);mark('core')" in source
assert "savedActivityPeriod(key)" in source
assert "state.core.settings.activity_leds?.[key]" not in source

# All three editable timing controls and help text retain the real Core range.
for label in ("Slow blink period (ms)", "Medium blink period (ms)", "Fast blink period (ms)"):
    assert f"'{label}':'" in source
assert source.count("Allowed range: 120–2000 ms.") >= 4
for key in ("activity_slow_period_ms", "activity_medium_period_ms", "activity_fast_period_ms"):
    assert f"['{key}'" in source
assert "120,2000,1" in source

# Preview is event-driven JS only; do not introduce a continuously running CSS animation.
assert "@keyframes" not in source[source.find(".hub-activity-samples"):source.find(".hub-setting-row{", source.find(".hub-activity-samples"))]
assert "animation:infinite" not in source
assert "setTimeout(toggle,period)" not in source, "sampler must use Core dwell logic, not raw period toggles"

# Fast preview stays aligned with Core's physical-switch reference at the 120 ms default.
cadence = 120
on_min = round(cadence * 1.04)
on_max = round(cadence * (1.04 + 0.13))
off_min = round(cadence * 0.24)
off_max = round(cadence * (0.24 + 0.06 + 0.03))
average_on = cadence * (1.04 + (0.5 * 0.13))
average_off = cadence * (0.24 + (0.5 * 0.06) + (0.5 * 0.03))
average_cycle = average_on + average_off
assert (on_min, on_max) == (125, 140)
assert (off_min, off_max) == (29, 40)
assert 5.8 <= 1000 / average_cycle <= 6.2
assert 0.78 <= average_on / average_cycle <= 0.82

print("PASS: Hub Activity LED saved-setting sampler contract")
