"""LangChain-based subagent that wraps the existing RAG service."""

from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableLambda

from broky.agents.base import BrokyAgent
from broky.core import BrokyContext
from broky.tools import RAGSearchTool


class RAGAgentExecutor(BrokyAgent):
    """Ejecutor LangChain del subagente RAG."""

    def __init__(self, tool: RAGSearchTool) -> None:
        self._tool = tool
        super().__init__(runnable=RunnableLambda(self._invoke_tool))

    def build_input(self, context: BrokyContext) -> Dict[str, Any]:
        payload = context.payload
        message = self._extract_message(payload)
        history = context.memory_snapshot.get("messages") if context.memory_snapshot else []
        realtor_id = payload.get("realtor_id") or context.realtor_id

        return {
            "message": message,
            "realtor_id": realtor_id,
            "history": history,
        }

    def handle_output(self, context: BrokyContext, result: Dict[str, Any]) -> BrokyContext:
        context.metadata.setdefault("subagents", {})["filter_rag"] = result
        reply = result.get("response")
        if reply:
            context.metadata.setdefault("subagent_replies", []).append(reply)
        return context

    def _invoke_tool(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        message = payload.get("message")
        realtor_id = payload.get("realtor_id")
        history = payload.get("history")
        if not message or not realtor_id:
            return {
                "status": "skipped",
                "error": "missing_inputs",
                "response": None,
                "sources": [],
            }

        response = self._tool.invoke(
            {
                "message": message,
                "realtor_id": realtor_id,
                "history": history,
            }
        )

        return {
            "status": "ok",
            **response,
        }

    @staticmethod
    def _extract_message(payload: Dict[str, Any]) -> Optional[str]:
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        normalized = payload.get("normalized")
        if isinstance(normalized, dict):
            alt = normalized.get("message")
            if isinstance(alt, str) and alt.strip():
                return alt.strip()
        return None
