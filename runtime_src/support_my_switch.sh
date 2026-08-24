#!/usr/bin/env sh
set -eu

SWITCH_VISION_ROOT="${SWITCH_VISION_ROOT:-/share/switch_vision}"
CONTRIBUTIONS_DIR="${CONTRIBUTIONS_DIR:-$SWITCH_VISION_ROOT/contributions}"
VERSION="${SWITCH_VISION_DISCOVERY_VERSION:-unknown}"
BUNDLE_VERSION="12"
MASK_MANAGEMENT_IPS="${SUPPORT_MASK_MANAGEMENT_IPS:-true}"
MASK_MAC_ADDRESSES="${SUPPORT_MASK_MAC_ADDRESSES:-true}"
MASK_HOSTNAMES="${SUPPORT_MASK_HOSTNAMES:-true}"
MASK_VLAN_NAMES="${SUPPORT_MASK_VLAN_NAMES:-false}"
MASK_INTERFACE_DESCRIPTIONS="${SUPPORT_MASK_INTERFACE_DESCRIPTIONS:-false}"
SANITIZER_SCRIPT="${SUPPORT_SANITIZER_SCRIPT:-/ha_entity_snapshot_sanitizer.py}"
BASE_SANITIZER_SCRIPT="${SUPPORT_BASE_SANITIZER_SCRIPT:-/sanitize_support_bundle.py}"
EMAIL_BUILDER_SCRIPT="${SUPPORT_EMAIL_BUILDER_SCRIPT:-/make_support_email.py}"
REGISTRY_LOOKUP_SCRIPT="${SUPPORT_REGISTRY_LOOKUP_SCRIPT:-/registry_lookup.py}"
REGISTRY_FILE="${SUPPORT_REGISTRY_FILE:-/opt/switch-vision/devices/supported_devices.json}"
CONTRIBUTOR_TYPE="${SUPPORT_CONTRIBUTOR_TYPE:-anonymous}"
CONTRIBUTOR_VALUE="${SUPPORT_CONTRIBUTOR_VALUE:-}"

log() {
  printf '%s\n' "[Support My Switch] $*"
}

case "$CONTRIBUTOR_TYPE" in
  anonymous|first_name|full_name|github|forum) ;;
  *)
    log "WARNING: Unknown contributor recognition type '$CONTRIBUTOR_TYPE'; using anonymous."
    CONTRIBUTOR_TYPE="anonymous"
    ;;
esac
if [ "$CONTRIBUTOR_TYPE" = "anonymous" ]; then
  CONTRIBUTOR_VALUE=""
fi
# Keep recognition text single-line and safe for JSON/email output.
CONTRIBUTOR_VALUE=$(printf '%s' "$CONTRIBUTOR_VALUE" | tr '\r\n\t' '   ' | sed 's/[[:cntrl:]]//g; s/^ *//; s/ *$//' | cut -c1-120)
if [ "$CONTRIBUTOR_TYPE" != "anonymous" ] && [ -z "$CONTRIBUTOR_VALUE" ]; then
  log "WARNING: Recognition was requested without a value; using anonymous."
  CONTRIBUTOR_TYPE="anonymous"
fi
CONTRIBUTOR_VALUE_JSON=$(printf '%s' "$CONTRIBUTOR_VALUE" | jq -Rs '.')

if [ ! -d "$SWITCH_VISION_ROOT" ]; then
  log "ERROR: Switch Vision data folder was not found: $SWITCH_VISION_ROOT"
  exit 1
fi

mkdir -p "$CONTRIBUTIONS_DIR"
COUNTER_FILE="$CONTRIBUTIONS_DIR/.contribution-counter"
LOCK_DIR="$CONTRIBUTIONS_DIR/.contribution-counter.lock"

tries=0
while ! mkdir "$LOCK_DIR" 2>/dev/null; do
  tries=$((tries + 1))
  if [ "$tries" -ge 50 ]; then
    log "ERROR: Could not acquire contribution counter lock."
    exit 1
  fi
  sleep 0.1
done
trap 'rm -rf "$LOCK_DIR" "${WORK_DIR:-}"' EXIT INT TERM

year=$(date +%Y)
last_year=""
last_number=0
if [ -f "$COUNTER_FILE" ]; then
  IFS=':' read -r last_year last_number < "$COUNTER_FILE" || true
fi
case "$last_number" in
  ''|*[!0-9]*) last_number=0 ;;
esac
if [ "$last_year" != "$year" ]; then
  last_number=0
fi
next_number=$((last_number + 1))
printf '%s:%s\n' "$year" "$next_number" > "$COUNTER_FILE"
rm -rf "$LOCK_DIR"

CONTRIBUTION_ID=$(printf 'SV-%s-%06d' "$year" "$next_number")
STAMP=$(date +%Y%m%d-%H%M%S)
BUNDLE_NAME="Switch_Vision_Contribution_${CONTRIBUTION_ID}_${STAMP}.zip"
BUNDLE_PATH="$CONTRIBUTIONS_DIR/$BUNDLE_NAME"
WORK_DIR=$(mktemp -d /tmp/switch-vision-contribution.XXXXXX)
BUNDLE_ROOT="$WORK_DIR/Support_My_Switch_${CONTRIBUTION_ID}"
DATA_COPY="$BUNDLE_ROOT/switch_vision"
SANITIZATION_JSON_TMP="$WORK_DIR/sanitization-result.json"
mkdir -p "$DATA_COPY"

log "Preparing contribution..."
log "Contribution ID: $CONTRIBUTION_ID"
log "Copying Switch Vision data..."

cp -a "$SWITCH_VISION_ROOT/." "$DATA_COPY/"
rm -rf "$DATA_COPY/contributions"

CREATED_AT=$(date -Iseconds)
DEVICE_SUMMARY_FILE="$BUNDLE_ROOT/DEVICE_SUMMARY.json"
FINGERPRINT_FILE="$BUNDLE_ROOT/DEVICE_FINGERPRINTS.json"
DATA_SANITIZATION_JSON="$WORK_DIR/data-sanitization-result.json"
FINAL_SANITIZATION_JSON="$WORK_DIR/final-sanitization-result.json"
COMBINED_SANITIZATION_JSON="$WORK_DIR/combined-sanitization-result.json"
printf '%s\n' "$CONTRIBUTION_ID" > "$BUNDLE_ROOT/Contribution_ID.txt"

case "$CONTRIBUTOR_TYPE" in
  first_name) RECOGNITION_LABEL="First name" ;;
  full_name) RECOGNITION_LABEL="Full name" ;;
  github) RECOGNITION_LABEL="GitHub username" ;;
  forum) RECOGNITION_LABEL="Forum username" ;;
  *) RECOGNITION_LABEL="Anonymous" ;;
esac
if [ "$CONTRIBUTOR_TYPE" = "anonymous" ]; then
  RECOGNITION_DISPLAY="Anonymous"
else
  RECOGNITION_DISPLAY="$RECOGNITION_LABEL: $CONTRIBUTOR_VALUE"
fi

cat > "$BUNDLE_ROOT/EMAIL_TEMPLATE.txt" <<EOF_EMAIL
To: switch-vision@zemerdon.com
Subject: Support My Switch - $CONTRIBUTION_ID

Hello,

Please find attached my Switch Vision contribution bundle:
$BUNDLE_NAME

Contribution ID: $CONTRIBUTION_ID
Recognition preference: $RECOGNITION_DISPLAY

What works:

What is missing or incorrect:

Anything unusual about this switch:

Thank you.
EOF_EMAIL

# First sanitize the copied Switch Vision folder. Device metadata is then derived
# from the privacy-processed capability files so raw names cannot be reintroduced.
log "Applying privacy protection to the copied data..."
python3 "$SANITIZER_SCRIPT" "$DATA_COPY" "$DATA_SANITIZATION_JSON" \
  --mask-management-ips "$MASK_MANAGEMENT_IPS" \
  --mask-mac-addresses "$MASK_MAC_ADDRESSES" \
  --mask-hostnames "$MASK_HOSTNAMES" \
  --mask-vlan-names "$MASK_VLAN_NAMES" \
  --mask-interface-descriptions "$MASK_INTERFACE_DESCRIPTIONS" >/dev/null

CAP_FILES=$(find "$DATA_COPY" -type f -path '*/capabilities/*-capabilities.json' 2>/dev/null | sort || true)
if [ -n "$CAP_FILES" ]; then
  # Re-run registry enrichment on the privacy-processed copies so Support My
  # Switch uses the same canonical model lookup as Discovery and diagnostics.
  if [ -f "$REGISTRY_LOOKUP_SCRIPT" ] && [ -f "$REGISTRY_FILE" ]; then
    printf '%s\n' "$CAP_FILES" | while IFS= read -r cap_file; do
      [ -n "$cap_file" ] || continue
      cap_model=$(jq -r '.device.detected_model_text // .device.model_text // .device.model // ""' "$cap_file")
      [ -n "$cap_model" ] || continue
      python3 "$REGISTRY_LOOKUP_SCRIPT" --registry "$REGISTRY_FILE" --model "$cap_model" --enrich "$cap_file" --enrich-key registry
      cap_tmp="${cap_file}.tmp"
      jq 'if (.registry.match // false) then .device.support_status=(.registry.status // .device.support_status) else . end' "$cap_file" > "$cap_tmp" && mv "$cap_tmp" "$cap_file"
    done
  fi
  # shellcheck disable=SC2086
  jq -s '[.[] | {
      source_walk: (.source_walk // ""),
      vendor: (.device.vendor // "unknown"),
      vendor_name: (.device.vendor_name // "Unknown"),
      family: (.device.family // "unknown"),
      model: (.device.detected_model_text // .device.model_text // "unknown"),
      detected_model: (.device.detected_model_text // .device.model_text // "unknown"),
      selected_model_override: (.device.model_override // null),
      effective_model: (.device.effective_model_text // .device.model_text // "unknown"),
      compatibility_mode: (.device.compatibility_mode // false),
      sys_object_id: (.device.sys_object_id // "unknown"),
      sys_name: (.device.sys_name // ""),
      support_status: (.registry.status // .device.support_status // "unknown"),
      registry_match: (.registry.match // false),
      registry_status: (.registry.status // "detected"),
      registry_last_validated_version: (.registry.last_validated_version // ""),
      registry_validation: (.registry.validation // {}),
      interface_count: (.summary.interface_count // 0),
      physical_count: (.summary.physical_count // 0),
      rj45_count: (.summary.rj45_count // 0),
      sfp_count: (.summary.sfp_count // 0),
      sfp_plus_count: (.summary.sfp_plus_count // 0),
      sfp28_count: (.summary.sfp28_count // 0),
      uplink_count: (.summary.uplink_count // ((.summary.sfp_count // 0) + (.summary.sfp_plus_count // 0) + (.summary.sfp28_count // 0))),
      stack_count: (.summary.stack_count // 0)
    }]' $CAP_FILES > "$DEVICE_SUMMARY_FILE"
else
  printf '[]\n' > "$DEVICE_SUMMARY_FILE"
fi

# Add normalized UniFi2MQTT devices from the already-sanitized snapshot so a
# UniFi-only contribution still has complete device summary/fingerprint data.
UNIFI_SUMMARY_SNAPSHOT="$DATA_COPY/unifi/devices.json"
if [ -f "$UNIFI_SUMMARY_SNAPSHOT" ]; then
  python3 - "$DEVICE_SUMMARY_FILE" "$UNIFI_SUMMARY_SNAPSHOT" "$REGISTRY_FILE" <<'PY_UNIFI_SUMMARY'
import json, re, sys
from pathlib import Path

summary_path, snapshot_path, registry_path = map(Path, sys.argv[1:4])
try:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    summary = []
try:
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    snapshot = {}
try:
    registry_doc = json.loads(registry_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    registry_doc = {}
if not isinstance(summary, list):
    summary = []
registry_devices = registry_doc.get("devices") if isinstance(registry_doc, dict) else []
if not isinstance(registry_devices, list):
    registry_devices = []

def canonical(value):
    text = " ".join(str(value or "").strip().split()).casefold()
    for prefix in ("unknown ubiquiti ", "ubiquiti unifi ", "ubiquiti ", "unknown "):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    return re.sub(r"[^a-z0-9]+", "", text)

def lookup(model):
    wanted = canonical(model)
    for item in registry_devices:
        if isinstance(item, dict) and canonical(item.get("model")) == wanted:
            return item
    return {}

for device in snapshot.get("devices", []) if isinstance(snapshot, dict) else []:
    if not isinstance(device, dict):
        continue
    model = str(device.get("model") or "Unknown")
    reg = lookup(model)
    validation = reg.get("validation") if isinstance(reg.get("validation"), dict) else {}
    ports = device.get("ports") if isinstance(device.get("ports"), list) else []
    rj45 = [p for p in ports if isinstance(p, dict) and str(p.get("connector") or "").upper() == "RJ45"]
    sfp = [p for p in ports if isinstance(p, dict) and str(p.get("connector") or "").upper() == "SFP"]
    sfp_plus = [p for p in ports if isinstance(p, dict) and str(p.get("connector") or "").upper() in {"SFPPLUS", "SFP+"}]
    sfp28 = [p for p in ports if isinstance(p, dict) and str(p.get("connector") or "").upper() == "SFP28"]
    uplinks = sfp + sfp_plus + sfp28
    summary.append({
        "source_walk": "",
        "data_source": "unifi_api",
        "vendor": "Ubiquiti",
        "vendor_name": str(device.get("name") or "masked-switch"),
        "family": reg.get("family") or "UniFi",
        "model": model,
        "detected_model": model,
        "selected_model_override": None,
        "effective_model": model,
        "compatibility_mode": False,
        "sys_object_id": "unifi-api",
        "sys_name": str(device.get("name") or "masked-switch"),
        "support_status": reg.get("status") or "detected",
        "registry_match": bool(reg),
        "registry_status": reg.get("status") or "detected",
        "registry_last_validated_version": reg.get("last_validated_version") or "",
        "registry_validation": validation,
        "interface_count": len(ports),
        "physical_count": len(ports),
        "rj45_count": len(rj45),
        "sfp_count": len(sfp),
        "sfp_plus_count": len(sfp_plus),
        "sfp28_count": len(sfp28),
        "uplink_count": len(uplinks),
        "stack_count": 0,
        "api_capabilities": device.get("api_capabilities") if isinstance(device.get("api_capabilities"), dict) else {},
    })
summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
PY_UNIFI_SUMMARY
fi

jq -c '.[]' "$DEVICE_SUMMARY_FILE" | while IFS= read -r device; do
  canonical=$(printf '%s' "$device" | jq -r '[.vendor,(if (.data_source == "unifi_api" and (.model == "UDM Pro Max" or .model == "USW Pro XG 24 PoE")) then "UniFi" else .family end),.model,.sys_object_id,.physical_count,.rj45_count,((.sfp_count // 0) + (.sfp_plus_count // 0)),.stack_count] | map(tostring) | join("|")')
  fingerprint=$(printf '%s' "$canonical" | sha256sum | awk '{print $1}')
  printf '%s\n' "$device" | jq --arg canonical "$canonical" --arg fingerprint "$fingerprint" '. + {fingerprint_source:$canonical, fingerprint_sha256:$fingerprint}'
done | jq -s '.' > "$FINGERPRINT_FILE"

PRIMARY_FINGERPRINT=$(jq -r '.[0].fingerprint_sha256 // "unavailable"' "$FINGERPRINT_FILE")
DEVICE_COUNT=$(jq 'length' "$DEVICE_SUMMARY_FILE")
FILE_COUNT=$(find "$DATA_COPY" -type f | wc -l | tr -d ' ')
TOTAL_BYTES=$(du -sb "$DATA_COPY" 2>/dev/null | awk '{print $1}')
[ -n "$TOTAL_BYTES" ] || TOTAL_BYTES=0

cat > "$BUNDLE_ROOT/README.txt" <<EOF_README
Switch Vision - Support My Switch contribution bundle

Contribution ID: $CONTRIBUTION_ID
Created: $CREATED_AT
Devices detected: $DEVICE_COUNT
Primary device fingerprint: $PRIMARY_FINGERPRINT

This bundle contains a privacy-processed copy of the complete Switch Vision
data folder, except for the contributions folder itself. The live Switch
Vision folder was not modified.

Privacy protection was applied according to SANITIZATION_REPORT.txt. Always
review the archive before sharing it because automated masking cannot identify
every possible piece of private or identifying information. If BUNDLE_QUALITY.txt
says REVIEW REQUIRED, do not share the archive until the listed issues have been
reviewed.

Contributor recognition: $RECOGNITION_DISPLAY

Next steps:
1. Review this archive and SANITIZATION_REPORT.txt.
2. Use EMAIL_TEMPLATE.txt to prepare your message.
3. Attach the ZIP and send it to switch-vision@zemerdon.com.

Support contact: switch-vision@zemerdon.com
EOF_README

# Run a second pass over the complete bundle root. This catches any identifying
# values introduced into generated bundle metadata and performs a residual audit.
python3 "$BASE_SANITIZER_SCRIPT" "$BUNDLE_ROOT" "$FINAL_SANITIZATION_JSON" \
  --mask-management-ips "$MASK_MANAGEMENT_IPS" \
  --mask-mac-addresses "$MASK_MAC_ADDRESSES" \
  --mask-hostnames "$MASK_HOSTNAMES" \
  --mask-vlan-names "$MASK_VLAN_NAMES" \
  --mask-interface-descriptions "$MASK_INTERFACE_DESCRIPTIONS" >/dev/null

jq -s '
  def addcounts(a;b): reduce (((a|keys_unsorted) + (b|keys_unsorted) | unique)[]) as $k ({}; .[$k] = ((a[$k] // 0) + (b[$k] // 0)));
  .[0] as $a | .[1] as $b |
  (addcounts($a.counts; $b.counts)) as $counts |
  {
    sanitization_version: 13,
    secrets_always_removed: true,
    serial_numbers_always_masked: true,
    options: $b.options,
    counts: $counts,
    processing_complete: (($a.processing_complete // false) and ($b.processing_complete // false)),
    processing_issue_count: (($a.processing_issue_count // 0) + ($b.processing_issue_count // 0)),
    processing_issues: ((($a.processing_issues // []) + ($b.processing_issues // [])) | unique_by(.file_id, .reason)),
    processing_issues_truncated: (($a.processing_issues_truncated // 0) + ($b.processing_issues_truncated // 0)),
    residual_audit: $b.residual_audit,
    audit_categories: $b.audit_categories,
    enabled_category_leaks_found: $b.enabled_category_leaks_found,
    observed_values: $b.observed_values,
    disabled_category_warnings: $b.disabled_category_warnings,
    disabled_category_warnings_found: $b.disabled_category_warnings_found,
    review_required_reasons: ([
      if (((($a.processing_complete // false) and ($b.processing_complete // false))) | not) then "privacy_processing_incomplete" else empty end,
      if $b.enabled_category_leaks_found then "enabled_privacy_category_leaks" else empty end
    ]),
    warning: $b.warning
  }
' "$DATA_SANITIZATION_JSON" "$FINAL_SANITIZATION_JSON" > "$COMBINED_SANITIZATION_JSON"
cp "$COMBINED_SANITIZATION_JSON" "$BUNDLE_ROOT/SANITIZATION_REPORT.json"

SECRETS_REMOVED=$(jq -r '.counts.secrets_removed + .counts.url_credentials_removed + .counts.cli_credentials_removed + .counts.authorization_headers_removed + .counts.entity_logical_communities_removed + .counts.csv_community_values_removed' "$COMBINED_SANITIZATION_JSON")
SERIALS_MASKED=$(jq -r '.counts.serial_numbers_masked // 0' "$COMBINED_SANITIZATION_JSON")
FILES_SCANNED=$(jq -r '.counts.files_scanned' "$COMBINED_SANITIZATION_JSON")
FILES_CHANGED=$(jq -r '.counts.files_changed' "$COMBINED_SANITIZATION_JSON")
IPS_MASKED=$(jq -r '.counts.ip_addresses_masked' "$COMBINED_SANITIZATION_JSON")
MACS_MASKED=$(jq -r '.counts.mac_addresses_masked' "$COMBINED_SANITIZATION_JSON")
HOSTS_MASKED=$(jq -r '.counts.hostnames_masked' "$COMBINED_SANITIZATION_JSON")
VLANS_MASKED=$(jq -r '.counts.vlan_names_masked' "$COMBINED_SANITIZATION_JSON")
DESCRIPTIONS_MASKED=$(jq -r '.counts.interface_descriptions_masked' "$COMBINED_SANITIZATION_JSON")
LEAKS_FOUND=$(jq -r '.enabled_category_leaks_found' "$COMBINED_SANITIZATION_JSON")
PROCESSING_COMPLETE=$(jq -r '.processing_complete // false' "$COMBINED_SANITIZATION_JSON")
PROCESSING_ISSUE_COUNT=$(jq -r '.processing_issue_count // 0' "$COMBINED_SANITIZATION_JSON")
BINARY_FILES_SKIPPED=$(jq -r '.counts.binary_files_skipped // 0' "$COMBINED_SANITIZATION_JSON")
OVERSIZED_FILES_SKIPPED=$(jq -r '.counts.oversized_files_skipped // 0' "$COMBINED_SANITIZATION_JSON")
READ_ERRORS=$(jq -r '.counts.read_errors // 0' "$COMBINED_SANITIZATION_JSON")
WRITE_ERRORS=$(jq -r '.counts.write_errors // 0' "$COMBINED_SANITIZATION_JSON")
SYMLINKS_SKIPPED=$(jq -r '.counts.symlinks_skipped // 0' "$COMBINED_SANITIZATION_JSON")
SPECIAL_FILES_SKIPPED=$(jq -r '.counts.special_files_skipped // 0' "$COMBINED_SANITIZATION_JSON")
FILES_EXCLUDED=$(jq -r '.counts.files_excluded // 0' "$COMBINED_SANITIZATION_JSON")
PROCESSING_ISSUES_JSON=$(jq -c '.processing_issues // []' "$COMBINED_SANITIZATION_JSON")
PROCESSING_ISSUE_LINES=$(jq -r '.processing_issues[]? | "- File ID \(.file_id): \(.reason), suffix \(.suffix), size \(.size_bytes // "unknown") bytes"' "$COMBINED_SANITIZATION_JSON")
[ -n "$PROCESSING_ISSUE_LINES" ] || PROCESSING_ISSUE_LINES="- None"
PRIVACY_WARNINGS_FOUND=$(jq -r '.disabled_category_warnings_found // false' "$COMBINED_SANITIZATION_JSON")
OBSERVED_ALIASES=$(jq -r '.observed_values.interface_aliases // 0' "$COMBINED_SANITIZATION_JSON")
OBSERVED_VLANS=$(jq -r '.observed_values.vlan_labels // 0' "$COMBINED_SANITIZATION_JSON")
RESIDUAL_CREDENTIALS=$(jq -r '.audit_categories.credentials.remaining // 0' "$COMBINED_SANITIZATION_JSON")
RESIDUAL_SERIALS=$(jq -r '.audit_categories.serial_numbers.remaining // 0' "$COMBINED_SANITIZATION_JSON")
RESIDUAL_PRIVATE_IPS=$(jq -r '.audit_categories.private_ipv4.remaining // "not enforced"' "$COMBINED_SANITIZATION_JSON")
RESIDUAL_MACS=$(jq -r '.audit_categories.mac_addresses.remaining // "not enforced"' "$COMBINED_SANITIZATION_JSON")
RESIDUAL_HOSTS=$(jq -r '.audit_categories.hostnames.remaining // "not enforced"' "$COMBINED_SANITIZATION_JSON")
RESIDUAL_UNIFI_DEVICE_IDS=$(jq -r '.audit_categories.unifi_device_ids.remaining // 0' "$COMBINED_SANITIZATION_JSON")
RESIDUAL_UNIFI_DASHBOARD_IDS=$(jq -r '.audit_categories.unifi_dashboard_ids.remaining // 0' "$COMBINED_SANITIZATION_JSON")
RESIDUAL_UNIFI_DASHBOARD_NAMES=$(jq -r '.audit_categories.unifi_dashboard_names.remaining // "not enforced"' "$COMBINED_SANITIZATION_JSON")
RESIDUAL_ALIASES=$(jq -r '.audit_categories.interface_aliases.remaining // "not enforced"' "$COMBINED_SANITIZATION_JSON")
RESIDUAL_VLANS=$(jq -r '.audit_categories.vlan_labels.remaining // "not enforced"' "$COMBINED_SANITIZATION_JSON")

privacy_audit_line() {
  label="$1"
  enabled="$2"
  count="$3"
  if [ "$enabled" = "true" ]; then
    printf '%s: %s' "$label" "$count"
  else
    printf '%s: not enforced - masking disabled' "$label"
  fi
}
CREDENTIAL_AUDIT="Credential values remaining: $RESIDUAL_CREDENTIALS"
SERIAL_AUDIT="Serial number values remaining: $RESIDUAL_SERIALS"
PRIVATE_IP_AUDIT=$(privacy_audit_line "Private IPv4 values remaining" "$MASK_MANAGEMENT_IPS" "$RESIDUAL_PRIVATE_IPS")
MAC_AUDIT=$(privacy_audit_line "Unmasked MAC values remaining" "$MASK_MAC_ADDRESSES" "$RESIDUAL_MACS")
HOST_AUDIT=$(privacy_audit_line "Hostname fields remaining" "$MASK_HOSTNAMES" "$RESIDUAL_HOSTS")
UNIFI_DASHBOARD_NAME_AUDIT=$(privacy_audit_line "UniFi dashboard names remaining" "$MASK_HOSTNAMES" "$RESIDUAL_UNIFI_DASHBOARD_NAMES")
ALIAS_AUDIT=$(privacy_audit_line "Interface alias values remaining" "$MASK_INTERFACE_DESCRIPTIONS" "$RESIDUAL_ALIASES")
VLAN_AUDIT=$(privacy_audit_line "VLAN labels remaining" "$MASK_VLAN_NAMES" "$RESIDUAL_VLANS")

if [ "$PROCESSING_COMPLETE" != "true" ] || [ "$LEAKS_FOUND" = "true" ]; then
  BUNDLE_QUALITY="REVIEW REQUIRED"
  BUNDLE_READY=false
  if [ "$PROCESSING_COMPLETE" != "true" ] && [ "$LEAKS_FOUND" = "true" ]; then
    QUALITY_MESSAGE="Privacy processing was incomplete and the final audit found values in enabled privacy categories. Do not share this archive until it has been reviewed."
  elif [ "$PROCESSING_COMPLETE" != "true" ]; then
    QUALITY_MESSAGE="One or more files could not be fully inspected or sanitized and were excluded from the archive. Review the processing issues before sharing."
  else
    QUALITY_MESSAGE="The final privacy audit found values in one or more enabled privacy categories. Review the sanitization report before sharing."
  fi
elif [ "$PRIVACY_WARNINGS_FOUND" = "true" ]; then
  BUNDLE_QUALITY="PASS WITH PRIVACY WARNINGS"
  BUNDLE_READY=true
  QUALITY_MESSAGE="All files were inspected, and no enabled privacy-category leaks were detected. Descriptive interface aliases or VLAN labels remain because their masking options were disabled; review the archive before sharing."
else
  BUNDLE_QUALITY="PASS"
  BUNDLE_READY=true
  QUALITY_MESSAGE="All files were inspected and no enabled privacy-category leaks were detected. A quick manual review is still recommended before sharing."
fi
cat > "$BUNDLE_ROOT/BUNDLE_QUALITY.txt" <<EOF_QUALITY
Bundle Quality: $BUNDLE_QUALITY
Contribution ID: $CONTRIBUTION_ID

$QUALITY_MESSAGE

Privacy processing:
- Complete: $PROCESSING_COMPLETE
- Files requiring review: $PROCESSING_ISSUE_COUNT
- Unsupported binary files excluded: $BINARY_FILES_SKIPPED
- Oversized files excluded: $OVERSIZED_FILES_SKIPPED
- Read errors: $READ_ERRORS
- Write errors: $WRITE_ERRORS
- Symbolic links excluded: $SYMLINKS_SKIPPED
- Special files excluded: $SPECIAL_FILES_SKIPPED
- Total files excluded from the archive: $FILES_EXCLUDED

Residual audit:
- $CREDENTIAL_AUDIT
- $SERIAL_AUDIT
- $PRIVATE_IP_AUDIT
- $MAC_AUDIT
- $HOST_AUDIT
- UniFi device IDs remaining: $RESIDUAL_UNIFI_DEVICE_IDS
- UniFi dashboard IDs remaining: $RESIDUAL_UNIFI_DASHBOARD_IDS
- $UNIFI_DASHBOARD_NAME_AUDIT
- $ALIAS_AUDIT
- $VLAN_AUDIT
- Descriptive interface aliases observed: $OBSERVED_ALIASES
- VLAN labels observed: $OBSERVED_VLANS
EOF_QUALITY

cat > "$BUNDLE_ROOT/SANITIZATION_REPORT.txt" <<EOF_SAN
Sanitization status: APPLIED

The live Switch Vision folder was not modified. Privacy processing was applied
only to the temporary copy used for this archive.

Always applied:
- Credential-like configuration values removed: $SECRETS_REMOVED
- Device serial numbers masked: $SERIALS_MASKED

Selected privacy options:
- Mask management IP addresses: $MASK_MANAGEMENT_IPS ($IPS_MASKED replacements)
- Mask MAC addresses: $MASK_MAC_ADDRESSES ($MACS_MASKED replacements)
- Mask hostnames and domains: $MASK_HOSTNAMES ($HOSTS_MASKED replacements)
- Mask VLAN names: $MASK_VLAN_NAMES ($VLANS_MASKED replacements)
- Mask interface descriptions: $MASK_INTERFACE_DESCRIPTIONS ($DESCRIPTIONS_MASKED replacements)

Processing summary:
- Text files scanned across both passes: $FILES_SCANNED
- Files changed across both passes: $FILES_CHANGED
- Complete privacy processing: $PROCESSING_COMPLETE
- Files requiring review: $PROCESSING_ISSUE_COUNT
- Unsupported binary files excluded: $BINARY_FILES_SKIPPED
- Oversized files excluded: $OVERSIZED_FILES_SKIPPED
- Read errors: $READ_ERRORS
- Write errors: $WRITE_ERRORS
- Symbolic links excluded: $SYMLINKS_SKIPPED
- Special files excluded: $SPECIAL_FILES_SKIPPED
- Total files excluded from the archive: $FILES_EXCLUDED

Excluded files requiring review (privacy-safe identifiers):
$PROCESSING_ISSUE_LINES

Final residual audit for enabled privacy categories:
- $CREDENTIAL_AUDIT
- $SERIAL_AUDIT
- $PRIVATE_IP_AUDIT
- $MAC_AUDIT
- $HOST_AUDIT
- UniFi device IDs remaining: $RESIDUAL_UNIFI_DEVICE_IDS
- UniFi dashboard IDs remaining: $RESIDUAL_UNIFI_DASHBOARD_IDS
- $UNIFI_DASHBOARD_NAME_AUDIT
- $ALIAS_AUDIT
- $VLAN_AUDIT
- Enabled-category leaks found: $LEAKS_FOUND

IMPORTANT
Automated masking reduces common privacy risks but cannot guarantee that all
identifying information was removed. Review the archive before sharing it.
EOF_SAN

# Count the complete archive payload, including generated metadata and the
# manifest itself. The previous count only covered the copied data directory.
FILE_COUNT=$(( $(find "$BUNDLE_ROOT" -type f | wc -l | tr -d ' ') + 1 ))
TOTAL_BYTES=$(du -sb "$BUNDLE_ROOT" 2>/dev/null | awk '{print $1}')
[ -n "$TOTAL_BYTES" ] || TOTAL_BYTES=0

UNIFI_DIAGNOSTICS_JSON="null"
UNIFI_DIAGNOSTICS_FILE="$DATA_COPY/unifi/diagnostics.json"

if [ -f "$UNIFI_DIAGNOSTICS_FILE" ]; then
  UNIFI_DIAGNOSTICS_JSON=$(
    jq -c '{
      file: "switch_vision/unifi/diagnostics.json",
      version: (.version // null),
      status: (.status // null),
      stage: (.stage // null),
      adopted_devices: (.adopted_devices // 0),
      switching_devices: (.switching_devices // 0),
      rejected_devices: (.rejected_devices // 0),
      empty_switch_polls: (.empty_switch_polls // 0),
      error_type: (.error_type // null)
    }' "$UNIFI_DIAGNOSTICS_FILE" 2>/dev/null \
      || printf 'null'
  )
fi

cat > "$BUNDLE_ROOT/MANIFEST.json" <<EOF_MANIFEST
{
  "bundle_version": $BUNDLE_VERSION,
  "bundle_type": "support_my_switch",
  "contribution_id": "$CONTRIBUTION_ID",
  "created_at": "$CREATED_AT",
  "switch_vision_version": "$VERSION",
  "source_path": "$SWITCH_VISION_ROOT",
  "contributions_excluded": true,
  "sanitized": true,
  "privacy_review_required": true,
  "bundle_quality": "$BUNDLE_QUALITY",
  "ready_to_send": $BUNDLE_READY,
  "recognition": {
    "type": "$CONTRIBUTOR_TYPE",
    "value": $CONTRIBUTOR_VALUE_JSON
  },
  "prepared_email_file": "EMAIL_TEMPLATE.txt",
  "bundle_quality_file": "BUNDLE_QUALITY.txt",
  "privacy_options": {
    "secrets_always_removed": true,
    "serial_numbers_always_masked": true,
    "mask_management_ips": $MASK_MANAGEMENT_IPS,
    "mask_mac_addresses": $MASK_MAC_ADDRESSES,
    "mask_hostnames": $MASK_HOSTNAMES,
    "mask_vlan_names": $MASK_VLAN_NAMES,
    "mask_interface_descriptions": $MASK_INTERFACE_DESCRIPTIONS
  },
  "sanitization_counts": {
    "credential_values_removed": $SECRETS_REMOVED,
    "serial_numbers_masked": $SERIALS_MASKED,
    "ip_addresses_masked": $IPS_MASKED,
    "mac_addresses_masked": $MACS_MASKED,
    "hostnames_masked": $HOSTS_MASKED,
    "vlan_names_masked": $VLANS_MASKED,
    "interface_descriptions_masked": $DESCRIPTIONS_MASKED,
    "files_scanned": $FILES_SCANNED,
    "files_changed": $FILES_CHANGED
  },
  "sanitization_processing": {
    "version": 13,
    "complete": $PROCESSING_COMPLETE,
    "issue_count": $PROCESSING_ISSUE_COUNT,
    "binary_files_skipped": $BINARY_FILES_SKIPPED,
    "oversized_files_skipped": $OVERSIZED_FILES_SKIPPED,
    "read_errors": $READ_ERRORS,
    "write_errors": $WRITE_ERRORS,
    "symlinks_skipped": $SYMLINKS_SKIPPED,
    "special_files_skipped": $SPECIAL_FILES_SKIPPED,
    "files_excluded": $FILES_EXCLUDED,
    "issues": $PROCESSING_ISSUES_JSON
  },
  "residual_audit": {
    "credentials": {"enforced": true, "remaining": $RESIDUAL_CREDENTIALS},
    "serial_numbers": {"enforced": true, "remaining": $RESIDUAL_SERIALS},
    "private_ipv4": {"enforced": $MASK_MANAGEMENT_IPS, "remaining": $( [ "$MASK_MANAGEMENT_IPS" = "true" ] && printf '%s' "$RESIDUAL_PRIVATE_IPS" || printf 'null' )},
    "mac_addresses": {"enforced": $MASK_MAC_ADDRESSES, "remaining": $( [ "$MASK_MAC_ADDRESSES" = "true" ] && printf '%s' "$RESIDUAL_MACS" || printf 'null' )},
    "hostnames": {"enforced": $MASK_HOSTNAMES, "remaining": $( [ "$MASK_HOSTNAMES" = "true" ] && printf '%s' "$RESIDUAL_HOSTS" || printf 'null' )},
    "unifi_device_ids": {"enforced": true, "remaining": $RESIDUAL_UNIFI_DEVICE_IDS},
    "unifi_dashboard_ids": {"enforced": true, "remaining": $RESIDUAL_UNIFI_DASHBOARD_IDS},
    "unifi_dashboard_names": {"enforced": $MASK_HOSTNAMES, "remaining": $( [ "$MASK_HOSTNAMES" = "true" ] && printf '%s' "$RESIDUAL_UNIFI_DASHBOARD_NAMES" || printf 'null' )},
    "interface_aliases": {"enforced": $MASK_INTERFACE_DESCRIPTIONS, "remaining": $( [ "$MASK_INTERFACE_DESCRIPTIONS" = "true" ] && printf '%s' "$RESIDUAL_ALIASES" || printf 'null' )},
    "vlan_labels": {"enforced": $MASK_VLAN_NAMES, "remaining": $( [ "$MASK_VLAN_NAMES" = "true" ] && printf '%s' "$RESIDUAL_VLANS" || printf 'null' )},
    "enabled_category_leaks_found": $LEAKS_FOUND
  },
  "unifi_diagnostics": $UNIFI_DIAGNOSTICS_JSON,
  "file_count": $FILE_COUNT,
  "total_bytes": $TOTAL_BYTES,
  "device_count": $DEVICE_COUNT,
  "primary_device_fingerprint": "$PRIMARY_FINGERPRINT",
  "device_summary_file": "DEVICE_SUMMARY.json",
  "device_fingerprints_file": "DEVICE_FINGERPRINTS.json",
  "sanitization_report_file": "SANITIZATION_REPORT.json"
}
EOF_MANIFEST

if [ "$PROCESSING_COMPLETE" != "true" ]; then
  log "WARNING: Privacy processing was incomplete for $PROCESSING_ISSUE_COUNT file(s)."
  log "This bundle requires review and is not marked ready to send."
fi
if [ "$LEAKS_FOUND" = "true" ]; then
  log "WARNING: The final privacy audit found values in enabled privacy categories."
  log "Review SANITIZATION_REPORT.txt before sharing this archive."
fi

log "Creating archive..."
(
  cd "$WORK_DIR"
  zip -qr "$BUNDLE_PATH" "$(basename "$BUNDLE_ROOT")"
)

if [ ! -s "$BUNDLE_PATH" ]; then
  log "ERROR: Bundle was not created."
  exit 1
fi

EMAIL_PATH="$CONTRIBUTIONS_DIR/Switch_Vision_Contribution_${CONTRIBUTION_ID}_${STAMP}.eml"
ACTIONS_PATH="$CONTRIBUTIONS_DIR/Switch_Vision_Contribution_${CONTRIBUTION_ID}_${STAMP}_Actions.html"
if [ "$BUNDLE_READY" = "true" ]; then
  log "Preparing email with the contribution archive attached..."
  python3 "$EMAIL_BUILDER_SCRIPT" \
    --archive "$BUNDLE_PATH" \
    --manifest "$BUNDLE_ROOT/MANIFEST.json" \
    --output-eml "$EMAIL_PATH" \
    --output-html "$ACTIONS_PATH"
  if [ ! -s "$EMAIL_PATH" ]; then
    log "ERROR: Prepared email was not created."
    exit 1
  fi
else
  rm -f "$EMAIL_PATH" "$ACTIONS_PATH"
  log "Prepared email withheld because the bundle requires privacy review."
fi

ARCHIVE_BYTES=$(du -b "$BUNDLE_PATH" 2>/dev/null | awk '{print $1}')
[ -n "$ARCHIVE_BYTES" ] || ARCHIVE_BYTES=0
ARCHIVE_SIZE=$(du -h "$BUNDLE_PATH" 2>/dev/null | awk '{print $1}')
[ -n "$ARCHIVE_SIZE" ] || ARCHIVE_SIZE="unknown"

log ""
log "Support My Switch Summary"
log "-------------------------"
log "Contribution ID: $CONTRIBUTION_ID"
log "Devices detected: $DEVICE_COUNT"
log "Primary fingerprint: $PRIMARY_FINGERPRINT"
log "Files archived: $FILE_COUNT"
log "Source data size: $TOTAL_BYTES bytes"
log "Archive size: $ARCHIVE_SIZE ($ARCHIVE_BYTES bytes)"
log ""
log "Bundle Quality"
log "--------------"
log "$BUNDLE_QUALITY"
log "$QUALITY_MESSAGE"
log ""
log "Contributor recognition: $RECOGNITION_DISPLAY"
log ""
log "Privacy Protection"
log "------------------"
if [ "$PROCESSING_COMPLETE" = "true" ]; then
  log "Applied successfully. A quick review is still recommended before sharing."
else
  log "Incomplete: $FILES_EXCLUDED file(s) were excluded and the archive requires review."
fi
log "Credentials removed: $SECRETS_REMOVED"
log "IPs / MACs / hostnames masked: $IPS_MASKED / $MACS_MASKED / $HOSTS_MASKED"
log ""
log "Next Step"
log "---------"
log "Review the archive, then email it to switch-vision@zemerdon.com"
if [ "$BUNDLE_READY" = "true" ]; then
  log "Open the prepared .eml file to review an email with the ZIP attached."
  log "Prepared email: $EMAIL_PATH"
  log "Action page: $ACTIONS_PATH"
else
  log "No prepared email was created because this archive requires review."
fi
log "Archive: $BUNDLE_PATH"
log "Done. Thank you for helping improve Switch Vision."
