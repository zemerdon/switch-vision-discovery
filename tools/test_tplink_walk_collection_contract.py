#!/usr/bin/env python3
"""Read-only product contract for bounded TP-Link targeted and split full walks."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "runtime_src/discovery_job.sh").read_text()
MIB = json.loads((ROOT / "runtime_src/opt/switch-vision/mib_database/vendors/tplink/sensors.json").read_text())
PRODUCTS = json.loads((ROOT / "runtime_src/opt/switch-vision/mib_database/vendors/tplink/products.json").read_text())
POLICY = MIB["collection"]
ROOT_ENTERPRISE = "1.3.6.1.4.1.11863"
EXPECTED = {
    ROOT_ENTERPRISE + ".6.1.1.1",       # read-only textual identity, not serial number
    ROOT_ENTERPRISE + ".6.1.1.5",       # system hardware revision
    ROOT_ENTERPRISE + ".6.1.1.6",       # system software revision
    ROOT_ENTERPRISE + ".6.4.1.1",       # CPU usage table
    ROOT_ENTERPRISE + ".6.4.1.2",       # memory usage table
    ROOT_ENTERPRISE + ".6.56.1.1.1",    # global PoE
    ROOT_ENTERPRISE + ".6.56.1.1.2.1.1",# per-port PoE
    ROOT_ENTERPRISE + ".6.96.1.7.1",   # optical diagnostics
}
assert set(POLICY["targeted_walk_oids"]) == EXPECTED
assert len(POLICY["targeted_walk_oids"]) == len(EXPECTED)
assert MIB["collection"]["system_description_oid"] in EXPECTED
assert all(".6.1.1.8" not in oid for oid in EXPECTED)  # protected device serial number
assert set(MIB["collection"]["mib_modules"]) == {"identity", "system", "cpu_memory", "poe"}
assert "TPLINK-SYSINFO-MIB" in MIB["collection"]["mib_modules"]["system"]
assert PRODUCTS["identity_mib"] == "TPLINK-PRODUCTS-MIB"
assert PRODUCTS["identity_oid_root"] == ROOT_ENTERPRISE + ".5"
assert {row["sys_object_id"] for row in PRODUCTS["products"]} == {
    ROOT_ENTERPRISE + ".5.94", ROOT_ENTERPRISE + ".5.98"
}
assert all("mib_symbol" not in row for row in PRODUCTS["products"])  # newer symbols not verified
assert POLICY["full_walk_roots"] == ["1.3.6.1.2.1", ROOT_ENTERPRISE]
assert len(POLICY["official_mib_archive_sha256"]) == 64
assert "T2600G-28MPS" in POLICY["official_mib_archive_url"]
# Split full walk keeps Juniper and TP-Link independent; no global timeout change.
assert 'if grep -Eqi "Juniper|TP-Link|JetStream"' in SOURCE
assert 'full_vendor_root="1.3.6.1.4.1.2636"' in SOURCE
assert 'full_vendor_root="1.3.6.1.4.1.11863"' in SOURCE
assert "Running split Juniper full SNMP walk" in SOURCE
assert "Running split TP-Link full SNMP walk" in SOURCE
assert 'full_timeout=8' in SOURCE and 'full_retries=2' in SOURCE
split = SOURCE.split("for oid in $FULL_OIDS; do", 1)[1].split("done", 1)[0]
assert split.count("$full_timeout") == 2 and split.count("$full_retries") == 2
# Targeted mode reads one reviewed source of truth and does not enumerate
# TP-Link's entire private enterprise branch or promote missing optional OIDs.
scope = SOURCE.split("# TP-Link JetStream: collect only reviewed", 1)[1]
scope = scope.split('  line_count=$(walk_line_count', 1)[0]
assert 'targeted_walk_oids[]?' in scope
assert 'if [ "$LIVE_SNMPWALK_MODE" != "full" ]' in scope
assert '1.3.6.1.4.1.11863.6.*' in scope
assert '1.3.6.1.4.1.11863 ' not in scope
assert 'tplink_count' in scope and '-gt 10' in scope
assert 'INFO: TP-Link optional MIB tree unavailable' in scope
assert 'failures=$((failures + 1))' not in scope
assert 'FULL_OIDS' not in scope
print("TP_LINK_SPLIT_FULL_AND_BOUNDED_VENDOR_TARGETED_WALK_PASS")
