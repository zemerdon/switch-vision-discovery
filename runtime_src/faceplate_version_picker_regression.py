#!/usr/bin/env python3
"""End-to-end Hub version selection, including unchanged PNG with new geometry."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import support_web as hub


def test() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        originals = (
            hub.DEFAULT_REGISTRY_FILE, hub.DEFAULT_GENERATED_CARD,
            hub._home_assistant_ws, hub._configured_devices_snapshot,
            hub.faceplate_offers.DEFAULT_PATH,
        )
        name = "switch.png"
        image_sha = "a" * 64
        old_geometry = "b" * 64
        new_geometry = "c" * 64
        versions = [
            {"filename": name, "version": "2.7.92", "sha256": image_sha,
             "geometry_sha256": old_geometry, "path": "faceplates-old/2.7.92/" + name},
            {"filename": name, "version": "2.7.93", "sha256": image_sha,
             "geometry_sha256": new_geometry, "path": "faceplates/" + name},
        ]
        choices = {"native_SW3": {
            "filename": name, "sha256": image_sha, "version": "2.7.92",
            "path": "faceplates-old/2.7.92/" + name,
            "geometry_sha256": old_geometry,
        }}
        calls = []
        user_calibration = {"ports": {"1": {"center": [13, 27]}}}
        saved = json.dumps(user_calibration, sort_keys=True)
        registry = root / "registry.json"
        registry.write_text(json.dumps({"devices": [{
            "model": "TL-SG2008P", "dashboard_support": True,
            "default_faceplate": "faceplates/" + name,
        }]}))

        def websocket(message):
            action = message["type"]
            if action == "switch_vision/list_assets":
                return {"core_version": "2.7.93",
                        "faceplate_fingerprints": {name: {"sha256": image_sha}},
                        "faceplate_revisions": {name: versions}}
            if action == "switch_vision/get_calibration":
                return {"exists": False}
            if action == "switch_vision/list_calibrations":
                return {"stock_artwork_choices": choices, "items": [user_calibration]}
            if action == "switch_vision/approve_stock_artwork":
                calls.append(message.copy())
                assert message["expected_version"] == choices["native_SW3"]["version"]
                chosen = next(row for row in versions
                              if row["sha256"] == message["approved_sha256"]
                              and row["version"] == message["approved_version"])
                choices["native_SW3"] = dict(chosen)
                return {"ok": True, "sha256": chosen["sha256"]}
            raise AssertionError(message)

        try:
            hub.DEFAULT_REGISTRY_FILE = registry
            hub.DEFAULT_GENERATED_CARD = root / "no-generated.yaml"
            hub._home_assistant_ws = websocket
            hub._configured_devices_snapshot = lambda _: {
                "devices": [{"device_key": "snmp:SW3", "switch_name": "SW3",
                             "switch_model": "TL-SG2008P", "display_name": "Switch 3"}]}
            hub.faceplate_offers.DEFAULT_PATH = root / "choice.json"
            before = hub._faceplate_upgrade_snapshot(root / "options.json")
            assert before["count"] == 1
            offer = before["offers"][0]
            assert not offer["collapsed"] and len(offer["versions"]) == 2
            request = {"action": "select", "device_key": "snmp:SW3",
                       "base_profile": "native_SW3", "available_sha256": image_sha,
                       "selected_sha256": image_sha, "selected_version": "2.7.93"}
            invalid = {**request, "selected_version": "2.7.99"}
            try:
                hub._faceplate_upgrade_action(root, invalid)
            except ValueError:
                pass
            else:
                raise AssertionError("Fabricated Core revision was accepted")
            assert calls == []
            assert hub._faceplate_upgrade_action(root, request)["action"] == "selected"
            assert choices["native_SW3"]["version"] == "2.7.93"
            assert hub._faceplate_upgrade_snapshot(root)["offers"][0]["collapsed"]
            assert json.dumps(user_calibration, sort_keys=True) == saved
            assert len(calls) == 1
        finally:
            (hub.DEFAULT_REGISTRY_FILE, hub.DEFAULT_GENERATED_CARD,
             hub._home_assistant_ws, hub._configured_devices_snapshot,
             hub.faceplate_offers.DEFAULT_PATH) = originals
    print("FACEPLATE_VERSION_PICKER_PASS")


if __name__ == "__main__":
    test()
