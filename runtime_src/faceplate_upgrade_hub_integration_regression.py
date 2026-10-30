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
                if "stock_faceplate" not in payload:
                    return {"exists": True, "invalid": False,
                            "profile": "native_SW3", "calibration": saved_calibration}
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
        generated_card = root / "generated-card.yaml"
        generated_card.write_text("""views:
  - cards:
      - type: custom:switch-vision-3650
        discovery_selected_switch: SW3
        selected_switch: SW3
        member: SW3
        switch_model: TL-SG2008P
""")
        hub.DEFAULT_GENERATED_CARD = generated_card
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
            # The automatic Hub endpoint must fail closed on a forged Custom
            # request without invoking Core or changing persisted choices.
            choices["custom_SW3"] = {
                "filename": stock_name, "sha256": old_sha,
                "path": f"faceplate-history/{old_sha}/{stock_name}",
            }
            assert len(hub._faceplate_upgrade_snapshot(root)["offers"]) == 1
            custom_before = dict(choices["custom_SW3"])
            for action_name in ("keep", "upgrade", "select"):
                try:
                    hub._faceplate_upgrade_action(root, {
                        "action": action_name, "device_key": "snmp:SW3",
                        "base_profile": "custom_SW3", "available_sha256": new_sha,
                    })
                except ValueError as exc:
                    assert "Native dashboards only" in str(exc)
                else:
                    raise AssertionError("Custom automatic upgrade was accepted")
                assert choices["custom_SW3"] == custom_before
                assert operations == []
            # The separate manual Custom faceplate picker remains supported.
            manual = hub._faceplate_upgrade_snapshot(root)["selections"]
            assert any(row["base_profile"] == "custom_SW3" for row in manual)
            body = {"device_key": "snmp:SW3", "base_profile": "native_SW3",
                    "available_sha256": new_sha, "action": "keep"}
            assert hub._faceplate_upgrade_action(root, body)["action"] == "kept"
            assert hub._faceplate_upgrade_snapshot(root)["offers"][0]["collapsed"] is True
            assert choices["native_SW3"]["sha256"] == old_sha
            body["action"] = "export"
            exported = hub._faceplate_upgrade_action(root, body)
            assert exported["action"] == "exported"
            assert exported["base_profile"] == "native_SW3"
            assert exported["geometry"] == saved_calibration
            assert not operations
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
        selected_switch: SW3
        member: SW3
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


def test_legacy_saved_calibration_upgrade() -> None:
    """A new Core artwork pin must not hide one old saved Native layout."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        old_registry = hub.DEFAULT_REGISTRY_FILE
        old_generated = hub.DEFAULT_GENERATED_CARD
        old_ws = hub._home_assistant_ws
        old_service = hub._home_assistant_service
        old_inventory = hub._configured_devices_snapshot
        old_preference = hub.faceplate_offers.DEFAULT_PATH
        old_sha, new_sha = "a" * 64, "b" * 64
        old_geometry, new_geometry = "c" * 64, "d" * 64
        registry = root / "models.json"
        registry.write_text(json.dumps({"devices": [{
            "model": "WS-C3560CG-8PC-S", "dashboard_support": True,
            "default_faceplate": "faceplates/new.png",
            "optional_faceplates": ["faceplates/old.png"],
        }]}))
        inventory = {"devices": [{
            "device_key": "snmp:SW3", "switch_name": "SW3",
            "switch_model": "WS-C3560CG-8PC-S",
        }]}
        choices = {
            "native_SW3": {"filename": "new.png", "sha256": new_sha,
                           "path": "faceplates/new.png", "version": "2.8.16"},
            "custom_SW3": {"filename": "old.png", "sha256": old_sha,
                           "path": "faceplates/old.png"},
        }
        saved = [{"active": True, "scope": "native", "base_profile": "native_SW3",
                  "saved_calibration_image": "old.png"}]
        revisions = {}
        for filename, digest, geometry in [
            ("old.png", old_sha, old_geometry),
            ("new.png", new_sha, new_geometry),
        ]:
            revisions[filename] = [{"filename": filename, "sha256": digest,
                                   "geometry_sha256": geometry, "version": "2.8.16",
                                   "path": "faceplates/" + filename}]
        calls = []
        fail_approval = False

        def websocket(payload):
            if payload["type"] == "switch_vision/list_assets":
                return {"core_version": "2.8.16",
                        "faceplate_fingerprints": {
                            "old.png": {"sha256": old_sha},
                            "new.png": {"sha256": new_sha}},
                        "faceplate_revisions": revisions}
            if payload["type"] == "switch_vision/get_calibration":
                assert payload["profile"] == "native_SW3"
                assert payload["stock_faceplate"] == "new.png"
                return {"exists": True}
            if payload["type"] == "switch_vision/list_calibrations":
                return {"stock_artwork_choices": choices, "items": list(saved)}
            if payload["type"] == "switch_vision/approve_stock_artwork":
                calls.append(dict(payload))
                assert payload["base_profile"] == "native_SW3"
                assert payload["previous_filename"] == "new.png"
                assert payload["filename"] == "new.png"
                assert payload["expected_sha256"] == new_sha
                assert payload["approved_sha256"] == new_sha
                assert payload["reset_switch_calibration"] is True
                if fail_approval:
                    raise RuntimeError("Core approval failed")
                saved.clear()
                return {"ok": True, "sha256": new_sha, "calibration_reset": True}
            raise AssertionError(payload)

        hub.DEFAULT_REGISTRY_FILE = registry
        generated_card = root / "generated-card.yaml"
        generated_card.write_text("""views:
  - cards:
      - type: custom:switch-vision-3650
        discovery_selected_switch: SW3
        selected_switch: SW3
        member: SW3
        switch_model: WS-C3560CG-8PC-S
""")
        hub.DEFAULT_GENERATED_CARD = generated_card
        hub._home_assistant_ws = websocket
        hub._home_assistant_service = lambda *_: (_ for _ in ()).throw(
            AssertionError("Must use atomic Core approval"))
        hub._configured_devices_snapshot = lambda _options: inventory
        hub.faceplate_offers.DEFAULT_PATH = root / "preferences.json"
        try:
            snapshot = hub._faceplate_upgrade_snapshot(root / "options.json")
            assert snapshot["count"] == 1, snapshot
            offer = snapshot["offers"][0]
            assert offer["migration_kind"] == "legacy_saved_calibration"
            assert offer["legacy_calibration_file"] == "old.png"
            assert offer["current_file"] == offer["available_file"] == "new.png"
            assert offer["current_sha256"] == offer["available_sha256"] == new_sha
            request = {"action": "keep", "device_key": "snmp:SW3",
                       "base_profile": "native_SW3", "available_sha256": new_sha}
            assert hub._faceplate_upgrade_action(root, request)["action"] == "kept"
            assert not calls and saved and choices["custom_SW3"]["sha256"] == old_sha
            request["action"] = "upgrade"
            fail_approval = True
            try:
                hub._faceplate_upgrade_action(root, request)
            except RuntimeError as err:
                assert "Core approval failed" in str(err)
            else:
                raise AssertionError("Failed approval was accepted")
            assert hub._faceplate_upgrade_snapshot(root)["count"] == 1
            fail_approval = False
            assert hub._faceplate_upgrade_action(root, request)["action"] == "upgraded"
            assert len(calls) == 2 and saved == []
            assert hub._faceplate_upgrade_snapshot(root)["count"] == 0
            assert choices["custom_SW3"]["sha256"] == old_sha
        finally:
            hub.DEFAULT_REGISTRY_FILE = old_registry
            hub.DEFAULT_GENERATED_CARD = old_generated
            hub._home_assistant_ws = old_ws
            hub._home_assistant_service = old_service
            hub._configured_devices_snapshot = old_inventory
            hub.faceplate_offers.DEFAULT_PATH = old_preference
    print("FACEPLATE_UPGRADE_LEGACY_HUB_INTEGRATION_PASS")


def test_same_artwork_legacy_geometry_upgrade() -> None:
    """A saved 6000x1325 Cisco layout must offer the 6000x900 factory reset."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        old_registry = hub.DEFAULT_REGISTRY_FILE
        old_generated = hub.DEFAULT_GENERATED_CARD
        old_ws = hub._home_assistant_ws
        old_inventory = hub._configured_devices_snapshot
        old_preferences = hub.faceplate_offers.DEFAULT_PATH
        image_name = "48rj45-4sfp.png"
        image_sha, geometry_sha = "a" * 64, "b" * 64
        revision = {"filename": image_name, "sha256": image_sha,
                    "geometry_sha256": geometry_sha,
                    "version": "sha-" + "c" * 20,
                    "path": "faceplates/" + image_name}
        factory = {"profile": "stock_48rj45_4sfp",
                   "model": "stock-48rj45-4sfp",
                   "image": {"file": "faceplates/" + image_name,
                             "width": 6000, "height": 900}}
        saved = {
            "profile": "default_cisco_48_port",
            "model": "stock-48rj45-4sfp",
            "image": {"file": "faceplates/" + image_name,
                      "width": 6000, "height": 1325},
            "user_topology_authoritative": True,
        }
        before = dict(saved)
        choices = {"native_SW5": dict(revision)}
        items = [{"active": True, "scope": "native", "base_profile": "native_SW5",
                  "saved_calibration_image": image_name}]
        calls = []
        registry = root / "models.json"
        registry.write_text(json.dumps({"devices": [{
            "model": "WS-C3650-48PD-E", "dashboard_support": True,
            "default_faceplate": "faceplates/" + image_name,
            "optional_faceplates": [],
        }]}))
        generated = root / "generated.yaml"
        generated.write_text("""views:
  - cards:
      - type: custom:switch-vision-3650
        discovery_selected_switch: 3650-server
        selected_switch: SW5
        switch_model: WS-C3650-48PD-E
""")
        inventory = {"devices": [{
            "device_key": "snmp:device", "switch_name": "3650-server",
            "switch_model": "WS-C3650-48PD-E",
        }]}
        def websocket(payload):
            action = payload["type"]
            if action == "switch_vision/list_assets":
                return {"core_version": "2.8.30",
                        "faceplate_fingerprints": {image_name: {"sha256": image_sha}},
                        "faceplate_revisions": {image_name: [revision]}}
            if action == "switch_vision/get_calibration":
                assert payload["profile"] == "native_SW5"
                return {"exists": True, "invalid": False,
                        "profile": "native_SW5", "calibration": saved,
                        "stock_artwork": {**revision, "geometry": factory}}
            if action == "switch_vision/list_calibrations":
                return {"stock_artwork_choices": choices, "items": items}
            if action == "switch_vision/approve_stock_artwork":
                calls.append(dict(payload))
                assert payload["base_profile"] == "native_SW5"
                assert payload["filename"] == payload["previous_filename"] == image_name
                assert payload["expected_sha256"] == payload["approved_sha256"] == image_sha
                assert payload["reset_switch_calibration"] is True
                saved.update(factory)
                saved["user_topology_authoritative"] = False
                return {"ok": True, "sha256": image_sha, "calibration_reset": True}
            raise AssertionError(payload)

        hub.DEFAULT_REGISTRY_FILE = registry
        hub.DEFAULT_GENERATED_CARD = generated
        hub._home_assistant_ws = websocket
        hub._configured_devices_snapshot = lambda _: inventory
        hub.faceplate_offers.DEFAULT_PATH = root / "collapsed.json"
        try:
            snapshot = hub._faceplate_upgrade_snapshot(root / "options.json")
            assert snapshot["count"] == 1, snapshot
            offer = snapshot["offers"][0]
            assert offer["migration_kind"] == "legacy_saved_geometry"
            assert offer["base_profile"] == "native_SW5"
            assert offer["saved_geometry_height"] == 1325
            assert offer["latest_geometry_height"] == 900
            body = {"device_key": "snmp:device", "base_profile": "native_SW5",
                    "available_sha256": image_sha}
            export = hub._faceplate_upgrade_action(root, {**body, "action": "export"})
            assert export["geometry"] == before
            assert not calls
            keep = hub._faceplate_upgrade_action(root, {**body, "action": "keep"})
            assert keep["action"] == "kept"
            assert hub._faceplate_upgrade_snapshot(root)["offers"][0]["collapsed"] is True
            assert saved == before and not calls
            upgraded = hub._faceplate_upgrade_action(root, {**body, "action": "upgrade"})
            assert upgraded["action"] == "upgraded" and upgraded["calibration_reset"]
            assert len(calls) == 1
            assert hub._faceplate_upgrade_snapshot(root)["count"] == 0
        finally:
            hub.DEFAULT_REGISTRY_FILE = old_registry
            hub.DEFAULT_GENERATED_CARD = old_generated
            hub._home_assistant_ws = old_ws
            hub._configured_devices_snapshot = old_inventory
            hub.faceplate_offers.DEFAULT_PATH = old_preferences
    print("FACEPLATE_SAME_ARTWORK_LEGACY_GEOMETRY_HUB_PASS")


if __name__ == "__main__":
    test()
    test_legacy_saved_calibration_upgrade()
    test_same_artwork_legacy_geometry_upgrade()
