from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime_src"


def load_entrypoint():
    spec = importlib.util.spec_from_file_location(
        "sv_discovery_contract_entrypoint_manual_model",
        RUNTIME / "discovery_contract_entrypoint.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PREPARE = RUNTIME / "physical_contract_prepare.sh"
    module.REGISTRY = RUNTIME / "opt/switch-vision/devices/supported_devices.json"
    return module


def write_manual_fixture_walk(path: Path) -> None:
    lines = [
        '.1.3.6.1.2.1.1.1.0 = STRING: "Cisco IOS Software, C3750E Software (C3750E-UNIVERSALK9-M), Version 15.2(4)E10"',
        '.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.9.1.516',
        '.1.3.6.1.2.1.47.1.1.1.1.13.1001 = STRING: "WS-C3750X-48P-S"',
    ]
    index = 10101
    for port in range(1, 49):
        lines.append(f'.1.3.6.1.2.1.31.1.1.1.1.{index} = STRING: "Gi1/0/{port}"')
        index += 1
    for port in range(1, 5):
        lines.append(f'.1.3.6.1.2.1.31.1.1.1.1.{10300 + port} = STRING: "Gi1/1/{port}"')
    for port in range(1, 3):
        lines.append(f'.1.3.6.1.2.1.31.1.1.1.1.{10400 + port} = STRING: "Te1/1/{port}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_manual_model_survives_authoritative_physical_contract() -> None:
    entry = load_entrypoint()
    with tempfile.TemporaryDirectory(prefix="sv_manual_model_contract_") as tmp:
        root = Path(tmp)
        walk_dir = root / "walks" / "manual_fixture"
        walk_dir.mkdir(parents=True)
        walk = walk_dir / "live-targeted-snmpwalk.txt"
        write_manual_fixture_walk(walk)
        options = {
            "snmpwalks_dir": str(root / "walks"),
            "input_path": str(walk),
            "switches": [
                {
                    "switch_name": "manual_fixture",
                    "output_dir": str(walk_dir),
                    "switch_model": "WS-C3750X-48P",
                    "enabled": "enabled",
                }
            ],
        }
        staged, ordered, accepted = entry._stage_options(options, root / "work")

        assert len(ordered) == 1
        assert len(accepted) == 1
        info = ordered[0]
        contract = info["contract"]
        assert contract["status"] == "resolved"
        assert contract["observed"]["physical"] == 52
        assert contract["observed"]["rj45"] == 48
        assert contract["observed"]["sfp"] == 2
        assert contract["observed"]["sfp_plus"] == 2
        assert contract["device"]["model"] == "WS-C3750X-48P-S"
        assert contract["device"]["effective_model"] == "WS-C3750X-48P"
        assert contract["device"]["model_override"] == "WS-C3750X-48P"
        assert contract["device"]["compatibility_mode"] is True
        assert contract["device"]["registry_match"] is True
        assert contract["device"]["exact_registry_match"] is False

        capability = json.loads(Path(info["capability"]).read_text(encoding="utf-8"))
        assert capability["device"]["detected_model_text"] == "WS-C3750X-48P-S"
        assert capability["device"]["model_text"] == "WS-C3750X-48P-S"
        assert capability["device"]["model_override"] == "WS-C3750X-48P"
        assert capability["device"]["effective_model_text"] == "WS-C3750X-48P"
        assert capability["device"]["compatibility_mode"] is True

        normalized = Path(info["destination"]).read_text(encoding="utf-8")
        assert 'STRING: "SwitchVisionNonPhysical10301"' in normalized
        assert 'STRING: "SwitchVisionNonPhysical10302"' in normalized
        interfaces = {row["if_index"]: row for row in capability["interfaces"]}
        assert interfaces[10303]["media"] == "sfp"
        assert interfaces[10304]["media"] == "sfp"
        assert interfaces[10401]["media"] == "sfp_plus"
        assert interfaces[10402]["media"] == "sfp_plus"
        assert staged["switches"][0]["switch_model"] == "WS-C3750X-48P"


if __name__ == "__main__":
    test_manual_model_survives_authoritative_physical_contract()
