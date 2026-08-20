#!/usr/bin/env python3
from pathlib import Path

path = Path('tools/prepare_v2127.py')
text = path.read_text(encoding='utf-8')
anchor = '''if seen != TARGET_MODELS:\n    raise SystemExit(f"ERROR: registry target mismatch: missing {sorted(TARGET_MODELS-seen)}")\nwrite(registry_path, json.dumps(registry, indent=2) + "\\n")\n'''
replacement = '''if seen != TARGET_MODELS:\n    raise SystemExit(f"ERROR: registry target mismatch: missing {sorted(TARGET_MODELS-seen)}")\n\n# Inventory every known UniFi exact model.  Dedicated 24+2 hardware uses the\n# UniFi artwork/profile; other layouts receive an explicit stock profile based\n# on their real API geometry.  No Ubiquiti model may retain a Cisco profile.\nfor device in registry.get("devices", []):\n    if not isinstance(device, dict) or device.get("vendor") != "Ubiquiti":\n        continue\n    ports = device.get("ports") if isinstance(device.get("ports"), dict) else {}\n    rj45 = int(ports.get("rj45") or 0)\n    uplinks = int(ports.get("uplinks") or 0)\n    if rj45 == 24 and uplinks == 2:\n        profile = "unifi_24p_rj45_2sfp"\n        faceplate = "faceplates/unifi-24p-rj45-2sfp.png"\n    else:\n        family = 24 if rj45 <= 24 else 48\n        sfp = 2 if uplinks <= 2 else 4\n        profile = f"stock_{family}rj45_{sfp}sfp"\n        faceplate = f"faceplates/{family}rj45-{sfp}sfp.png"\n    device["calibration_profile"] = profile\n    device["default_faceplate"] = faceplate\n    visuals = device.setdefault("visuals", {})\n    if not isinstance(visuals, dict):\n        raise SystemExit(f"ERROR: {device.get('model')}: visuals is not a mapping")\n    visuals["recommended_faceplate"] = faceplate\n    visuals["calibration_profile"] = profile\n    notes = device.setdefault("notes", [])\n    explicit_note = "UniFi visual selection is explicit for this exact model and follows its validated API port geometry; no Cisco-specific profile fallback is used."\n    if isinstance(notes, list) and explicit_note not in notes:\n        notes.append(explicit_note)\n\nwrite(registry_path, json.dumps(registry, indent=2) + "\\n")\n'''
if text.count(anchor) != 1:
    raise SystemExit(f'ERROR: expected one registry-write anchor, found {text.count(anchor)}')
text = text.replace(anchor, replacement, 1)
path.write_text(text, encoding='utf-8', newline='\n')
print('Added explicit UniFi visual inventory to Discovery 2.1.27 preparation')
