#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def load_entrypoint(repo_root: Path):
    module_path = repo_root / 'runtime_src' / 'discovery_contract_entrypoint.py'
    spec = importlib.util.spec_from_file_location('discovery_contract_entrypoint_test', module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_walk(path: Path, sysdescr: str, ports: int) -> None:
    lines = [
        f'.1.3.6.1.2.1.1.1.0 = STRING: "{sysdescr}"',
        '.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.8072.3.2.10',
    ]
    for idx in range(1, ports + 1):
        lines.extend(
            [
                f'.1.3.6.1.2.1.31.1.1.1.1.{idx} = STRING: "0/{idx}"',
                f'.1.3.6.1.2.1.2.2.1.2.{idx} = STRING: "Port {idx}"',
                f'.1.3.6.1.2.1.2.2.1.7.{idx} = INTEGER: up(1)',
                f'.1.3.6.1.2.1.2.2.1.8.{idx} = INTEGER: up(1)',
                f'.1.3.6.1.2.1.31.1.1.1.15.{idx} = Gauge32: 1000',
                f'.1.3.6.1.2.1.31.1.1.1.6.{idx} = Counter64: {idx * 1000}',
                f'.1.3.6.1.2.1.31.1.1.1.10.{idx} = Counter64: {idx * 2000}',
            ]
        )
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    runtime = repo_root / 'runtime_src'
    entry = load_entrypoint(repo_root)
    entry.LEGACY = runtime / 'discovery_job.sh'
    entry.PREPARE = runtime / 'physical_contract_prepare.sh'
    entry.REGISTRY = runtime / 'opt' / 'switch-vision' / 'devices' / 'supported_devices.json'

    with tempfile.TemporaryDirectory(prefix='sv-mark-current-run-') as temp_name:
        temp = Path(temp_name)
        source_root = temp / 'source-walks'
        sw1 = source_root / 'SW1'
        sw2 = source_root / 'SW2'
        sw1.mkdir(parents=True)
        sw2.mkdir(parents=True)

        sw1_targeted = sw1 / 'live-targeted-snmpwalk.txt'
        sw2_targeted = sw2 / 'live-targeted-snmpwalk.txt'
        make_walk(sw1_targeted, 'Linux USWProHD24PoE 4.4.153 #0 mips', 28)
        make_walk(sw2_targeted, 'Linux USWProXG8PoE 4.4.153 #0 mips', 10)

        # Historical decoys prove the normalized second pass does not silently
        # turn current-run generation into stored-walk reuse.
        make_walk(sw1 / 'live-full-snmpwalk.txt', 'Linux USWProHD24PoE 4.4.153 #0 mips', 28)
        make_walk(sw2 / 'live-full-snmpwalk.txt', 'Linux USWProXG8PoE 4.4.153 #0 mips', 10)

        current_walks = temp / 'current-run-walks.txt'
        current_targets = temp / 'current-run-targets.txt'
        current_walks.write_text(f'{sw1_targeted}\n{sw2_targeted}\n', encoding='utf-8')
        sep = '\x1c'
        current_targets.write_text(
            f'{sw1_targeted}{sep}SW1{sep}192.0.2.11{sep}SW1{sep}readonly\n'
            f'{sw2_targeted}{sep}SW2{sep}192.0.2.12{sep}SW2{sep}readonly\n',
            encoding='utf-8',
        )
        entry.CURRENT_RUN_WALKS = current_walks
        entry.CURRENT_RUN_TARGETS = current_targets
        records = entry._read_current_run_records()
        assert [record['switch'] for record in records] == ['SW1', 'SW2']

        report = temp / 'report.txt'
        generated = temp / 'generated.yaml'
        card = temp / 'card.yaml'
        options = {
            'input_path': str(sw1_targeted),
            'snmpwalks_dir': str(source_root),
            'report_path': str(report),
            'run_snmp_walks': 'true',
            'enable_switch_list': 'true',
            'parse_all_walks': 'false',
            'generate_snmp2mqtt': 'true',
            'clean_output_before_walk': 'false',
            'targets_csv': str(temp / 'original-targets.csv'),
            'last_run_summary_path': str(temp / 'summary.txt'),
            'generated_yaml_path': str(generated),
            'generated_card_path': str(card),
            'snmp_log_path': str(temp / 'discovery.log'),
            'minimum_valid_walk_lines': '1',
            'generate_support_my_switch_bundle': 'false',
            'switches': [
                {
                    'switch_name': 'SW1',
                    'switch_host': '192.0.2.11',
                    'sensor_prefix': 'SW1',
                    'snmp_community': 'readonly',
                    'enabled': 'enabled',
                    'walk_mode': 'targeted',
                    'output_dir': str(sw1),
                },
                {
                    'switch_name': 'SW2',
                    'switch_host': '192.0.2.12',
                    'sensor_prefix': 'SW2',
                    'snmp_community': 'readonly',
                    'enabled': 'enabled',
                    'walk_mode': 'targeted',
                    'output_dir': str(sw2),
                },
            ],
        }

        work = temp / 'work'
        work.mkdir()
        staged, ordered = entry._stage_options(options, work, records)
        assert options['parse_all_walks'] == 'false'
        assert staged['parse_all_walks'] == 'true'
        assert len(ordered) == 2

        staged_root = Path(staged['snmpwalks_dir'])
        staged_walks = sorted(path.relative_to(staged_root).as_posix() for path in staged_root.rglob('*.txt'))
        assert staged_walks == [
            'SW1/live-targeted-snmpwalk.txt',
            'SW2/live-targeted-snmpwalk.txt',
        ], staged_walks
        assert 'Gi1/0/1' in (staged_root / staged_walks[0]).read_text(encoding='utf-8')
        assert 'Te1/1/4' in (staged_root / staged_walks[0]).read_text(encoding='utf-8')
        assert 'Te1/1/2' in (staged_root / staged_walks[1]).read_text(encoding='utf-8')

        staged_options = temp / 'staged-options.json'
        staged_options.write_text(json.dumps(staged, indent=2) + '\n', encoding='utf-8')
        env = os.environ.copy()
        env['SWITCH_VISION_OPTIONS_FILE'] = str(staged_options)
        env['SWITCH_VISION_CAPABILITIES_DIR'] = str(temp / 'runtime-capabilities')
        env['SWITCH_VISION_SHARE_DIR'] = str(temp / 'share')
        result = subprocess.run(
            [str(runtime / 'discovery_job.sh')],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if result.returncode != 0:
            print(result.stdout)
            raise SystemExit(result.returncode)

        entry._patch_report(report, ordered)
        entry._patch_yaml(generated, ordered)
        report_text = report.read_text(encoding='utf-8')
        assert 'Model/platform: USW Pro HD 24 PoE' in report_text, report_text
        assert 'Model/platform: USW Pro XG 8 PoE' in report_text, report_text
        assert '- Physical switch interfaces detected: 28' in report_text, report_text
        assert '- Physical switch interfaces detected: 10' in report_text, report_text
        assert generated.is_file(), result.stdout
        generated_text = generated.read_text(encoding='utf-8')
        status_rows = generated_text.count('oid: 1.3.6.1.2.1.2.2.1.8.')
        assert status_rows == 38, f'expected 38 current-run status rows, got {status_rows}\n{generated_text}'
        assert '# Detected model: USW Pro HD 24 PoE' in generated_text
        assert '# Detected model: USW Pro XG 8 PoE' in generated_text

    print('Switch Vision Mark current-run physical-contract regression: PASS')


if __name__ == '__main__':
    main()
