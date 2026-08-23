#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "switch_vision_discovery/config.yaml"
PROFILES = ROOT / "runtime_src/profiles/switch-vision-profiles.yaml"
REGISTRY = ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"
SELF_TEST = ROOT / "runtime_src/self-test.sh"
SUBMISSION_ID = re.compile(r"(?i)SV[-_]20\d{2}[-_]\d+")
CONTRIBUTION_BREADCRUMB = re.compile(
    r"(?i)(?:unifi[-_]contrib|community[-_]validation)[/_-]\d{6}"
)
VERSION_RE = re.compile(r'(?m)^version:\s*"([^"]+)"')
MIGRATION_VERSION = "2.1.44"

PROMOTE_TO_EXPERIMENTAL = {
    "UCG Ultra",
    "US 16 PoE 150W",
    "USW Ultra",
}
KEEP_EXPERIMENTAL = {"USW Pro Max 24"}


def current_version() -> str:
    match = VERSION_RE.search(CONFIG.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("Could not resolve Discovery version")
    return match.group(1)


def sanitize_profile_text(text: str) -> str:
    # Preserve hardware statements while replacing private submission IDs with
    # neutral public evidence wording. These rewrites exist only to migrate the
    # legacy public profile source in v2.1.44; later versions fail on any new ID.
    text = re.sub(
        r"SV-2026-\d+\s+and\s+SV-2026-\d+\s+confirm",
        "Independent community hardware captures confirm",
        text,
    )
    text = re.sub(
        r"SV-2026-\d+\s+and\s+SV-2026-\d+",
        "independent community contributions",
        text,
    )
    text = re.sub(
        r"SV-2026-\d+\s+confirms",
        "Community hardware evidence confirms",
        text,
    )
    text = re.sub(
        r"SV-2026-\d+\s+contains",
        "Community hardware evidence contains",
        text,
    )
    text = SUBMISSION_ID.sub("community contribution", text)

    replacements = {
        "Profile derived from two matching community contribution devices.":
            "Profile derived from two matching community-contributed devices.",
        "Support My Switch contributions independent community contributions":
            "independent Support My Switch community contributions",
        "Support My Switch contribution community contribution":
            "a Support My Switch community contribution",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def migrate_profile_statuses(text: str) -> str:
    for profile in sorted(
        {
            "ubiquiti-ucg-ultra-api",
            "ubiquiti-us-16-poe-150w-api",
            "ubiquiti-usw-ultra-api",
        }
    ):
        pattern = re.compile(
            rf"(?m)(^  {re.escape(profile)}:\n    status: )(detected|experimental)$"
        )
        text, count = pattern.subn(r"\1experimental", text, count=1)
        if count != 1:
            raise SystemExit(f"Could not normalize support status for {profile}")

    pro_max = re.search(
        r"(?m)^  ubiquiti-usw-pro-max-24-api:\n    status: ([^\n]+)$",
        text,
    )
    if not pro_max or pro_max.group(1).strip() != "experimental":
        raise SystemExit("USW Pro Max 24 must remain Experimental in v2.1.44")
    return text


def migrate_registry() -> None:
    original = REGISTRY.read_text(encoding="utf-8")
    document = json.loads(original)
    devices = document.get("devices") if isinstance(document, dict) else None
    if not isinstance(devices, list):
        raise SystemExit("Supported-device registry devices list is missing")

    seen: set[str] = set()
    targets = PROMOTE_TO_EXPERIMENTAL | KEEP_EXPERIMENTAL
    for row in devices:
        if not isinstance(row, dict):
            continue
        model = str(row.get("model") or "")
        if model not in targets:
            continue
        seen.add(model)
        status = str(row.get("status") or "")
        if model in PROMOTE_TO_EXPERIMENTAL:
            if status not in {"detected", "experimental"}:
                raise SystemExit(f"Unexpected support status for {model}: {status!r}")
            row["status"] = "experimental"
        elif status != "experimental":
            raise SystemExit(f"{model} must remain Experimental, found {status!r}")
        row["evidence"] = "multiple_real_hardware_unifi_api_contributions"

    missing = targets - seen
    if missing:
        raise SystemExit(f"Missing required supported-device records: {sorted(missing)}")

    rendered = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    if rendered != original:
        REGISTRY.write_text(rendered, encoding="utf-8", newline="\n")


def migrate_self_test() -> None:
    original = SELF_TEST.read_text(encoding="utf-8")
    text = original

    old_status = '    expected_status = "experimental" if model == "USW Pro Max 24" else "detected"\n'
    new_status = '    expected_status = "experimental"\n'
    if old_status in text:
        text = text.replace(old_status, new_status, 1)
    elif new_status not in text:
        raise SystemExit("Could not update Community UniFi support-status regression")

    old_profile_assert = '    assert profile in profiles, profile\n'
    new_profile_assert = (
        '    assert profile in profiles, profile\n'
        '    assert profiles[profile]["status"] == "experimental", model\n'
    )
    if new_profile_assert not in text:
        if old_profile_assert not in text:
            raise SystemExit("Could not extend Community UniFi profile-status regression")
        text = text.replace(old_profile_assert, new_profile_assert, 1)

    replacements = {
        "community-validation/000036": "community-hardware",
        "unifi-contrib-000003": "unifi-community-fixture-a",
        "unifi-contrib-000057": "unifi-community-fixture-b",
        "sv57_snapshot": "v219_community_snapshot",
        "PYTEST_V219_SV57": "PYTEST_V219_COMMUNITY",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    if SUBMISSION_ID.search(text) or CONTRIBUTION_BREADCRUMB.search(text):
        raise SystemExit("Private contribution identifier remains in shipped runtime self-test")
    if text != original:
        SELF_TEST.write_text(text, encoding="utf-8", newline="\n")


def assert_public_runtime_clean() -> None:
    for path in (PROFILES, SELF_TEST):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if SUBMISSION_ID.search(text) or CONTRIBUTION_BREADCRUMB.search(text):
            raise SystemExit(f"Private contribution identifier remains in public runtime source: {path}")


def main() -> None:
    version = current_version()
    profiles = PROFILES.read_text(encoding="utf-8")

    if version == MIGRATION_VERSION:
        migrated = migrate_profile_statuses(sanitize_profile_text(profiles))
        if SUBMISSION_ID.search(migrated):
            raise SystemExit("Private Support My Switch identifier remains in public profile source")
        if migrated != profiles:
            PROFILES.write_text(migrated, encoding="utf-8", newline="\n")
        migrate_registry()
        migrate_self_test()
        assert_public_runtime_clean()
        print("Public support metadata v2.1.44 migration: PASS")
        return

    # The migration is deliberately not a permanent auto-sanitizer. After
    # v2.1.44, new private IDs in public source are a hard failure that requires
    # an explicit canonical-source fix.
    assert_public_runtime_clean()
    print("Public support metadata privacy preflight: PASS")


if __name__ == "__main__":
    main()
