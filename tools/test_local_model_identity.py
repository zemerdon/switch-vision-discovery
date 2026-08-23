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

    print("Local model identity isolation: PASS")


if __name__ == "__main__":
    main()
