#!/usr/bin/env python3
"""Offline tests for Hub detection after Home Assistant Core restart."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import faceplate_upgrade_offers as f


def test():
    old_hash, new_hash = "a" * 64, "b" * 64
    inventory = [{"device_key": "snmp:SW3", "switch_name": "SW3",
                  "display_name": "PoE switch", "resolved_model": "TL-SG2008P"}]
    recommended = {"TL-SG2008P": "new.png"}
    images = {"old.png": old_hash, "new.png": new_hash}
    saved = [{"base_profile": "native_SW3", "active": True, "model": "stock",
              "faceplate": "default", "faceplate_source": "default",
              "saved_calibration_image": "old.png"}]

    offers = f.offers_from_saved(inventory, recommended, images, saved)
    assert len(offers) == 1 and offers[0]["current_file"] == "old.png"
    assert offers[0]["base_profile"] == "native_SW3"
    assert offers[0]["collapsed"] is False
    # Two legitimate switches can be offered independently and matched by model.
    second_device = {"device_key": "snmp:SW4", "switch_name": "SW4",
                     "resolved_model": "Model B"}
    second_profile = {**saved[0], "base_profile": "native_SW4",
                      "saved_calibration_image": "old-b.png"}
    both = f.offers_from_saved(
        inventory + [second_device], {**recommended, "Model B": "new-b.png"},
        {**images, "old-b.png": "c" * 64, "new-b.png": "d" * 64},
        saved + [second_profile])
    assert {entry["device_key"] for entry in both} == {"snmp:SW3", "snmp:SW4"}
    assert next(entry for entry in both if entry["device_key"] == "snmp:SW4")["model"] == "Model B"

    with TemporaryDirectory() as directory:
        state = Path(directory) / "offers.json"
        f.keep_current("snmp:SW3", new_hash, state)
        assert f.load(state) == {"snmp:SW3": new_hash}
        offers = f.offers_from_saved(inventory, recommended, images, saved, f.load(state))
        assert offers[0]["collapsed"] is True
        # A future different offered SHA must reopen the comparison.
        offers = f.offers_from_saved(inventory, recommended,
                                     {"old.png": old_hash, "new.png": "c" * 64},
                                     saved, f.load(state))
        assert offers[0]["collapsed"] is False

    # Existing per-switch reset clears that saved profile => offer disappears.
    assert f.offers_from_saved(inventory, recommended, images, []) == []
    # Ambiguous native/custom scopes => no unsafe one-click reset.
    assert f.offers_from_saved(inventory, recommended, images,
                              saved + [{**saved[0], "base_profile": "custom_SW3"}]) == []
    # The same model on a different switch cannot borrow SW3's saved profile.
    sw4 = [{**inventory[0], "device_key": "snmp:SW4", "switch_name": "SW4"}]
    assert f.offers_from_saved(sw4, recommended, images, saved) == []
    # No real old image => never show a false before/after visual.
    assert f.offers_from_saved(inventory, recommended, {"new.png": new_hash}, saved) == []
    # Same-name stock edits must compare actual old/new bytes, not filenames.
    same = [{**saved[0], "saved_calibration_image": "new.png",
             "saved_stock_sha256": old_hash,
             "saved_stock_preview": f"faceplate-history/{old_hash}/new.png"}]
    same_offers = f.offers_from_saved(inventory, recommended,
                                      {"new.png": new_hash}, same)
    assert len(same_offers) == 1 and same_offers[0]["same_filename"] is True
    assert same_offers[0]["current_preview"] == f"faceplate-history/{old_hash}/new.png"
    assert same_offers[0]["current_sha256"] == old_hash
    # A legacy saved profile may reference the Installer's first stock image.
    legacy = [{**same[0], "saved_stock_preview": "faceplate-history/legacy/new.png"}]
    assert len(f.offers_from_saved(inventory, recommended,
                                  {"new.png": new_hash}, legacy)) == 1
    # Unknown, identical or forged old pixels must never trigger a reset.
    for broken in (
        {**same[0], "saved_stock_sha256": new_hash},
        {**same[0], "saved_stock_sha256": ""},
        {**same[0], "saved_stock_preview": "new.png"},
        {**same[0], "saved_stock_preview": "../secret.png"},
        {**same[0], "saved_stock_preview": f"faceplate-history/{new_hash}/new.png"},
    ):
        assert f.offers_from_saved(inventory, recommended,
                                   {"new.png": new_hash}, [broken]) == []
    # Changed content with no retained proof still fails closed.
    assert f.offers_from_saved(inventory, {"TL-SG2008P": "old.png"},
                               {"old.png": new_hash}, saved) == []
    # Existing per-user custom stock selection remains a real offer until reset.
    custom = [{**saved[0], "faceplate": "old.png", "faceplate_source": "custom"}]
    assert len(f.offers_from_saved(inventory, recommended, images, custom)) == 1
    assert f.filename("../../secret.png") == ""
    assert f.installed_assets({"faceplate_fingerprints": {
        "new.png": {"sha256": new_hash}, "../bad.png": {"sha256": old_hash}
    }}) == {"new.png": new_hash}
    assert f.registry_defaults({"devices": [{"model": "TL-SG2008P",
        "dashboard_support": True, "default_faceplate": "faceplates/new.png"}]}) == recommended

    doc = {"views": [{"cards": [{"type": "custom:switch-vision-3650",
        "discovery_selected_switch": "SW3", "switch_model": "TL-SG2008P"}]}]}
    assert f.generated_exact_models(doc, set(recommended)) == {"SW3": "TL-SG2008P"}
    doc["views"][0]["cards"].append({"type": "custom:switch-vision-3650",
        "discovery_selected_switch": "SW3", "switch_model": "Different model"})
    assert f.generated_exact_models(doc, {"TL-SG2008P", "Different model"}) == {}
    # Per-switch installed artwork selection is independent of whether
    # Calibration was ever saved. Same-name updates require real old bytes.
    pins = {"native_SW3": {
        "filename": "new.png", "sha256": old_hash,
        "path": f"faceplate-history/{old_hash}/new.png",
    }}
    stock_offers = f.offers_from_choices(inventory, recommended,
                                        {"new.png": new_hash}, pins)
    assert len(stock_offers) == 1
    assert stock_offers[0]["same_filename"] is True
    assert stock_offers[0]["current_preview"] == f"faceplate-history/{old_hash}/new.png"
    assert stock_offers[0]["base_profile"] == "native_SW3"
    assert f.offers_from_choices(inventory, recommended,
                                 {"new.png": new_hash}, {}) == []
    assert f.offers_from_choices(inventory, recommended,
                                 {"new.png": new_hash}, {"native_SW3": {
                                     "filename": "new.png", "sha256": old_hash,
                                     "unavailable": "true"}}) != []
    pins["native_SW3"] = {
        "filename": "new.png", "sha256": new_hash, "path": "faceplates/new.png",
    }
    assert f.offers_from_choices(inventory, recommended, {"new.png": new_hash}, pins) == []
    # Custom artwork is independently selectable manually, but does not
    # generate an automatic Hub upgrade even when it remains out of date.
    pins["custom_SW3"] = {
        "filename": "new.png", "sha256": old_hash,
        "path": f"faceplate-history/{old_hash}/new.png",
    }
    assert f.offers_from_choices(inventory, recommended,
                                 {"new.png": new_hash}, pins) == []
    # Regression: a Custom dashboard already using the latest stock artwork
    # must not mask an older Native dashboard's genuine pending upgrade.
    revisions = {"new.png": [
        {"filename": "new.png", "sha256": new_hash, "geometry_sha256": "e" * 64,
         "version": "sha-" + "e" * 20, "path": "faceplates/new.png"},
        {"filename": "new.png", "sha256": old_hash, "geometry_sha256": "f" * 64,
         "version": "sha-" + "f" * 20,
         "path": f"faceplate-history/revisions/sha/{old_hash}/new.png"},
    ]}
    split_pins = {
        "custom_SW3": {"filename": "new.png", "sha256": new_hash,
                       "geometry_sha256": "e" * 64, "version": "sha-" + "e" * 20,
                       "path": "faceplates/new.png"},
        "native_SW3": {"filename": "new.png", "sha256": old_hash,
                       "geometry_sha256": "f" * 64, "version": "sha-" + "f" * 20,
                       "path": f"faceplate-history/revisions/sha/{old_hash}/new.png"},
    }
    pending = f.offers_from_choices(
        inventory, recommended, {"new.png": new_hash}, split_pins,
        revisions=revisions)
    assert len(pending) == 1 and pending[0]["base_profile"] == "native_SW3"
    # Hub offers only Native when both scopes are outdated. Once Native is
    # approved, it must never follow up with an automatic Custom offer.
    old_pin = {"filename": "new.png", "sha256": old_hash,
               "geometry_sha256": "f" * 64, "version": "sha-" + "f" * 20,
               "path": f"faceplate-history/revisions/sha/{old_hash}/new.png"}
    both_due = {"custom_SW3": dict(old_pin), "native_SW3": dict(old_pin)}
    first = f.offers_from_choices(inventory, recommended,
                                  {"new.png": new_hash}, both_due,
                                  revisions=revisions)
    assert len(first) == 1 and first[0]["base_profile"] == "native_SW3"
    both_due["native_SW3"] = dict(split_pins["custom_SW3"])
    next_due = f.offers_from_choices(inventory, recommended,
                                     {"new.png": new_hash}, both_due,
                                     revisions=revisions)
    assert next_due == []
    assert both_due["custom_SW3"]["sha256"] == old_hash
    custom_only = {"custom_SW3": dict(old_pin)}
    assert f.offers_from_choices(inventory, recommended,
                                 {"new.png": new_hash}, custom_only,
                                 revisions=revisions) == []
    # When both scopes already use the latest image/geometry there is no offer,
    # even though older verified revisions remain available in the picker.
    split_pins["native_SW3"] = dict(split_pins["custom_SW3"])
    assert f.offers_from_choices(inventory, recommended, {"new.png": new_hash},
                                 split_pins, revisions=revisions) == []
    # Rename a recommended filename without erasing an existing older choice.
    renamed = f.offers_from_choices(inventory, recommended,
                                   {"new.png": new_hash}, {"native_SW3": {
                                       "filename": "old.png", "sha256": old_hash,
                                       "path": f"faceplate-history/{old_hash}/old.png"}})
    assert len(renamed) == 1 and renamed[0]["same_filename"] is False
    # The main adoption path: a shared stock PNG gets a dedicated model
    # filename and factory geometry. It remains an offer even if artwork
    # pixels happen to match, or the earlier pin predates revision versions.
    identical_art = f.offers_from_choices(
        inventory, recommended, {"new.png": old_hash},
        {"native_SW3": {"filename": "old.png", "sha256": old_hash,
                        "path": "faceplates/old.png"}},
        revisions={"new.png": [{
            "filename": "new.png", "version": "sha-" + "c" * 20,
            "sha256": old_hash, "geometry_sha256": "d" * 64,
            "path": "faceplates/new.png",
        }]},
    )
    assert len(identical_art) == 1
    assert identical_art[0]["collapsed"] is False
    assert identical_art[0]["same_filename"] is False
    assert identical_art[0]["available_geometry_sha256"] == "d" * 64
    # Existing generic artwork must remain selectable for that switch; other
    # switches using the same generic stock have no offer unless their own
    # exact model mapping changes.
    assert f.offers_from_choices(
        inventory, {"TL-SG2008P": "old.png"},
        {"old.png": old_hash, "new.png": old_hash},
        {"native_SW3": {"filename": "old.png", "sha256": old_hash,
                        "path": "faceplates/old.png"}},
    ) == []
    versions = [{"filename":"new.png","version":"2.7.92","sha256":new_hash,"geometry_sha256":old_hash,"path":"faceplates-old/2.7.92/new.png"},{"filename":"new.png","version":"2.7.93","sha256":new_hash,"geometry_sha256":new_hash,"path":"faceplates/new.png"}]
    selected = {"native_SW3":{"filename":"new.png","sha256":new_hash,"version":"2.7.92","path":"faceplates-old/2.7.92/new.png"}}
    offer = f.offers_from_choices(inventory, recommended, {"new.png":new_hash}, selected, revisions={"new.png":versions})
    assert len(offer) == 1 and not offer[0]["collapsed"] and len(offer[0]["versions"]) == 2
    print("FACEPLATE_UPGRADE_OFFERS_PASS")


if __name__ == "__main__":
    test()
