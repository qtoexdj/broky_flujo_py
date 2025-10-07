from __future__ import annotations

import logging
from typing import Any, Dict, List

from supabase import Client

logger = logging.getLogger(__name__)


class ProjectFilesRepository:
    """Helpers to fetch project files stored in Supabase."""

    def __init__(self, client: Client, table: str = "project_files") -> None:
        self._client = client
        self._table = table

    def list_files(self, project_id: str, file_type: str) -> List[Dict[str, Any]]:
        try:
            response = (
                self._client.table(self._table)
                .select("url, type, name")
                .eq("project_id", project_id)
                .eq("type", file_type)
                .execute()
            )
        except Exception:  # pragma: no cover - log and continue
            logger.exception(
                "No se pudieron obtener archivos para project_id=%s type=%s",
                project_id,
                file_type,
            )
            return []

        data = getattr(response, "data", None)
        if isinstance(data, list):
            return data
        return []
