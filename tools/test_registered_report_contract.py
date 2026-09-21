from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / "runtime_src/discovery_job.sh"

CASES = (
    {
        "name": "gs1900-8",
        "model": "GS1900-8",
        "sysdescr": "Zyxel GS1900-8",
        "profile": "zyxel-gs1900-8",
        "ifnames": [f"GigabitEthernet{i}" for i in range(1, 9)] + [f"LAG{i}" for i in range(1, 9)],
    },
    {
        "name": "gs1915-24ep",
        "model": "GS1915-24EP",
        "sysdescr": "Zyxel GS1915-24EP Managed Switch",
        "profile": "zyxel-gs1915-24ep",
        "ifnames": [f"swp{i:02d}" for i in range(24)],
    },
    {
        "name": "hp1810-24g",
        "model": "HP 1810-24G",
        "sysdescr": "HP 1810-24G, PL.2.10",
        "profile": "hp-1810-24g-24p-2sfp",
        "ifnames": [str(i) for i in range(1, 27)] + ["IP", "Link Aggregate"],
    },
    {
        "name": "sr-s25g3420f",
        "model": "SR-S25G3420F",
        "sysdescr": "Sirivision SR-S25G3420F Managed Switch",
        "profile": "sirivision-sr-s25g3420f",
        "ifnames": [f"HisgmiiEthernet{i}" for i in range(1, 17)]
        + [f"TenGigabitEthernet{i}" for i in range(17, 21)]
        + ["Vlan1", "LAG1"],
    },
)


def write_walk(path: Path, sysdescr: str, ifnames: list[str]) -> None:
    lines = [
        f'.1.3.6.1.2.1.1.1.0 = STRING: "{sysdescr}"',
        '.1.3.6.1.2.1.1.5.0 = STRING: "sv-report-regression"',
    ]
    for idx, name in enumerate(ifnames, start=1):
        lines.extend(
            [
                f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: "{name}"',
                f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: up(1)',
                f'.1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 1000',
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_case(case: dict[str, object], root: Path) -> str:
    name = str(case["name"])
    work = root / name
    walk_root = work / "snmpwalks"
    walk_dir = walk_root / name
    walk_dir.mkdir(parents=True)
    walk = walk_dir / "live-full-snmpwalk.txt"
    report = work / "report.txt"
    generated = work / "generated.yaml"
    card = work / "card.yaml"
    targets = work / "targets.csv"
    last_run = work / "last-run.txt"
    caps = work / "capabilities"
    options = work / "options.json"

    write_walk(walk, str(case["sysdescr"]), list(case["ifnames"]))
    targets.write_text(
        "switch name,switch host,sensor prefix,switch snmp community,output_dir,display name\n"
        f"{name},192.0.2.50,REG,public,{walk_dir},{case['model']}\n",
        encoding="utf-8",
    )
    options.write_text(
        json.dumps(
            {
                "input_path": str(walk),
                "snmpwalks_dir": str(walk_root),
                "report_path": str(report),
                "parse_all_walks": True,
                "generate_snmp2mqtt": True,
                "targets_csv": str(targets),
                "generated_yaml_path": str(generated),
                "generated_card_path": str(card),
                "last_run_summary_path": str(last_run),
                "run_snmp_walks": False,
                "enable_switch_list": False,
                "live_output_dir": str(work / "live"),
                "live_output_path": str(work / "live" / "live-targeted-snmpwalk.txt"),
                "live_log_path": str(work / "live-snmpwalk.log"),
            }
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "SWITCH_VISION_OPTIONS_FILE": str(options),
            "CV_VENDOR_DIR": str(ROOT / "runtime_src/opt/switch-vision/vendors"),
            "CV_MIB_DATABASE_DIR": str(ROOT / "runtime_src/opt/switch-vision/mib_database"),
            "SWITCH_VISION_CAPABILITIES_DIR": str(caps),
            "SWITCH_VISION_SHARE_DIR": str(work / "share"),
            "SWITCH_VISION_RUNTIME_DIR": str(ROOT / "runtime_src"),
            "SWITCH_VISION_REGISTRY_LOOKUP": str(ROOT / "runtime_src/registry_lookup.py"),
            "SWITCH_VISION_DEVICE_REGISTRY": str(
                ROOT / "runtime_src/opt/switch-vision/devices/supported_devices.json"
            ),
        }
    )
    result = subprocess.run(
        ["sh", str(JOB)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, f"{name}:\n{result.stdout}"
    return report.read_text(encoding="utf-8")


def assert_registered_report(case: dict[str, object], report: str) -> None:
    model = str(case["model"])
    profile = str(case["profile"])
    required = (
        f"Model/platform: {model}",
        f"- Matched profile: {profile}",
        "- Profile status: experimental",
        f"- PASS: exact model matched in Switch Vision supported-device registry: {model} (experimental)",
        "- Ready for SNMP2MQTT generation: yes, review-only",
        "- Exact model detected: yes",
        f"- Suggested profile: {profile}",
        "- Support status: experimental / partially validated",
    )
    for marker in required:
        assert marker in report, f"{model}: missing {marker!r}\n{report}"

    forbidden = (
        "known Switch Vision model not confirmed",
        "- Exact model detected: no",
        "- Suggested profile: unknown",
        "- Support status: unsupported",
        "Cisco trunk status OIDs",
        "Cisco dynamic trunk state OIDs",
    )
    for marker in forbidden:
        assert marker not in report, f"{model}: stale marker {marker!r}\n{report}"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sv-registered-report-") as td:
        root = Path(td)
        for case in CASES:
            assert_registered_report(case, run_case(case, root))
    print("Switch Vision registered-model report contract: PASS")


if __name__ == "__main__":
    main()
