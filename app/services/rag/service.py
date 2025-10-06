"""Main RAG engine that orchestrates vector retrieval and OpenAI generation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from openai import OpenAI

from app.core.config import Settings
from app.services.rag.context_formatter import format_rag_context
from app.services.rag.vector_client import (
    VectorSearchClient,
    VectorSearchResult,
    VectorSearchServiceError,
)

logger = logging.getLogger(__name__)


class RAGService:
    """Coordinates Retrieval-Augmented Generation logic for property queries."""

    def __init__(
        self,
        settings: Settings,
        *,
        vector_client: Optional[VectorSearchClient] = None,
        llm_client: Optional[OpenAI] = None,
    ) -> None:
        self._settings = settings
        self._vector_client = vector_client or VectorSearchClient(settings)
        self._llm_client = llm_client or OpenAI(api_key=settings.openai_api_key)
        self._prompt = self._load_prompt()

    def answer_query(
        self,
        *,
        message: str,
        realtor_id: str,
        history: Optional[Sequence[Dict[str, Any]]] = None,
        limit: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Generate an answer constrained by retrieved project context."""

        sanitized_question = message.strip()
        if not sanitized_question:
            raise ValueError("El mensaje del usuario no puede estar vacío")

        vector_results, vector_failed = self._search_context(
            query=sanitized_question,
            realtor_id=realtor_id,
            limit=limit,
            threshold=threshold,
        )

        if vector_failed:
            logger.warning(
                "Vector service unavailable, returning safe fallback reply | realtor=%s",
                realtor_id,
            )
            return self._build_failure_response()

        context_text = format_rag_context(vector_results)
        sources = _extract_sources(vector_results)

        logger.info(
            "Generando respuesta RAG | realtor=%s | resultados=%d",
            realtor_id,
            len(vector_results),
        )

        system_prompt = self._build_system_prompt(context_text, sanitized_question)
        messages = self._compose_messages(system_prompt, history, sanitized_question)

        completion = self._llm_client.chat.completions.create(
            model=self._settings.openai_model,
            temperature=0.3,
            max_tokens=1000,
            messages=messages,
        )

        content = completion.choices[0].message.content.strip()
        usage = getattr(completion, "usage", None)

        return {
            "response": content,
            "sources": sources,
            "context": context_text,
            "sources_count": len(sources),
            "usage": usage.model_dump() if hasattr(usage, "model_dump") else usage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _search_context(
        self,
        *,
        query: str,
        realtor_id: str,
        limit: Optional[int],
        threshold: Optional[float],
    ) -> Tuple[List[VectorSearchResult], bool]:
        try:
            results = self._vector_client.search(
                query=query,
                realtor_id=realtor_id,
                limit=limit,
                threshold=threshold,
            )
        except VectorSearchServiceError:
            logger.warning("Fallo al recuperar contexto vectorial para %s", realtor_id)
            return [], True

        if results:
            return results, False

        for fallback in self._build_fallback_queries(query):
            try:
                fallback_results = self._vector_client.search(
                    query=fallback,
                    realtor_id=realtor_id,
                    limit=limit,
                    threshold=threshold,
                )
            except VectorSearchServiceError:
                logger.warning(
                    "Fallo en búsqueda vectorial de respaldo '%s' para %s",
                    fallback,
                    realtor_id,
                )
                return [], True

            if fallback_results:
                logger.info(
                    "Búsqueda vectorial fallback '%s' devolvió %d resultados",
                    fallback,
                    len(fallback_results),
                )
                return fallback_results, False

        return [], False

    def _build_failure_response(self) -> Dict[str, Any]:
        """Return a safe response when RAG cannot run due to service errors."""

        return {
            "response": self._settings.rag_failure_reply,
            "sources": [],
            "context": "",
            "sources_count": 0,
            "usage": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": "vector_service_unavailable",
        }

    def _build_system_prompt(self, context: str, question: str) -> str:
        base_instructions = self._prompt
        context_block = context.strip() or "Sin contexto relevante disponible."

        guidance = (
            "Reglas estrictas:\n"
            "1. Responde únicamente con la información del contexto.\n"
            "2. Si no encuentras datos suficientes en el contexto, indica que no hay información disponible.\n"
            "3. Menciona siempre el nombre del proyecto y detalles concretos (precios, ubicación, tipología, estado) si están presentes.\n"
            "4. Mantén un tono profesional y conciso.\n"
            "5. No inventes ni hagas suposiciones fuera del contexto."
        )

        return (
            f"{base_instructions}\n\n"
            f"Consulta del usuario: {question}\n\n"
            f"Contexto:\n{context_block}\n\n"
            f"{guidance}"
        )

    def _load_prompt(self) -> str:
        path = Path(self._settings.rag_prompt_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[3] / path
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning(
                "Prompt RAG no encontrado en %s; usando configuración por defecto",
                path,
            )
            return self._settings.rag_system_prompt
        except Exception:  # pragma: no cover - logging only
            logger.exception(
                "Error leyendo el prompt RAG en %s; usando configuración por defecto",
                path,
            )
            return self._settings.rag_system_prompt

        stripped = text.strip()
        if not stripped:
            logger.warning(
                "Prompt RAG vacío en %s; usando configuración por defecto", path
            )
            return self._settings.rag_system_prompt

        logger.info("Prompt RAG cargado desde %s", path)
        return stripped

    @staticmethod
    def _compose_messages(
        system_prompt: str,
        history: Optional[Sequence[Dict[str, Any]]],
        question: str,
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

        if history:
            for item in history:
                role = item.get("role")
                content = item.get("message") or item.get("content")
                if role not in {"user", "assistant"} or not content:
                    continue
                messages.append({"role": role, "content": str(content)})

        messages.append({"role": "user", "content": question})
        return messages

    @staticmethod
    def _build_fallback_queries(query: str) -> List[str]:
        """Generate simplified alternatives when the main search returns nothing."""

        normalized = _strip_accents(query).lower()
        normalized = normalized.replace("¿", " ").replace("?", " ").strip()
        normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()

        if not normalized:
            return []

        tokens = [
            token
            for token in normalized.split()
            if token and token not in _STOPWORDS and len(token) > 2
        ]

        candidates: List[str] = []

        if normalized and normalized != query:
            candidates.append(normalized)

        keywords = " ".join(tokens)
        if keywords and keywords not in {query, normalized}:
            candidates.append(keywords)

        if tokens:
            top_tokens = " ".join(tokens[:5])
            if top_tokens and top_tokens not in candidates:
                candidates.append(top_tokens)

        return candidates


def _extract_sources(results: Iterable[VectorSearchResult]) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    for item in results:
        metadata = item.metadata or {}
        name = (
            metadata.get("project_name")
            or metadata.get("name")
            or metadata.get("title")
            or metadata.get("property_name")
            or item.project_id
        )
        sources.append(
            {
                "project_id": item.project_id,
                "name": name,
                "score": item.score,
            }
        )
    return sources


__all__ = ["RAGService"]


_STOPWORDS = {
    "que",
    "qué",
    "tienes",
    "tengo",
    "hay",
    "una",
    "un",
    "los",
    "las",
    "en",
    "de",
    "para",
    "con",
    "disponibles",
    "disponible",
    "sobre",
    "cuáles",
    "cuales",
    "donde",
    "dónde",
    "me",
    "puedes",
    "puedo",
    "por",
    "favor",
}


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
