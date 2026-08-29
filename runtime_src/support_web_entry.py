#!/usr/bin/env python3
"""Switch Vision Discovery Hub entrypoint with compatibility instrumentation."""
from __future__ import annotations

import core_bridge
import support_web
import unifi_multi_controller_bridge


core_bridge.install(support_web)
unifi_multi_controller_bridge.install(support_web)


if __name__ == "__main__":
    raise SystemExit(support_web.main())
