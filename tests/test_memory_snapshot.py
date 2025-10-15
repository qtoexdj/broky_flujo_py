from broky.agents.response import ResponseAgentExecutor
from broky.memory.supabase import SupabaseConversationMemory


class _FakeHistoryRepo:
    def __init__(self):
        self.requests: list[tuple[str, int]] = []

    def fetch_history(self, session_id: str, limit: int = 30):
        self.requests.append((session_id, limit))
        data = [
            {"id": index, "sender_role": "assistant" if index % 2 == 0 else "user", "message": f"msg-{index}"}
            for index in range(1, 11)
        ]
        return data[:limit]


def test_supabase_conversation_memory_respects_window_limit():
    repo = _FakeHistoryRepo()
    memory = SupabaseConversationMemory(repo, window=5)

    history = memory.load("session-123")

    assert repo.requests == [("session-123", 5)]
    assert len(history) == 5
    assert history[0]["message"] == "msg-1"
    assert history[-1]["message"] == "msg-5"


def test_response_agent_history_uses_last_messages():
    full_history = [{"message": f"turn-{i}", "sender_role": "user"} for i in range(1, 13)]
    trimmed = ResponseAgentExecutor._extract_history({"messages": full_history})  # type: ignore[attr-defined]

    assert len(trimmed) == ResponseAgentExecutor.MAX_HISTORY_MESSAGES
    assert [item["message"] for item in trimmed] == [f"turn-{i}" for i in range(7, 13)]
