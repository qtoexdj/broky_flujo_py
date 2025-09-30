from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore

from app.core.config import Settings
from app.services.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class VectorProjectSearcher:
    """Wraps Supabase vector search to retrieve project snippets by similarity."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._vector_store: Optional[SupabaseVectorStore] = None
        self._init_vector_store()

    def _init_vector_store(self) -> None:
        client = get_supabase_client(self._settings)
        if not client:
            logger.info("Supabase no configurado; vector search deshabilitado")
            return

        embeddings = OpenAIEmbeddings(
            model=self._settings.openai_embeddings_model,
            api_key=self._settings.openai_api_key,
        )

        self._vector_store = SupabaseVectorStore(
            client=client,
            embedding=embeddings,
            table_name=self._settings.vector_table_name,
            query_name="match_vector_projects",
        )
        logger.info(
            "Vector store inicializado con tabla '%s' y modelo '%s'",
            self._settings.vector_table_name,
            self._settings.openai_embeddings_model,
        )

    def search(
        self, query: str, realtor_id: Optional[str] = None, top_k: Optional[int] = None
    ) -> List[Tuple[str, Dict[str, Any], float]]:
        if not self._vector_store:
            logger.debug("Vector store no disponible, se omite búsqueda")
            return []

        k = top_k or self._settings.vector_match_count
        filter_dict = {"realtor_id": realtor_id} if realtor_id else None

        logger.info(
            "Buscando proyectos vectoriales | query='%s' | realtor_id=%s | top_k=%s",
            query,
            realtor_id,
            k,
        )

        try:
            results = self._vector_store.similarity_search_with_relevance_scores(
                query,
                k=k,
                filter=filter_dict,
            )
        except NotImplementedError:
            logger.warning(
                "similarity_search_with_relevance_scores no implementado en SupabaseVectorStore; se omite búsqueda"
            )
            return []
        except Exception:
            logger.exception("Error realizando búsqueda vectorial de proyectos")
            return []

        logger.info("Búsqueda vectorial devolvió %d resultados", len(results))

        formatted: List[Tuple[str, Dict[str, Any], float]] = []
        for doc, score in results:
            metadata = doc.metadata or {}
            formatted.append((doc.page_content, metadata, score))
        return formatted
