#!/usr/bin/env python3
"""Offline Hub/Core contract: approval selects art, never resets Calibration."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import support_web as hub


def test() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        old_registry = hub.DEFAULT_REGISTRY_FILE
        old_generated = hub.DEFAULT_GENERATED_CARD
        old_ws = hub._home_assistant_ws
        old_service = hub._home_assistant_service
        old_inventory = hub._configured_devices_snapshot
        old_preference = hub.faceplate_offers.DEFAULT_PATH
        old_sha, new_sha = "a" * 64, "b" * 64
        stock_name = "switch.png"
        registry = root / "models.json"
        registry.write_text(json.dumps({"devices": [{
            "model": "TL-SG2008P", "default_faceplate": "faceplates/" + stock_name,
            "dashboard_support": True,
        }]}))
        inventory = {"devices": [{
            "device_key": "snmp:SW3", "switch_name": "SW3",
            "display_name": "Switch 3", "switch_model": "TL-SG2008P",
        }]}
        saved_calibration = {"geometry": {"port1": [13, 27]}}
        original_calibration = json.dumps(saved_calibration, sort_keys=True)
        choices = {"native_SW3": {
            "filename": stock_name, "sha256": old_sha,
            "path": f"faceplate-history/{old_sha}/{stock_name}",
        }}
        operations = []
        fail_approval = False

        def websocket(payload):
            nonlocal fail_approval
            action = payload["type"]
            if action == "switch_vision/list_assets":
                return {"core_version": "2.7.90", "faceplate_fingerprints": {
                    stock_name: {"sha256": new_sha},
                }}
            if action == "switch_vision/get_calibration":
                assert payload["profile"] == "native_SW3"
                assert payload["stock_faceplate"] == stock_name
                return {"exists": False}
            if action == "switch_vision/list_calibrations":
                return {"stock_artwork_choices": choices, "items": [saved_calibration]}
            if action == "switch_vision/approve_stock_artwork":
                operations.append(dict(payload))
                if fail_approval:
                    raise RuntimeError("Core artwork approval failed")
                assert payload["base_profile"] == "native_SW3"
                assert payload["filename"] == stock_name
                assert payload["previous_filename"] == stock_name
                assert payload["expected_sha256"] == old_sha
                assert payload["approved_sha256"] == new_sha
                choices["native_SW3"] = {
                    "filename": stock_name, "sha256": new_sha,
                    "path": "faceplates/" + stock_name,
                }
                return {"ok": True, "sha256": new_sha, "calibration_reset": True}
            raise AssertionError(payload)

        hub.DEFAULT_REGISTRY_FILE = registry
        hub.DEFAULT_GENERATED_CARD = root / "no-generated-card.yaml"
        hub._home_assistant_ws = websocket
        hub._home_assistant_service = lambda *_: (_ for _ in ()).throw(
            AssertionError("Use Core's single atomic artwork + Calibration reset transaction")
        )
        hub._configured_devices_snapshot = lambda _options: inventory
        hub.faceplate_offers.DEFAULT_PATH = root / "preferences.json"
        try:
            before = hub._faceplate_upgrade_snapshot(root / "options.json")
            assert before["count"] == 1
            offer = before["offers"][0]
            assert offer["same_filename"] is True
            assert offer["base_profile"] == "native_SW3"
            assert offer["current_preview"] == f"faceplate-history/{old_sha}/{stock_name}"
            body = {"device_key": "snmp:SW3", "base_profile": "native_SW3",
                    "available_sha256": new_sha, "action": "keep"}
            assert hub._faceplate_upgrade_action(root, body)["action"] == "kept"
            assert hub._faceplate_upgrade_snapshot(root)["offers"][0]["collapsed"] is True
            assert choices["native_SW3"]["sha256"] == old_sha
            body["action"] = "upgrade"
            fail_approval = True
            try:
                hub._faceplate_upgrade_action(root, body)
            except RuntimeError as err:
                assert "approval failed" in str(err)
            else:
                raise AssertionError("failed approval was accepted")
            assert hub._faceplate_upgrade_snapshot(root)["count"] == 1
            fail_approval = False
            assert hub._faceplate_upgrade_action(root, body)["action"] == "upgraded"
            assert hub._faceplate_upgrade_snapshot(root)["count"] == 0
            assert len(operations) == 2
            assert operations[-1]["reset_switch_calibration"] is True
            assert json.dumps(saved_calibration, sort_keys=True) == original_calibration
            # If old bytes cannot be shown, still offer verified current stock;
            # never fabricate an image representing the missing old revision.
            choices["native_SW3"] = {
                "filename": stock_name, "sha256": old_sha,
                "unavailable": "true",
            }
            unavailable = hub._faceplate_upgrade_snapshot(root)
            assert unavailable["count"] == 1
            assert unavailable["offers"][0]["old_preview_unavailable"] is True
            assert unavailable["offers"][0]["current_preview"] == ""
            # Existing generated exact-model card remains supported without
            # triggering a new discovery run.
            saved_card = root / "generated-card.yaml"
            saved_card.write_text("""views:
  - cards:
      - type: custom:switch-vision-3650
        discovery_selected_switch: SW3
        switch_model: TL-SG2008P
""")
            hub.DEFAULT_GENERATED_CARD = saved_card
            inventory["devices"][0]["switch_model"] = "auto"
            assert hub._faceplate_upgrade_snapshot(root)["count"] == 1
            # Names that collapse to one profile cannot select each other's art.
            inventory["devices"] = [
                {"device_key": "snmp:A B", "switch_name": "A B",
                 "switch_model": "TL-SG2008P"},
                {"device_key": "snmp:A_B", "switch_name": "A_B",
                 "switch_model": "TL-SG2008P"},
            ]
            assert hub._faceplate_upgrade_snapshot(root)["devices_checked"] == 0
        finally:
            hub.DEFAULT_REGISTRY_FILE = old_registry
            hub.DEFAULT_GENERATED_CARD = old_generated
            hub._home_assistant_ws = old_ws
            hub._home_assistant_service = old_service
            hub._configured_devices_snapshot = old_inventory
            hub.faceplate_offers.DEFAULT_PATH = old_preference
    print("FACEPLATE_UPGRADE_HUB_INTEGRATION_PASS")


if __name__ == "__main__":
    test()
