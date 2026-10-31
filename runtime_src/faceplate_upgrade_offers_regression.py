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

    # The generated Native switch key, not Hub's internal device name, owns
    # the Calibration that Reset Current Switch would replace.
    mapped_doc = {"views": [{"cards": [{"type": "custom:switch-vision-3650",
        "discovery_selected_switch": "3650-server", "selected_switch": "SW1",
        "member": "SW1", "switch_model": "TL-SG2008P"}]}]}
    mapping = f.generated_native_targets(mapped_doc, set(recommended))
    assert mapping == {"3650-server": [{
        "native_switch_key": "SW1", "model": "TL-SG2008P"}]}
    mapped = [{**inventory[0], "switch_name": "3650-server",
               "native_switch_key": "SW1"}]
    mapped_pins = {
        "native_SW1": {"filename": "new.png", "sha256": old_hash,
                       "path": f"faceplate-history/{old_hash}/new.png"},
        "native_3650-server": {"filename": "new.png", "sha256": old_hash,
                       "path": f"faceplate-history/{old_hash}/new.png"},
    }
    mapped_offers = f.offers_from_choices(mapped, recommended,
                                           {"new.png": new_hash}, mapped_pins)
    assert len(mapped_offers) == 1
    assert mapped_offers[0]["base_profile"] == "native_SW1"
    assert f.offers_from_choices(mapped, recommended, {"new.png": new_hash},
                                 {"native_3650-server": mapped_pins["native_3650-server"]}) == []
    mapped_doc["views"][0]["cards"].append({
        "type": "custom:switch-vision-3650",
        "discovery_selected_switch": "different-device",
        "selected_switch": "SW1", "switch_model": "TL-SG2008P"})
    assert f.generated_native_targets(mapped_doc, set(recommended)) == {}

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

    # Cisco 3560CG: Core's first post-upgrade read already pinned Compact,
    # but one active Native Calibration still contains the old model artwork.
    cisco = "WS-C3560CG-8PC-S"
    compact = "c3560cg-8pc-s-compact.png"
    generic = "c3560cg-8pc-s.png"
    registered = {"devices": [{
        "model": cisco, "dashboard_support": True,
        "default_faceplate": "faceplates/" + compact,
        "optional_faceplates": ["faceplates/" + generic],
    }]}
    legacy = f.eligible_legacy_faceplates(registered)
    assert legacy == {cisco: {generic}}
    switch = [{"device_key": "snmp:cisco3560", "switch_name": "cisco3560",
               "resolved_model": cisco}]
    image_shas = {compact: new_hash, generic: old_hash}
    complete = {
        name: [{"filename": name, "sha256": digest,
                "geometry_sha256": ("e" if name == compact else "f") * 64,
                "version": "sha-" + ("e" if name == compact else "f") * 20,
                "path": "faceplates/" + name}]
        for name, digest in image_shas.items()
    }
    current = {"native_cisco3560": {
        **complete[compact][0],
    }}
    active_legacy = [{
        "active": True, "base_profile": "native_cisco3560",
        "scope": "native", "saved_calibration_image": generic,
    }]
    def migration(**overrides):
        args = dict(inventory=switch, defaults={cisco: compact},
                    assets=image_shas, choices=current,
                    profiles=active_legacy, revisions=complete,
                    eligible=legacy)
        args.update(overrides)
        return f.legacy_calibration_offers(**args)
    repaired = migration()
    assert len(repaired) == 1
    assert repaired[0]["migration_kind"] == "legacy_saved_calibration"
    assert repaired[0]["legacy_calibration_file"] == generic
    assert repaired[0]["legacy_calibration_sha256"] == old_hash
    assert repaired[0]["current_file"] == repaired[0]["available_file"] == compact
    assert repaired[0]["current_sha256"] == repaired[0]["available_sha256"] == new_hash
    assert repaired[0]["versions"] == []
    assert migration(collapsed={"snmp:cisco3560@native_cisco3560": "e" * 64})[0]["collapsed"]
    assert not repaired[0]["collapsed"]
    # Only exact, currently verified stock image/geometry pairs are eligible.
    assert migration(profiles=[]) == []
    assert migration(profiles=[{**active_legacy[0],
                                "saved_calibration_image": compact}]) == []
    assert migration(profiles=[{**active_legacy[0],
                                "scope": "custom"}]) == []
    assert migration(profiles=[{**active_legacy[0],
                                "base_profile": "custom_cisco3560"}]) == []
    assert migration(profiles=active_legacy * 2) == []
    assert migration(eligible={cisco: set()}) == []
    assert migration(revisions={compact: complete[compact]}) == []
    assert migration(revisions={**complete, generic: [{**complete[generic][0],
                              "geometry_sha256": ""}]}) == []
    assert migration(choices={"native_cisco3560": {**current["native_cisco3560"],
                               "unavailable": True}}) == []
    assert migration(choices={"native_cisco3560": {**current["native_cisco3560"],
                               "sha256": old_hash}}) == []
    assert migration(existing_offers=[{"device_key": "snmp:cisco3560",
                                        "base_profile": "native_cisco3560"}]) == []
    assert migration(inventory=[{"device_key": "snmp:other",
                                 "switch_name": "other", "resolved_model": cisco}]) == []
    assert current["native_cisco3560"]["sha256"] == new_hash
    assert active_legacy[0]["saved_calibration_image"] == generic
    print("FACEPLATE_UPGRADE_OFFERS_PASS")


def test_verified_legacy_geometry_upgrade() -> None:
    """Three old 6000x1325 Native layouts, two current 2960s untouched."""
    sha = "a" * 64
    geo = "b" * 64
    stock = "48rj45-4sfp.png"
    factory = {
        "model": "stock-48rj45-4sfp",
        "profile": "stock_48rj45_4sfp",
        "image": {"file": "faceplates/" + stock, "width": 6000, "height": 900},
        "ports": {
            "1": {"center": [558.147321429, 422.879464286]},
            "2": {"center": [558.171428571, 662.914285714]},
            "47": {"center": [4706.785714286, 422.879464286]},
            "48": {"center": [4714.821428571, 662.946428571]},
        },
    }
    latest = {"filename": stock, "sha256": sha, "geometry_sha256": geo,
              "version": "sha-" + "c" * 20, "path": "faceplates/" + stock}
    rows = [
        {"device_key": "snmp:" + name, "switch_name": name,
         "native_switch_key": name, "resolved_model": model}
        for name, model in (
            ("SW5", "WS-C3650-48PD-E"),
            ("SW6", "WS-C3650-48PD-L"),
            ("SW7", "WS-C2960X-48FPD-L"),
            ("SW9", "WS-C2960S-48FPD-L"),
            ("SW10", "EX3300-48P"),
        )
    ]
    defaults = {
        "WS-C3650-48PD-E": stock, "WS-C3650-48PD-L": stock,
        "EX3300-48P": stock,
        "WS-C2960X-48FPD-L": "48rj45-2sfp-compact.png",
        "WS-C2960S-48FPD-L": "48rj45-2sfp-compact.png",
    }
    profiles = [
        {"base_profile": "native_" + name, "scope": "native",
         "active": True, "saved_calibration_image": stock}
        for name in ("SW5", "SW6", "SW10")
    ]
    choices = {"native_" + name: dict(latest) for name in ("SW5", "SW6", "SW10")}
    saved = {"native_" + name: {
        "exists": True, "invalid": False, "profile": "native_" + name,
        "stock_artwork": {**latest, "geometry": factory},
        "calibration": {
            "profile": "default_cisco_48_port",
            "model": "stock-48rj45-4sfp", "user_topology_authoritative": True,
            "image": {"file": "faceplates/" + stock, "width": 6000, "height": 1325},
            "ports": {
                "1": {"center": [515.625, 724.0234375]},
                "2": {"center": [518.5546875, 996.484375]},
                "47": {"center": [4669.921875, 724.0234375]},
                "48": {"center": [4675.78125, 993.5546875]},
            },
        },
    } for name in ("SW5", "SW6", "SW10")}
    params = dict(inventory=rows, defaults=defaults,
                  assets={stock: sha}, choices=choices, profiles=profiles,
                  revisions={stock: [latest]}, saved_by_base=saved)
    offers = f.legacy_same_artwork_geometry_offers(**params)
    assert {x["switch_name"] for x in offers} == {"SW5", "SW6", "SW10"}
    assert all(x["migration_kind"] == "legacy_saved_geometry" for x in offers)
    assert all(x["saved_geometry_height"] == 1325 and
               x["latest_geometry_height"] == 900 and
               x["same_filename"] for x in offers)
    assert not any(x["switch_name"] in {"SW7", "SW9"} for x in offers)
    assert f.legacy_same_artwork_geometry_offers(
        **{**params, "collapsed": {"snmp:SW5@native_SW5": geo}})[0]["collapsed"]
    assert len(f.legacy_same_artwork_geometry_offers(
        **{**params, "existing_offers": [{"device_key": "snmp:SW5",
                                         "base_profile": "native_SW5"}]})) == 2

    for field, value in (
        ("profile", "user_saved_profile"),
        ("model", "unknown"),
        ("ports", dict(factory["ports"])),
    ):
        modified = {**saved["native_SW5"]["calibration"], field: value}
        broken = {**saved, "native_SW5": {
            **saved["native_SW5"], "calibration": modified}}
        assert {x["switch_name"] for x in f.legacy_same_artwork_geometry_offers(
            **{**params, "saved_by_base": broken})} == {"SW6", "SW10"}
    for broken in (
        {**saved["native_SW5"], "invalid": True},
        {**saved["native_SW5"], "profile": "native_OTHER"},
        {**saved["native_SW5"], "stock_artwork": {
            **saved["native_SW5"]["stock_artwork"], "geometry_sha256": "f" * 64}},
        {**saved["native_SW5"], "stock_artwork": {
            **saved["native_SW5"]["stock_artwork"], "geometry": None}},
    ):
        changed = {**saved, "native_SW5": broken}
        assert len(f.legacy_same_artwork_geometry_offers(
            **{**params, "saved_by_base": changed})) == 2
    assert len(f.legacy_same_artwork_geometry_offers(
        **{**params, "choices": {**choices, "native_SW5": {
            **choices["native_SW5"], "sha256": "f" * 64}}})) == 2
    assert len(f.legacy_same_artwork_geometry_offers(
        **{**params, "profiles": profiles + [dict(profiles[0])]})) == 2
    assert len(f.legacy_same_artwork_geometry_offers(
        **{**params, "profiles": [{**x, "scope": "custom"}
                                  if x["base_profile"] == "native_SW5" else x
                                  for x in profiles]})) == 2
    # After the one-switch consented reset, the profile is factory-current.
    repaired = {**saved, "native_SW5": {
        **saved["native_SW5"], "calibration": {
            **saved["native_SW5"]["calibration"],
            "profile": "stock_48rj45_4sfp",
            "image": dict(factory["image"]),
        }}}
    assert len(f.legacy_same_artwork_geometry_offers(
        **{**params, "saved_by_base": repaired})) == 2
    print("FACEPLATE_LEGACY_SAME_ARTWORK_GEOMETRY_PASS")


def test_owner_dashboard_stack_and_juniper_geometry_offers() -> None:
    """Reproduce the saved dashboard's SW5/SW6 shared stack and SW10 alias."""
    stock = "48rj45-4sfp.png"
    compact = "48rj45-2sfp-compact.png"
    image_sha, geometry_sha = "a" * 64, "b" * 64
    latest = {"filename": stock, "sha256": image_sha,
              "geometry_sha256": geometry_sha,
              "path": "faceplates/" + stock, "version": "sha-" + "c" * 20}
    models = {"WS-C3650-48PD-E", "EX3300-48P",
              "WS-C2960X-48FPD-L", "WS-C2960S-48FPD-L"}
    # These are the actual distinct identity relationships from the captured
    # generated dashboard, with management addresses and metadata omitted.
    cards = [
        {"type": "custom:switch-vision-3650",
         "discovery_selected_switch": "3650-stack", "selected_switch": "SW5",
         "switch_model": "WS-C3650-48PD-E", "stack_enabled": True,
         "stack_member_number": 1},
        {"type": "custom:switch-vision-3650",
         "discovery_selected_switch": "3650-stack", "selected_switch": "SW6",
         "switch_model": "WS-C3650-48PD-E", "stack_enabled": True,
         "stack_member_number": 2},
        {"type": "custom:switch-vision-3650",
         "discovery_selected_switch": "ex3300-48p", "selected_switch": "SW10",
         "switch_model": "Juniper EX3300-48P"},
        {"type": "custom:switch-vision-3650",
         "discovery_selected_switch": "2960x-48p", "selected_switch": "SW7",
         "switch_model": "WS-C2960X-48FPD-L"},
        {"type": "custom:switch-vision-3650",
         "discovery_selected_switch": "2960S-48p", "selected_switch": "SW9",
         "switch_model": "WS-C2960S-48FPD-L"},
    ]
    targets = f.generated_native_targets({"views": [{"cards": cards}]}, models)
    assert [x["native_switch_key"] for x in targets["3650-stack"]] == ["SW5", "SW6"]
    assert targets["ex3300-48p"] == [{"native_switch_key": "SW10", "model": "EX3300-48P"}]
    assert f.generated_exact_models({"views": [{"cards": cards}]}, models)["ex3300-48p"] == "EX3300-48P"
    assert f.canonical_model("Unreviewed EX3300-48P", models) == ""
    invalid = [dict(cards[0]), {**cards[1], "stack_member_number": 1}]
    assert "3650-stack" not in f.generated_native_targets({"cards": invalid}, models)
    invalid = [dict(cards[0]), {**cards[1], "stack_enabled": False}]
    assert "3650-stack" not in f.generated_native_targets({"cards": invalid}, models)

    devices = [
        {"device_key": "snmp:stack", "switch_name": "3650-stack",
         "native_switch_key": "SW5", "resolved_model": "WS-C3650-48PD-E"},
        {"device_key": "snmp:stack", "switch_name": "3650-stack",
         "native_switch_key": "SW6", "resolved_model": "WS-C3650-48PD-E"},
        {"device_key": "snmp:juniper", "switch_name": "ex3300-48p",
         "native_switch_key": "SW10", "resolved_model": "EX3300-48P"},
        {"device_key": "snmp:2960x", "switch_name": "2960x-48p",
         "native_switch_key": "SW7", "resolved_model": "WS-C2960X-48FPD-L"},
        {"device_key": "snmp:2960s", "switch_name": "2960S-48p",
         "native_switch_key": "SW9", "resolved_model": "WS-C2960S-48FPD-L"},
    ]
    defaults = {"WS-C3650-48PD-E": stock, "EX3300-48P": stock,
                "WS-C2960X-48FPD-L": compact,
                "WS-C2960S-48FPD-L": compact}
    factory = {
        "model": "stock-48rj45-4sfp", "profile": "stock_48rj45_4sfp",
        "image": {"file": "faceplates/" + stock, "width": 6000, "height": 900},
        "ports": {"1": {"center": [558.147321429, 422.879464286]},
                  "2": {"center": [558.171428571, 662.914285714]},
                  "47": {"center": [4706.785714286, 422.879464286]},
                  "48": {"center": [4714.821428571, 662.946428571]}},
    }
    legacy = {
        "model": "stock-48rj45-4sfp", "profile": "default_cisco_48_port",
        "user_topology_authoritative": True,
        "ports": {"1": {"center": [515.625, 724.0234375]},
                  "2": {"center": [518.5546875, 996.484375]},
                  "47": {"center": [4669.921875, 724.0234375]},
                  "48": {"center": [4675.78125, 993.5546875]}},
    }
    saved = {"native_" + name: {
        "exists": True, "invalid": False, "profile": "native_" + name,
        "calibration": dict(legacy),
        "stock_artwork": {**latest, "geometry": factory},
    } for name in ("SW5", "SW6", "SW10")}
    profiles = [{"base_profile": "native_" + name, "scope": "native",
                 "active": True, "saved_calibration_image": None}
                for name in ("SW5", "SW6", "SW10")]
    choices = {"native_" + name: dict(latest) for name in ("SW5", "SW6", "SW10")}
    offers = f.legacy_same_artwork_geometry_offers(
        devices, defaults, {stock: image_sha}, choices, profiles,
        {stock: [latest]}, saved)
    assert {x["base_profile"] for x in offers} == {
        "native_SW5", "native_SW6", "native_SW10"}, offers
    assert all(x["migration_kind"] == "legacy_saved_geometry" for x in offers)
    assert all(x["saved_geometry_height"] is None for x in offers)
    # Missing/modified legacy anchors must not authorize an offer.
    changed = {**saved, "native_SW5": {**saved["native_SW5"],
               "calibration": {**legacy, "ports": dict(factory["ports"])}}}
    assert {x["base_profile"] for x in f.legacy_same_artwork_geometry_offers(
        devices, defaults, {stock: image_sha}, choices, profiles,
        {stock: [latest]}, changed)} == {"native_SW6", "native_SW10"}
    print("FACEPLATE_REAL_STACK_AND_JUNIPER_SHAPE_PASS")


if __name__ == "__main__":
    test()
    test_verified_legacy_geometry_upgrade()
    test_owner_dashboard_stack_and_juniper_geometry_offers()
