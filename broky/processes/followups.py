"""Utility helpers to replicate follow-up processes from the legacy workflow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.services.followup_repository import FollowupRepository


def schedule_prospect_followup(
    repository: FollowupRepository,
    *,
    official_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    config = official_data.get("followup_configuration")
    if not config:
        return None

    prospect_id = official_data.get("prospect_id")
    realtor_id = official_data.get("realtor_id")
    if not prospect_id or not realtor_id:
        return None

    scheduled_at = _compute_followup_date(config)
    if not scheduled_at:
        return None

    pending = repository.list_open_followups(
        prospect_id=prospect_id,
        realtor_id=realtor_id,
        followup_type="prospect",
    )
    repository.delete_followups(pending)

    record = repository.create_followup(
        prospect_id=prospect_id,
        realtor_id=realtor_id,
        followup_type="prospect",
        scheduled_at=scheduled_at,
        type_followup="1",
    )

    return {
        "scheduled_at": scheduled_at,
        "type": "prospect",
        "record": record,
    }


def schedule_broker_followup(
    repository: FollowupRepository,
    *,
    official_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    notifications = official_data.get("notifications_brokers_configurations") or {}
    config = notifications.get("no_response") or {}

    if not isinstance(config, dict):
        return None

    if str(config.get("type")).lower() == "no-followup":
        return None

    scheduled_at = _compute_followup_date(config)
    if not scheduled_at:
        return None

    prospect_id = official_data.get("prospect_id")
    realtor_id = official_data.get("realtor_id")
    if not prospect_id or not realtor_id:
        return None

    pending = repository.list_open_followups(
        prospect_id=prospect_id,
        realtor_id=realtor_id,
        followup_type="broker",
    )
    repository.delete_followups(pending)

    record = repository.create_followup(
        prospect_id=prospect_id,
        realtor_id=realtor_id,
        followup_type="broker",
        scheduled_at=scheduled_at,
    )

    return {
        "scheduled_at": scheduled_at,
        "type": "broker",
        "record": record,
    }


def _compute_followup_date(configuration: Any) -> Optional[str]:
    rules = []
    if isinstance(configuration, list):
        rules = configuration
    elif isinstance(configuration, dict):
        rules = [configuration]

    if not rules:
        return None

    # Take the rule with Order_followup == "1" if present, otherwise the first rule.
    selected = None
    for rule in rules:
        if isinstance(rule, dict) and str(rule.get("Order_followup")) == "1":
            selected = rule
            break
    if selected is None:
        selected = rules[0] if isinstance(rules[0], dict) else None

    if not isinstance(selected, dict):
        return None

    range_value = selected.get("Range")
    type_range = str(selected.get("Type_range") or "").lower()
    try:
        delta = float(range_value)
    except (TypeError, ValueError):
        return None

    base = datetime.now(timezone.utc)
    if type_range.startswith("hour"):
        target = base + timedelta(hours=delta)
    else:
        target = base + timedelta(days=delta)

    return target.isoformat()
