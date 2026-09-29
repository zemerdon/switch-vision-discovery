# Switch Vision Discovery self-test UniFi community-hardware module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# community-hardware Community UniFi exact-model contract regression.
python3 - "$RUNTIME_REGISTRY" "$BASE_DIR/profiles/switch-vision-profiles.yaml" <<'PYTEST_FIELD_UNIFI'
import json
import sys
from pathlib import Path
import yaml

registry = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
profiles_doc = yaml.safe_load(Path(sys.argv[2]).read_text(encoding="utf-8")) or {}
profiles = profiles_doc.get("profiles", profiles_doc)
models = {d["model"]: d for d in registry["devices"] if isinstance(d, dict)}

expected = {
    "UCG Ultra": (5, 0, False, True, "ubiquiti-ucg-ultra-api"),
    "US 16 PoE 150W": (16, 2, True, True, "ubiquiti-us-16-poe-150w-api"),
    "USW Pro Max 24": (24, 2, False, True, "ubiquiti-usw-pro-max-24-api"),
    "USW Ultra": (8, 0, True, True, "ubiquiti-usw-ultra-api"),
}
for model, (rj45, uplinks, poe, dashboard, profile) in expected.items():
    item = models[model]
    expected_status = "experimental"
    assert item["status"] == expected_status, model
    assert item["ports"]["rj45"] == rj45, model
    assert item["ports"]["uplinks"] == uplinks, model
    assert item["ports"]["poe"] is poe, model
    assert item["dashboard_support"] is dashboard, model
    assert item["mapping_profile"] == profile, model
    assert [c["id"] for c in item["contributions"]] == ["community-validation-1", "community-validation-2"], model
    assert item["contributions"][0]["contributor"]["public_credit"] is False, model
    assert item["contributions"][1]["contributor"]["display_name"] == "community contributor", model
    assert all(c["api_capabilities"]["per_port_traffic"] is False for c in item["contributions"]), model
    assert profile in profiles, profile
    assert profiles[profile]["status"] == "experimental", model

promax = models["USW Pro Max 24"]
assert promax["calibration_profile"] == "unifi_24p_rj45_2sfp"
assert promax["default_faceplate"] == "faceplates/unifi-24p-rj45-2sfp.png"
ucg = models["UCG Ultra"]
assert ucg["calibration_profile"] == "default_unifi_5_rj45"
assert ucg["default_faceplate"] == "faceplates/unifi-5rj45.png"
ultra = models["USW Ultra"]
assert ultra["calibration_profile"] == "default_unifi_8_rj45"
assert ultra["default_faceplate"] == "faceplates/unifi-8rj45.png"
assert profiles["ubiquiti-usw-pro-max-24-api"]["interface_patterns"]["sfp_10g"] == ["api-port-25", "api-port-26"]
assert profiles["ubiquiti-us-16-poe-150w-api"]["interface_patterns"]["sfp_1g"] == ["api-port-17", "api-port-18"]
assert "ports_1_7_only" in models["USW Ultra"]["validation"]["poe"]
assert "2p5g_capable" in promax["validation"]["rj45_mapping"]
print("Switch Vision Discovery Community registry/profile contract: PASS")
PYTEST_FIELD_UNIFI

python3 - "$tmp_dir/community-unifi.json" <<'PYTEST_FIELD_SNAPSHOT'
import json
import sys
from pathlib import Path

def ports(rj45, sfp=0):
    rows = [{"idx": n, "connector": "RJ45", "max_speed_mbps": 1000} for n in range(1, rj45 + 1)]
    rows += [{"idx": rj45 + n, "connector": "SFPPLUS", "max_speed_mbps": 10000} for n in range(1, sfp + 1)]
    return rows

snapshot = {"devices": [
    {"id": "community-ucg", "name": "UCG Ultra", "model": "UCG Ultra", "api_capabilities": {"port_detail": True, "per_port_traffic": False}, "ports": ports(5)},
    {"id": "community-us16", "name": "US 16 PoE 150W", "model": "US 16 PoE 150W", "api_capabilities": {"port_detail": True, "per_port_traffic": False}, "ports": ports(16, 2)},
    {"id": "community-promax24", "name": "USW Pro Max 24", "model": "USW Pro Max 24", "api_capabilities": {"port_detail": True, "per_port_traffic": False}, "ports": ports(24, 2)},
    {"id": "community-ultra", "name": "USW Ultra", "model": "USW Ultra", "api_capabilities": {"port_detail": True, "per_port_traffic": False}, "ports": ports(8)},
]}
Path(sys.argv[1]).write_text(json.dumps(snapshot), encoding="utf-8")
PYTEST_FIELD_SNAPSHOT

python3 "$BASE_DIR/unifi_dashboard_cards.py" \
    --snapshot "$tmp_dir/community-unifi.json" \
    --registry "$RUNTIME_REGISTRY" \
    --summary > "$tmp_dir/community-unifi-cards.yaml"
grep -q 'switch_model: UCG Ultra' "$tmp_dir/community-unifi-cards.yaml"
grep -q 'switch_model: US 16 PoE 150W' "$tmp_dir/community-unifi-cards.yaml"
grep -q 'switch_model: USW Pro Max 24' "$tmp_dir/community-unifi-cards.yaml"
grep -q 'switch_model: USW Ultra' "$tmp_dir/community-unifi-cards.yaml"
! grep -q 'generic_faceplate: true' "$tmp_dir/community-unifi-cards.yaml"
test "$(grep -c 'generic_faceplate: false' "$tmp_dir/community-unifi-cards.yaml")" -eq 4
grep -q 'UniFi cards emitted: 4; exact cards: 4; generic fallbacks: 0; exact support pending: 0; issues: 0' "$tmp_dir/community-unifi-cards.yaml"
echo "Switch Vision Discovery community-hardware generated-card regression: PASS"
