# Switch Vision Discovery self-test UniFi exact-model/API mapping module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# community-validation UniFi exact-model/API mapping regression.
python3 - "$RUNTIME_REGISTRY" "$BASE_DIR/profiles/switch-vision-profiles.yaml" <<'PYTEST_community_validation'
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
assert xg16["status"] == "experimental"
assert xg16["dashboard_support"] is True
assert xg16["calibration_profile"] == "unifi_4_rj45_12sfp"
assert xg16["default_faceplate"] == "faceplates/unifi-4-rj45-12sfp.png"
assert xg16["unifi_api_port_map"]["sfp"] == list(range(1, 13))
assert xg16["unifi_api_port_map"]["rj45"] == [13, 14, 15, 16]

agg = models["USW Pro Aggregation"]
assert agg["status"] == "experimental"
assert agg["dashboard_support"] is True
assert agg["ports"]["rj45"] == 0
assert agg["ports"]["ten_gigabit_sfp_plus"] == 28
assert agg["ports"]["twenty_five_gigabit_sfp28"] == 4
assert agg["unifi_api_port_map"]["sfp"] == list(range(1, 33))
assert agg["calibration_profile"] == "unifi_32sfp"
assert agg["default_faceplate"] == "faceplates/unifi-32sfp.png"

p48 = profiles["ubiquiti-us-48-api"]
assert p48["layout"] == {"members": 1, "rj45_ports": 48, "sfp_1g_ports": 2, "sfp_10g_ports": 2}
assert p48["interface_patterns"]["sfp_10g"] == ["api-port-49", "api-port-50", "0/49", "0/50"]
assert p48["interface_patterns"]["sfp_1g"] == ["api-port-51", "api-port-52", "0/51", "0/52"]
pxg = profiles["ubiquiti-us-xg-16-api"]
assert pxg["interface_patterns"]["rj45"] == ["api-port-13", "api-port-14", "api-port-15", "api-port-16", "0/13", "0/14", "0/15", "0/16"]
assert pxg["interface_patterns"]["sfp_10g"] == [f"api-port-{n}" for n in range(1, 13)] + [f"0/{n}" for n in range(1, 13)]
pagg = profiles["ubiquiti-usw-pro-aggregation-api"]
assert pagg["status"] == "experimental"
assert pagg["layout"]["rj45_ports"] == 0
assert pagg["layout"]["sfp_10g_ports"] == 28
assert pagg["layout"]["sfp_25g_ports"] == 4
assert pagg["interface_patterns"]["sfp_25g"] == [f"api-port-{n}" for n in range(29, 33)]

fiber = models["UCG Fiber"]
assert fiber["status"] == "experimental"
assert fiber["dashboard_support"] is True
assert fiber["ports"]["rj45"] == 5
assert fiber["ports"]["uplinks"] == 2
assert fiber["ports"]["poe"] is True
assert fiber["unifi_api_port_map"] == {"rj45": [1, 2, 3, 4, 5], "sfp": [6, 7]}
assert fiber["calibration_profile"] == "unifi_8_rj45_2sfp"
assert fiber["default_faceplate"] == "faceplates/unifi-8-rj45-2sfp.png"
pfiber = profiles["ubiquiti-ucg-fiber-api"]
assert pfiber["status"] == "experimental"
assert pfiber["layout"] == {"members": 1, "rj45_ports": 5, "sfp_1g_ports": 0, "sfp_10g_ports": 2}
assert pfiber["interface_patterns"]["rj45"] == [f"api-port-{n}" for n in range(1, 6)]
assert pfiber["interface_patterns"]["sfp_10g"] == ["api-port-6", "api-port-7"]
print("Switch Vision Discovery community-validation UniFi contract regression: PASS")
PYTEST_community_validation

python3 - "$tmp_dir/community-validation-unifi.json" <<'PYTEST_community_validation_SNAPSHOT'
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
        {
            "id": "ucg-fiber-test",
            "name": "UCG Fiber test",
            "model": "UCG Fiber",
            "api_capabilities": {"port_detail": True, "per_port_traffic": False},
            "ports": ports([(n, "RJ45") for n in range(1, 6)] + [(6, "SFPPLUS"), (7, "SFPPLUS")]),
        },
    ]
}
Path(sys.argv[1]).write_text(json.dumps(snapshot), encoding="utf-8")
PYTEST_community_validation_SNAPSHOT
python3 "$BASE_DIR/unifi_dashboard_cards.py" \
    --snapshot "$tmp_dir/community-validation-unifi.json" \
    --registry "$RUNTIME_REGISTRY" \
    --summary > "$tmp_dir/community-validation-cards.yaml"
grep -q 'switch_model: US 48' "$tmp_dir/community-validation-cards.yaml"
grep -q 'unifi_sfp_port_offset: 48' "$tmp_dir/community-validation-cards.yaml"
grep -q 'switch_model: US XG 16' "$tmp_dir/community-validation-cards.yaml"
grep -q 'switch_model: USW Pro Aggregation' "$tmp_dir/community-validation-cards.yaml"
grep -q 'switch_model: UCG Fiber' "$tmp_dir/community-validation-cards.yaml"
grep -q 'calibration_profile: unifi_4_rj45_12sfp' "$tmp_dir/community-validation-cards.yaml"
grep -q 'calibration_profile: unifi_32sfp' "$tmp_dir/community-validation-cards.yaml"
grep -q 'calibration_profile: unifi_8_rj45_2sfp' "$tmp_dir/community-validation-cards.yaml"
grep -q 'port_count: 5' "$tmp_dir/community-validation-cards.yaml"
grep -q 'sfp_port_count: 2' "$tmp_dir/community-validation-cards.yaml"
! grep -q 'USW Pro Aggregation.*dashboard support is pending verified visuals' "$tmp_dir/community-validation-cards.yaml"
grep -q 'UniFi cards emitted: 4; waiting for visuals/registry: 0' "$tmp_dir/community-validation-cards.yaml"
echo "Switch Vision Discovery community-validation generated-card regression: PASS"
