"""Repository helpers for the chats_history_n8n table in Supabase."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from supabase import Client

logger = logging.getLogger(__name__)


class ChatHistoryRepository:
    """Lightweight wrapper around Supabase chat history storage."""

    def __init__(self, client: Client, table: str = "chats_history_n8n") -> None:
        self._client = client
        self._table = table

    def fetch_history(self, session_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        try:
            query = (
                self._client.table(self._table)
                .select("*")
                .eq("session_id", session_id)
                .order("id", desc=False)
                .limit(limit)
            )
            response = query.execute()
        except Exception:  # pragma: no cover - logging only
            logger.exception(
                "No se pudo recuperar el historial de chat para session_id=%s",
                session_id,
            )
            return []

        data = getattr(response, "data", None)
        if not isinstance(data, list):
            return []

        entries: List[Dict[str, Any]] = []
        for row in data:
            raw_message = row.get("message")
            role = row.get("sender_role")
            content: Optional[str] = None
            parsed: Optional[Dict[str, Any]] = None

            if isinstance(raw_message, dict):
                msg_type = str(raw_message.get("type") or "").lower()
                if not role:
                    role = "assistant" if msg_type in {"ai", "assistant"} else "user"
                content = raw_message.get("content")
                parsed = raw_message
            elif isinstance(raw_message, str):
                try:
                    decoded = json.loads(raw_message)
                except (json.JSONDecodeError, TypeError):
                    decoded = None
                if isinstance(decoded, dict):
                    msg_type = str(decoded.get("type") or "").lower()
                    if not role:
                        role = "assistant" if msg_type in {"ai", "assistant"} else "user"
                    content = decoded.get("content")
                    parsed = decoded
                else:
                    content = raw_message

            if not role:
                role = "user"

            entries.append(
                {
                    "id": row.get("id"),
                    "sender_role": role,
                    "message": content,
                    "raw_message": parsed or raw_message,
                }
            )

        return entries

    def append_message(
        self,
        *,
        session_id: str,
        sender_role: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        message_type = "ai" if sender_role == "assistant" else "human"
        message_payload: Dict[str, Any] = {
            "type": message_type,
            "content": message,
            "additional_kwargs": {},
            "response_metadata": {},
        }
        if metadata:
            message_payload["metadata"] = metadata

        payload: Dict[str, Any] = {
            "session_id": session_id,
            "message": json.dumps(message_payload, ensure_ascii=False),
        }

        try:
            self._client.table(self._table).insert(payload).execute()
        except Exception:  # pragma: no cover - logging only
            logger.exception(
                "No se pudo persistir el mensaje en chats_history_n8n | session_id=%s",
                session_id,
            )

    def delete_last(self, session_id: str) -> None:
        try:
            response = (
                self._client.table(self._table)
                .select("id")
                .eq("session_id", session_id)
                .order("id", desc=True)
                .limit(1)
                .execute()
            )
            rows = getattr(response, "data", None) or []
            if not rows:
                return
            record_id = rows[0].get("id")
            if record_id is None:
                return
            self._client.table(self._table).delete().eq("id", record_id).execute()
        except Exception:  # pragma: no cover - optional helper
            logger.warning(
                "No se pudo eliminar el último registro de chats_history_n8n para %s",
                session_id,
                exc_info=True,
            )


__all__ = ["ChatHistoryRepository"]
