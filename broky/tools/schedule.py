"""Tools to manage prospect visit scheduling in Supabase."""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.services.prospect_repository import ProspectRepository


class ScheduleVisitInput(BaseModel):
    prospect_id: str = Field(..., description="Identificador del prospecto")
    scheduled_at: str = Field(..., description="Fecha agendada en formato YYYY-MM-DD")
    stage: Optional[str] = Field(
        default="scheduled",
        description="Stage del prospecto tras agendar la visita",
    )


class ScheduleVisitTool(BaseTool):
    """Registra en Supabase la fecha de visita y actualiza el stage."""

    name: str = "schedule_visit"
    description: str = (
        "Actualiza `scheduled_at` y el `stage` de un prospecto en Supabase cuando se agenda una visita."
    )
    args_schema: type[BaseModel] = ScheduleVisitInput

    def __init__(self, repository: ProspectRepository) -> None:
        super().__init__()
        self._repository = repository

    def _run(  # type: ignore[override]
        self,
        prospect_id: str,
        scheduled_at: str,
        stage: Optional[str] = "scheduled",
    ) -> dict:
        record = self._repository.update_schedule(
            prospect_id,
            scheduled_at=scheduled_at,
            stage=stage,
        )
        return {
            "status": "ok" if record else "noop",
            "prospect": record,
        }

    async def _arun(self, *args, **kwargs) -> dict:  # pragma: no cover
        return self._run(*args, **kwargs)
