#!/usr/bin/env python3
"""Create a ready-to-open .eml file and a small local action page.

The contribution ZIP is attached to the message. No email is sent and no mail
credentials are required.
"""
from __future__ import annotations

import argparse
import html
import json
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path
from urllib.parse import quote

SUPPORT_ADDRESS = "switch-vision@zemerdon.com"


def _bool_text(value: object) -> str:
    return "Yes" if bool(value) else "No"


def _device_lines(manifest_path: Path) -> list[str]:
    summary_path = manifest_path.parent / "DEVICE_SUMMARY.json"
    if not summary_path.exists():
        return ["- No device summary was available."]
    try:
        devices = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["- Device summary could not be read."]
    lines: list[str] = []
    for device in devices:
        vendor = str(device.get("vendor_name") or device.get("vendor") or "Unknown")
        model = str(device.get("model") or "Unknown model")
        family = str(device.get("family") or "").strip()
        suffix = f" ({family})" if family and family.lower() != "unknown" else ""
        lines.append(f"- {vendor} {model}{suffix}")
    return lines or ["- No devices were detected."]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-eml", required=True, type=Path)
    parser.add_argument("--output-html", required=True, type=Path)
    args = parser.parse_args()

    archive = args.archive.resolve()
    manifest_path = args.manifest.resolve()
    if not archive.is_file():
        raise SystemExit(f"Archive not found: {archive}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not bool(manifest.get("ready_to_send")):
        raise SystemExit(
            "Prepared email not created: the contribution bundle requires privacy review."
        )

    contribution_id = str(manifest.get("contribution_id") or "Unknown")
    version = str(manifest.get("switch_vision_version") or "Unknown")
    quality = str(manifest.get("bundle_quality") or "Unknown")
    recognition = manifest.get("recognition") or {}
    recognition_type = str(recognition.get("type") or "anonymous")
    recognition_value = str(recognition.get("value") or "").strip()
    recognition_text = "Anonymous" if recognition_type == "anonymous" else f"{recognition_type}: {recognition_value}"
    privacy = manifest.get("privacy_options") or {}

    subject = f"Switch Vision Contribution - {contribution_id}"
    device_lines = _device_lines(manifest_path)
    body = "\n".join([
        "Hello,",
        "",
        "Please find attached my Switch Vision Support My Switch contribution bundle.",
        "",
        f"Contribution ID: {contribution_id}",
        f"Switch Vision version: {version}",
        f"Bundle quality: {quality}",
        f"Recognition preference: {recognition_text}",
        "",
        "Detected hardware:",
        *device_lines,
        "",
        "Privacy options:",
        f"- Credentials removed: {_bool_text(privacy.get('secrets_always_removed'))}",
        f"- Device serial numbers masked: {_bool_text(privacy.get('serial_numbers_always_masked'))}",
        f"- Management IPs masked: {_bool_text(privacy.get('mask_management_ips'))}",
        f"- MAC addresses masked: {_bool_text(privacy.get('mask_mac_addresses'))}",
        f"- Hostnames masked: {_bool_text(privacy.get('mask_hostnames'))}",
        f"- VLAN names masked: {_bool_text(privacy.get('mask_vlan_names'))}",
        f"- Interface descriptions masked: {_bool_text(privacy.get('mask_interface_descriptions'))}",
        "",
        "What works:",
        "",
        "What is missing or incorrect:",
        "",
        "Anything unusual about this switch:",
        "",
        "Thank you.",
    ])

    message = EmailMessage(policy=SMTP)
    message["To"] = SUPPORT_ADDRESS
    message["Subject"] = subject
    message.set_content(body)
    message.add_attachment(
        archive.read_bytes(),
        maintype="application",
        subtype="zip",
        filename=archive.name,
    )

    args.output_eml.parent.mkdir(parents=True, exist_ok=True)
    args.output_eml.write_bytes(message.as_bytes(policy=SMTP))

    mailto = f"mailto:{SUPPORT_ADDRESS}?subject={quote(subject)}&body={quote(body)}"
    page = f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>Support My Switch - {html.escape(contribution_id)}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 18px;line-height:1.5}}
.actions{{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}}
a.button{{display:inline-block;padding:12px 18px;border:1px solid #777;border-radius:8px;text-decoration:none;color:inherit}}
a.primary{{font-weight:700}}
small{{color:#666}}
</style>
</head>
<body>
<h1>Contribution ready</h1>
<p><strong>{html.escape(contribution_id)}</strong></p>
<div class=\"actions\">
<a class=\"button primary\" href=\"{html.escape(args.output_eml.name)}\">Prepare Email</a>
<a class=\"button\" href=\"{html.escape(archive.name)}\" download>Download Archive</a>
<a class=\"button\" href=\"{html.escape(mailto)}\">Open Email Without Attachment</a>
</div>
<p><small>Prepare Email opens or downloads a standard .eml message with the ZIP already attached. Nothing is sent automatically.</small></p>
</body>
</html>
"""
    args.output_html.write_text(page, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
