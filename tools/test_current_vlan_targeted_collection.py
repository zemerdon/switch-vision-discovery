#!/usr/bin/env python3
"""Verify optional standard Q-BRIDGE collection bounds and isolation."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
script = (root / "runtime_src/discovery_job.sh").read_text()
start = '  QBRIDGE_CURRENT_OIDS=""'
end = '  # Zyxel 890.1.15 is shared by multiple real models.'
assert script.count(start) == 1 and script.count(end) == 1
block = start + script.split(start, 1)[1].split(end, 1)[0]
egress = "1.3.6.1.2.1.17.7.1.4.2.1.4"
untagged = "1.3.6.1.2.1.17.7.1.4.2.1.5"
assert egress in block and untagged in block
assert block.count("for oid in $QBRIDGE_CURRENT_OIDS; do") == 1
assert 'LIVE_SNMPWALK_MODE" != "full"' in block
assert 'GS1900-8([[:space:],"]|$)' in block
assert 'QBRIDGE_CURRENT_OIDS="' + untagged + '"' in block
assert '"$LIVE_SNMP_COMMUNITY"' in block
assert "failures=$((failures + 1))" not in block
assert "INFO: Current VLAN table unavailable:" in block
assert "1.3.6.1.4.1." not in block
print("RFC 4363 current VLAN bounded targeted OIDs: PASS")
