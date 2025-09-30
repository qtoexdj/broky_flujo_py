import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import Settings
from app.experimental.chatbot.flow import build_conversation_graph
from app.experimental.chatbot.memory import ConversationMemory
from app.services.project_repository import ProjectRepository
from app.services.supabase_client import get_supabase_client
from app.experimental.chatbot.vector_search import VectorProjectSearcher

logger = logging.getLogger(__name__)


class ConversationService:
    """Coordinates memory, Supabase context and the LangGraph flow."""

    def __init__(self, settings: Settings, history_limit: int = 12) -> None:
        self._settings = settings
        self._memory = ConversationMemory(max_messages=history_limit)
        self._graph = build_conversation_graph(settings)

        client = get_supabase_client(settings)
        self._projects_repo = ProjectRepository(client) if client else None
        self._vector_searcher = VectorProjectSearcher(settings) if client else None

    def process_message(
        self,
        user_id: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        realtor_id: Optional[str] = None,
    ) -> str:
        logger.info(
            "Procesando mensaje | user_id=%s | realtor_id=%s | texto='%s'",
            user_id,
            realtor_id,
            message,
        )

        history = self._memory.get(user_id)
        logger.debug("Historial recuperado con %d mensajes", len(history))

        combined_metadata = dict(metadata or {})
        if realtor_id:
            combined_metadata.setdefault("realtor_id", realtor_id)

        user_message = HumanMessage(
            content=message,
            additional_kwargs={"metadata": combined_metadata},
        )

        context_messages: List[SystemMessage] = [
            SystemMessage(content=self._settings.system_prompt)
        ]

        if realtor_id:
            context_text = self._build_project_context(realtor_id, message)
            if context_text:
                logger.info("Contexto de proyectos generado (%d chars)", len(context_text))
                context_messages.append(SystemMessage(content=context_text))
            else:
                logger.info("No se generó contexto adicional para realtor %s", realtor_id)

        input_messages = [
            *context_messages,
            *history,
            user_message,
        ]

        result = self._graph.invoke({"messages": input_messages})
        messages = result["messages"]
        bot_message = messages[-1]

        updated_history = [*history, user_message, bot_message]
        self._memory.update(user_id, updated_history)
        logger.debug("Historial actualizado con %d mensajes", len(updated_history))

        return bot_message.content

    def _build_project_context(self, realtor_id: str, query: str) -> Optional[str]:
        if not self._projects_repo and not self._vector_searcher:
            logger.debug("Supabase no configurado; se omite la carga de proyectos")
            return None

        sections: List[str] = []

        vector_section = self._build_vector_context(realtor_id, query)
        if vector_section:
            sections.append(vector_section)

        repo_section = self._build_repo_context(realtor_id)
        if repo_section:
            sections.append(repo_section)

        if not sections:
            logger.info("Sin resultados de proyectos para realtor %s", realtor_id)
            return None

        return "\n\n".join(sections)

    def _build_vector_context(self, realtor_id: str, query: str) -> Optional[str]:
        if not self._vector_searcher:
            return None

        results = self._vector_searcher.search(query=query, realtor_id=realtor_id)
        if not results:
            logger.info(
                "Búsqueda vectorial sin resultados | realtor_id=%s | query='%s'",
                realtor_id,
                query,
            )
            return None

        lines = []
        for idx, (content, metadata, score) in enumerate(results, start=1):
            name = metadata.get("property_name") or metadata.get("project_name")
            if not name:
                name = metadata.get("project_id") or f"Resultado {idx}"

            location = metadata.get("location") or metadata.get("city")
            extras = []
            if location:
                extras.append(f"ubicación: {location}")
            if metadata.get("prices"):
                extras.append(f"precios: {metadata['prices']}")
            extras.append(f"score: {score:.3f}")

            snippet = content.replace("\n", " ")
            snippet = snippet[:280] + ("…" if len(snippet) > 280 else "")

            detail_parts = [snippet]
            if extras:
                detail_parts.append("; ".join(extras))
            detail = " | ".join(detail_parts)

            lines.append(f"- {name}: {detail}")

        logger.info(
            "Construido contexto vectorial con %d resultados para realtor %s",
            len(lines),
            realtor_id,
        )

        return (
            f"Resultados vectoriales (asesor {realtor_id}, consulta '{query}'):\n"
            + "\n".join(lines)
        )

    def _build_repo_context(self, realtor_id: str) -> Optional[str]:
        if not self._projects_repo:
            return None

        try:
            projects = self._projects_repo.list_by_realtor(realtor_id)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Error consultando proyectos para el realtor %s", realtor_id)
            return "No fue posible obtener proyectos en este momento."

        if not projects:
            logger.info("Repositorio sin resultados para realtor %s", realtor_id)
            return None

        summaries = [self._format_project_summary(project) for project in projects]
        joined = "\n".join(f"- {summary}" for summary in summaries)
        logger.info(
            "Construido contexto de repositorio con %d proyectos para realtor %s",
            len(summaries),
            realtor_id,
        )
        return (
            f"Listado general de proyectos del asesor {realtor_id}:\n"
            f"{joined}"
        )

    @staticmethod
    def _format_project_summary(project: Dict[str, Any]) -> str:
        name = (
            project.get("name")
            or project.get("title")
            or project.get("project_name")
            or f"ID {project.get('id')}"
        )

        extra_parts: List[str] = []
        for key in ("status", "stage", "city", "location"):
            value = project.get(key)
            if value:
                extra_parts.append(f"{key}: {value}")

        price = project.get("price") or project.get("starting_price")
        if price:
            extra_parts.append(f"precio: {price}")

        if extra_parts:
            return f"{name} ({', '.join(extra_parts)})"

        return str(name)
