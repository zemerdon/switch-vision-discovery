#!/usr/bin/env python3
"""Synthetic Q-BRIDGE diagnostics: joins, bitmaps, privacy and fail-closed gaps."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

RUNTIME = Path(__file__).resolve().parents[1] / "runtime_src"
sys.path.insert(0, str(RUNTIME))
spec = importlib.util.spec_from_file_location("qbridge_diag_test", RUNTIME / "support_diagnostics.py")
assert spec and spec.loader
diag = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = diag
spec.loader.exec_module(diag)


def fixture(root: Path, *, missing=False, bad_bitmap=False, stale=False):
    folder = root / "snmpwalks" / "unit"
    folder.mkdir(parents=True)
    (folder / "gs1900-physical-contract.json").write_text(json.dumps({
        "device": {"effective_model": "GS1900-8"},
        "ports": [{"physical_id": "member1-rj45-2",
                   "source": {"if_index": 7, "if_name": "GigabitEthernet2"},
                   "compatibility_name": "Gi1/0/2"}]}))
    lines = [
        ".1.3.6.1.2.1.31.1.1.1.1.7 = STRING: GigabitEthernet2",
        ".1.3.6.1.2.1.17.1.4.1.2.5 = INTEGER: 7",
        ".1.3.6.1.2.1.17.7.1.4.5.1.1.5 = INTEGER: 1",
    ]
    if not missing:
        for vlan in (1, 10, 20):
            lines += [
                f".1.3.6.1.2.1.17.7.1.4.2.1.4.0.{vlan} = Hex-STRING: " + ("GG" if bad_bitmap else "08"),
                f".1.3.6.1.2.1.17.7.1.4.2.1.5.0.{vlan} = Hex-STRING: " + ("08" if vlan == 1 else "00"),
            ]
    (folder / "live-full-snmpwalk.txt").write_text("\n".join(lines) + "\n")
    generated = {"targets": [{
        "name": "fixture",
        "device_model": "GS1900-8",
        "sensors": [
            {"name": "Port Native", "object_id": "fixture_port_native", "source": "qbridge_vlan",
             "interface": "GigabitEthernet2", "attribute": "native_vlan"},
            {"name": "Port Members", "object_id": "fixture_port_members", "source": "qbridge_vlan",
             "interface": "Gi1/0/2", "attribute": "member_vlans"},
        ]}]}
    states = [{"entity_id": "sensor.fixture_port_native", "state": "1"}]
    return generated, states


def main():
    assert diag._qbridge_bitmap("Hex-STRING: 40") == {2}
    assert diag._qbridge_bitmap("Hex-STRING: 00 80") == {9}
    assert diag._qbridge_bitmap("Hex-STRING: GG") is None
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        generated, states = fixture(root)
        r = diag.build_qbridge_correlation(
            root, generated, states, file_provenance=diag.build_file_provenance(root))
        port = r["devices"][0]["ports"][0]
        assert r["status"] == "observed" and r["device_count"] == 1, r
        assert (port["if_index"], port["bridge_port"], port["pvid"]) == (7, 5, 1)
        assert port["member_vlans"] == [1, 10, 20] and port["untagged_vlans"] == [1]
        assert port["tagged_vlans"] == [10, 20] and port["resolution"] == "observed", port
        assert port["generated_attributes"]["native_vlan"]["identity"] == "raw_if_name"
        assert port["generated_attributes"]["native_vlan"]["ha_state"] == "1"
        assert port["generated_attributes"]["member_vlans"]["identity"] == "compatibility_alias"
        assert port["generated_attributes"]["member_vlans"]["ha_state_status"] == "unavailable"
        serialized = json.dumps(r)
        assert "GigabitEthernet2" not in serialized and "Gi1/0/2" not in serialized
        assert "switch1" not in serialized
        extra = root / "snmpwalks" / "second"
        extra.mkdir()
        (extra / "live-full-snmpwalk.txt").write_text(
            ".1.3.6.1.2.1.17.1.4.1.2.5 = INTEGER: 7\n"
            ".1.3.6.1.2.1.17.7.1.4.5.1.1.5 = INTEGER: 1\n")
        multi = diag.build_qbridge_correlation(root, generated)
        assert any(d.get("reason") == "physical_contract_scope_unavailable" for d in multi["devices"])
        assert not next(d for d in multi["devices"] if d["ports"])["ports"][0]["generated_attributes"]
    for opts, expected in [
        ({"missing": True}, "static_egress_missing"),
        ({"bad_bitmap": True}, "current_egress_invalid_bitmap"),
    ]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generated, states = fixture(root, **opts)
            p = diag.build_qbridge_correlation(root, generated, states)["devices"][0]["ports"][0]
            assert p["member_vlans"] is None and p["resolution"] == "unavailable", p
            assert expected in p["issues"], p
    # VLAN StaticTable has one VLAN index (current table has timeMark + VLAN).
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        generated, states = fixture(root, missing=True)
        walk = root / "snmpwalks" / "unit" / "live-full-snmpwalk.txt"
        extra = []
        for vlan in (1, 10, 20):
            extra.append(f".1.3.6.1.2.1.17.7.1.4.3.1.2.{vlan} = Hex-STRING: 08")
            extra.append(f".1.3.6.1.2.1.17.7.1.4.3.1.4.{vlan} = Hex-STRING: " + ("08" if vlan == 1 else "00"))
        walk.write_text(walk.read_text() + "\n".join(extra) + "\n")
        port = diag.build_qbridge_correlation(root, generated, states)["devices"][0]["ports"][0]
        assert port["membership_source"] == "static", port
        assert port["member_vlans"] == [1, 10, 20], port
        assert port["resolution"] == "observed", port
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        generated, states = fixture(root)
        states += [{"entity_id": "sensor.fixture_port_members", "state": "1,10,30"}]
        port = diag.build_qbridge_correlation(root, generated, states)["devices"][0]["ports"][0]
        assert port["resolution"] == "conflict", port
        assert "ha_member_vlans_disagrees_with_walk" in port["issues"], port
        assert port["generated_attributes"]["member_vlans"]["ha_state"] == "1,10,30"
        states[-1]["state"] = "VLAN Private Office Name"
        port = diag.build_qbridge_correlation(root, generated, states)["devices"][0]["ports"][0]
        assert port["generated_attributes"]["member_vlans"]["ha_state"] is None
        assert "Private Office Name" not in json.dumps(port)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        generated, states = fixture(root, missing=True)
        walk = root / "snmpwalks" / "unit" / "live-full-snmpwalk.txt"
        walk.write_text(
            walk.read_text()
            + ".1.3.6.1.2.1.17.7.1.4.2.1.4.0.1 = Hex-STRING: 08\n"
            + ".1.3.6.1.2.1.17.7.1.4.3.1.2.1 = Hex-STRING: 08\n"
            + ".1.3.6.1.2.1.17.7.1.4.3.1.4.1 = Hex-STRING: 08\n"
        )
        port = diag.build_qbridge_correlation(root, generated, states)["devices"][0]["ports"][0]
        assert port["membership_source"] == "current", port
        assert port["member_vlans"] is None and port["resolution"] == "unavailable", port
        assert "current_untagged_missing" in port["issues"], port
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        generated, states = fixture(root)
        walk = root / "snmpwalks" / "unit" / "live-full-snmpwalk.txt"
        rows = [row for row in walk.read_text().splitlines()
                if ".1.3.6.1.2.1.17.7.1.4.2.1.5.0.10" not in row]
        walk.write_text("\n".join(rows) + "\n")
        port = diag.build_qbridge_correlation(root, generated, states)["devices"][0]["ports"][0]
        assert port["resolution"] == "unavailable", port
        assert "membership_untagged_vlan_rows_missing" in port["issues"], port
    print("Q-BRIDGE support diagnostic regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
