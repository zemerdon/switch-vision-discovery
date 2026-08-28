#!/usr/bin/env python3
"""Switch Vision Discovery Hub entrypoint with Core-bridge instrumentation."""
from __future__ import annotations

import core_bridge
import support_web


core_bridge.install(support_web)


if __name__ == "__main__":
    raise SystemExit(support_web.main())
