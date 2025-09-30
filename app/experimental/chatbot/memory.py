from threading import Lock
from typing import Dict, List

from langchain_core.messages import BaseMessage


class ConversationMemory:
    """Very small in-memory store to keep recent chat history per user."""

    def __init__(self, max_messages: int = 10) -> None:
        self._max_messages = max_messages
        self._store: Dict[str, List[BaseMessage]] = {}
        self._lock = Lock()

    def get(self, user_id: str) -> List[BaseMessage]:
        with self._lock:
            history = self._store.get(user_id, [])
            return list(history)

    def update(self, user_id: str, messages: List[BaseMessage]) -> None:
        with self._lock:
            self._store[user_id] = list(messages[-self._max_messages :])

    def clear(self, user_id: str) -> None:
        with self._lock:
            self._store.pop(user_id, None)

    def reset(self) -> None:
        with self._lock:
            self._store.clear()
