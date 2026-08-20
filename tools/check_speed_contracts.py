#!/usr/bin/env python3
from __future__ import annotations

import urllib.request
from pathlib import Path

SNMP_INTERFACE_URL = "https://raw.githubusercontent.com/zemerdon/switch-vision-snmp2mqtt/main/src/interface.ts"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Switch-Vision-Speed-Contract/1"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


def main() -> int:
    job = Path("runtime_src/discovery_job.sh").read_text(encoding="utf-8")
    profiles = Path("runtime_src/profiles/switch-vision-profiles.yaml").read_text(encoding="utf-8")
    snmp = fetch(SNMP_INTERFACE_URL)

    required_discovery = [
        "function yaml_speed_sensor(model, idx, label, has_highspeed, has_ifspeed, cap_mbps)",
        "if (has_highspeed)",
        "else if (has_ifspeed)",
        '1.3.6.1.2.1.31.1.1.1.15.',
        '1.3.6.1.2.1.2.2.1.5.',
        'model == "S5720-12TP-LI-AC" && label ~ /^SFP 1G /',
    ]
    missing = [token for token in required_discovery if token not in job]
    if missing:
        raise SystemExit("Discovery speed contract missing: " + ", ".join(missing))

    helper = job[job.index("function yaml_speed_sensor"):job.index("function yaml_interface_sensor")]
    if helper.index("if (has_highspeed)") > helper.index("else if (has_ifspeed)"):
        raise SystemExit("Discovery speed contract: legacy ifSpeed precedes ifHighSpeed")

    if "physical_speed_caps_mbps:" not in profiles or "sfp_1g: 1000" not in profiles:
        raise SystemExit("Discovery speed contract: S5720 physical 1G SFP cap missing")

    required_snmp = [
        'speed_mbps: "1.3.6.1.2.1.31.1.1.1.15"',
    ]
    missing_snmp = [token for token in required_snmp if token not in snmp]
    if missing_snmp:
        raise SystemExit("SNMP2MQTT speed contract no longer uses ifHighSpeed for speed_mbps")

    print("Switch Vision interface speed contracts: PASS (ifHighSpeed preferred; S5720 physical 1G cap present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
