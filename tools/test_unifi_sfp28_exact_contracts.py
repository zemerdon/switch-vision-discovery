from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "runtime_src" / "profiles" / "switch-vision-profiles.yaml"
REGISTRY = ROOT / "runtime_src" / "opt" / "switch-vision" / "devices" / "supported_devices.json"
SUPPORT = ROOT / "runtime_src" / "support_my_switch.sh"
DASHBOARD = ROOT / "runtime_src" / "unifi_dashboard_cards.py"

profiles = yaml.safe_load(PROFILES.read_text(encoding="utf-8"))["profiles"]
udm_profile = profiles["ubiquiti-udm-pro-max-api"]
xg_profile = profiles["ubiquiti-usw-pro-xg-24-poe-api"]
assert udm_profile["layout"]["rj45_ports"] == 9
assert udm_profile["layout"]["sfp_10g_ports"] == 2
assert udm_profile["layout"]["sfp_25g_ports"] == 0
assert xg_profile["layout"]["rj45_ports"] == 24
assert xg_profile["layout"]["sfp_10g_ports"] == 0
assert xg_profile["layout"]["sfp_25g_ports"] == 2
assert xg_profile["interface_patterns"]["sfp_25g"] == ["api-port-25", "api-port-26"]

registry_doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
models = {d["model"]: d for d in registry_doc["devices"] if isinstance(d, dict)}
udm = models["UDM Pro Max"]
xg = models["USW Pro XG 24 PoE"]
assert udm["status"] == "experimental"
assert udm["mapping_profile"] == "ubiquiti-udm-pro-max-api"
assert xg["status"] == "experimental"
assert xg["mapping_profile"] == "ubiquiti-usw-pro-xg-24-poe-api"
assert xg["ports"]["twenty_five_gigabit_sfp28"] == 2
for item in (udm, xg):
    public = json.dumps(item).casefold()
    assert "kc1koc" not in public
    assert "sv-2026-000011" not in public
    assert "switch_vision_contribution" not in public

support_text = SUPPORT.read_text(encoding="utf-8")
FINGERPRINT_FILTER = '[.vendor,(if (.data_source == "unifi_api" and (.model == "UDM Pro Max" or .model == "USW Pro XG 24 PoE")) then "UniFi" else .family end),.model,.sys_object_id,.physical_count,.rj45_count,((.sfp_count // 0) + (.sfp_plus_count // 0)),.stack_count] | map(tostring) | join("|")'
assert FINGERPRINT_FILTER.split(" | map", 1)[0] in support_text
marker = "<<'PY_UNIFI_SUMMARY'"
start = support_text.index(marker)
start = support_text.index("\n", start) + 1
end = support_text.index("\nPY_UNIFI_SUMMARY", start)
embedded = support_text[start:end]

snapshot = {
    "devices": [
        {
            "id": "masked-device",
            "name": "masked-switch",
            "model": "USW Pro XG 24 PoE",
            "api_capabilities": {"port_detail": True, "per_port_traffic": False},
            "ports": [
                *[
                    {
                        "idx": idx,
                        "connector": "RJ45",
                        "max_speed_mbps": 2500 if idx <= 8 else 10000,
                        "speed_mbps": 1000 if idx == 1 else None,
                        "poe": {"available": True, "standard": "802.3bt", "type": 4},
                    }
                    for idx in range(1, 25)
                ],
                {"idx": 25, "connector": "SFP28", "max_speed_mbps": 25000, "speed_mbps": 25000},
                {"idx": 26, "connector": "SFP28", "max_speed_mbps": 25000, "speed_mbps": 10000},
            ],
        }
    ]
}

with tempfile.TemporaryDirectory() as temp_name:
    temp = Path(temp_name)
    summary_path = temp / "summary.json"
    snapshot_path = temp / "snapshot.json"
    embedded_path = temp / "summary_helper.py"
    summary_path.write_text("[]\n", encoding="utf-8")
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    embedded_path.write_text(embedded + "\n", encoding="utf-8")
    subprocess.run(
        [sys.executable, str(embedded_path), str(summary_path), str(snapshot_path), str(REGISTRY)],
        check=True,
    )
    rows = json.loads(summary_path.read_text(encoding="utf-8"))
    assert len(rows) == 1
    row = rows[0]
    assert row["registry_match"] is True
    assert row["registry_status"] == "experimental"
    assert row["rj45_count"] == 24
    assert row["sfp_count"] == 0
    assert row["sfp_plus_count"] == 0
    assert row["sfp28_count"] == 2
    assert row["uplink_count"] == 2
    fingerprint_source = subprocess.run(
        ["jq", "-r", FINGERPRINT_FILTER],
        input=json.dumps(row),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    ).stdout.strip()
    assert fingerprint_source == "Ubiquiti|UniFi|USW Pro XG 24 PoE|unifi-api|26|24|0|0"

    dashboard_snapshot = temp / "dashboard-snapshot.json"
    dashboard_snapshot.write_text(json.dumps(snapshot), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(DASHBOARD),
            "--snapshot",
            str(dashboard_snapshot),
            "--registry",
            str(REGISTRY),
            "--indent",
            "0",
            "--summary",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    output = result.stdout
    assert "switch_model: USW Pro XG 24 PoE" in output
    assert "port_count: 24" in output
    assert "sfp_port_count: 2" in output
    assert "generic_faceplate: false" in output
    assert "sfp:\n    - 25\n    - 26" in output

print("Switch Vision Discovery UDM Pro Max / USW Pro XG 24 PoE + SFP28 contracts: PASS")
