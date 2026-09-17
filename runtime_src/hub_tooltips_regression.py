#!/usr/bin/env python3
from pathlib import Path
import ast
import re

SOURCE = Path(__file__).with_name('support_web.py').read_text(encoding='utf-8')

match = re.search(r"const H=\{(?P<body>.*?)\};const OL=", SOURCE, re.S)
assert match, 'Hub help map H was not found'
entries = {}
for key, value in re.findall(r"'((?:[^'\\]|\\.)*)':'((?:[^'\\]|\\.)*)'", match.group('body')):
    entries[ast.literal_eval("'" + key + "'")] = ast.literal_eval("'" + value + "'")

required = {
    'Sensitivity preset', 'Slow activity maximum (%)', 'Medium activity maximum (%)',
    'Slow blink period (ms)', 'Medium blink period (ms)', 'Fast blink period (ms)',
    'Activity hold (seconds)', 'Hysteresis (%)', 'UI density', 'Text size',
    'Content width', 'MQTT host', 'MQTT port', 'MQTT username', 'MQTT password',
    'Targets path', 'Generated YAML path', 'Imported targets path',
    'Run SNMP walks', 'Use saved switch list', 'Parse all stored walks',
    'Generate SNMP2MQTT YAML', 'Clean generated output before walk',
    'Create Support My Switch bundle after Discovery', 'Switch Name (Used internally only)',
    'Display name', 'Switch host', 'Sensor prefix', 'SNMP community', 'State',
    'Walk mode', 'Switch model', 'Card header title', 'Input walk path',
    'SNMP walks directory', 'Discovery report path', 'Targets CSV path',
    'Last-run summary path', 'Generated SNMP2MQTT path', 'Generated dashboard path',
    'SNMP log path', 'SNMP timeout', 'SNMP retries', 'Minimum valid walk lines',
    'Automatic retention', 'Retained backups', 'Mask management IPs',
    'Mask MAC addresses', 'Mask hostnames', 'Mask VLAN names',
    'Mask interface descriptions', 'Contributor recognition', 'Contributor value',
}
missing = sorted(required - entries.keys())
assert not missing, f'missing authored Hub help: {missing}'

for label, help_text in entries.items():
    assert help_text.strip(), f'empty help text: {label}'
    assert help_text.strip().casefold() != label.strip().casefold(), f'label-only help: {label}'
    assert len(help_text.strip()) >= 24, f'help text is too terse to be useful: {label}: {help_text}'

assert "const help=h||H[t]||''" in SOURCE
assert "if(help)target.title=help" in SOURCE
assert "if(help)i.title=help" in SOURCE
assert "s.append(hubHelp(help))" in SOURCE

start = SOURCE.index('function installDiscoveryTooltips(root=document)')
end = SOURCE.index('const discoveryTooltipObserver=', start)
block = SOURCE[start:end]
assert "DISCOVERY_TOOLTIP_HELP[el.id]||''" in block
assert "el.getAttribute('aria-label')" not in block
assert "label.querySelector(':scope > span')" not in block
assert "el.textContent.trim()" not in block

assert "'Hysteresis (%)':'Adds a buffer around the Slow/Medium/Fast traffic thresholds" in SOURCE
print('Switch Vision Hub authored-help tooltip regression: PASS')
