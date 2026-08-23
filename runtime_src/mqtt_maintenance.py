#!/usr/bin/env python3
"""Pure ownership and planning helpers for Switch Vision MQTT maintenance."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

ORIGIN_NAME = "Switch Vision SNMP2MQTT"
ORIGIN_URL = "https://github.com/zemerdon/switch-vision-snmp2mqtt"
_COMPONENTS = {"sensor", "binary_sensor"}
_OBJECT_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _clean_prefix(value: Any) -> str:
    text = str(value or "").strip().strip("/")
    if not text or "+" in text or "#" in text:
        return ""
    return text


def discovery_subscription_filter(prefix: Any) -> str:
    """Return the narrow read-only subscription used to inspect discovery."""
    safe_prefix = _clean_prefix(prefix)
    if not safe_prefix:
        raise ValueError("MQTT discovery prefix is invalid.")
    return f"{safe_prefix}/+/snmp2mqtt/+/config"


def classify_owned_retained_config(
    topic: Any,
    payload: Any,
    retain: Any,
    prefix: Any,
    base_topic: Any,
) -> dict[str, str] | None:
    """Return a privacy-safe owned entry or None when ownership is not proven."""
    if retain is not True:
        return None

    safe_prefix = _clean_prefix(prefix)
    safe_base = _clean_prefix(base_topic)
    topic_text = str(topic or "").strip().strip("/")
    if not safe_prefix or not safe_base or not topic_text:
        return None

    parts = topic_text.split("/")
    prefix_parts = safe_prefix.split("/")
    if len(parts) != len(prefix_parts) + 4:
        return None
    if parts[: len(prefix_parts)] != prefix_parts:
        return None

    component, node_id, object_id, leaf = parts[-4:]
    if (
        component not in _COMPONENTS
        or node_id != "snmp2mqtt"
        or leaf != "config"
        or not _OBJECT_RE.fullmatch(object_id)
    ):
        return None

    if isinstance(payload, bytes):
        try:
            payload_text = payload.decode("utf-8")
        except UnicodeDecodeError:
            return None
    elif isinstance(payload, str):
        payload_text = payload
    else:
        return None

    try:
        document = json.loads(payload_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(document, dict):
        return None

    origin = document.get("origin")
    if not isinstance(origin, dict) or origin.get("name") != ORIGIN_NAME:
        return None
    origin_url = origin.get("url")
    if origin_url not in (None, "", ORIGIN_URL):
        return None

    unique_id = str(document.get("unique_id") or "")
    if unique_id != object_id:
        return None

    payload_object_id = document.get("object_id")
    if payload_object_id not in (None, "", object_id):
        return None

    expected_entity_id = f"{component}.{object_id}"
    default_entity_id = document.get("default_entity_id")
    if default_entity_id not in (None, "", expected_entity_id):
        return None

    state_topic = str(document.get("state_topic") or "").strip().strip("/")
    if not state_topic.startswith(f"{safe_base}/"):
        return None

    return {
        "topic": topic_text,
        "component": component,
        "object_id": object_id,
        "entity_id": expected_entity_id,
    }


def _plan_token(current_topics: list[str], owned_topics: list[str]) -> str:
    payload = json.dumps(
        {
            "current_topics": sorted(set(current_topics)),
            "owned_topics": sorted(set(owned_topics)),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_repair_plan(
    current_topics: list[str],
    owned_entries: list[dict[str, str]],
) -> dict[str, Any]:
    """Build a deterministic repair plan without exposing MQTT payloads."""
    current = sorted(
        {
            str(topic).strip().strip("/")
            for topic in current_topics
            if str(topic).strip()
        }
    )

    by_topic: dict[str, dict[str, str]] = {}
    for raw in owned_entries:
        if not isinstance(raw, dict):
            continue
        topic = str(raw.get("topic") or "").strip().strip("/")
        component = str(raw.get("component") or "")
        object_id = str(raw.get("object_id") or "")
        entity_id = str(raw.get("entity_id") or "")
        if (
            not topic
            or component not in _COMPONENTS
            or not _OBJECT_RE.fullmatch(object_id)
            or entity_id != f"{component}.{object_id}"
        ):
            continue
        by_topic[topic] = {
            "topic": topic,
            "component": component,
            "object_id": object_id,
            "entity_id": entity_id,
        }

    owned_topics = sorted(by_topic)
    current_set = set(current)
    owned_set = set(owned_topics)
    stale_topics = sorted(owned_set - current_set)
    active_topics = sorted(owned_set & current_set)
    missing_topics = sorted(current_set - owned_set)

    stale_entries = [
        {
            "component": by_topic[topic]["component"],
            "object_id": by_topic[topic]["object_id"],
            "entity_id": by_topic[topic]["entity_id"],
        }
        for topic in stale_topics
    ]

    return {
        "plan_token": _plan_token(current, owned_topics),
        "owned_retained_count": len(owned_topics),
        "current_expected_count": len(current),
        "current_retained_count": len(active_topics),
        "current_missing_retained_count": len(missing_topics),
        "stale_count": len(stale_topics),
        "stale_entries": stale_entries,
        "_stale_topics": stale_topics,
        "_current_topics": current,
    }


def public_repair_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Return only browser-safe fields from an internal repair plan."""
    return {
        key: value
        for key, value in plan.items()
        if not str(key).startswith("_")
    }
