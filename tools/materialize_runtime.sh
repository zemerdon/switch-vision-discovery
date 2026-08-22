#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

VERSION=$(sed -n 's/^version: "\([^"]*\)"/\1/p' switch_vision_discovery/config.yaml | head -n 1)
if [ -z "$VERSION" ]; then
  echo "ERROR: Could not resolve Discovery version from config.yaml" >&2
  exit 1
fi

# Keep runtime-reported versions and their packaged regression assertions
# synchronized with the Home Assistant app version before packaging. This
# removes hand-maintained version drift from the runtime archive contract.
for file in runtime_src/run.sh runtime_src/discovery_job.sh runtime_src/self-test.sh; do
  sed -E -i "s/SWITCH_VISION_DISCOVERY_VERSION=\"[0-9.]+\"/SWITCH_VISION_DISCOVERY_VERSION=\"$VERSION\"/g" "$file"
  grep -Fq "SWITCH_VISION_DISCOVERY_VERSION=\"$VERSION\"" "$file"
done

rm -f switch_vision_discovery/runtime.tar.gz
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
  -czf switch_vision_discovery/runtime.tar.gz -C runtime_src .

echo "Materialized Switch Vision Discovery runtime v$VERSION"
