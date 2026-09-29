# Switch Vision Discovery self-test Support My Switch ordering module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# v2.2.5 automatic Support My Switch ordering regression. The shell Discovery
# stage must never build the automatic contribution before the Hub has checked
# the SNMP2MQTT handoff.
PYTHONPATH="$BASE_DIR" python3 - "$tmp_dir" <<'PYTEST_V225_BUNDLE_ORDER'
import json
import os
from pathlib import Path
import stat
import sys

import support_web as web

tmp = Path(sys.argv[1]) / "v225-bundle-order"
tmp.mkdir(parents=True, exist_ok=True)

options = {
    "switches": [],
    "stack_member_prefixes": [],
    "generate_support_my_switch_bundle": True,
    "support_mask_management_ips": True,
    "support_mask_mac_addresses": True,
    "support_mask_hostnames": True,
    "support_mask_vlan_names": False,
    "support_mask_interface_descriptions": False,
    "support_contributor_type": "anonymous",
    "support_contributor_value": "",
}

# A normal Hub run suppresses shell-side automatic capture in the temporary
# snapshot without changing the authoritative saved option.
normal_snapshot = tmp / "normal-options.json"
web._write_authoritative_discovery_options_snapshot(
    normal_snapshot,
    options=options,
)
normal_doc = json.loads(normal_snapshot.read_text(encoding="utf-8"))
assert normal_doc["generate_support_my_switch_bundle"] is False
assert options["generate_support_my_switch_bundle"] is True

# Regeneration is never a contribution-capture action.
web._self_addon_options = lambda: dict(options)
regen_snapshot = tmp / "regen-options.json"
web._write_snmp2mqtt_regeneration_options_snapshot(regen_snapshot)
regen_doc = json.loads(regen_snapshot.read_text(encoding="utf-8"))
assert regen_doc["generate_support_my_switch_bundle"] is False

settings = web._support_settings_from_options(options)
assert settings["mask_management_ips"] is True
assert settings["mask_vlan_names"] is False
assert settings["contributor_type"] == "anonymous"

# The Hub-owned automatic helper preserves only the Support My Switch settings,
# invokes the local support backend, and exposes no backend stdout/private IDs.
support = tmp / "support.sh"
support.write_text(
    "#!/bin/sh\n"
    'printf "%s|%s\n" "$SUPPORT_MASK_MANAGEMENT_IPS" "$SUPPORT_CONTRIBUTOR_TYPE" '
    '>"$CONTRIBUTIONS_DIR/helper-marker.txt"\n',
    encoding="utf-8",
)
support.chmod(support.stat().st_mode | stat.S_IXUSR)
contributions = tmp / "contributions"
web.DEFAULT_SUPPORT_SCRIPT = support
web.DEFAULT_CONTRIBUTIONS_DIR = contributions
os.environ["SWITCH_VISION_DISCOVERY_VERSION"] = "2.2.5"
lines = []
assert web._generate_automatic_support_bundle(settings, lines) is True
assert (contributions / "helper-marker.txt").read_text(encoding="utf-8").strip() == "true|anonymous"
assert any("after the SNMP2MQTT handoff check" in line for line in lines)

source = Path(web.__file__).read_text(encoding="utf-8")
start = source.index("def _run_discovery(")
end = source.index("\ndef _read_supervisor_token(", start)
run_source = source[start:end]
assert run_source.index("_ensure_snmp2mqtt_running(") < run_source.index(
    "_generate_automatic_support_bundle("
)
assert 'snapshot_options["generate_support_my_switch_bundle"] = False' in source
assert 'regenerated["generate_support_my_switch_bundle"] = False' in source

print("Switch Vision Discovery v2.2.5 post-handoff bundle ordering regression: PASS")
PYTEST_V225_BUNDLE_ORDER
