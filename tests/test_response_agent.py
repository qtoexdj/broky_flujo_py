"""Tests for the response agent behaviour on multi-turn conversations."""

from broky.agents.response import ResponseAgentExecutor
from broky.core.context import BrokyContext


def test_response_agent_uses_fallback_when_reply_is_empty():
    """Regresiones: el segundo mensaje no debe quedarse sin respuesta."""

    context = BrokyContext(
        session_id="test-session",
        payload={"message": "Hola"},
        realtor_id="realtor-123",
        prospect_id="prospect-456",
    )
    context.metadata["filters"] = {"filter_contact": True}

    agent = ResponseAgentExecutor()

    updated_context = agent.handle_output(context, {"reply": "   ", "stage": None})

    reply = updated_context.metadata.get("reply")
    assert reply, "El agente debe generar un fallback cuando la respuesta del modelo es vacía"
    assert "asesor humano" in reply.lower()
