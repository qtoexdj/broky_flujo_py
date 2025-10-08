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

    def update_calification(
        self,
        prospect_id: str,
        *,
        calification: Dict[str, Any],
        stage: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "calification_variables": calification,
        }
        if stage:
            payload["stage"] = stage

        try:
            response = (
                self._client.table(self._table)
                .update(payload)
                .eq("id", prospect_id)
                .execute()
            )
        except Exception:  # pragma: no cover - log y propagar
            logger.exception(
                "Error actualizando calificación del prospecto %s",
                prospect_id,
            )
            raise

        data = getattr(response, "data", None) or []
        return data[0] if data else None

    def get_calification(self, prospect_id: str) -> Dict[str, Any]:
        try:
            response = (
                self._client.table(self._table)
                .select("calification_variables, stage")
                .eq("id", prospect_id)
                .limit(1)
                .execute()
            )
        except Exception:  # pragma: no cover - log y continuar
            logger.exception(
                "Error leyendo calificación del prospecto %s",
                prospect_id,
            )
            return {}

        rows = getattr(response, "data", None) or []
        if not rows:
            return {}
        record = rows[0]
        variables = record.get("calification_variables") or {}
        if not isinstance(variables, dict):
            variables = {}
        stage = record.get("stage")
        return {
            "calification_variables": variables,
            "stage": stage,
        }

    def update_schedule(
        self,
        prospect_id: str,
        *,
        scheduled_at: Optional[str],
        stage: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {}
        if scheduled_at is not None:
            payload["scheduled_at"] = scheduled_at
        if stage:
            payload["stage"] = stage

        if not payload:
            return None

        try:
            response = (
                self._client.table(self._table)
                .update(payload)
                .eq("id", prospect_id)
                .execute()
            )
        except Exception:  # pragma: no cover - log y propagar
            logger.exception(
                "Error actualizando agenda del prospecto %s",
                prospect_id,
            )
            raise

        data = getattr(response, "data", None) or []
        return data[0] if data else None

    def assign_vendor(self, prospect_id: str, vendor_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Assign or remove a vendor (broker) from the prospect."""

        payload: Dict[str, Any] = {"vendor_id": vendor_id}
        if vendor_id is None:
            payload["vendor_id"] = None

        try:
            response = (
                self._client.table(self._table)
                .update(payload)
                .eq("id", prospect_id)
                .execute()
            )
        except Exception:  # pragma: no cover - log y propagar
            logger.exception(
                "Error asignando vendor_id=%s al prospecto %s",
                vendor_id,
                prospect_id,
            )
            raise

        data = getattr(response, "data", None) or []
        return data[0] if data else None
