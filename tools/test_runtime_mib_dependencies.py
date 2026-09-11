from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILES = [ROOT / "runtime_src/Dockerfile", ROOT / "switch_vision_discovery/Dockerfile"]
REQUIRED_PACKAGES = ["net-snmp-tools", "net-snmp", "libsmi", "jq", "zip", "python3", "py3-yaml", "py3-websockets"]
REQUIRED_COMMANDS = ["snmpwalk", "snmptranslate", "smilint", "smidump"]
REQUIRED_MIBS = [
    "IF-MIB.txt",
    "BRIDGE-MIB.txt",
    "HOST-RESOURCES-MIB.txt",
    "Q-BRIDGE-MIB",
    "ENTITY-MIB",
    "ENTITY-SENSOR-MIB",
    "POWER-ETHERNET-MIB",
    "MAU-MIB",
]

for dockerfile in DOCKERFILES:
    text = dockerfile.read_text(encoding="utf-8")
    for package in REQUIRED_PACKAGES:
        assert package in text, f"{dockerfile}: missing runtime package {package}"
    for command in REQUIRED_COMMANDS:
        assert f"command -v {command}" in text, f"{dockerfile}: missing build proof for {command}"
    for mib in REQUIRED_MIBS:
        assert mib in text, f"{dockerfile}: missing bundled MIB proof for {mib}"
    assert "MIBS=ALL" not in text, f"{dockerfile}: runtime must retain deterministic numeric SNMP output"

job = (ROOT / "runtime_src/discovery_job.sh").read_text(encoding="utf-8")
for oid in [
    "1.3.6.1.2.1.10.7",
    "1.3.6.1.2.1.26",
    "1.3.6.1.2.1.25.3.3.1.2",
    "1.3.6.1.2.1.47.1.1.1.1",
    "1.3.6.1.2.1.99.1.1.1",
    "1.3.6.1.2.1.105.1.3.1",
]:
    assert oid in job, f"targeted standard evidence root missing: {oid}"

catalog = (ROOT / "runtime_src/opt/switch-vision/mib_database/standard/sensors.json").read_text(encoding="utf-8")
for name in ["HOST-RESOURCES-MIB", "ENTITY-SENSOR-MIB", "POWER-ETHERNET-MIB", "EtherLike-MIB", "MAU-MIB"]:
    assert name in catalog, f"standard MIB knowledge catalog missing {name}"

print("Switch Vision Discovery self-contained MIB/runtime dependency contract: PASS")
