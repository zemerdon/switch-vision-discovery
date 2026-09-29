# Switch Vision Discovery self-test physical-evidence module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# Physical contracts separate valid raw SNMP evidence from an exact-model
# topology authorization. An unregistered model must be retained for review,
# while an EX3300 with only one observed uplink is a resolved partial view.
PYTHONPATH="$BASE_DIR" python3 - <<'PYTEST_PHYSICAL_EVIDENCE'
import physical_contract as contract

def interface(index, name, media):
    return {"if_index": index, "name": name, "media": media, "physical": True}

unregistered = contract.resolve(
    {
        "device": {"model_text": "WS-C3850-12XS-E", "vendor_name": "Cisco"},
        "interfaces": [interface(1, "Te1/1/1", "sfp_plus")],
    },
    {"devices": []},
)
assert unregistered["status"] == "unregistered"
assert unregistered["device"]["registry_match"] is False
assert unregistered["observed"]["physical"] == 1

ex_registry = {"devices": [{
    "model": "EX3300-48P",
    "vendor": "Juniper",
    "ports": {"rj45": 48, "uplinks": 4},
    "stack_support": False,
}]}
ex_interfaces = [interface(index, f"ge-0/0/{index - 1}", "rj45") for index in range(1, 49)]
ex_interfaces.append(interface(49, "xe-0/1/0", "sfp_plus"))
ex = contract.resolve(
    {"device": {"model_text": "EX3300-48P", "vendor_name": "Juniper"}, "interfaces": ex_interfaces},
    ex_registry,
)
assert ex["status"] == "resolved"
assert ex["unobserved_physical"]["uplinks"] == 3
assert ex["unobserved_physical"]["reason"]
print("Switch Vision physical evidence / EX3300 partial-observation regression: PASS")
PYTEST_PHYSICAL_EVIDENCE
