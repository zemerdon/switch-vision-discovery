from pathlib import Path

path = Path("tools/test_c3750_48p_live_mapping.py")
text = path.read_text(encoding="utf-8")
old = '''            "run_snmp_walks": False,
            "enable_switch_list": False,
'''
new = '''            "run_snmp_walks": False,
            "enable_switch_list": False,
            "live_output_dir": str(work / "live"),
            "live_output_path": str(work / "live" / "live-targeted-snmpwalk.txt"),
            "live_log_path": str(work / "live-snmpwalk.log"),
'''
if old in text:
    text = text.replace(old, new, 1)
old = '''        "SWITCH_VISION_CAPABILITIES_DIR": str(caps),
'''
new = '''        "SWITCH_VISION_CAPABILITIES_DIR": str(caps),
        "SWITCH_VISION_SHARE_DIR": str(work / "share"),
'''
if old in text:
    text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
