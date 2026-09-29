# Switch Vision Discovery self-test manual dashboard-export module.
# Sourced by self-test.sh with the existing self-test environment intact.
# Keep this as an exact behavioral extraction; production logic is not duplicated here.

# Manual dashboard export regression. Native generated YAML remains unchanged;
# full export removes the known Layout Card wrapper, cards-only preserves cards,
# and unknown future custom view dependencies fail closed.
python3 "$BASE_DIR/dashboard_yaml_export_regression.py"
