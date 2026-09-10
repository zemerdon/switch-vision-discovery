# Switch Vision Discovery

Public Home Assistant app repository for **Switch Vision Discovery**.

Switch Vision Discovery provides read-only multi-vendor switch discovery, capability reporting, Support My Switch diagnostics, and review-only SNMP2MQTT/dashboard generation for Switch Vision.

## Installation

Normal Switch Vision users should install and update Discovery through **Switch Vision Installer**. The Installer registers this repository automatically.

Repository URL:

`https://github.com/zemerdon/switch-vision-discovery`

## Current app

- Authoritative app version: `switch_vision_discovery/config.yaml`
- Architectures: amd64, aarch64
- Container image: `ghcr.io/zemerdon/switch-vision-discovery`
- Current Switch Vision Core compatibility floor: v2.3.10+ for the Calibration Profile management/storage API used by Discovery

Switch Vision components are independently versioned. The main Switch Vision Core product source is maintained separately and is not published in this repository.

## Exact-model support status

Discovery's reviewed exact-model registry is the public software source of truth for Switch Vision device support state. The normal confidence ladder is **Detected -> Experimental -> Community Validated -> Confirmed Supported**.

A first valid contribution adds the exact model as **Detected**; a reviewed Experimental mapping/profile or dashboard implementation may already exist at this stage. A second meaningfully independent contribution that corroborates the model's evidence promotes it to **Experimental**. A third independent contribution plus applicable visual/real-hardware confirmation can promote it to **Community Validated**. **Confirmed Supported** is a later repeatability/maturity decision rather than an automatic fourth contribution.

Duplicate/replayed evidence does not increase confidence, conflicting evidence blocks promotion, and non-applicable hardware capabilities are never invented to complete a checklist. Public support status is derived from the reviewed registry rather than directly from private Support My Switch evidence.
