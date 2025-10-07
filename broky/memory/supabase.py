"""Supabase-backed conversation memory for LangChain agents."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.chat_history_repository import ChatHistoryRepository


class SupabaseConversationMemory:
    """Adapter que expone el historial de conversación como memoria LangChain."""

    def __init__(
        self,
        repository: ChatHistoryRepository | None,
        *,
        window: int = 30,
    ) -> None:
        self._repo = repository
        self._window = window

    def load(self, session_id: str) -> List[Dict[str, Any]]:
        """Retorna los últimos mensajes persistidos para el session_id."""

        if not session_id:
            return []
        if not self._repo:
            return []
        return self._repo.fetch_history(session_id, limit=self._window)

    def snapshot(self, session_id: str) -> Dict[str, Any]:
        """Pequeño helper para serializar el estado de memoria actual."""

        history = self.load(session_id)
        return {
            "session_id": session_id,
            "messages": history,
        }

    def append(
        self,
        *,
        session_id: str,
        user_message: Optional[str] = None,
        assistant_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist incremental changes replicando la estrategia del webhook actual."""

        if not self._repo:
            return

        if user_message:
            self._repo.append_message(
                session_id=session_id,
                sender_role="user",
                message=user_message,
                metadata={"source": "langchain"},
            )

        if assistant_message:
            self._repo.append_message(
                session_id=session_id,
                sender_role="assistant",
                message=assistant_message,
                metadata=metadata,
            )
