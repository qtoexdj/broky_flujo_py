"""Tool registry centralizing LangChain tool configuration."""

from __future__ import annotations

from typing import Dict, Iterable, Optional

from langchain_core.tools import BaseTool

from app.core.config import get_settings
from app.services.project_repository import ProjectRepository
from app.services.project_interest_service import ProjectInterestService
from app.services.prospect_repository import ProspectRepository
from app.services.project_files_repository import ProjectFilesRepository
from app.services.prospect_repository import ProspectRepository
from app.services.realtor_repository import RealtorRepository
from app.services.rag.service import RAGService
from app.services.supabase_client import get_supabase_client

from broky.tools.rag import RAGSearchTool
from broky.tools.supabase import (
    PropertiesByProspectTool,
    ProspectCreateTool,
    ProspectLookupTool,
    RealtorLookupTool,
)
from broky.tools.project_interest import ProjectInterestLinkTool
from broky.tools.calification import CalificationUpdateTool
from broky.tools.schedule import ScheduleVisitTool
from broky.tools.projects import ProjectsListTool, ProjectFilesTool

class ToolRegistry:
    """Mantiene un catálogo de herramientas bajo el namespace `broky.tools`."""

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool, *, name: Optional[str] = None) -> None:
        key = name or tool.name
        if not key:
            raise ValueError("Las herramientas requieren nombre explícito")
        namespaced = f"broky.tools.{key}"
        self._tools[namespaced] = tool

    def get(self, name: str) -> BaseTool:
        namespaced = name if name.startswith("broky.tools.") else f"broky.tools.{name}"
        return self._tools[namespaced]

    def all(self) -> Iterable[BaseTool]:
        return self._tools.values()


def register_default_tools(
    registry: ToolRegistry,
    *,
    supabase_client=None,
) -> None:
    """Hook donde iremos registrando herramientas comunes."""

    settings = get_settings()
    client = supabase_client or get_supabase_client(settings)

    if client:
        realtor_repo = RealtorRepository(client)
        prospect_repo = ProspectRepository(client)
        project_repo = ProjectRepository(client)

        registry.register(RealtorLookupTool(realtor_repo))
        registry.register(ProspectLookupTool(prospect_repo))
        registry.register(ProspectCreateTool(prospect_repo))
        registry.register(PropertiesByProspectTool(project_repo))

        project_interest_service = ProjectInterestService(client)
        registry.register(ProjectInterestLinkTool(project_interest_service))

        registry.register(CalificationUpdateTool(prospect_repo))
        registry.register(ScheduleVisitTool(prospect_repo))

        project_files_repo = ProjectFilesRepository(client)
        registry.register(ProjectsListTool(project_repo))
        registry.register(ProjectFilesTool(project_files_repo))

    if settings.vector_service_configured and settings.openai_api_key:
        rag_service = RAGService(settings)
        registry.register(RAGSearchTool(rag_service))
