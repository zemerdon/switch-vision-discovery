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

## User-first Discovery behavior

Switch Vision Discovery is deliberately **fail-soft for reachable hardware**. The goal is to give the user something useful and diagnosable whenever the switch answers, rather than turn an incomplete model mapping or optional telemetry gap into a failed Discovery run.

- If a reachable switch has an exact registry match, Discovery uses that registered model, topology and approved card/faceplate contract.
- If a reachable switch is not registered, Discovery uses the safest neutral best-fit card that can contain the **observed** physical RJ45/uplink positions. The card is clearly marked as approximate and its port counts are capped to observed hardware, so extra stock-canvas sockets never become phantom ports or entities.
- If a reachable switch does not expose enough trustworthy topology to draw even a safe fallback, Discovery still completes and clearly directs the user to **Support My Switch** so exact support can be added.
- Missing optional MIBs/OIDs, sensors, telemetry, artwork, unsupported models and partial model knowledge are warnings/diagnostics, not reachability failures.
- In a multi-switch run, one unreachable/auth-blocked target does not invalidate other reachable targets.
- Hard runtime failure is reserved for inability to communicate/authenticate with any required target, invalid configuration/runtime that prevents a real attempt, or a genuine Switch Vision software/integrity fault.

This user-facing fail-soft policy does **not** weaken release engineering. Registry integrity, topology, privacy, calibration, deterministic packaging and release gates remain strict and must be repaired/rerun when they fail.

## Exact-model support status

Discovery's reviewed exact-model registry is the public software source of truth for Switch Vision device support state. The normal confidence ladder is **Detected -> Experimental -> Community Validated -> Confirmed Supported**.

A first valid contribution adds the exact model as **Detected**; a reviewed Experimental mapping/profile or dashboard implementation may already exist at this stage. A second meaningfully independent contribution that corroborates the model's evidence promotes it to **Experimental**. A third independent contribution plus applicable visual/real-hardware confirmation can promote it to **Community Validated**. **Confirmed Supported** is a later repeatability/maturity decision rather than an automatic fourth contribution.

Duplicate/replayed evidence does not increase confidence, conflicting evidence blocks promotion, and non-applicable hardware capabilities are never invented to complete a checklist. Public support status is derived from the reviewed registry rather than directly from private Support My Switch evidence.
