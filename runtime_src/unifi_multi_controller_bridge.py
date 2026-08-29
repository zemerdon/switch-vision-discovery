#!/usr/bin/env python3
"""Privacy-safe Discovery Hub compatibility for UniFi2MQTT multi-controller mode."""
from __future__ import annotations

from typing import Any

_SENTINEL_API_KEY = "__switch_vision_multi_controller_managed__"

_PAGE_PATCHES: tuple[tuple[str, str], ...] = (
    (
        "const configured=!!(d?.installed&&String(o.controller_url||'').trim()&&String(o.site_id||'').trim()&&d?.api_key_configured&&String(o.mqtt_host||'').trim());",
        "const configured=!!(d?.installed&&(d?.multi_controller_enabled?d?.controller_credentials_configured:(String(o.controller_url||'').trim()&&String(o.site_id||'').trim()&&d?.api_key_configured))&&String(o.mqtt_host||'').trim());",
    ),
    (
        "const controllerReady=!!(String(o.controller_url||'').trim()&&String(o.site_id||'').trim()&&d.api_key_configured);",
        "const multi=!!d.multi_controller_enabled;const controllerReady=multi?!!d.controller_credentials_configured:!!(String(o.controller_url||'').trim()&&String(o.site_id||'').trim()&&d.api_key_configured);",
    ),
    (
        "diagTile('Controller',controllerReady?'Configured':'Needs setup',controllerReady?'diag-good':'diag-warn')",
        "diagTile('Controller',controllerReady?(multi?`${d.controller_count||0} controllers`:'Configured'):'Needs setup',controllerReady?'diag-good':'diag-warn')",
    ),
    (
        "$('unifi_api_key').required=!d.api_key_configured;$('unifi_mqtt_password').value='';$('unifiApiKeyState').textContent=d.api_key_configured?'Configured — leave blank to keep':'Required — not configured';",
        "$('unifi_api_key').required=!multi&&!d.api_key_configured;for(const id of ['unifi_controller_url','unifi_site_id','unifi_verify_ssl','unifi_api_key'])$(id).disabled=multi;$('unifi_mqtt_password').value='';$('unifiApiKeyState').textContent=multi?'Managed in Home Assistant App configuration':(d.api_key_configured?'Configured — leave blank to keep':'Required — not configured');",
    ),
    (
        "$('unifiSettingsStatus').textContent='Secrets are never read back into this page. Blank secret fields preserve the stored values.'",
        "$('unifiSettingsStatus').textContent=d.multi_controller_enabled?'Multi-controller mode is active. Manage controllers and API keys in the Home Assistant App configuration; global MQTT and polling settings can still be changed here.':'Secrets are never read back into this page. Blank secret fields preserve the stored values.'",
    ),
)


def _controller_summary(options: Any) -> dict[str, Any]:
    controllers = options.get("controllers") if isinstance(options, dict) else None
    if not isinstance(controllers, list) or not controllers:
        return {
            "multi_controller_enabled": False,
            "controller_count": 0,
            "controller_credentials_configured": False,
        }

    configured = True
    for raw in controllers:
        if not isinstance(raw, dict):
            configured = False
            continue
        controller_id = str(raw.get("id") or "").strip()
        controller_url = str(raw.get("controller_url") or "").strip()
        api_key = str(raw.get("api_key") or "").strip()
        if not controller_id or not controller_url or not api_key:
            configured = False

    return {
        "multi_controller_enabled": True,
        "controller_count": len(controllers),
        "controller_credentials_configured": configured,
    }


def _patch_page(page: str) -> str:
    updated = page
    for old, new in _PAGE_PATCHES:
        count = updated.count(old)
        if count != 1:
            raise RuntimeError(
                "UniFi2MQTT multi-controller Hub patch contract changed "
                f"(expected one match, found {count})."
            )
        updated = updated.replace(old, new, 1)
    return updated


def install(module: Any) -> None:
    """Install multi-controller-safe status/save behavior into support_web."""
    if getattr(module, "_sv_unifi_multi_controller_bridge_installed", False):
        return

    original_status = module._unifi2mqtt_settings_status
    original_validate = module._validate_unifi2mqtt_options

    def settings_status() -> dict[str, Any]:
        result = original_status()
        options = result.get("options")
        if not isinstance(options, dict):
            options = {}
            result["options"] = options

        # The legacy status function intentionally hides top-level secrets but
        # knows nothing about nested controller API keys. Consume the list only
        # long enough to derive counts/readiness, then remove it before the
        # response can reach the browser.
        summary = _controller_summary(options)
        options.pop("controllers", None)

        legacy_api_key = bool(result.get("api_key_configured"))
        result["legacy_api_key_configured"] = legacy_api_key
        result.update(summary)
        if summary["multi_controller_enabled"]:
            result["api_key_configured"] = bool(
                summary["controller_credentials_configured"]
            )
        return result

    def validate_options(data: Any, current: dict[str, Any]) -> dict[str, Any]:
        if isinstance(data, dict) and "controllers" in data:
            raise ValueError(
                "Controller lists and per-controller API keys must be managed "
                "from the Home Assistant App configuration."
            )

        summary = _controller_summary(current)
        if not summary["multi_controller_enabled"]:
            return original_validate(data, current)

        if not summary["controller_credentials_configured"]:
            raise ValueError(
                "Multi-controller configuration is incomplete. Open the Home "
                "Assistant App configuration and complete every controller entry."
            )

        # The legacy validator correctly validates all global settings, but it
        # also requires the legacy top-level API key. Multi-controller mode owns
        # credentials inside the preserved controller list, so use a temporary
        # sentinel only for validation and never persist it.
        had_api_key = "api_key" in current
        original_api_key = current.get("api_key")
        working = dict(current)
        if not str(working.get("api_key") or "").strip():
            working["api_key"] = _SENTINEL_API_KEY

        validated = original_validate(data, working)
        validated["controllers"] = current.get("controllers")

        if validated.get("api_key") == _SENTINEL_API_KEY:
            if had_api_key:
                validated["api_key"] = original_api_key
            else:
                validated.pop("api_key", None)
        return validated

    module._unifi2mqtt_settings_status = settings_status
    module._validate_unifi2mqtt_options = validate_options
    module._PAGE = _patch_page(module._PAGE)
    module._sv_unifi_multi_controller_bridge_installed = True
