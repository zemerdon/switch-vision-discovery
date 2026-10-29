#!/usr/bin/env python3
"""Device Overview faceplate picker: generic -> dedicated, post-dismissal,
per-switch atomic visual reset, stale/tampered input and version selection."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import support_web as hub


def test() -> None:
    with TemporaryDirectory() as td:
        base = Path(td)
        old_file, new_file = "generic.png", "model-specific.png"
        old_sha, dedicated_sha = "a" * 64, "b" * 64
        old_geo, dedicated_geo = "c" * 64, "d" * 64
        old_ver, dedicated_ver = "sha-" + "1" * 20, "sha-" + "2" * 20
        catalog = {
            old_file: [{"filename": old_file, "sha256": old_sha,
                        "geometry_sha256": old_geo, "version": old_ver,
                        "path": "faceplates/" + old_file}],
            new_file: [{"filename": new_file, "sha256": dedicated_sha,
                        "geometry_sha256": dedicated_geo, "version": dedicated_ver,
                        "path": "faceplates/" + new_file}],
        }
        selected = {"native_SW3": {
            "filename": old_file, "sha256": old_sha, "version": old_ver,
            "geometry_sha256": old_geo, "path": "faceplates/" + old_file,
        }}
        calls: list[dict] = []
        reset_count = 0
        registry = base / "registry.json"
        registry.write_text(json.dumps({"devices": [
            {"model": "SG200-26", "dashboard_support": True,
             "default_faceplate": "faceplates/" + new_file},
            {"model": "OTHER", "dashboard_support": True,
             "default_faceplate": "faceplates/unrelated.png"},
        ]}))
        inventory = {"devices": [
            {"device_key": "snmp:SW3", "switch_name": "SW3",
             "switch_model": "SG200-26", "display_name": "Rack Switch"},
            {"device_key": "snmp:SW4", "switch_name": "SW4",
             "switch_model": "OTHER", "display_name": "Other Switch"},
        ]}
        def websocket(message: dict) -> dict:
            nonlocal reset_count
            kind = message["type"]
            if kind == "switch_vision/list_assets":
                return {"core_version": "2.7.96",
                        "faceplate_fingerprints": {
                            old_file: {"sha256": old_sha},
                            new_file: {"sha256": dedicated_sha},
                        }, "faceplate_revisions": catalog}
            if kind == "switch_vision/get_calibration":
                return {"exists": False}
            if kind == "switch_vision/list_calibrations":
                return {"stock_artwork_choices": selected, "items": []}
            if kind == "switch_vision/approve_stock_artwork":
                calls.append(dict(message))
                assert message["base_profile"] == "native_SW3"
                assert message["reset_switch_calibration"] is True
                assert message["expected_sha256"] == selected["native_SW3"]["sha256"]
                assert message["previous_filename"] == selected["native_SW3"]["filename"]
                choice = next(item for values in catalog.values() for item in values
                              if item["filename"] == message["filename"]
                              and item["sha256"] == message["approved_sha256"]
                              and item["version"] == message["approved_version"])
                selected["native_SW3"] = {
                    **choice, "eligible_faceplates": [old_file, new_file],
                }
                reset_count += 1
                return {"ok": True, "sha256": choice["sha256"],
                        "calibration_reset": True}
            raise AssertionError(message)

        previous = (hub.DEFAULT_REGISTRY_FILE, hub.DEFAULT_GENERATED_CARD,
                    hub._home_assistant_ws, hub._configured_devices_snapshot,
                    hub.faceplate_offers.DEFAULT_PATH)
        try:
            hub.DEFAULT_REGISTRY_FILE = registry
            hub.DEFAULT_GENERATED_CARD = base / "generated.yaml"
            hub.DEFAULT_GENERATED_CARD.write_text("""views:
  - cards:
      - type: custom:switch-vision-3650
        discovery_selected_switch: SW3
        selected_switch: SW3
        member: SW3
        switch_model: SG200-26
      - type: custom:switch-vision-3650
        discovery_selected_switch: SW4
        selected_switch: SW4
        member: SW4
        switch_model: OTHER
""")
            hub._home_assistant_ws = websocket
            hub._configured_devices_snapshot = lambda _: inventory
            hub.faceplate_offers.DEFAULT_PATH = base / "offer-preferences.json"
            snapshot = hub._faceplate_upgrade_snapshot(base / "options.json")
            assert snapshot["count"] == 1
            assert len(snapshot["selections"]) == 2
            assert len(snapshot["selections"][0]["options"]) == 2
            assert snapshot["selections"][0]["verified_current"] is True
            assert snapshot["selections"][0]["current_file"] == old_file
            # Every registered device remains visible even when Core cannot
            # verify an old stock selection; no reset button is exposed.
            missing = snapshot["selections"][1]
            assert missing["device_key"] == "snmp:SW4"
            assert missing["verified_current"] is False
            assert missing["options"] == []
            proposal = snapshot["offers"][0]
            # Dismissing the automatic offer never hides the device picker.
            keep = {"action": "keep", "device_key": "snmp:SW3",
                    "base_profile": "native_SW3", "available_sha256": dedicated_sha}
            assert hub._faceplate_upgrade_action(base, keep)["action"] == "kept"
            snapshot = hub._faceplate_upgrade_snapshot(base)
            assert snapshot["offers"][0]["collapsed"] is True
            assert len(snapshot["selections"]) == 2
            assert reset_count == 0
            pick = {
                "action": "pick", "device_key": "snmp:SW3",
                "base_profile": "native_SW3", "available_sha256": old_sha,
                "expected_filename": old_file, "expected_version": old_ver,
                "selected_filename": new_file, "selected_sha256": dedicated_sha,
                "selected_version": dedicated_ver,
            }
            for changed in [
                {**pick, "selected_sha256": "f" * 64},
                {**pick, "selected_filename": "unrelated.png"},
                {**pick, "expected_filename": new_file},
                {**pick, "expected_version": "sha-stale"},
            ]:
                try: hub._faceplate_upgrade_action(base, changed)
                except ValueError: pass
                else: raise AssertionError("Unverified or stale selection accepted")
            assert calls == []
            reply = hub._faceplate_upgrade_action(base, pick)
            assert reply["action"] == "selected" and reply["calibration_reset"] is True
            assert reset_count == 1
            assert selected["native_SW3"]["filename"] == new_file
            assert not hub._faceplate_upgrade_snapshot(base)["selections"][0]["current_file"] == old_file
            assert {item["filename"] for item in
                    hub._faceplate_upgrade_snapshot(base)["selections"][0]["options"]} == {old_file, new_file}
            # A stale second click may never reset again.
            try: hub._faceplate_upgrade_action(base, pick)
            except ValueError: pass
            else: raise AssertionError("Stale second adoption was accepted")
            assert reset_count == 1
            # One verified current faceplate is useful information and must
            # not disappear merely because no upgrade choices exist.
            one = hub.faceplate_offers.selectable_for_devices(
                [{"device_key": "snmp:SW3", "switch_name": "SW3",
                  "display_name": "Rack Switch", "resolved_model": "SG200-26"}],
                {"SG200-26": old_file}, {old_file: old_sha},
                {"native_SW3": {"filename": old_file, "sha256": old_sha,
                                "path": "faceplates/" + old_file}},
                {old_file: catalog[old_file]},
            )
            assert len(one) == 1
            assert one[0]["verified_current"] is True
            assert one[0]["current_file"] == old_file
            assert len(one[0]["options"]) == 1
            # An unrecognised model with an already verified Core artwork pin
            # still reports its current selection without inventing an offer.
            unresolved_model = hub.faceplate_offers.selectable_for_devices(
                [{"device_key": "snmp:SW3", "switch_name": "SW3",
                  "display_name": "Rack Switch", "resolved_model": ""}],
                {}, {old_file: old_sha},
                {"native_SW3": {"filename": old_file, "sha256": old_sha,
                                "path": "faceplates/" + old_file}},
                {old_file: catalog[old_file]},
            )
            assert len(unresolved_model) == 1
            assert unresolved_model[0]["verified_current"] is True
            assert len(unresolved_model[0]["options"]) == 1
            # An older Core pin with verified artwork but no revision version
            # must still be shown without offering an unsafe selection.
            without_catalog = hub.faceplate_offers.selectable_for_devices(
                [{"device_key": "snmp:SW3", "switch_name": "SW3",
                  "display_name": "Rack Switch", "resolved_model": "SG200-26"}],
                {"SG200-26": old_file}, {old_file: old_sha},
                {"native_SW3": {"filename": old_file, "sha256": old_sha,
                                "path": "faceplates/" + old_file}},
                {},
            )
            assert len(without_catalog) == 1
            assert without_catalog[0]["verified_current"] is True
            assert without_catalog[0]["options"] == []
        finally:
            (hub.DEFAULT_REGISTRY_FILE, hub.DEFAULT_GENERATED_CARD,
             hub._home_assistant_ws, hub._configured_devices_snapshot,
             hub.faceplate_offers.DEFAULT_PATH) = previous
    print("FACEPLATE_DEVICE_PICKER_PASS")


if __name__ == "__main__":
    test()
