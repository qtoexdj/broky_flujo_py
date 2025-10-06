"""Service layer to manage prospect-project interest links in Supabase."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from supabase import Client

logger = logging.getLogger(__name__)


@dataclass
class ProjectInterestOperationResult:
    """Details about link/unlink operations for project interests."""

    added: List[str]
    removed: List[str]
    skipped: List[str]
    project_records: List[Dict[str, Any]]


class ProjectInterestService:
    """Encapsulates CRUD helpers for `prospect_project_interests`."""

    def __init__(
        self,
        client: Client,
        *,
        interest_table: str = "prospect_project_interests",
        project_table: str = "projects",
    ) -> None:
        self._client = client
        self._interest_table = interest_table
        self._project_table = project_table

    def link_projects(
        self,
        *,
        prospect_id: str,
        project_ids: Sequence[str],
        realtor_id: Optional[str] = None,
    ) -> ProjectInterestOperationResult:
        """Link the given projects to the prospect, skipping existing ones."""

        normalized_ids = _normalize_ids(project_ids)
        if not normalized_ids:
            return ProjectInterestOperationResult([], [], [], [])

        valid_projects = self._fetch_projects(normalized_ids, realtor_id)
        valid_ids = {project["id"] for project in valid_projects}
        skipped = [pid for pid in normalized_ids if pid not in valid_ids]

        existing_ids = self._fetch_existing_links(prospect_id, valid_ids)
        to_insert = list(valid_ids - existing_ids)
        already_linked = list(existing_ids)

        added_ids: List[str] = []
        if to_insert:
            payload = [
                {"prospect_id": prospect_id, "project_id": project_id}
                for project_id in to_insert
            ]
            try:
                response = self._client.table(self._interest_table).insert(payload).execute()
                data = getattr(response, "data", None)
                if isinstance(data, list):
                    added_ids = [row.get("project_id") for row in data if row.get("project_id")]
                else:
                    added_ids = to_insert
            except Exception:  # pragma: no cover - log and continue without breaking the flow
                logger.exception(
                    "No se pudieron insertar intereses de prospecto | prospect_id=%s | projects=%s",
                    prospect_id,
                    to_insert,
                )
                skipped.extend(project_id for project_id in to_insert if project_id not in skipped)
                added_ids = []

        return ProjectInterestOperationResult(
            added=added_ids,
            removed=[],
            skipped=skipped + already_linked,
            project_records=[project for project in valid_projects if project["id"] in valid_ids],
        )

    def unlink_projects(
        self,
        *,
        prospect_id: str,
        project_ids: Sequence[str],
    ) -> ProjectInterestOperationResult:
        """Remove links between the prospect and the provided projects."""

        normalized_ids = _normalize_ids(project_ids)
        if not normalized_ids:
            return ProjectInterestOperationResult([], [], [], [])

        removed: List[str] = []
        try:
            for chunk in _chunk_list(list(normalized_ids), size=50):
                response = (
                    self._client.table(self._interest_table)
                    .delete()
                    .eq("prospect_id", prospect_id)
                    .in_("project_id", chunk)
                    .execute()
                )
                data = getattr(response, "data", None) or []
                for row in data:
                    project_id = row.get("project_id")
                    if project_id:
                        removed.append(project_id)
        except Exception:  # pragma: no cover - log and continue
            logger.exception(
                "No se pudieron eliminar intereses de prospecto | prospect_id=%s | projects=%s",
                prospect_id,
                list(normalized_ids),
            )

        skipped = [pid for pid in normalized_ids if pid not in removed]
        return ProjectInterestOperationResult(
            added=[],
            removed=removed,
            skipped=skipped,
            project_records=[],
        )

    def _fetch_projects(
        self,
        project_ids: Iterable[str],
        realtor_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        ids = list(project_ids)
        if not ids:
            return []

        try:
            query = self._client.table(self._project_table).select("*")
            query = query.in_("id", ids)
            if realtor_id:
                query = query.eq("realtor_id", realtor_id)
            response = query.execute()
        except Exception:  # pragma: no cover - log and continue
            logger.exception(
                "No se pudieron recuperar proyectos para ids=%s y realtor_id=%s",
                ids,
                realtor_id,
            )
            return []

        data = getattr(response, "data", None)
        if isinstance(data, list):
            return data
        return []

    def _fetch_existing_links(
        self,
        prospect_id: str,
        project_ids: Iterable[str],
    ) -> set[str]:
        ids = list(project_ids)
        if not ids:
            return set()

        try:
            response = (
                self._client.table(self._interest_table)
                .select("project_id")
                .eq("prospect_id", prospect_id)
                .in_("project_id", ids)
                .execute()
            )
        except Exception:  # pragma: no cover - log and continue
            logger.exception(
                "No se pudieron consultar intereses existentes | prospect_id=%s",
                prospect_id,
            )
            return set()

        data = getattr(response, "data", None) or []
        existing = {row.get("project_id") for row in data if row.get("project_id")}
        return existing


def _normalize_ids(project_ids: Sequence[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for raw in project_ids:
        if not raw:
            continue
        project_id = str(raw)
        if project_id and project_id not in seen:
            seen.add(project_id)
            result.append(project_id)
    return result


def _chunk_list(items: List[str], *, size: int) -> List[List[str]]:
    if size <= 0:
        return [items]
    return [items[i : i + size] for i in range(0, len(items), size)]


__all__ = ["ProjectInterestService", "ProjectInterestOperationResult"]
