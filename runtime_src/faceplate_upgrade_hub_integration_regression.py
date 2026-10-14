#!/usr/bin/env python3
"""Mocked Hub/Core boundary regression for safe faceplate offer lifecycle."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import support_web as hub

def test() -> None:
    with TemporaryDirectory() as root:
        root = Path(root)
        old_registry = hub.DEFAULT_REGISTRY_FILE
        old_generated = hub.DEFAULT_GENERATED_CARD
        old_ws = hub._home_assistant_ws
        old_service = hub._home_assistant_service
        old_inventory = hub._configured_devices_snapshot
        old_preference = hub.faceplate_offers.DEFAULT_PATH
        registry = root / "models.json"
        registry.write_text(json.dumps({"devices": [{"model": "TL-SG2008P",
            "default_faceplate": "faceplates/new.png", "dashboard_support": True}]}))
        current = [{"base_profile": "native_SW3", "active": True,
                    "faceplate": "default", "faceplate_source": "default",
                    "saved_calibration_image": "old.png"}]
        mock_inv = {"devices": [{"device_key": "snmp:SW3", "switch_name": "SW3",
            "display_name": "Switch 3", "switch_model": "TL-SG2008P"}]}
        services = []
        failed = False

        def ws(data):
            if data["type"] == "switch_vision/list_assets":
                return {"core_version": "2.7.86", "faceplate_fingerprints": {
                    "old.png": {"sha256": "a" * 64},
                    "new.png": {"sha256": "b" * 64}}}
            if data["type"] == "switch_vision/list_calibrations":
                return {"items": current}
            raise AssertionError(data)

        def service(domain, service_name, args):
            services.append((domain, service_name, dict(args)))
            if failed:
                raise RuntimeError("Core reset failed")
            assert (domain, service_name) == ("switch_vision", "reset_calibrations")
            assert args == {"scope": "switch", "base_profile": "native_SW3"}
            current.clear()

        hub.DEFAULT_REGISTRY_FILE = registry
        hub.DEFAULT_GENERATED_CARD = root / "no-generated-card.yaml"
        hub._home_assistant_ws = ws
        hub._home_assistant_service = service
        hub._configured_devices_snapshot = lambda _path: mock_inv
        hub.faceplate_offers.DEFAULT_PATH = root / "preferences.json"
        try:
            first = hub._faceplate_upgrade_snapshot(root / "options.json")
            assert first["count"] == 1
            item = first["offers"][0]
            assert item["base_profile"] == "native_SW3"
            assert item["collapsed"] is False
            body = {"action": "keep", "device_key": "snmp:SW3", "available_sha256": "b" * 64}
            assert hub._faceplate_upgrade_action(root, body)["action"] == "kept"
            assert hub._faceplate_upgrade_snapshot(root)["offers"][0]["collapsed"] is True
            assert not services
            body["action"] = "upgrade"
            failed = True
            try:
                hub._faceplate_upgrade_action(root, body)
                raise AssertionError("failed Core reset must propagate")
            except RuntimeError as err:
                assert "Core reset failed" in str(err)
            assert hub._faceplate_upgrade_snapshot(root)["count"] == 1
            failed = False
            result = hub._faceplate_upgrade_action(root, body)
            assert result["action"] == "upgraded"
            assert hub._faceplate_upgrade_snapshot(root)["count"] == 0
            assert len(services) == 2
            # A conflicting profile base (SW 3 => SW_3) disables both offers.
            current.append({"base_profile": "native_SW_3", "active": True,
                "faceplate": "default", "faceplate_source": "default",
                "saved_calibration_image": "old.png"})
            mock_inv["devices"] = [
                {"device_key": "snmp:SW_3", "switch_name": "SW_3", "switch_model": "TL-SG2008P"},
                {"device_key": "snmp:SW 3", "switch_name": "SW 3", "switch_model": "TL-SG2008P"},
            ]
            assert hub._faceplate_upgrade_snapshot(root)["count"] == 0
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
