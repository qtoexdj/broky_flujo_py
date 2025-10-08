from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from supabase import Client

logger = logging.getLogger(__name__)


class ProfileRepository:
    """Helpers to fetch broker profiles associated to a realtor."""

    def __init__(self, client: Client, table: str = "profiles") -> None:
        self._client = client
        self._table = table

    def list_active_brokers(self, realtor_id: str) -> List[Dict[str, Any]]:
        """Return brokers in active status for the specified realtor."""

        try:
            response = (
                self._client.table(self._table)
                .select("*")
                .eq("realtor_id", realtor_id)
                .eq("role", "broker")
                .eq("status", "active")
                .execute()
            )
        except Exception:  # pragma: no cover - log and continue
            logger.exception(
                "No se pudieron recuperar brokers activos para realtor_id=%s",
                realtor_id,
            )
            return []

        data = getattr(response, "data", None)
        if isinstance(data, list):
            return data
        return []

    def get_by_id(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Return a specific profile if accessible."""

        try:
            response = (
                self._client.table(self._table)
                .select("*")
                .eq("id", profile_id)
                .limit(1)
                .execute()
            )
        except Exception:  # pragma: no cover - log and continue
            logger.exception("No se pudo recuperar el profile %s", profile_id)
            return None

        rows = getattr(response, "data", None) or []
        return rows[0] if rows else None


__all__ = ["ProfileRepository"]
