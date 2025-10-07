"""Tools to update prospect calification data in Supabase."""

from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.services.prospect_repository import ProspectRepository


class CalificationUpdateInput(BaseModel):
    prospect_id: str = Field(..., description="Identificador del prospecto")
    calification: Dict[str, Any] = Field(
        ..., description="Variables de calificación normalizadas"
    )
    stage: Optional[str] = Field(
        default=None,
        description="Etapa del pipeline a actualizar (ej. qualified)",
    )


class CalificationUpdateTool(BaseTool):
    """Actualiza los campos de calificación del prospecto en Supabase."""

    name: str = "calification_update"
    description: str = (
        "Actualiza calification_variables y stage de un prospecto en Supabase."
    )
    args_schema: type[BaseModel] = CalificationUpdateInput

    def __init__(self, repository: ProspectRepository) -> None:
        super().__init__()
        self._repository = repository

    def _run(  # type: ignore[override]
        self,
        prospect_id: str,
        calification: Dict[str, Any],
        stage: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = self._repository.get_calification(prospect_id)
        merged = {}
        if isinstance(existing.get("calification_variables"), dict):
            merged.update(existing["calification_variables"])
        for key, value in calification.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            merged[key] = value

        if isinstance(stage, str) and not stage.strip():
            stage = None

        if stage is None:
            stage_value = existing.get("stage")
        else:
            stage_value = stage

        record = self._repository.update_calification(
            prospect_id,
            calification=merged,
            stage=stage_value,
        )
        return {
            "status": "ok" if record else "noop",
            "prospect": record,
        }

    async def _arun(self, *args, **kwargs) -> Dict[str, Any]:  # pragma: no cover
        return self._run(*args, **kwargs)
