"""Placeholder master agent that will orchestrate downstream agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from app.core.config import Settings
from app.workflows.inbound import InboundState


@dataclass
class AgentDecision:
    reply: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class MasterAgent:
    """Temporary orchestrator that will later route towards specialized agents."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def handle(self, state: InboundState) -> AgentDecision:
        handoff_required = bool(state.get("handoff_required"))
        logs = state.get("logs", [])

        if handoff_required:
            reason = state.get("handoff_reason") or "manual_review"
            reply = (
                "Gracias por tu mensaje. Un miembro del equipo te contactará en breve "
                "para continuar la conversación."
            )
            metadata = {"handoff_reason": reason, "logs": logs}
            return AgentDecision(reply=reply, metadata=metadata)

        reply = (
            "Hemos recibido tu solicitud y la estamos procesando de forma automática. "
            "En breve recibirás una respuesta personalizada."
        )
        metadata = {"automation_allowed": True, "logs": logs}
        return AgentDecision(reply=reply, metadata=metadata)


__all__ = ["AgentDecision", "MasterAgent"]
