#!/usr/bin/env python3
"""Topology contract for sourced Discovery self-test modules."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"
SELF_TEST = RUNTIME / "self-test.sh"


def main() -> int:
    source = SELF_TEST.read_text(encoding="utf-8")
    modules = sorted(RUNTIME.glob("self_test_*.sh"))
    assert modules, "no extracted self-test modules found"

    names = {module.name for module in modules}
    assert len(names) == len(modules)

    for module in modules:
        include = f'. "$BASE_DIR/{module.name}"'
        assert source.count(include) == 1, module.name
        module_source = module.read_text(encoding="utf-8")
        for other in names:
            assert f'$BASE_DIR/{other}' not in module_source, (module.name, other)

    print(f"Discovery self-test module topology: PASS ({len(modules)} modules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
