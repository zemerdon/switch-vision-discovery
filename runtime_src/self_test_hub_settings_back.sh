# Switch Vision Discovery self-test Hub Settings Back module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# Discovery 2.3.39 Hub Settings Back regression.
sv_require_literal 'Hub Settings Save action' 'id="hubSettingsSave" class="primary" type="button" disabled>Save changes</button>' "$SV_HUB_SOURCE"
sv_require_literal 'Hub Settings Reload action' 'id="hubSettingsReload" type="button">Reload</button>' "$SV_HUB_SOURCE"
sv_require_literal 'Hub Settings Back action' 'id="hubSettingsBack" type="button">Back</button>' "$SV_HUB_SOURCE"
sv_require_literal 'Hub Settings Back goBack binding' "q('hubSettingsBack')?.addEventListener('click',goBack);" "$SV_HUB_SOURCE"
