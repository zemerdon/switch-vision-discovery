#!/usr/bin/env python3
"""HP rear A1-A4 binding requires observed physical ports, not absence of a harmless exact-model selection."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "runtime_src/discovery_job.sh").read_text(encoding="utf-8")
START = SOURCE.index("emit_generated_card_hp_rear_sfp_bindings() {")
END = SOURCE.index("\nbuild_juniper_port_mode_metadata() {", START)
FUNCTION = SOURCE[START:END]
HP = "HP J8693A Switch 3500yl-48G"


def emitted(override: str | None, ports: bool = True) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        interfaces = [
            {"physical": True, "media": "uplink", "name": f"A{port}", "if_index": 48 + port}
            for port in range(1, 5)
        ] if ports else []
        device = {"detected_model_text": HP, "model_text": HP}
        if override is not None:
            device["model_override"] = override
        (directory / "HP_3500-capabilities.json").write_text(
            json.dumps({"device": device, "interfaces": interfaces}), encoding="utf-8"
        )
        sh = (
            "exact_model_for_generated_card() { printf '%s\\n' 'HP J8693A Switch 3500yl-48G'; }\n"
            + FUNCTION
            + "\nCAPABILITIES_DIR=\"$1\"\n"
            + "emit_generated_card_hp_rear_sfp_bindings HP_3500 hptest\n"
        )
        result = subprocess.run(["sh", "-c", sh, "sh", str(directory)],
                                text=True, capture_output=True, check=True)
        return result.stdout.strip()


class Hp3500RearBindingOverride(unittest.TestCase):
    def test_no_override_emits_observed_rear_sensors(self) -> None:
        result = emitted(None)
        self.assertIn('"rSFP1":{"interface_name":"A1","entity_base":"sensor.hptest_rear_10g_1","if_index":49}', result)
        self.assertIn('"rSFP4":{"interface_name":"A4","entity_base":"sensor.hptest_rear_10g_4","if_index":52}', result)

    def test_identical_override_does_not_hide_observed_rear_sensors(self) -> None:
        result = emitted(HP)
        self.assertIn('"rSFP1":{"interface_name":"A1","entity_base":"sensor.hptest_rear_10g_1","if_index":49}', result)
        self.assertIn('"rSFP4":{"interface_name":"A4","entity_base":"sensor.hptest_rear_10g_4","if_index":52}', result)

    def test_different_override_cannot_invent_binds(self) -> None:
        self.assertEqual(emitted("Another Vendor Test Model"), "")

    def test_no_observed_rear_module_keeps_binds_absent(self) -> None:
        self.assertEqual(emitted(HP, ports=False), "")


if __name__ == "__main__":
    unittest.main()
