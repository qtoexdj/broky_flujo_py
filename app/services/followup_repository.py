from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from supabase import Client

logger = logging.getLogger(__name__)


class FollowupRepository:
    """Helpers to maintain follow-up records for prospects and brokers."""

    def __init__(self, client: Client, table: str = "followups") -> None:
        self._client = client
        self._table = table

    def list_open_followups(
        self,
        *,
        prospect_id: str,
        realtor_id: str,
        followup_type: str,
    ) -> List[int]:
        try:
            response = (
                self._client.table(self._table)
                .select("id")
                .eq("prospect_id", prospect_id)
                .eq("realtor_id", realtor_id)
                .eq("type", followup_type)
                .eq("completed", False)
                .execute()
            )
        except Exception:  # pragma: no cover - log and continue
            logger.exception(
                "No se pudieron consultar followups pendientes | prospect_id=%s | realtor_id=%s | type=%s",
                prospect_id,
                realtor_id,
                followup_type,
            )
            return []

        data = getattr(response, "data", None) or []
        return [row.get("id") for row in data if isinstance(row.get("id"), int)]

    def delete_followups(self, followup_ids: Iterable[int]) -> None:
        ids = [fid for fid in followup_ids if isinstance(fid, int)]
        if not ids:
            return

        try:
            self._client.table(self._table).delete().in_("id", ids).execute()
        except Exception:  # pragma: no cover - log and continue
            logger.exception("No se pudieron eliminar followups %s", ids)

    def create_followup(
        self,
        *,
        prospect_id: str,
        realtor_id: str,
        followup_type: str,
        scheduled_at: str,
        type_followup: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "prospect_id": prospect_id,
            "realtor_id": realtor_id,
            "type": followup_type,
            "completed": False,
            "date_followup_scheduled": scheduled_at,
        }
        if type_followup:
            payload["type_followup"] = type_followup

        try:
            response = self._client.table(self._table).insert(payload).execute()
        except Exception:  # pragma: no cover - log and continue
            logger.exception(
                "No se pudo crear followup | prospect_id=%s | realtor_id=%s | type=%s",
                prospect_id,
                realtor_id,
                followup_type,
            )
            return None

        data = getattr(response, "data", None) or []
        return data[0] if data else None
