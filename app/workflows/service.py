"""Runtime helpers to execute the inbound workflow with optional fallbacks."""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.core.config import Settings
from app.workflows.inbound import InboundState, build_inbound_workflow

logger = logging.getLogger(__name__)


class InboundWorkflowService:
    """Wrapper around the LangGraph workflow to simplify execution from FastAPI."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._graph = None

    def run(self, payload: Dict[str, Any]) -> InboundState:
        """Execute the workflow or return a fallback state when Supabase is missing."""

        logger.info("Inbound workflow recibido con claves: %s", list(payload.keys()))

        if not self._settings.supabase_configured:
            logger.warning(
                "Supabase no configurado; se ejecuta flujo reducido para el webhook"
            )
            return self._fallback_state(payload)

        graph = self._ensure_graph()
        result = graph.invoke({"payload": payload})
        return result

    def _ensure_graph(self):
        if self._graph is None:
            self._graph = build_inbound_workflow(self._settings)
        return self._graph

    @staticmethod
    def _fallback_state(payload: Dict[str, Any]) -> InboundState:
        logs = ["Supabase no configurado; se omite pipeline inbound"]
        return {
            "payload": payload,
            "logs": logs,
            "normalized": {},
            "realtor": None,
            "prospect": None,
            "prospect_exists": False,
            "created_prospect": False,
            "properties_interested": [],
            "mentioned_properties": [],
            "automation_allowed": False,
            "handoff_required": True,
            "handoff_reason": "supabase_not_configured",
        }


__all__ = ["InboundWorkflowService"]
