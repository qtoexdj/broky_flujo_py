"""Subagente que administra los intereses de proyectos para un prospecto."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from app.core.config import Settings
from app.services.project_interest_service import (
    ProjectInterestOperationResult,
    ProjectInterestService,
)

logger = logging.getLogger(__name__)


@dataclass
class ProjectInterestSubAgentResult:
    """Respuesta estructurada para el subagente de actualización de proyectos."""

    reply: str
    status: str
    added_projects: List[Dict[str, Any]]
    skipped: List[str]
    removed: List[str]
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reply": self.reply,
            "status": self.status,
            "added_projects": self.added_projects,
            "skipped": self.skipped,
            "removed": self.removed,
            "error": self.error,
        }


class ProjectInterestSubAgent:
    """Coordina la actualización de intereses de proyectos en Supabase."""

    def __init__(
        self,
        settings: Settings,
        service: Optional[ProjectInterestService],
    ) -> None:
        self._settings = settings
        self._service = service

    def run(
        self,
        *,
        prospect_id: Optional[str],
        realtor_id: Optional[str],
        mentioned_projects: Sequence[str] | None,
        action: str = "link",
    ) -> Optional[ProjectInterestSubAgentResult]:
        if not prospect_id:
            logger.warning("ProjectInterestSubAgent sin prospect_id; se omite ejecución")
            return None

        if not mentioned_projects:
            logger.info(
                "ProjectInterestSubAgent sin proyectos mencionados | prospect_id=%s",
                prospect_id,
            )
            return None

        if not self._service:
            logger.info("ProjectInterestSubAgent sin servicio configurado (Supabase no disponible)")
            return ProjectInterestSubAgentResult(
                reply="Guardaremos tus proyectos una vez restablezcamos la conexión.",
                status="fallback",
                added_projects=[],
                skipped=list(mentioned_projects),
                removed=[],
                error="service_unavailable",
            )

        normalized_projects = [str(project_id) for project_id in mentioned_projects if project_id]
        if not normalized_projects:
            return None

        try:
            if action == "unlink":
                operation = self._service.unlink_projects(
                    prospect_id=prospect_id,
                    project_ids=normalized_projects,
                )
            else:
                operation = self._service.link_projects(
                    prospect_id=prospect_id,
                    project_ids=normalized_projects,
                    realtor_id=realtor_id,
                )
        except Exception:  # pragma: no cover - log y devolver fallback
            logger.exception(
                "Error ejecutando ProjectInterestService | action=%s", action
            )
            return ProjectInterestSubAgentResult(
                reply="No pude actualizar los proyectos en este momento, un asesor revisará tu solicitud.",
                status="error",
                added_projects=[],
                skipped=normalized_projects,
                removed=[],
                error="service_exception",
            )

        return self._build_result(operation, action)

    def _build_result(
        self,
        operation: ProjectInterestOperationResult,
        action: str,
    ) -> ProjectInterestSubAgentResult:
        added_records = self._filter_projects(operation.project_records, operation.added)
        if action == "unlink":
            reply = self._compose_unlink_reply(operation)
            status = "ok" if operation.removed else "noop"
        else:
            reply = self._compose_link_reply(operation, added_records)
            status = "ok" if operation.added else "noop"

        return ProjectInterestSubAgentResult(
            reply=reply,
            status=status,
            added_projects=added_records,
            skipped=operation.skipped,
            removed=operation.removed,
            error=None,
        )

    @staticmethod
    def _filter_projects(
        projects: Sequence[Dict[str, Any]],
        allowed_ids: Sequence[str],
    ) -> List[Dict[str, Any]]:
        allowed = {pid for pid in allowed_ids if pid}
        if not allowed:
            return []
        filtered: List[Dict[str, Any]] = []
        for project in projects:
            project_id = str(project.get("id")) if project else None
            if project_id in allowed:
                filtered.append(project)
        return filtered

    @staticmethod
    def _compose_link_reply(operation: ProjectInterestOperationResult, projects: Sequence[Dict[str, Any]]) -> str:
        if operation.added:
            names = _format_project_names(projects, fallback_ids=operation.added)
            return f"He guardado tus proyectos de interés: {names}."

        if operation.skipped:
            return (
                "No pude guardar los proyectos mencionados, revisaré con un asesor para ayudarte."
            )

        return "No encontré proyectos nuevos para guardar en tu ficha."

    @staticmethod
    def _compose_unlink_reply(operation: ProjectInterestOperationResult) -> str:
        if operation.removed:
            return "Actualicé tu ficha y eliminé los proyectos indicados."
        if operation.skipped:
            return "No encontré los proyectos para eliminarlos, un asesor lo revisará contigo."
        return "No había proyectos pendientes de eliminar."


def _format_project_names(
    projects: Sequence[Dict[str, Any]],
    *,
    fallback_ids: Sequence[str],
) -> str:
    names: List[str] = []
    fallback_iter = iter(fallback_ids)
    for project in projects:
        if not isinstance(project, dict):
            continue
        name = (
            project.get("name")
            or project.get("name_property")
            or project.get("title")
        )
        if name:
            names.append(str(name))
    for project_id in fallback_iter:
        if len(names) >= len(fallback_ids):
            break
        if project_id not in names:
            names.append(str(project_id))
    if not names:
        return "los proyectos indicados"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + f" y {names[-1]}"


__all__ = ["ProjectInterestSubAgent", "ProjectInterestSubAgentResult"]
