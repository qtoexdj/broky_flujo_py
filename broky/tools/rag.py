"""RAG integration tool for LangChain agents."""

from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.services.rag.service import RAGService


class RAGSearchInput(BaseModel):
    message: str = Field(..., description="Consulta del usuario ya normalizada")
    realtor_id: str = Field(..., description="Realtor asociado para multi-tenancy")
    history: Optional[list[Dict[str, Any]]] = Field(
        default=None, description="Historial de conversación relevante"
    )
    limit: Optional[int] = Field(default=None)
    threshold: Optional[float] = Field(default=None)


class RAGSearchTool(BaseTool):
    name: str = "rag_search"
    description: str = (
        "Consulta el microservicio vectorial y genera respuesta enriquecida usando RAGService."
    )
    args_schema: type[BaseModel] = RAGSearchInput

    def __init__(self, rag_service: RAGService) -> None:
        super().__init__()
        self._service = rag_service

    def _run(  # type: ignore[override]
        self,
        message: str,
        realtor_id: str,
        history: Optional[list[Dict[str, Any]]] = None,
        limit: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        response = self._service.answer_query(
            message=message,
            realtor_id=realtor_id,
            history=history,
            limit=limit,
            threshold=threshold,
        )
        return response

    async def _arun(self, *args, **kwargs) -> Dict[str, Any]:  # pragma: no cover
        return self._run(*args, **kwargs)
