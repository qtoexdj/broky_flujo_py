from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from supabase import Client

logger = logging.getLogger(__name__)


class ProspectRepository:
    """Encapsulates CRUD operations for the `prospects` table."""

    def __init__(self, client: Client, table: str = "prospects") -> None:
        self._client = client
        self._table = table

    def find_by_realtor_and_phone(
        self, realtor_id: str, telephone: str
    ) -> Optional[Dict[str, Any]]:
        try:
            response = (
                self._client.table(self._table)
                .select("*")
                .eq("realtor_id", realtor_id)
                .eq("telephone", telephone)
                .limit(1)
                .execute()
            )
        except Exception:  # pragma: no cover - propagate while logging
            logger.exception(
                "Error buscando prospecto realtor_id=%s telephone=%s",
                realtor_id,
                telephone,
            )
            raise

        data = getattr(response, "data", None) or []
        return data[0] if data else None

    def create(
        self,
        *,
        realtor_id: str,
        telephone: str,
        name: Optional[str] = None,
        source: Optional[str] = None,
        automatization: bool = True,
        stage: str = "new-prospect",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "realtor_id": realtor_id,
            "telephone": telephone,
            "stage": stage,
            "automatization": automatization,
            "calification_variables": {},
            "mentioned_properties": [],
        }
        if name:
            payload["name"] = name
        if source:
            payload["source"] = source

        try:
            response = self._client.table(self._table).insert(payload).execute()
        except Exception:  # pragma: no cover - propagate while logging
            logger.exception("Error creando nuevo prospecto para %s", telephone)
            raise

        data = getattr(response, "data", None) or []
        if not data:
            msg = "No se recibió respuesta al crear el prospecto"
            raise RuntimeError(msg)
        return data[0]

    def get_by_id(self, prospect_id: str) -> Optional[Dict[str, Any]]:
        try:
            response = (
                self._client.table(self._table)
                .select("*")
                .eq("id", prospect_id)
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception("Error recuperando prospecto %s", prospect_id)
            raise

        data = getattr(response, "data", None) or []
        return data[0] if data else None
