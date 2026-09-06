from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WEB=(ROOT/'runtime_src/support_web.py').read_text(encoding='utf-8')
CONTRACT=(ROOT/'tools/check_component_contracts.py').read_text(encoding='utf-8')
assert '_PUBLIC_RELEASE_COMPONENTS' not in WEB
assert 'switch_vision_installer/app/component_manager.py' in WEB
assert 'ComponentSpec\\(' in WEB and '/releases/latest' in WEB and '"published_at": published_at' in WEB
assert 'faceplate_width_mode' in WEB and 'faceplate_custom_width' in WEB and "['800','800 px'],['1024','1024 px'],['custom','Custom']" in WEB
assert '("CONF_FACEPLATE_WIDTH_MODE", "faceplate_width_mode")' in CONTRACT
assert '("CONF_FACEPLATE_CUSTOM_WIDTH", "faceplate_custom_width")' in CONTRACT
assert 'function hubHelp(' in WEB and 'role\',\'tooltip' in WEB and 'aria-expanded' in WEB and "e.key==='Escape'" in WEB
assert 'function attachActionHelp(' in WEB and 'applyHubTooltips' not in WEB and "querySelectorAll('button,input,select,textarea')" not in WEB
print('Discovery 2.3.45 Hub UI/UX regression: PASS')
