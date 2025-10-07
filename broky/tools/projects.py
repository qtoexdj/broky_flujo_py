"""Tools related to project catalog and files."""

from __future__ import annotations

from typing import Dict, Iterable, List

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.services.project_repository import ProjectRepository
from app.services.project_files_repository import ProjectFilesRepository


class ProjectsListInput(BaseModel):
    realtor_id: str = Field(..., description="Identificador de la inmobiliaria")


class ProjectsListTool(BaseTool):
    """Devuelve la lista de proyectos (id y nombre) asociados a un realtor."""

    name: str = "projects_list"
    description: str = "Obtiene los proyectos disponibles para un realtor."
    args_schema: type[BaseModel] = ProjectsListInput

    def __init__(self, repository: ProjectRepository) -> None:
        super().__init__()
        self._repository = repository

    def _run(self, realtor_id: str) -> List[Dict[str, str]]:  # type: ignore[override]
        projects = self._repository.list_by_realtor(realtor_id)
        return [
            {
                "id": str(project.get("id")),
                "name": project.get("name_property") or project.get("name") or "",
            }
            for project in projects
            if project.get("id")
        ]

    async def _arun(self, realtor_id: str):  # pragma: no cover
        return self._run(realtor_id)


class ProjectFilesInput(BaseModel):
    project_id: str = Field(..., description="ID del proyecto")
    file_type: str = Field(..., description="Tipo de archivo: image, video, kmz, document")


class ProjectFilesTool(BaseTool):
    """Devuelve URLs de archivos para un proyecto y tipo."""

    name: str = "project_files"
    description: str = "Obtiene las URLs de archivos del proyecto filtrados por tipo."
    args_schema: type[BaseModel] = ProjectFilesInput

    def __init__(self, repository: ProjectFilesRepository) -> None:
        super().__init__()
        self._repository = repository

    def _run(self, project_id: str, file_type: str) -> List[Dict[str, str]]:  # type: ignore[override]
        files = self._repository.list_files(project_id, file_type)
        results: List[Dict[str, str]] = []
        for item in files:
            url = item.get("url")
            if not url:
                continue
            results.append(
                {
                    "url": str(url),
                    "type": file_type,
                    "name": item.get("name") or "",
                }
            )
        return results

    async def _arun(self, *args, **kwargs):  # pragma: no cover
        return self._run(*args, **kwargs)
