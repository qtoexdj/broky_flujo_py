"""Common context shared between LangGraph and LangChain layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BrokyContext:
    """Container for conversation state across the hybrid runtime.

    The structure keeps the payload del webhook, ids básicos y el snapshot
    que cada agente LangChain necesita para mantener continuidad. Se diseña
    para ser serializable (dict) y compatible con LangGraph StateGraph.
    """

    session_id: str
    payload: Dict[str, Any]
    realtor_id: Optional[str] = None
    prospect_id: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    handoff_required: bool = False
    handoff_reason: Optional[str] = None
    memory_snapshot: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def append_log(self, message: str) -> None:
        """Add a log entry preserving order for trazabilidad."""

        if message:
            self.logs.append(message)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the context for LangGraph checkpoints or logging."""

        return {
            "session_id": self.session_id,
            "payload": self.payload,
            "realtor_id": self.realtor_id,
            "prospect_id": self.prospect_id,
            "logs": list(self.logs),
            "handoff_required": self.handoff_required,
            "handoff_reason": self.handoff_reason,
            "memory_snapshot": self.memory_snapshot,
            "metadata": self.metadata,
        }

    @classmethod
    def from_state(cls, state: Dict[str, Any]) -> "BrokyContext":
        """Rehydrate a context from persisted state dictionaries."""

        return cls(
            session_id=state.get("session_id") or "",
            payload=dict(state.get("payload") or {}),
            realtor_id=state.get("realtor_id"),
            prospect_id=state.get("prospect_id"),
            logs=list(state.get("logs") or []),
            handoff_required=bool(state.get("handoff_required", False)),
            handoff_reason=state.get("handoff_reason"),
            memory_snapshot=dict(state.get("memory_snapshot") or {}),
            metadata=dict(state.get("metadata") or {}),
        )
