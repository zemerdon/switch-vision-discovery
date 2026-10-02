# Switch Vision Discovery self-test UniFi community-validation module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# v2.1.19 community-validation UniFi profile regression.
v219_community_snapshot="$tmp_dir/unifi-community-fixture-b.json"
python3 - "$v219_community_snapshot" <<'PYTEST_V219_COMMUNITY'
import json, sys
path = sys.argv[1]

def port(idx, connector="RJ45", max_speed=1000, poe=False, standard=None):
    return {
        "idx": idx,
        "state": "UP",
        "connector": connector,
        "speed_mbps": max_speed,
        "max_speed_mbps": max_speed,
        "poe": {
            "available": bool(poe),
            "enabled": bool(poe),
            "state": "UP" if poe else "DOWN",
            "standard": standard,
        },
    }

mini = [port(i) for i in range(1, 6)]
pro24 = [port(i) for i in range(1, 25)] + [
    port(25, "SFPPLUS", 10000), port(26, "SFPPLUS", 10000)
]
us8 = [
    port(i, poe=(5 <= i <= 8), standard="802.3af" if 5 <= i <= 8 else None)
    for i in range(1, 9)
]
us8[6]["poe"]["state"] = "DOWN"
udm = [port(i, poe=True, standard="802.3at") for i in range(1, 9)]
udm += [port(9, "RJ45", 2500), port(10, "SFPPLUS", 10000), port(11, "SFPPLUS", 10000)]
usw24 = [
    port(i, poe=(i <= 16), standard="802.3at" if i <= 16 else None)
    for i in range(1, 25)
] + [port(25, "SFP", 1000), port(26, "SFP", 1000)]
usw24g2 = [port(i) for i in range(1, 25)] + [
    port(25, "SFP", 1000), port(26, "SFP", 1000)
]

devices = []
for n in range(1, 4):
    devices.append({
        "id": f"sv57-mini-{n}",
        "name": f"Flex Mini {n}",
        "model": "USW Flex Mini",
        "ports": mini,
        "api_capabilities": {"port_detail": True, "per_port_traffic": False},
    })
devices += [
    {"id":"sv57-pro24","name":"Pro24","model":"USW Pro 24","ports":pro24,
     "api_capabilities":{"port_detail":True,"per_port_traffic":False}},
    {"id":"sv57-us8","name":"US8","model":"US 8 60W","ports":us8,
     "api_capabilities":{"port_detail":True,"per_port_traffic":False}},
    {"id":"sv57-udm","name":"UDM SE","model":"UniFi Dream Machine PRO SE","ports":udm,
     "api_capabilities":{"port_detail":True,"per_port_traffic":False}},
    {"id":"sv57-usw24","name":"USW24","model":"USW-24-PoE","ports":usw24,
     "api_capabilities":{"port_detail":True,"per_port_traffic":False}},
    {"id":"sv57-usw24g2","name":"USW24G2","model":"USW-24-G2","ports":usw24g2,
     "api_capabilities":{"port_detail":True,"per_port_traffic":True}},
]
json.dump({"schema_version":1,"devices":devices}, open(path,"w"))
PYTEST_V219_COMMUNITY

python3 "$BASE_DIR/unifi_dashboard_cards.py" \
  --snapshot "$v219_community_snapshot" \
  --registry "$RUNTIME_REGISTRY" \
  --indent 0 \
  > "$tmp_dir/unifi-community-fixture-b-cards.yaml"

for model in "USW Flex Mini" "USW Pro 24" "US 8 60W" "UniFi Dream Machine PRO SE" "USW-24-PoE" "USW-24-G2"; do
  grep -q "switch_model: $model" "$tmp_dir/unifi-community-fixture-b-cards.yaml"
done

[ "$(grep -c 'switch_model: USW Flex Mini' "$tmp_dir/unifi-community-fixture-b-cards.yaml")" -eq 3 ]

python3 - "$RUNTIME_REGISTRY" "$BASE_DIR/profiles/switch-vision-profiles.yaml" <<'PYTEST_V219_REGISTRY'
import json, sys
from pathlib import Path
import yaml
reg=json.loads(Path(sys.argv[1]).read_text())
prof=yaml.safe_load(Path(sys.argv[2]).read_text())
profiles=prof.get("profiles", prof)
devices={d["model"]:d for d in reg["devices"]}

assert devices["USW-24-PoE"]["ports"]["gigabit_sfp"] == 2
assert devices["USW-24-PoE"]["ports"]["ten_gigabit_sfp_plus"] == 0
assert devices["USW-24-G2"]["status"] == "experimental"
assert devices["USW-24-G2"]["ports"]["rj45"] == 24
assert devices["USW-24-G2"]["ports"]["gigabit_sfp"] == 2
assert devices["USW-24-G2"]["ports"]["poe"] is False
assert devices["USW-24-G2"]["mapping_profile"] == "ubiquiti-usw-24-g2-api"
assert devices["USW Pro 24"]["ports"]["gigabit_sfp"] == 0
assert devices["USW Pro 24"]["ports"]["ten_gigabit_sfp_plus"] == 2
assert devices["US 8 60W"]["validation"]["poe"] == "live_api_confirmed_ports_5_8_802_3af"
assert devices["UniFi Dream Machine PRO SE"]["validation"]["poe"] == "live_api_confirmed_ports_1_8"
assert devices["USW Flex Mini"]["validation"]["exact_model_detection"] == "live_api_confirmed_multiple_devices"
assert devices["USW Flex Mini"]["status"] == "community_validated"
assert devices["USW Flex Mini"]["last_validated_version"] == "3.0.18"
assert devices["USW Flex Mini"]["visuals"]["status"] == "community_validated"
assert profiles["ubiquiti-usw-pro-24-api"]["layout"]["sfp_10g_ports"] == 2
assert profiles["ubiquiti-usw-24-poe-api"]["layout"]["sfp_1g_ports"] == 2
assert profiles["ubiquiti-usw-24-g2-api"]["layout"]["sfp_1g_ports"] == 2
print("Switch Vision Discovery v2.1.19 community-validation profile regression: PASS")
PYTEST_V219_REGISTRY
