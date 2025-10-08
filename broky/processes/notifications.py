"""Prepare notification payloads for brokers and internal teams."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def build_notifications(
    *,
    official_data: Dict[str, Any],
    handoff_reason: Optional[str],
    filters: Dict[str, Any],
    broker_assignment: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Produce structured notifications that can be dispatched by external services."""

    notifications: List[Dict[str, Any]] = []
    timestamp = datetime.now(timezone.utc).isoformat()

    broker_config = (
        official_data.get("notifications_brokers_configurations") or {}
    )
    channel = broker_config.get("channel") or "internal"

    prospect = official_data.get("prospect") or {}
    realtor = official_data.get("realtor") or {}

    base_payload = {
        "timestamp": timestamp,
        "realtor_id": official_data.get("realtor_id"),
        "prospect_id": prospect.get("id"),
        "prospect_name": prospect.get("name"),
        "prospect_telephone": prospect.get("telephone"),
        "message": official_data.get("message"),
        "stage": prospect.get("stage"),
        "channel": channel,
        "realtor_name": realtor.get("name"),
    }

    if filters.get("filter_contact") or handoff_reason == "contacto_humano":
        vendor = broker_assignment.get("vendor") if isinstance(broker_assignment, dict) else None
        notifications.append(
            {
                **base_payload,
                "type": "broker_handoff",
                "handoff_reason": handoff_reason or "contacto_humano",
                "vendor": vendor,
                "telephone": vendor.get("telephone") if isinstance(vendor, dict) else None,
            }
        )

    if filters.get("filter_desinteres") or handoff_reason == "desinteres":
        notifications.append(
            {
                **base_payload,
                "type": "prospect_opt_out",
                "handoff_reason": handoff_reason or "desinteres",
            }
        )

    return notifications


__all__ = ["build_notifications"]
