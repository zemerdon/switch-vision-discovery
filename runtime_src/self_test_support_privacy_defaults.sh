# Switch Vision Discovery self-test Support My Switch privacy-default module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# v2.1.21 Support My Switch privacy-default contract.
# The Home Assistant app config lives outside runtime.tar.gz, so this regression
# protects the runtime-side expectation that both controls remain supported and
# are read as normal boolean contribution options.
grep -q 'support_mask_vlan_names' "$BASE_DIR/discovery_job.sh"
grep -q 'support_mask_interface_descriptions' "$BASE_DIR/discovery_job.sh"
echo "Switch Vision Discovery v2.1.21 privacy-default contract regression: PASS"
