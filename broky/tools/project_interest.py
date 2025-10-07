"""Tools to manage prospect project interests via Supabase."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.services.project_interest_service import ProjectInterestService


class ProjectInterestLinkInput(BaseModel):
    prospect_id: str = Field(..., description="Identificador del prospecto")
    project_ids: List[str] = Field(..., description="Lista de proyectos a vincular")
    realtor_id: Optional[str] = Field(default=None)


class ProjectInterestLinkTool(BaseTool):
    name: str = "project_interest_link"
    description: str = (
        "Vincula proyectos a un prospecto en Supabase usando ProjectInterestService."
    )
    args_schema: type[BaseModel] = ProjectInterestLinkInput

    def __init__(self, service: ProjectInterestService) -> None:
        super().__init__()
        self._service = service

    def _run(  # type: ignore[override]
        self,
        prospect_id: str,
        project_ids: List[str],
        realtor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        operation = self._service.link_projects(
            prospect_id=prospect_id,
            project_ids=project_ids,
            realtor_id=realtor_id,
        )
        return {
            "status": "ok" if operation.added else "noop",
            "added": operation.added,
            "skipped": operation.skipped,
            "project_records": operation.project_records,
        }

    async def _arun(self, *args, **kwargs) -> Dict[str, Any]:  # pragma: no cover
        return self._run(*args, **kwargs)
