#!/usr/bin/env python3
from pathlib import Path

SOURCE = Path(__file__).with_name("support_web.py").read_text(encoding="utf-8")

# UI/UX refinement must remain a presentation layer: keep existing workflows
# and controls while improving hierarchy, feedback, and responsive behavior.
for marker in (
    ".sv-feedback{",
    ".sv-feedback.is-loading",
    "function setFeedback(id,text,state='info')",
    "device-summary-title-row",
    "device-health-chip",
    "device-summary-facts",
    "function deviceSummaryFact(label,value)",
    "device-details-label",
    "function advsec(t,p='')",
    "advsec('Activity LED tuning'",
    "advsec('Paths & SNMP timing'",
    "advsec('Discovery configuration backups'",
    "@media(max-width:900px)",
    "@media(max-width:760px)",
    "@media(max-width:520px)",
    "--sv-touch-target:44px",
    "body[class*=\"width-\"] main{width:100%!important}",
    "setFeedback('discoveryStatus',label,feedbackState)",
    "setFeedback('configuredDevicesStatus'",
    "setFeedback('devicesActionStatus'",
    "setFeedback('unifiSettingsStatus'",
):
    assert marker in SOURCE, marker

# The responsive pass must not replace desktop density/content-width controls
# or remove the advanced controls it visually groups.
for marker in (
    "const UI_DENSITY_SCALE=",
    "const UI_WIDTH_SCALE=",
    "activity_slow_max_utilization_pct",
    "activity_medium_max_utilization_pct",
    "activity_hold_seconds",
    "activity_hysteresis_pct",
    "snmp_timeout",
    "snmp_retries",
    "minimum_valid_walk_lines",
    "backup_retention_enabled",
    "backup_retention_count",
    "function runDiscovery()",
    "function regenerateSnmp2mqttYaml()",
    "function regenerateDashboardCardYaml()",
    "function renderUnifiedDevices()",
    "function setConfiguredDeviceState(",
    "function moveConfiguredDevice(",
):
    assert marker in SOURCE, marker

# Explicitly guard against the rejected wizard/simplified-workflow direction.
for forbidden in (
    "Discovery Wizard",
    "wizard-step",
    "wizardStep",
    "basic mode",
    "simple mode",
):
    assert forbidden not in SOURCE, forbidden

print("Switch Vision Hub UI/UX refinement contract: PASS")
