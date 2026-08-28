#!/usr/bin/env python3
"""Synthetic regression fixtures for the August 2026 Support My Switch batch.

This file intentionally contains no private contribution artifacts. It records
only topology/interface-name facts already validated from retained evidence.
The executable checks are added alongside the parser changes in this branch.
"""

# Evidence-backed target layouts:
# - Dell PowerConnect 5548P: 48 RJ45 + 2 SFP+
# - Cisco WS-C3750X-48P: 48 access RJ45 per member; module aliases must not double count
# - Cisco SG350-20: 20 front-panel logical positions; combo semantics remain conservative
# - Zyxel GS1900-24E: 24 RJ45
# - Ubiquiti USW Pro HD 24 PoE: 24 RJ45 + 4 SFP+
# - Ubiquiti USW Pro XG 8 PoE: 8 RJ45 + 2 SFP+
# - HP J8693A: generated card must bind its four `uplink` entities, not forced sfp_10g names

if __name__ == "__main__":
    print("Contributor regression scaffold present")
