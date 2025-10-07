"""Supabase-backed tools exposed to LangChain agents."""

from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.services.project_repository import ProjectRepository
from app.services.prospect_repository import ProspectRepository
from app.services.realtor_repository import RealtorRepository


class RealtorLookupInput(BaseModel):
    channel_id: str = Field(..., description="Identificador del canal (WhatsApp)")


class RealtorLookupTool(BaseTool):
    name: str = "realtor_lookup"
    description: str = (
        "Recupera la ficha de la inmobiliaria registrada en Supabase usando el channel_id."
    )
    args_schema: type[BaseModel] = RealtorLookupInput

    def __init__(self, repository: RealtorRepository) -> None:
        super().__init__()
        self._repository = repository

    def _run(self, channel_id: str) -> Dict[str, Any]:  # type: ignore[override]
        realtor = self._repository.get_by_channel_id(channel_id)
        return realtor or {}

    async def _arun(self, channel_id: str) -> Dict[str, Any]:  # pragma: no cover
        return self._run(channel_id)


class ProspectLookupInput(BaseModel):
    realtor_id: str = Field(..., description="Identificador del realtor (UUID)")
    telephone: str = Field(..., description="Teléfono del prospecto")


class ProspectLookupTool(BaseTool):
    name: str = "prospect_lookup"
    description: str = (
        "Busca un prospecto en Supabase combinando realtor_id y telephone, devolviendo el registro si existe."
    )
    args_schema: type[BaseModel] = ProspectLookupInput

    def __init__(self, repository: ProspectRepository) -> None:
        super().__init__()
        self._repository = repository

    def _run(self, realtor_id: str, telephone: str) -> Dict[str, Any]:  # type: ignore[override]
        prospect = self._repository.find_by_realtor_and_phone(realtor_id, telephone)
        return prospect or {}

    async def _arun(self, realtor_id: str, telephone: str) -> Dict[str, Any]:  # pragma: no cover
        return self._run(realtor_id, telephone)


class ProspectCreateInput(BaseModel):
    realtor_id: str
    telephone: str
    name: Optional[str] = Field(default=None)
    source: Optional[str] = Field(default="langchain")
    automatization: bool = Field(default=True)
    stage: str = Field(default="new-prospect")


class ProspectCreateTool(BaseTool):
    name: str = "prospect_create"
    description: str = (
        "Crea un nuevo prospecto en Supabase con los datos mínimos requeridos y devuelve el registro resultante."
    )
    args_schema: type[BaseModel] = ProspectCreateInput

    def __init__(self, repository: ProspectRepository) -> None:
        super().__init__()
        self._repository = repository

    def _run(  # type: ignore[override]
        self,
        realtor_id: str,
        telephone: str,
        name: Optional[str] = None,
        source: Optional[str] = "langchain",
        automatization: bool = True,
        stage: str = "new-prospect",
    ) -> Dict[str, Any]:
        prospect = self._repository.create(
            realtor_id=realtor_id,
            telephone=telephone,
            name=name,
            source=source,
            automatization=automatization,
            stage=stage,
        )
        return prospect

    async def _arun(self, *args, **kwargs) -> Dict[str, Any]:  # pragma: no cover
        return self._run(*args, **kwargs)


class PropertiesByProspectInput(BaseModel):
    prospect_id: str = Field(..., description="Identificador del prospecto")


class PropertiesByProspectTool(BaseTool):
    name: str = "properties_by_prospect"
    description: str = (
        "Lista los proyectos marcados como interés para un prospecto específico usando Supabase."
    )
    args_schema: type[BaseModel] = PropertiesByProspectInput

    def __init__(self, repository: ProjectRepository) -> None:
        super().__init__()
        self._repository = repository

    def _run(self, prospect_id: str) -> Dict[str, Any]:  # type: ignore[override]
        records = self._repository.list_interested_projects(prospect_id)
        return {"prospect_id": prospect_id, "projects": records}

    async def _arun(self, prospect_id: str) -> Dict[str, Any]:  # pragma: no cover
        return self._run(prospect_id)
