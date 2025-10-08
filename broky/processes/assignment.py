"""Helpers to assign brokers to prospects during hand-off flows."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.profile_repository import ProfileRepository
from app.services.prospect_repository import ProspectRepository


def assign_broker_if_needed(
    profile_repo: Optional[ProfileRepository],
    prospect_repo: Optional[ProspectRepository],
    *,
    official_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Assign a broker to the prospect when none is linked.

    Returns metadata describing the decision so that higher layers can act upon it.
    """

    result: Dict[str, Any] = {
        "performed": False,
        "reason": None,
        "vendor": None,
    }

    if not profile_repo or not prospect_repo:
        result["reason"] = "repositories_unavailable"
        return result

    prospect = official_data.get("prospect") or {}
    prospect_id = prospect.get("id")
    realtor_id = official_data.get("realtor_id")

    if not prospect_id or not realtor_id:
        result["reason"] = "missing_identifiers"
        return result

    if prospect.get("vendor_id"):
        result["reason"] = "already_assigned"
        return result

    brokers = profile_repo.list_active_brokers(str(realtor_id))
    if not brokers:
        result["reason"] = "no_active_brokers"
        return result

    selected = brokers[0]

    record = prospect_repo.assign_vendor(str(prospect_id), selected.get("id"))

    result.update(
        {
            "performed": True,
            "vendor": {
                "id": selected.get("id"),
                "name": selected.get("name"),
                "email": selected.get("email"),
                "telephone": selected.get("telephone"),
            },
            "prospect": record or prospect,
        }
    )
    return result


__all__ = ["assign_broker_if_needed"]
