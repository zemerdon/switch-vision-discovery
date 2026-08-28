#!/usr/bin/env sh
set -eu

SWITCH_VISION_DISCOVERY_VERSION="2.3.26"
export SWITCH_VISION_DISCOVERY_VERSION

# Persistent app options are owned by Home Assistant Supervisor. Never edit
# /data/options.json directly; startup migration uses the authoritative API.
if ! python3 /migrate_options.py; then
  echo "Switch Vision Discovery continuing with backward-compatible option defaults" >&2
fi

mkdir -p /share/switch_vision /share/switch_vision/contributions
touch /share/switch_vision/discovery-web.log

echo "Switch Vision Discovery service starting in idle/ready mode."
echo "Support My Switch Web UI: listening on Home Assistant Ingress (port 8099)."
exec python3 /support_web.py \
  --port 8099 \
  --version "$SWITCH_VISION_DISCOVERY_VERSION" \
  --discovery-script /discovery_job.sh
