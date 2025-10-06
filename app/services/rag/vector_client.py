"""HTTP client for the external vector search microservice."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class VectorSearchServiceError(RuntimeError):
    """Raised when the vector microservice cannot be reached successfully."""


@dataclass
class VectorSearchResult:
    """Representation of a single result returned by the vector service."""

    project_id: str
    score: float
    metadata: Dict[str, Any]
    content: str

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "VectorSearchResult":
        return cls(
            project_id=str(payload.get("project_id")),
            score=float(payload.get("score", 0.0)),
            metadata=dict(payload.get("metadata") or {}),
            content=str(payload.get("content") or ""),
        )


class VectorSearchClient:
    """Thin wrapper to query the deployed vector microservice."""

    def __init__(self, settings: Settings, client: Optional[httpx.Client] = None) -> None:
        self._settings = settings
        self._base_url = (
            str(settings.vector_service_url).rstrip("/")
            if settings.vector_service_url
            else None
        )
        self._timeout = settings.vector_service_timeout
        self._client = client

        if not self._base_url:
            logger.warning("VECTOR_SERVICE_URL no configurado; búsqueda vectorial deshabilitada")

    def search(
        self,
        *,
        query: str,
        realtor_id: str,
        limit: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> List[VectorSearchResult]:
        if not self._base_url:
            return []

        payload = {
            "query": query.strip(),
            "realtor_id": realtor_id,
            "limit": limit or self._settings.vector_search_limit,
            "threshold": threshold if threshold is not None else self._settings.vector_search_threshold,
        }

        logger.info(
            "Invocando servicio vectorial | url=%s | realtor=%s | limit=%s | threshold=%s",
            self._base_url,
            realtor_id,
            payload["limit"],
            payload["threshold"],
        )

        max_attempts = 2
        last_exception: Optional[Exception] = None
        data: Optional[Dict[str, Any]] = None

        for attempt in range(max_attempts):
            client: Optional[httpx.Client] = None
            try:
                client = self._client or httpx.Client(
                    base_url=self._base_url,
                    timeout=self._timeout,
                )
                response = client.post("/vectors/search", json=payload)
                response.raise_for_status()
                content = response.json()
                if not isinstance(content, dict):
                    raise VectorSearchServiceError(
                        "Respuesta inválida del microservicio vectorial",
                    )
                data = content
                break
            except httpx.TimeoutException as exc:
                last_exception = exc
                logger.warning(
                    "Timeout consultando el microservicio vectorial (intento %d/%d)",
                    attempt + 1,
                    max_attempts,
                )
            except httpx.HTTPStatusError as exc:
                last_exception = exc
                logger.warning(
                    "HTTP %s desde el microservicio vectorial (intento %d/%d): %s",
                    exc.response.status_code,
                    attempt + 1,
                    max_attempts,
                    exc.response.text,
                )
            except Exception as exc:  # pragma: no cover - defensive failure path
                last_exception = exc
                logger.exception(
                    "Error inesperado al invocar el microservicio vectorial | intento %d/%d",
                    attempt + 1,
                    max_attempts,
                )
            finally:
                if self._client is None and client is not None:
                    client.close()

            if attempt + 1 < max_attempts:
                backoff_seconds = min(1.0, 0.4 * (2**attempt))
                logger.info(
                    "Reintentando consulta vectorial tras %.2fs", backoff_seconds
                )
                time.sleep(backoff_seconds)

        if data is None:
            raise VectorSearchServiceError("No se pudo consultar el microservicio vectorial") from last_exception

        raw_results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(raw_results, list):
            logger.warning("Respuesta del microservicio sin 'results' válido: %s", data)
            return []

        results = [VectorSearchResult.from_dict(item) for item in raw_results]
        logger.info("Servicio vectorial devolvió %d resultados", len(results))
        return results


__all__ = [
    "VectorSearchClient",
    "VectorSearchResult",
    "VectorSearchServiceError",
]
