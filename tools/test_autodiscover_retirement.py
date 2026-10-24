#!/usr/bin/env python3
"""AutoDiscover retirement: no scan surface, safe legacy configuration reads."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime_src"))
import support_web as hub  # noqa: E402

def main() -> None:
    runtime = ROOT / "runtime_src"
    page = (runtime / "support_web.html").read_text()
    backend = (runtime / "support_web.py").read_text()
    assert "autodiscover" not in page.lower(), "AutoDiscover remains in Hub UI"
    assert "/api/autodiscover/" not in backend, "AutoDiscover API still reachable"
    assert "import autodiscover" not in backend
    assert not (runtime / "autodiscover.py").exists()
    assert not (runtime / "hub_autodiscover.py").exists()
    assert "function selectDevicesTab(" in page
    assert "['run','configure','overview']" in page
    assert "function renderDeviceConfiguration()" in page
    assert "model_override" in (runtime / "discovery_report_stage.sh").read_text()

    # Pre-removal file restores silently drop the scan-only list while
    # retaining actual configured switches and their automatic model choice.
    legacy = {
        "format": hub.DISCOVERY_EXPORT_FORMAT,
        "configuration": {
            "switches": [{
                "switch_name": "SW1", "switch_host": "192.0.2.10",
                "sensor_prefix": "sw1", "snmp_community": "readonly",
                "enabled": "enabled", "walk_mode": "targeted",
                "switch_model": "auto",
            }],
            "stack_member_prefixes": [],
            "autodiscover_networks": ["192.0.2.0/24"],
        },
    }
    imported = hub._validate_discovery_import(copy.deepcopy(legacy))
    assert "autodiscover_networks" not in imported
    assert imported["switches"][0]["switch_host"] == "192.0.2.10"
    assert imported["switches"][0]["switch_model"] == "auto"
    current = {"switches": imported["switches"], "autodiscover_networks": ["192.0.2.0/24"]}
    cleaned = hub._discovery_options_without_retired_keys(current)
    assert "autodiscover_networks" not in cleaned
    assert cleaned["switches"] == current["switches"]
    assert "autodiscover_networks" in current, "must not mutate caller/source state"
    print("AutoDiscover retirement, legacy import, and model detection: PASS")

if __name__ == "__main__":
    main()
