from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from supabase import Client

logger = logging.getLogger(__name__)


class RealtorRepository:
    """Small helper around the `realtors` table."""

    def __init__(self, client: Client, table: str = "realtors") -> None:
        self._client = client
        self._table = table

    def get_by_channel_id(self, channel_id: str) -> Optional[Dict[str, Any]]:
        try:
            response = (
                self._client.table(self._table)
                .select("*")
                .eq("channel_id", channel_id)
                .limit(1)
                .execute()
            )
        except Exception:  # pragma: no cover - log and bubble up
            logger.exception("Error consultando realtor por channel_id %s", channel_id)
            raise

        data = getattr(response, "data", None) or []
        return data[0] if data else None
