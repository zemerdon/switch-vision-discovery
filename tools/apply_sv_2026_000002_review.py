#!/usr/bin/env python3
"""Temporary review-branch patcher for SV-2026-000002; remove before final review."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_REGISTRY_URL = (
    "https://raw.githubusercontent.com/zemerdon/switch-vision-releases/"
    "fc61bc6719e759a7299310d772b3e97cd80024ab/src/devices/supported_devices.json"
)
REGISTRY = ROOT / "runtime_src" / "opt" / "switch-vision" / "devices" / "supported_devices.json"
PROFILES = ROOT / "runtime_src" / "profiles" / "switch-vision-profiles.yaml"
CARDS = ROOT / "runtime_src" / "unifi_dashboard_cards.py"
SELF_TEST = ROOT / "runtime_src" / "self-test.sh"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one patch target, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


# Synchronize the informational registry exactly from the reviewed Core head.
request = urllib.request.Request(
    CORE_REGISTRY_URL,
    headers={"User-Agent": "Switch-Vision-Discovery-SV-2026-000002/1"},
)
with urllib.request.urlopen(request, timeout=30) as response:
    registry_bytes = response.read()
payload = json.loads(registry_bytes.decode("utf-8"))
models = {str(item.get("model")): item for item in payload.get("devices", []) if isinstance(item, dict)}
for model in ("US 48", "US XG 16", "USW Pro Aggregation"):
    if model not in models:
        raise SystemExit(f"reviewed Core registry is missing {model}")
REGISTRY.write_bytes(registry_bytes)

# Keep the existing legacy sequential fields for old cards, but make exact
# dashboard-disabled models non-renderable and forward explicit API maps when
# a future verified visual enables them.
replace_once(
    CARDS,
    'str(p.get("connector") or "").upper() in {"SFP", "SFPPLUS", "SFP+"}',
    'str(p.get("connector") or "").upper() in {"SFP", "SFPPLUS", "SFP+", "SFP28"}',
)
replace_once(
    CARDS,
    '''        if not reg:\n            lines.append(f"{pad}# UniFi {json.dumps(model)} detected, but no exact Switch Vision registry entry exists yet.")\n            skipped += 1\n            continue\n        visual_fallback = False\n''',
    '''        if not reg:\n            lines.append(f"{pad}# UniFi {json.dumps(model)} detected, but no exact Switch Vision registry entry exists yet.")\n            skipped += 1\n            continue\n        if reg.get("dashboard_support") is not True:\n            lines.append(f"{pad}# UniFi {json.dumps(model)} detected; dashboard support is pending verified visuals.")\n            skipped += 1\n            continue\n        api_port_map = reg.get("unifi_api_port_map") if isinstance(reg.get("unifi_api_port_map"), dict) else None\n        visual_fallback = False\n''',
)
replace_once(
    CARDS,
    '''        if visual_fallback:\n            lines.append(f"{pad}# Generic 48 RJ45 + 4 SFP temporary visual fallback for {json.dumps(model)}.")\n''',
    '''        if api_port_map is not None:\n            card["unifi_api_port_map"] = api_port_map\n        if visual_fallback:\n            lines.append(f"{pad}# Generic 48 RJ45 + 4 SFP temporary visual fallback for {json.dumps(model)}.")\n''',
)

profile_text = PROFILES.read_text(encoding="utf-8")
profile_marker = "  ubiquiti-us-48-api:"
if profile_marker not in profile_text:
    profile_block = r'''
  ubiquiti-us-48-api:
    status: experimental
    vendor: Ubiquiti
    family: UniFi Switch
    model_patterns:
    - US 48
    layout:
      members: 1
      rj45_ports: 48
      sfp_1g_ports: 2
      sfp_10g_ports: 2
    interface_patterns:
      rj45:
      - api-port-{port}
      sfp_1g:
      - api-port-51
      - api-port-52
      sfp_10g:
      - api-port-49
      - api-port-50
    notes:
    - SV-2026-000002 confirms the legacy sequential API path: RJ45 1-48, 10G SFP+ 49-50, 1G SFP 51-52.
  ubiquiti-us-xg-16-api:
    status: detected
    vendor: Ubiquiti
    family: UniFi Switch XG
    model_patterns:
    - US XG 16
    layout:
      members: 1
      rj45_ports: 4
      sfp_1g_ports: 0
      sfp_10g_ports: 12
    interface_patterns:
      rj45:
      - api-port-13
      - api-port-14
      - api-port-15
      - api-port-16
      sfp_1g: []
      sfp_10g:
      - api-port-1
      - api-port-2
      - api-port-3
      - api-port-4
      - api-port-5
      - api-port-6
      - api-port-7
      - api-port-8
      - api-port-9
      - api-port-10
      - api-port-11
      - api-port-12
    notes:
    - SV-2026-000002 confirms optical-first API numbering; do not replace this with a copper-first offset.
    - Dashboard output remains disabled until verified 12-SFP+ + 4-RJ45 visual coordinates exist.
  ubiquiti-usw-pro-aggregation-api:
    status: detected
    vendor: Ubiquiti
    family: UniFi Switch Pro Aggregation
    model_patterns:
    - USW Pro Aggregation
    layout:
      members: 1
      rj45_ports: 0
      sfp_1g_ports: 0
      sfp_10g_ports: 28
      sfp_25g_ports: 4
    interface_patterns:
      rj45: []
      sfp_1g: []
      sfp_10g:
      - api-port-1
      - api-port-2
      - api-port-3
      - api-port-4
      - api-port-5
      - api-port-6
      - api-port-7
      - api-port-8
      - api-port-9
      - api-port-10
      - api-port-11
      - api-port-12
      - api-port-13
      - api-port-14
      - api-port-15
      - api-port-16
      - api-port-17
      - api-port-18
      - api-port-19
      - api-port-20
      - api-port-21
      - api-port-22
      - api-port-23
      - api-port-24
      - api-port-25
      - api-port-26
      - api-port-27
      - api-port-28
      sfp_25g:
      - api-port-29
      - api-port-30
      - api-port-31
      - api-port-32
    notes:
    - SV-2026-000002 confirms 28x 10G SFP+ plus 4x 25G SFP28 and no RJ45 ports.
    - The sfp_25g fields preserve observed hardware truth for this detected-only profile; dashboard output remains disabled until verified 32-port optical geometry exists.
'''
    PROFILES.write_text(profile_text.rstrip() + "\n" + profile_block.lstrip("\n"), encoding="utf-8", newline="\n")

self_test_text = SELF_TEST.read_text(encoding="utf-8")
self_test_marker = "Switch Vision Discovery SV-2026-000002 UniFi contract regression: PASS"
if self_test_marker not in self_test_text:
    self_test_block = r'''

# SV-2026-000002 UniFi exact-model/API mapping regression.
python3 - "$RUNTIME_REGISTRY" "$BASE_DIR/profiles/switch-vision-profiles.yaml" <<'PYTEST_SV_2026_000002'
import json
import sys
from pathlib import Path
import yaml

registry = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
profiles_doc = yaml.safe_load(Path(sys.argv[2]).read_text(encoding="utf-8")) or {}
profiles = profiles_doc.get("profiles", profiles_doc)
models = {d["model"]: d for d in registry["devices"] if isinstance(d, dict)}

us48 = models["US 48"]
assert us48["status"] == "experimental"
assert us48["ports"]["rj45"] == 48
assert us48["ports"]["gigabit_sfp"] == 2
assert us48["ports"]["ten_gigabit_sfp_plus"] == 2
assert "unifi_api_port_map" not in us48

xg16 = models["US XG 16"]
assert xg16["status"] == "detected"
assert xg16["dashboard_support"] is False
assert xg16["unifi_api_port_map"]["sfp"] == list(range(1, 13))
assert xg16["unifi_api_port_map"]["rj45"] == [13, 14, 15, 16]

agg = models["USW Pro Aggregation"]
assert agg["status"] == "detected"
assert agg["dashboard_support"] is False
assert agg["ports"]["rj45"] == 0
assert agg["ports"]["ten_gigabit_sfp_plus"] == 28
assert agg["ports"]["twenty_five_gigabit_sfp28"] == 4
assert agg["unifi_api_port_map"]["sfp"] == list(range(1, 33))

p48 = profiles["ubiquiti-us-48-api"]
assert p48["layout"] == {"members": 1, "rj45_ports": 48, "sfp_1g_ports": 2, "sfp_10g_ports": 2}
assert p48["interface_patterns"]["sfp_10g"] == ["api-port-49", "api-port-50"]
assert p48["interface_patterns"]["sfp_1g"] == ["api-port-51", "api-port-52"]
pxg = profiles["ubiquiti-us-xg-16-api"]
assert pxg["interface_patterns"]["rj45"] == ["api-port-13", "api-port-14", "api-port-15", "api-port-16"]
assert pxg["interface_patterns"]["sfp_10g"] == [f"api-port-{n}" for n in range(1, 13)]
pagg = profiles["ubiquiti-usw-pro-aggregation-api"]
assert pagg["layout"]["rj45_ports"] == 0
assert pagg["layout"]["sfp_10g_ports"] == 28
assert pagg["layout"]["sfp_25g_ports"] == 4
assert pagg["interface_patterns"]["sfp_25g"] == [f"api-port-{n}" for n in range(29, 33)]
print("Switch Vision Discovery SV-2026-000002 UniFi contract regression: PASS")
PYTEST_SV_2026_000002

python3 - "$tmp_dir/sv-2026-000002-unifi.json" <<'PYTEST_SV_2026_000002_SNAPSHOT'
import json
import sys
from pathlib import Path

def ports(items):
    return [{"idx": idx, "connector": connector} for idx, connector in items]

snapshot = {
    "devices": [
        {
            "id": "us48-test",
            "name": "US 48 test",
            "model": "US 48",
            "api_capabilities": {"port_detail": True, "per_port_traffic": False},
            "ports": ports([(n, "RJ45") for n in range(1, 49)] + [(49, "SFPPLUS"), (50, "SFPPLUS"), (51, "SFP"), (52, "SFP")]),
        },
        {
            "id": "xg16-test",
            "name": "US XG 16 test",
            "model": "US XG 16",
            "api_capabilities": {"port_detail": True, "per_port_traffic": False},
            "ports": ports([(n, "SFPPLUS") for n in range(1, 13)] + [(n, "RJ45") for n in range(13, 17)]),
        },
        {
            "id": "aggregation-test",
            "name": "Pro Aggregation test",
            "model": "USW Pro Aggregation",
            "api_capabilities": {"port_detail": True, "per_port_traffic": False},
            "ports": ports([(n, "SFPPLUS") for n in range(1, 29)] + [(n, "SFP28") for n in range(29, 33)]),
        },
    ]
}
Path(sys.argv[1]).write_text(json.dumps(snapshot), encoding="utf-8")
PYTEST_SV_2026_000002_SNAPSHOT
python3 "$BASE_DIR/unifi_dashboard_cards.py" \
    --snapshot "$tmp_dir/sv-2026-000002-unifi.json" \
    --registry "$RUNTIME_REGISTRY" \
    --summary > "$tmp_dir/sv-2026-000002-cards.yaml"
grep -q 'switch_model: US 48' "$tmp_dir/sv-2026-000002-cards.yaml"
grep -q 'unifi_sfp_port_offset: 48' "$tmp_dir/sv-2026-000002-cards.yaml"
! grep -q 'switch_model: US XG 16' "$tmp_dir/sv-2026-000002-cards.yaml"
! grep -q 'switch_model: USW Pro Aggregation' "$tmp_dir/sv-2026-000002-cards.yaml"
grep -q 'US XG 16.*dashboard support is pending verified visuals' "$tmp_dir/sv-2026-000002-cards.yaml"
grep -q 'USW Pro Aggregation.*dashboard support is pending verified visuals' "$tmp_dir/sv-2026-000002-cards.yaml"
grep -q 'UniFi cards emitted: 1; waiting for visuals/registry: 2' "$tmp_dir/sv-2026-000002-cards.yaml"
echo "Switch Vision Discovery SV-2026-000002 generated-card regression: PASS"
'''
    SELF_TEST.write_text(self_test_text.rstrip() + self_test_block + "\n", encoding="utf-8", newline="\n")

print("SV-2026-000002 Discovery review patch applied")
