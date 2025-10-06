"""Subagente que consulta el microservicio RAG y encapsula su respuesta."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from app.core.config import Settings
from app.services.rag.service import RAGService

logger = logging.getLogger(__name__)


@dataclass
class RAGSubAgentResult:
    """Resultado estructurado entregado por el subagente de RAG."""

    reply: str
    sources: List[Dict[str, Any]]
    mentioned_properties: List[str]
    usage: Optional[Dict[str, Any]]
    raw_response: Dict[str, Any]
    status: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reply": self.reply,
            "sources": self.sources,
            "mentioned_properties": self.mentioned_properties,
            "usage": self.usage,
            "raw_response": self.raw_response,
            "status": self.status,
            "error": self.error,
        }


class RAGSubAgent:
    """Wrapper que prepara la llamada RAG y aplica fallbacks controlados."""

    def __init__(self, settings: Settings, service: Optional[RAGService] = None) -> None:
        self._settings = settings
        self._service = service or RAGService(settings)

    def run(
        self,
        *,
        message: str,
        history: Optional[Sequence[Dict[str, Any]]],
        realtor_id: Optional[str],
    ) -> Optional[RAGSubAgentResult]:
        if not realtor_id:
            logger.warning("RAGSubAgent sin realtor_id; se omite ejecución")
            return None

        if not message.strip():
            logger.warning("RAGSubAgent recibió mensaje vacío; se omite ejecución")
            return None

        if not self._settings.vector_service_configured:
            logger.info("Servicio vectorial no configurado; se responde con fallback RAG")
            return self._fallback_result(reason="vector_service_disabled")

        normalized_history: List[Dict[str, str]] = []
        if history:
            for item in history:
                role = item.get("sender_role") or item.get("role")
                content = item.get("message") or item.get("content")
                if role in {"user", "assistant"} and isinstance(content, str):
                    stripped = content.strip()
                    if stripped:
                        normalized_history.append({"role": role, "message": stripped})

        try:
            rag_response = self._service.answer_query(
                message=message,
                realtor_id=realtor_id,
                history=normalized_history,
            )
        except ValueError:
            raise
        except Exception:  # pragma: no cover - fallback controlado
            logger.exception("Error ejecutando el servicio RAG")
            return self._fallback_result(reason="rag_exception")

        reply = str(rag_response.get("response") or "").strip()
        status = "ok"
        error: Optional[str] = None
        if not reply:
            reply = self._settings.rag_failure_reply
            status = "fallback"
            error = "empty_response"

        sources = rag_response.get("sources") or []
        mentioned = [
            str(source.get("project_id"))
            for source in sources
            if source.get("project_id")
        ]
        usage = rag_response.get("usage")

        if rag_response.get("error"):
            status = "fallback"
            error = str(rag_response.get("error"))

        return RAGSubAgentResult(
            reply=reply,
            sources=sources,
            mentioned_properties=mentioned,
            usage=usage,
            raw_response=rag_response,
            status=status,
            error=error,
        )

    def _fallback_result(self, *, reason: str) -> RAGSubAgentResult:
        return RAGSubAgentResult(
            reply=self._settings.rag_failure_reply,
            sources=[],
            mentioned_properties=[],
            usage=None,
            raw_response={"error": reason},
            status="fallback",
            error=reason,
        )


__all__ = ["RAGSubAgent", "RAGSubAgentResult"]
