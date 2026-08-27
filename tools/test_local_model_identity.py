#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = ROOT / "runtime_src/opt/switch-vision/vendors"
MIB_DIR = ROOT / "runtime_src/opt/switch-vision/mib_database"


def shell_model(walk: Path) -> str:
    script = f'''
set -eu
CV_VENDOR_DIR={str(VENDOR_DIR)!r}
. "$CV_VENDOR_DIR/model_identity.sh"
cv_cap_extract_model_text "$1"
'''
    result = subprocess.run(
        ["sh", "-c", script, "sh", str(walk)],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def shell_identity(walk: Path) -> tuple[str, str, str, str]:
    script = f'''
set -eu
CV_MIB_DATABASE_DIR={str(MIB_DIR)!r}
CV_VENDOR_DIR={str(VENDOR_DIR)!r}
. "$CV_VENDOR_DIR/base.sh"
. "$CV_VENDOR_DIR/generic.sh"
. "$CV_VENDOR_DIR/cisco.sh"
. "$CV_VENDOR_DIR/known_vendor.sh"
. "$CV_VENDOR_DIR/interface.sh"
. "$CV_VENDOR_DIR/loader.sh"
cv_detect_vendor_identity "$1"
printf '%s\n%s\n%s\n%s\n' "$CV_ID_VENDOR" "$CV_ID_FAMILY" "$CV_ID_MODEL_HINT" "$(cv_cap_extract_model_text "$1")"
'''
    result = subprocess.run(
        ["sh", "-c", script, "sh", str(walk)],
        check=True,
        text=True,
        capture_output=True,
    )
    values = result.stdout.splitlines()
    if len(values) != 4:
        raise AssertionError(f"Unexpected identity output: {result.stdout!r}")
    return values[0], values[1], values[2], values[3]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        hp = tmpdir / "hp-j8693a-with-dell-neighbour.walk"
        hp.write_text(
            '.1.3.6.1.2.1.1.1.0 = STRING: "HP J8693A Switch 3500yl-48G, revision K.16.02.0036"\n'
            '.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.11.1\n'
            '.1.3.6.1.2.1.1.5.0 = STRING: "hp-local"\n'
            '.1.0.8802.1.1.2.1.4.1.1.9.1.1 = STRING: "N2128PX-ON"\n',
            encoding="utf-8",
        )
        vendor, family, hint, model = shell_identity(hp)
        assert vendor == "hp_aruba", vendor
        assert family == "3500yl", family
        assert hint == "HP J8693A Switch 3500yl-48G", hint
        assert model == "HP J8693A Switch 3500yl-48G", model

        cisco = tmpdir / "cisco-local-entity-model-with-dell-neighbour.walk"
        cisco.write_text(
            '.1.3.6.1.2.1.1.1.0 = STRING: "Cisco IOS Software, C3650 Software"\n'
            '.1.3.6.1.2.1.47.1.1.1.1.13.1 = STRING: "WS-C3650-48PD-E"\n'
            '.1.0.8802.1.1.2.1.4.1.1.9.1.1 = STRING: "N2128PX-ON"\n',
            encoding="utf-8",
        )
        assert shell_model(cisco) == "WS-C3650-48PD-E"

        dell = tmpdir / "dell-local-with-hp-neighbour.walk"
        dell.write_text(
            '.1.3.6.1.2.1.1.1.0 = STRING: "Dell EMC Networking N2128PX-ON"\n'
            '.1.0.8802.1.1.2.1.4.1.1.9.1.1 = STRING: "HP J8693A Switch 3500yl-48G"\n',
            encoding="utf-8",
        )
        assert shell_model(dell) == "N2128PX-ON"

        mikrotik = tmpdir / "mikrotik-local-with-cisco-neighbour.walk"
        rows = [
            '.1.3.6.1.2.1.1.1.0 = STRING: "RouterOS CRS328-24P-4S+"',
            '.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.14988.1',
            '.1.3.6.1.2.1.47.1.1.1.1.2.1 = STRING: "RouterOS on CRS328-24P-4S+"',
            '.1.0.8802.1.1.2.1.4.1.1.9.1.1 = STRING: "WS-C3650-48PD-E"',
        ]
        for idx in range(1, 25):
            rows.append(f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: "ether{idx}"')
        for port in range(1, 5):
            idx = 24 + port
            rows.append(f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: "sfp-sfpplus{port}"')
        rows.extend([
            '.1.3.6.1.2.1.31.1.1.1.1.29 = STRING: "bridge"',
            '.1.3.6.1.2.1.31.1.1.1.1.30 = STRING: "lo"',
        ])
        mikrotik.write_text("\n".join(rows) + "\n", encoding="utf-8")
        vendor, family, hint, model = shell_identity(mikrotik)
        assert vendor == "mikrotik", vendor
        assert family == "CRS328", family
        assert hint == "CRS328-24P-4S+", hint
        assert model == "CRS328-24P-4S+", model

        script = f"""
set -eu
CV_MIB_DATABASE_DIR={str(MIB_DIR)!r}
CV_VENDOR_DIR={str(VENDOR_DIR)!r}
SWITCH_VISION_DISCOVERY_VERSION=2.3.22
export CV_MIB_DATABASE_DIR CV_VENDOR_DIR SWITCH_VISION_DISCOVERY_VERSION
. "$CV_VENDOR_DIR/base.sh"
. "$CV_VENDOR_DIR/generic.sh"
. "$CV_VENDOR_DIR/cisco.sh"
. "$CV_VENDOR_DIR/known_vendor.sh"
. "$CV_VENDOR_DIR/interface.sh"
. "$CV_VENDOR_DIR/loader.sh"
cv_write_capabilities_json "$1" "$2" ""
"""
        cap_path = tmpdir / "mikrotik.capabilities.json"
        subprocess.run(["sh", "-c", script, "sh", str(mikrotik), str(cap_path)], check=True)
        import json
        caps = json.loads(cap_path.read_text(encoding="utf-8"))
        assert caps["summary"]["interface_count"] == 30
        assert caps["summary"]["physical_count"] == 28
        assert caps["summary"]["rj45_count"] == 24
        assert caps["summary"]["sfp_plus_count"] == 4
        assert all(not row["physical"] for row in caps["interfaces"] if row["name"] in {"bridge", "lo"})

    print("Local model identity isolation and MikroTik CRS328 contract: PASS")


if __name__ == "__main__":
    main()
