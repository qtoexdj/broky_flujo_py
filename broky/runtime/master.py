"""Bridge layer that executes the Master Agent using LangChain."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.core.config import Settings
from app.services.chat_history_repository import ChatHistoryRepository
from app.services.supabase_client import get_supabase_client
from app.services.followup_repository import FollowupRepository

from broky.agents import (
    MasterAgentExecutor,
    ProjectInterestAgentExecutor,
    RAGAgentExecutor,
    CalificationAgentExecutor,
    ScheduleAgentExecutor,
    FilesAgentExecutor,
)
from broky.core import BrokyContext
from broky.memory import SupabaseConversationMemory
from broky.tools import ToolRegistry, register_default_tools
from broky.processes import (
    schedule_broker_followup,
    schedule_prospect_followup,
    process_contact_request,
    process_user_opt_out,
)

logger = logging.getLogger(__name__)


@dataclass
class MasterAgentOutput:
    reply: str
    intents: list[str]
    filters: Dict[str, Any]
    handoff: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


class MasterAgentRuntime:
    """Orquesta la ejecución del Master Agent desde el pipeline inbound."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        client = get_supabase_client(settings)
        self._history_repo = ChatHistoryRepository(client) if client else None
        self._memory = SupabaseConversationMemory(self._history_repo) if self._history_repo else None
        self._executor = MasterAgentExecutor()

        self._tool_registry = ToolRegistry()
        register_default_tools(self._tool_registry, supabase_client=client)

        self._rag_agent: Optional[RAGAgentExecutor]
        try:
            rag_tool = self._tool_registry.get("rag_search")
            self._rag_agent = RAGAgentExecutor(rag_tool)
        except KeyError:
            self._rag_agent = None

        self._project_interest_agent: Optional[ProjectInterestAgentExecutor]
        try:
            pi_tool = self._tool_registry.get("project_interest_link")
            self._project_interest_agent = ProjectInterestAgentExecutor(pi_tool)
        except KeyError:
            self._project_interest_agent = None

        try:
            cal_tool = self._tool_registry.get("calification_update")
            self._calification_agent = CalificationAgentExecutor(cal_tool)
        except KeyError:
            self._calification_agent = None

        try:
            schedule_tool = self._tool_registry.get("schedule_visit")
            self._schedule_agent = ScheduleAgentExecutor(schedule_tool)
        except KeyError:
            self._schedule_agent = None

        try:
            projects_tool = self._tool_registry.get("projects_list")
            files_tool = self._tool_registry.get("project_files")
            self._files_agent = FilesAgentExecutor(projects_tool, files_tool)
        except KeyError:
            self._files_agent = None

        self._followup_repo = FollowupRepository(client) if client else None

    def run(self, state: Dict[str, Any]) -> MasterAgentOutput:
        payload = dict(state.get("payload") or {})
        normalized = dict(state.get("normalized") or {})

        session_id = self._resolve_session_id(payload, normalized)
        context = BrokyContext(
            session_id=session_id,
            payload=self._compose_payload(payload, state),
            realtor_id=normalized.get("realtor_id") or payload.get("realtor_id"),
            prospect_id=normalized.get("prospect_id") or payload.get("prospect_id"),
        )

        if self._memory and session_id:
            context.memory_snapshot = self._memory.snapshot(session_id)

        context.metadata["inbound_state"] = state

        updated_context = self._executor.invoke(context)
        updated_context = self._run_subagents(updated_context)

        metadata = updated_context.metadata
        reply = self._compose_reply(metadata)
        intents = metadata.get("intents") or []
        filters = metadata.get("filters") or {}
        handoff = bool(metadata.get("master_agent", {}).get("handoff", False))

        metadata["final_reply"] = reply

        self._persist_memory(
            session_id=session_id,
            payload=payload,
            reply=reply,
            intents=intents,
            filters=filters,
            extra_metadata=metadata.get("subagents"),
        )

        return MasterAgentOutput(
            reply=reply,
            intents=intents,
            filters=filters,
            handoff=handoff,
            metadata=metadata,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_session_id(payload: Dict[str, Any], normalized: Dict[str, Any]) -> str:
        for key in ("session_id", "chat_id", "user_id"):
            candidate = normalized.get(key) or payload.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        return payload.get("from") or "anonymous"

    def _run_subagents(self, context: BrokyContext) -> BrokyContext:
        context.metadata.setdefault("subagents", {})
        context.metadata.setdefault("subagent_replies", [])
        filters = context.metadata.get("filters") or {}

        if filters.get("filter_rag") and self._rag_agent:
            context = self._rag_agent.invoke(context)
        if filters.get("filter_intention") and self._project_interest_agent:
            context = self._project_interest_agent.invoke(context)
        if filters.get("filter_calification") and self._calification_agent:
            context = self._calification_agent.invoke(context)
        if filters.get("filter_schedule") and self._schedule_agent:
            context = self._schedule_agent.invoke(context)
        if filters.get("filter_files") and self._files_agent:
            context = self._files_agent.invoke(context)

        if self._followup_repo:
            context = self._run_followups(context)

        context = self._run_handoff(context)

        return context

    @staticmethod
    def _compose_reply(metadata: Dict[str, Any]) -> str:
        base_reply = metadata.get("reply") or ""
        subagent_replies = metadata.get("subagent_replies") or []
        if isinstance(subagent_replies, list):
            additional = " ".join(reply for reply in subagent_replies if reply)
            if additional:
                if base_reply:
                    return f"{base_reply} {additional}".strip()
                return additional
        return base_reply

    def _run_followups(self, context: BrokyContext) -> BrokyContext:
        official = {}
        payload = context.payload
        if isinstance(payload, dict):
            official = payload.get("official_data") or {}

        if not isinstance(official, dict):
            return context

        prospect_result = schedule_prospect_followup(
            self._followup_repo,
            official_data=official,
        )
        broker_result = schedule_broker_followup(
            self._followup_repo,
            official_data=official,
        )

        if prospect_result or broker_result:
            followups_meta = context.metadata.setdefault("followups", {})
            if prospect_result:
                followups_meta["prospect"] = prospect_result
            if broker_result:
                followups_meta["broker"] = broker_result

        return context

    def _run_handoff(self, context: BrokyContext) -> BrokyContext:
        filters = context.metadata.get("filters") or {}
        replies = context.metadata.setdefault("subagent_replies", [])

        if filters.get("filter_desinteres"):
            reply = process_user_opt_out(context.metadata)
            replies.append(reply)
        elif filters.get("filter_contact"):
            reply = process_contact_request(context.metadata)
            replies.append(reply)

        return context

    def _compose_payload(self, payload: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        enriched = dict(payload)
        normalized = state.get("normalized")
        if isinstance(normalized, dict):
            enriched.setdefault("normalized", normalized)
        official = state.get("official_data") or state.get("official")
        if official:
            enriched["official_data"] = official
        return enriched

    def _persist_memory(
        self,
        *,
        session_id: str,
        payload: Dict[str, Any],
        reply: str,
        intents: list[str],
        filters: Dict[str, Any],
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._memory:
            return

        user_message = self._extract_message(payload)
        metadata = {
            "intents": intents,
            "filters": filters,
        }
        if extra_metadata:
            metadata["subagents"] = extra_metadata
        self._memory.append(
            session_id=session_id,
            user_message=user_message,
            assistant_message=reply,
            metadata=metadata,
        )

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
