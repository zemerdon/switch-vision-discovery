#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parents[1]
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
GENERATED_ROOTS = ("runtime_src", "tools", "switch_vision_discovery")
RUNTIME_VERSION_FILES = (
    "runtime_src/run.sh",
    "runtime_src/discovery_job.sh",
    "runtime_src/self-test.sh",
)
PERMANENT_CHECKS = (
    "tools/test_unifi_dashboard_failure_modes.py",
    "tools/test_local_model_identity.py",
    "tools/test_ha_entity_snapshot.py",
    "tools/test_public_attribution_privacy.py",
    "tools/test_visual_contract_policy.py",
    "tools/test_faceplate_catalog_contract.py",
    "tools/check_component_contracts.py",
    "tools/check_speed_contracts.py",
    "tools/check_hub_identity.py",
    "tools/test_regenerate_yaml_contract.py",
    "tools/test_support_email_mime.py",
    "tools/test_c3750_48p_contract.py",
    "tools/test_c3750_48p_live_mapping.py",
    "tools/audit_functional_contracts.py",
    "tools/audit_hub_control_inventory.py",
    "tools/test_hub_save_reset_contracts.py",
    "tools/test_unifi_multi_controller_hub.py",
    "tools/test_calibration_core_bridge_contract.py",
    "tools/test_registry_roundtrip.py",
)
SHELL_CHECKS = ("tools/test_contributor_interface_batch.sh",)


def release_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PATH"] = f"{Path(sys.executable).absolute().parent}:{env.get('PATH', '')}"
    return env


def run(args: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(
        args,
        cwd=cwd,
        env=env or release_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.returncode:
        raise SystemExit(
            f"Discovery release check command failed ({proc.returncode}): {' '.join(args)}"
        )
    return proc.stdout or ""


def git_status(root: Path) -> str:
    return subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        text=True,
    )


def resolve_version(root: Path) -> str:
    payload = yaml.safe_load(
        (root / "switch_vision_discovery/config.yaml").read_text(encoding="utf-8")
    ) or {}
    version = str(payload.get("version") or "").strip()
    if not SEMVER_RE.fullmatch(version):
        raise SystemExit(f"Discovery version is not exact semantic version: {version!r}")
    return version


def generated_junk(root: Path) -> list[Path]:
    problems: list[Path] = []
    for relative in GENERATED_ROOTS:
        base = root / relative
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_dir() and path.name == "__pycache__":
                problems.append(path)
            elif path.is_file() and (
                path.suffix in {".pyc", ".pyo"} or path.name == ".DS_Store"
            ):
                problems.append(path)
    return problems


def reject_generated_junk(root: Path) -> None:
    problems = generated_junk(root)
    if problems:
        shown = ", ".join(str(path.relative_to(root)) for path in problems[:20])
        raise SystemExit(f"Discovery generated cache/junk material present: {shown}")
    print("Discovery source hygiene: PASS")


def compile_python_sources(root: Path) -> None:
    paths = sorted((root / "tools").glob("*.py"))
    paths.extend(sorted((root / "runtime_src").glob("*.py")))
    if not paths:
        raise SystemExit("Discovery Python source inventory is empty")
    for path in paths:
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec")
    print(f"Discovery Python syntax: PASS ({len(paths)} files)")


def validate_runtime_version_contract(root: Path, version: str) -> None:
    marker = f'SWITCH_VISION_DISCOVERY_VERSION="{version}"'
    for relative in RUNTIME_VERSION_FILES:
        text = (root / relative).read_text(encoding="utf-8")
        if marker not in text:
            raise SystemExit(
                f"Discovery runtime version contract failed for {relative}: "
                f"missing {marker!r}"
            )
    print(f"Discovery {version} app/runtime version contract: PASS")


def validate_release_transport(root: Path) -> None:
    builder = (root / ".github/workflows/builder.yaml").read_text(encoding="utf-8")
    publisher = (
        root / ".github/workflows/publish-discovery-release.yml"
    ).read_text(encoding="utf-8")
    forbidden_builder = (
        (r"^\s+packages:\s*write\s*$", "packages: write"),
        (r"^\s+push:\s*true\s*$", "push: true"),
        (r"^\s+name:\s*Publish multi-arch manifest\s*$", "Publish multi-arch manifest"),
    )
    for pattern, label in forbidden_builder:
        if re.search(pattern, builder, re.MULTILINE):
            raise SystemExit(
                f"automatic Discovery publication capability remains in builder.yaml: {label}"
            )
    required_publisher = (
        "startsWith(github.event.pull_request.head.ref, 'release/discovery-')",
        ".sv-release-request.json",
        "TARGET_SHA",
        "BASE_SHA",
        "packages: write",
        "push: true",
        "Publish multi-arch manifest",
        'IMAGE_NAME: ${{ steps.normalize.outputs.image_name }}',
        'imagetools inspect "$REGISTRY_PREFIX/$IMAGE_NAME:$VERSION"',
        'version_ref="$REGISTRY_PREFIX/$IMAGE_NAME:$VERSION"',
        'latest_ref="$REGISTRY_PREFIX/$IMAGE_NAME:latest"',
    )
    missing = [token for token in required_publisher if token not in publisher]
    if missing:
        raise SystemExit(
            "Discovery guarded release transport contract missing: " + ", ".join(missing)
        )
    print("Discovery guarded release transport contract: PASS")


def archive_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_archive_hygiene(path: Path) -> None:
    problems: list[str] = []
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            p = PurePosixPath(member.name)
            if p.is_absolute() or ".." in p.parts:
                problems.append(f"unsafe path: {member.name}")
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                problems.append(f"link/special entry: {member.name}")
            if "__pycache__" in p.parts or p.suffix in {".pyc", ".pyo"}:
                problems.append(f"Python cache/bytecode: {member.name}")
    if problems:
        raise SystemExit("Discovery runtime archive hygiene failed: " + "; ".join(problems[:20]))
    print("Discovery runtime archive hygiene: PASS")


def validate_packaged_runtime(root: Path, archive_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="sv-discovery-runtime-") as tmp:
        target = Path(tmp)
        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(target, filter="data")
        required = (
            target / "opt/switch-vision/devices/supported_devices.json",
            target / "opt/switch-vision/mib_database",
            target / "opt/switch-vision/vendors",
            target / "discovery_contract_entrypoint.py",
            target / "physical_contract_prepare.sh",
            target / "self-test.sh",
        )
        missing = [str(path.relative_to(target)) for path in required if not path.exists()]
        if missing:
            raise SystemExit(
                "Discovery packaged runtime is missing required paths: " + ", ".join(missing)
            )
        for relative in (
            "support_web.py",
            "registry_lookup.py",
            "vendor_sensor_scan.py",
            "unifi_dashboard_cards.py",
        ):
            source = (target / relative).read_text(encoding="utf-8")
            compile(source, str(target / relative), "exec")
    print("Discovery packaged runtime structure/Python contract: PASS")


def run_permanent_checks(root: Path) -> None:
    for relative in PERMANENT_CHECKS:
        print(f"=== {relative} ===")
        run([sys.executable, relative], root)
    for relative in SHELL_CHECKS:
        print(f"=== {relative} ===")
        run(["sh", relative], root)
    print(
        "Discovery permanent regression/audit suite: PASS "
        f"({len(PERMANENT_CHECKS)} Python checks, {len(SHELL_CHECKS)} shell checks)"
    )


def build_and_self_test_image(root: Path, version: str) -> None:
    tag = f"switch-vision-discovery-release-check:{version}"
    env = release_env()
    subprocess.run(
        ["docker", "image", "rm", "-f", tag],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    try:
        run(
            [
                "docker",
                "build",
                "--build-arg",
                f"BUILD_VERSION={version}",
                "--build-arg",
                "BUILD_ARCH=amd64",
                "-t",
                tag,
                "switch_vision_discovery",
            ],
            root,
            env=env,
        )
        run(
            ["docker", "run", "--rm", "--entrypoint", "/self-test.sh", tag],
            root,
            env=env,
        )
    finally:
        subprocess.run(
            ["docker", "image", "rm", "-f", tag],
            cwd=root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    print(f"Discovery {version} non-publishing image build/self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the product-owned Switch Vision Discovery release validation."
    )
    parser.add_argument("--mode", choices=("release",), required=True)
    args = parser.parse_args()
    if args.mode != "release":
        raise SystemExit("unsupported release-check mode")

    root = ROOT
    baseline_status = git_status(root)
    version = resolve_version(root)

    reject_generated_junk(root)
    compile_python_sources(root)
    validate_release_transport(root)

    archive_path = root / "switch_vision_discovery/runtime.tar.gz"
    if not archive_path.is_file():
        raise SystemExit("Discovery tracked runtime archive is missing")
    tracked_archive = archive_path.read_bytes()
    tracked_archive_digest = archive_digest(archive_path)
    validate_runtime_version_contract(root, version)
    run([sys.executable, "tools/check_runtime_parity.py"], root)
    validate_archive_hygiene(archive_path)
    validate_packaged_runtime(root, archive_path)
    print(f"Discovery tracked runtime archive: PASS ({tracked_archive_digest})")

    run(["sh", "tools/materialize_runtime.sh"], root)
    validate_runtime_version_contract(root, version)
    run([sys.executable, "tools/check_runtime_parity.py"], root)
    validate_archive_hygiene(archive_path)
    validate_packaged_runtime(root, archive_path)
    first_digest = archive_digest(archive_path)

    run_permanent_checks(root)

    run(["sh", "tools/materialize_runtime.sh"], root)
    second_digest = archive_digest(archive_path)
    if second_digest != first_digest:
        raise SystemExit(
            "Discovery deterministic runtime archive contract failed: "
            f"first={first_digest} second={second_digest}"
        )
    print(f"Discovery deterministic runtime archive: PASS ({first_digest})")

    validate_runtime_version_contract(root, version)
    run([sys.executable, "tools/check_runtime_parity.py"], root)
    validate_archive_hygiene(archive_path)
    reject_generated_junk(root)

    build_and_self_test_image(root, version)

    archive_path.write_bytes(tracked_archive)
    if archive_digest(archive_path) != tracked_archive_digest:
        raise SystemExit("Discovery tracked runtime archive restore failed")
    run([sys.executable, "tools/check_runtime_parity.py"], root)
    validate_archive_hygiene(archive_path)
    validate_packaged_runtime(root, archive_path)
    print("Discovery tracked runtime archive restore: PASS")

    final_status = git_status(root)
    if final_status != baseline_status:
        print("Discovery release check changed repository state.", file=sys.stderr)
        print("--- baseline status ---", file=sys.stderr)
        print(
            baseline_status,
            end="" if baseline_status.endswith("\n") else "\n",
            file=sys.stderr,
        )
        print("--- final status ---", file=sys.stderr)
        print(
            final_status,
            end="" if final_status.endswith("\n") else "\n",
            file=sys.stderr,
        )
        return 1

    print(f"Discovery {version} deterministic release validation: PASS")
    print("SV_RELEASE_CHECK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
