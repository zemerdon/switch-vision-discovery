from __future__ import annotations
from email import policy
from email.parser import BytesParser
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "runtime_src" / "make_support_email.py"


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        archive = root / "Switch_Vision_Contribution_test.zip"
        payload = b"switch-vision-test-archive"
        archive.write_bytes(payload)
        manifest = root / "MANIFEST.json"
        manifest.write_text(json.dumps({
            "ready_to_send": True, "contribution_id": "SV-TEST-000001",
            "switch_vision_version": "2.1.48", "bundle_quality": "PASS",
            "recognition": {"type": "anonymous", "value": ""},
            "privacy_options": {"secrets_always_removed": True, "serial_numbers_always_masked": True, "mask_management_ips": True, "mask_mac_addresses": True, "mask_hostnames": True, "mask_vlan_names": True, "mask_interface_descriptions": True}
        }), encoding="utf-8")
        devices = [
            {"vendor_name": "UCG Ultra", "model": "UCG Ultra", "family": "UniFi Cloud Gateway Ultra"},
            {"vendor_name": "US 16 PoE 150W", "model": "US 16 PoE 150W", "family": "UniFi Switch 16 PoE 150W"},
            {"vendor_name": "USW Pro Max 24", "model": "USW Pro Max 24", "family": "UniFi Switch Pro Max 24"},
            {"vendor_name": "  usw ultra  ", "model": "USW ULTRA", "family": "UniFi Switch Ultra"},
            {"vendor_name": "Cisco", "model": "WS-C3650-48PS", "family": "Catalyst 3650"},
        ]
        (root / "DEVICE_SUMMARY.json").write_text(json.dumps(devices), encoding="utf-8")
        eml = root / "prepared.eml"; html = root / "prepared.html"
        subprocess.run([sys.executable, str(SCRIPT), "--archive", str(archive), "--manifest", str(manifest), "--output-eml", str(eml), "--output-html", str(html)], check=True)
        raw = eml.read_bytes()
        assert b"\r\n" in raw
        assert b"\n" not in raw.replace(b"\r\n", b"")
        message = BytesParser(policy=policy.SMTP).parsebytes(raw)
        assert message["To"] == "switch-vision@zemerdon.com"
        assert message["Subject"] == "Switch Vision Contribution - SV-TEST-000001"
        assert message.get_content_type() == "multipart/mixed"
        body = message.get_body(preferencelist=("plain",)).get_content()
        expected_lines = [
            "- UCG Ultra (UniFi Cloud Gateway Ultra)",
            "- US 16 PoE 150W (UniFi Switch 16 PoE 150W)",
            "- USW Pro Max 24 (UniFi Switch Pro Max 24)",
            "- USW ULTRA (UniFi Switch Ultra)",
            "- Cisco WS-C3650-48PS (Catalyst 3650)",
        ]
        for line in expected_lines:
            assert line in body, line
        assert "UCG Ultra UCG Ultra" not in body
        assert "US 16 PoE 150W US 16 PoE 150W" not in body
        assert "USW Pro Max 24 USW Pro Max 24" not in body
        assert "usw ultra usw ultra" not in body.casefold()
        attachments = list(message.iter_attachments())
        assert len(attachments) == 1
        attachment = attachments[0]
        assert attachment.get_filename() == archive.name
        assert attachment.get_content_type() == "application/zip"
        assert attachment.get_payload(decode=True) == payload
        assert "MIME-Version" not in str(message["Subject"])
        print("Switch Vision Support My Switch SMTP/MIME and hardware-name regression: PASS")


if __name__ == "__main__":
    main()
