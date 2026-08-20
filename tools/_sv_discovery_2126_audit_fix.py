#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import re
import subprocess
import urllib.request
from pathlib import Path

VERSION = "2.1.26"
CORE_REGISTRY_URL = (
    "https://raw.githubusercontent.com/zemerdon/"
    "switch-vision-releases/main/src/devices/supported_devices.json"
)
CONFIG = Path("switch_vision_discovery/config.yaml")
CHANGELOG = Path("switch_vision_discovery/CHANGELOG.md")
RUNTIME_JOB = Path("runtime_src/discovery_job.sh")
REGISTRY = Path("runtime_src/opt/switch-vision/devices/supported_devices.json")
ARCHIVE = Path("switch_vision_discovery/runtime.tar.gz")


def stop(message: str) -> None:
    raise SystemExit(f"STOP: {message}")


def write(path: Path, text: str) -> None:
    path.write_text(
        text.replace("\r\n", "\n").replace("\r", "\n"),
        encoding="utf-8",
        newline="\n",
    )


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Switch-Vision-Discovery-v2.1.26/1"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        stop(f"remote JSON at {url} is not an object")
    return value


def models(payload: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for item in payload.get("devices", []):
        if not isinstance(item, dict):
            continue
        model = str(item.get("model") or "").strip()
        if model:
            result[model] = item
    return result


def patch_versions() -> None:
    config = CONFIG.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'(?m)^version:\s*"2\.1\.25"\s*$',
        f'version: "{VERSION}"',
        config,
        count=1,
    )
    if count != 1:
        stop(f"expected one Discovery config version 2.1.25, found {count}")
    write(CONFIG, updated)

    runtime = RUNTIME_JOB.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'(?m)^SWITCH_VISION_DISCOVERY_VERSION="2\.1\.(?:24|25)"$',
        f'SWITCH_VISION_DISCOVERY_VERSION="{VERSION}"',
        runtime,
        count=1,
    )
    if count != 1:
        stop(f"expected one stale Discovery runtime version, found {count}")
    write(RUNTIME_JOB, updated)


def sync_shared_unifi_visuals() -> None:
    discovery = json.loads(REGISTRY.read_text(encoding="utf-8"))
    core = fetch_json(CORE_REGISTRY_URL)
    d = models(discovery)
    c = models(core)

    if len(d) != 28:
        stop(f"expected current Discovery registry to contain 28 models, found {len(d)}")
    if not set(c).issubset(d):
        missing = sorted(set(c) - set(d))
        stop("Core models are missing from Discovery: " + ", ".join(missing))

    shared_unifi = [
        model
        for model in sorted(set(c) & set(d))
        if str(c[model].get("vendor") or "").strip() == "Ubiquiti"
    ]
    if len(shared_unifi) != 5:
        stop(
            f"expected 5 current shared Core/Discovery Ubiquiti models, "
            f"found {len(shared_unifi)}: {shared_unifi}"
        )

    for model in shared_unifi:
        source = c[model]
        target = d[model]
        for field in ("calibration_profile", "default_faceplate", "optional_faceplates"):
            if field in source:
                target[field] = copy.deepcopy(source[field])
        if isinstance(source.get("visuals"), dict):
            target["visuals"] = copy.deepcopy(source["visuals"])

    write(REGISTRY, json.dumps(discovery, ensure_ascii=False, indent=2) + "\n")
    print("Synced shared Ubiquiti visual defaults:")
    for model in shared_unifi:
        print(" -", model)


def patch_changelog() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    heading = "## v2.1.26 — Cross-component contract audit fixes"
    if heading in text:
        return
    entry = f'''{heading}\n\n- Correct the packaged Discovery runtime version identifier so runtime status, logs, and support metadata report v2.1.26 consistently with the Home Assistant app version.\n- Synchronize the five Ubiquiti models shared with Switch Vision Core v2.4.0 to the dedicated `unifi-24p-rj45-2sfp.png` faceplate and `unifi_24p_rj45_2sfp` calibration profile.\n- Preserve Discovery's additional exact-model hardware knowledge, including Dell N2128PX-ON and newer UniFi models that are not yet present in the Core supported-device index.\n- Add a cross-component CI contract check covering Discovery app/runtime version parity, Core-model presence, shared hardware mappings, shared Ubiquiti visual defaults, and the Discovery → SNMP2MQTT generated-YAML path.\n- Keep existing SNMP walks, device mappings, UniFi API port geometry, Support My Switch behavior, calibration profile management, and generated entity contracts unchanged.\n\n'''
    marker = "# Changelog\n\n"
    if marker not in text:
        stop("Discovery changelog header not found")
    write(CHANGELOG, text.replace(marker, marker + entry, 1))


def rebuild_runtime_archive() -> None:
    ARCHIVE.unlink(missing_ok=True)
    subprocess.run(
        ["tar", "-czf", str(ARCHIVE), "-C", "runtime_src", "."],
        check=True,
    )


def main() -> None:
    patch_versions()
    sync_shared_unifi_visuals()
    patch_changelog()
    rebuild_runtime_archive()

    subprocess.run(["python3", "tools/check_runtime_parity.py"], check=True)
    subprocess.run(["python3", "tools/check_component_contracts.py"], check=True)
    subprocess.run(["sh", "-n", str(RUNTIME_JOB)], check=True)

    Path("tools/_sv_discovery_2126_audit_fix.py").unlink(missing_ok=True)
    Path(".github/workflows/build-discovery-2126-audit-fix.yml").unlink(
        missing_ok=True
    )


if __name__ == "__main__":
    main()
