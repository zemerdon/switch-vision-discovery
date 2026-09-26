#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "runtime_src" / "discovery_job.sh"


def production_card_writer() -> str:
    source = JOB.read_text(encoding="utf-8")
    start = source.index("write_generated_dashboard_card() {")
    end = source.index("\nquarantine_invalid_generated_live_yaml() {", start)
    return source[start:end]


with tempfile.TemporaryDirectory(prefix="sv-generated-card-row-failure-") as temporary:
    root = Path(temporary)
    bin_dir = root / "bin"
    bin_dir.mkdir()
    fake_jq = bin_dir / "jq"
    fake_jq.write_text("#!/bin/sh\nexit 42\n", encoding="utf-8")
    fake_jq.chmod(0o755)

    config = root / "options.json"
    config.write_text(
        '{"switches":[{"switch_name":"SW1","switch_host":"192.0.2.10"}]}\n',
        encoding="utf-8",
    )
    dashboard = root / "dashboard.yaml"
    previous = "# previous known-good dashboard\n"
    dashboard.write_text(previous, encoding="utf-8")
    log_path = root / "discovery.log"

    harness = root / "harness.sh"
    harness.write_text(
        textwrap.dedent(
            f"""
            set -eu
            PATH="{bin_dir}:$PATH"
            SWITCH_VISION_DISCOVERY_VERSION="3.0.7"
            GENERATED_CARD_SNMP_ENABLED="true"
            CONFIG_FILE="{config}"
            GENERATED_CARD_PATH="{dashboard}"
            GENERATED_CARD_FULL_PATH="{root / "dashboard.full.yaml"}"
            LIVE_LOG_PATH="{log_path}"
            SWITCH_VISION_SHARE_DIR="{root}"
            SWITCH_VISION_DEVICE_CONTROL_PATH="{root / "device-control.json"}"
            SWITCH_VISION_DASHBOARD_DEVICE_ORDER_HELPER="{root / "missing-helper.py"}"
            SWITCH_VISION_UNIFI_SNAPSHOT="{root / "no-unifi.json"}"
            SWITCH_VISION_DEVICE_REGISTRY="{root / "no-registry.json"}"
            SWITCH_VISION_UNIFI_DASHBOARD_HELPER="{root / "no-helper.py"}"
            SELECTED_SWITCH=""
            LIVE_SWITCH_LABEL="SW1"
            LIVE_SWITCH_IP="192.0.2.10"
            DEFAULT_PREFIX="sw1"
            DEFAULT_HOST="192.0.2.10"

            trap 'rm -f /tmp/switch_vision_generated_dashboard_raw_$$.yaml /tmp/switch_vision_generated_port_modes_$$.tsv /tmp/switch_vision_unifi_bound_ids_$$.txt /tmp/switch_vision_generated_card_rows_$$.tsv' EXIT

            truthy() {{ [ "$1" = "true" ]; }}
            build_juniper_port_mode_metadata() {{ : > "$1"; }}
            json_has_configured_switch_rows() {{ return 0; }}
            model_metadata_for_generated_card() {{ return 0; }}
            emit_generated_card_port_counts() {{ return 0; }}
            emit_generated_card_sfp_logical_port_map() {{ return 0; }}
            calibration_profile_for_generated_card() {{ return 0; }}
            device_mac_for_generated_card() {{ return 0; }}
            emit_generated_port_metadata() {{ return 0; }}
            collect_multi_walks() {{ : > "$1"; }}
            target_switch_for_walk() {{ printf 'SW1'; }}
            target_prefix_for_walk() {{ printf 'sw1'; }}
            target_for_walk() {{ printf '192.0.2.10'; }}
            exact_model_for_generated_card() {{ return 0; }}
            lower_value() {{ printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }}
            yaml_quote() {{ python3 -c 'import json,sys; print(json.dumps(sys.stdin.read(), ensure_ascii=False))'; }}
            """
        )
        + production_card_writer()
        + textwrap.dedent(
            """
            set +e
            write_generated_dashboard_card
            rc=$?
            set -e
            echo "FUNCTION_RC=$rc"
            """
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["sh", str(harness)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rc_line = next(
        (line for line in result.stdout.splitlines() if line.startswith("FUNCTION_RC=")),
        "",
    )
    assert rc_line and rc_line != "FUNCTION_RC=0", result.stdout
    assert dashboard.read_text(encoding="utf-8") == previous
    assert "Generated dashboard card row extraction failed" in log_path.read_text(
        encoding="utf-8"
    )

print("Discovery generated-card row extraction fail-closed regression: PASS")
