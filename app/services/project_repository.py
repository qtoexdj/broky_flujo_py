from __future__ import annotations

import logging
from typing import Any, Dict, List

from supabase import Client

logger = logging.getLogger(__name__)


class ProjectRepository:
    """Helpers to fetch projects linked to a prospect."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def list_interested_projects(self, prospect_id: str) -> List[Dict[str, Any]]:
        """Return project records the prospect has marked as interested."""

        try:
            interest_resp = (
                self._client.table("prospect_project_interests")
                .select("project_id")
                .eq("prospect_id", prospect_id)
                .execute()
            )
        except Exception:  # pragma: no cover - do not break the flow on errors
            logger.warning(
                "No se pudo consultar prospect_project_interests para %s",
                prospect_id,
                exc_info=True,
            )
            return []

        interest_rows = getattr(interest_resp, "data", None) or []
        project_ids = [row["project_id"] for row in interest_rows if row.get("project_id")]

        if not project_ids:
            return []

        try:
            projects_resp = (
                self._client.table("projects")
                .select("*")
                .in_("id", project_ids)
                .execute()
            )
        except Exception:  # pragma: no cover - if projects table fails, log and continue
            logger.warning(
                "No se pudo recuperar la información de projects para ids %s",
                project_ids,
                exc_info=True,
            )
            return []

        projects = getattr(projects_resp, "data", None)
        if isinstance(projects, list):
            return projects

        return []
