#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "tools" / "sv_release_check.py"
PIN_HELPER = ROOT / "tools" / "prepare_core_faceplate_pin.py"
REQUIREMENTS = ROOT / "tools" / "sv_release_check.requirements.txt"
PIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*==[A-Za-z0-9][A-Za-z0-9._+!-]*$")


def load_entrypoint():
    spec = importlib.util.spec_from_file_location(
        "switch_vision_discovery_release_check", ENTRY
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load Discovery release-check entrypoint")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    assert ENTRY.is_file()
    assert REQUIREMENTS.is_file()

    source = ENTRY.read_text(encoding="utf-8")
    compile(source, str(ENTRY), "exec")
    for marker in (
        "tools/materialize_runtime.sh",
        "tools/check_runtime_parity.py",
        "tools/check_component_contracts.py",
        "switch_vision_discovery/runtime.tar.gz",
        "self-test.sh",
        "docker",
        "SV_RELEASE_CHECK_PASS",
        "git_status(root)",
        "--core-source-root",
        "--core-source-sha",
        "SWITCH_VISION_CORE_SOURCE_ROOT",
        "SWITCH_VISION_CORE_SOURCE_SHA",
        "tools/prepare_core_faceplate_pin.py",
        "validate_archive_hygiene",
        "validate_release_transport",
        "first_digest",
        "second_digest",
    ):
        assert marker in source, marker

    assert "Path(sys.executable).absolute().parent" in source
    assert "Path(sys.executable).resolve().parent" not in source
    assert "tracked_archive = archive_path.read_bytes()" in source
    assert "Discovery tracked runtime archive restore: PASS" in source

    pin_source = PIN_HELPER.read_text(encoding="utf-8")
    compile(pin_source, str(PIN_HELPER), "exec")
    assert "sys.dont_write_bytecode = True" in pin_source
    assert pin_source.index("sys.dont_write_bytecode = True") < pin_source.index(
        "import check_component_contracts as contracts"
    )

    materializer = (ROOT / "tools" / "materialize_runtime.sh").read_text(encoding="utf-8")
    for marker in ("--exclude='__pycache__'", "--exclude='*/__pycache__'", "--exclude='*.pyc'", "--exclude='*.pyo'", "--exclude='*.bak.*'"):
        assert marker in materializer, marker

    pins = [
        line.strip()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert pins == ["PyYAML==6.0.2", "websockets==15.0.1"]
    assert all(PIN_RE.fullmatch(line) for line in pins)

    component_contracts = (ROOT / "tools" / "check_component_contracts.py").read_text(encoding="utf-8")
    for marker in (
        'if core_source_root is not None:',
        'pinned_faceplate_labels = load_core_faceplate_catalog(core_source_root)',
        'pinned_faceplate_labels = load_pinned_faceplate_catalog()',
        'Discovery published Core faceplate pin does not match coordinated',
    ):
        assert marker in component_contracts, marker

    module = load_entrypoint()
    version = module.resolve_version(ROOT)
    module.validate_runtime_version_contract(ROOT, version)
    assert callable(module.reject_generated_junk)
    assert callable(module.validate_release_transport)
    assert callable(module.build_and_self_test_image)

    print("Discovery product-owned release-check contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
