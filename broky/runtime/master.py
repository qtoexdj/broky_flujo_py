"""Bridge layer that executes the Master Agent using LangChain."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.config import Settings
from app.services.chat_history_repository import ChatHistoryRepository
from app.services.followup_repository import FollowupRepository
from app.services.profile_repository import ProfileRepository
from app.services.prospect_repository import ProspectRepository
from app.services.supabase_client import get_supabase_client

from broky.agents import (
    MasterAgentExecutor,
    ResponseAgentExecutor,
    FixingResponseAgentExecutor,
    SplitResponseAgentExecutor,
    JustificationAgentExecutor,
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
    assign_broker_if_needed,
    build_notifications,
    process_contact_request,
    process_user_opt_out,
    schedule_broker_followup,
    schedule_prospect_followup,
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
        self._profile_repo = ProfileRepository(client) if client else None
        self._prospect_repo = ProspectRepository(client) if client else None
        self._memory = SupabaseConversationMemory(self._history_repo) if self._history_repo else None
        self._executor = MasterAgentExecutor()
        self._response_agent = ResponseAgentExecutor()
        self._fixing_agent = FixingResponseAgentExecutor()
        self._splitter_agent = SplitResponseAgentExecutor()
        self._justification_agent = JustificationAgentExecutor()

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
        updated_context = self._run_response(updated_context)
        updated_context = self._run_fixing_response(updated_context)
        updated_context = self._run_splitter(updated_context)
        updated_context = self._run_justification(updated_context)

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
            postprocess=metadata.get("postprocess"),
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

    def _run_response(self, context: BrokyContext) -> BrokyContext:
        try:
            return self._response_agent.invoke(context)
        except Exception:  # pragma: no cover - fallback defensivo
            logger.exception("Error ejecutando ResponseAgent; se usará fallback")
            return context

    def _run_fixing_response(self, context: BrokyContext) -> BrokyContext:
        try:
            return self._fixing_agent.invoke(context)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception(
                "Error ejecutando FixingResponseAgent; se mantiene respuesta original"
            )
            return context

    def _run_splitter(self, context: BrokyContext) -> BrokyContext:
        combined_reply = self._compose_full_response(context)
        if combined_reply:
            context.metadata["reply"] = combined_reply
        try:
            updated = self._splitter_agent.invoke(context)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Error ejecutando SplitResponseAgent; no se dividirá la respuesta")
            return context

        postprocess = updated.metadata.get("postprocess") if isinstance(updated.metadata, dict) else None
        if isinstance(postprocess, dict):
            split_messages = postprocess.get("split_messages")
            if isinstance(split_messages, list) and split_messages:
                first = split_messages[0]
                if isinstance(first, str) and first.strip():
                    updated.metadata["reply"] = first.strip()
        return updated

    def _run_justification(self, context: BrokyContext) -> BrokyContext:
        try:
            return self._justification_agent.invoke(context)
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Error ejecutando JustificationAgent; se omitirá la justificación")
            return context

    @staticmethod
    def _compose_reply(metadata: Dict[str, Any]) -> str:
        postprocess = metadata.get("postprocess") if isinstance(metadata, dict) else None
        if isinstance(postprocess, dict):
            split_messages = postprocess.get("split_messages")
            if isinstance(split_messages, list):
                for item in split_messages:
                    if isinstance(item, str) and item.strip():
                        return item.strip()

        base_reply = metadata.get("reply") if isinstance(metadata, dict) else None
        if isinstance(base_reply, str) and base_reply.strip():
            return base_reply.strip()

        subagent_replies = metadata.get("subagent_replies") if isinstance(metadata, dict) else None
        if isinstance(subagent_replies, list):
            combined = " ".join(reply for reply in subagent_replies if reply)
            if combined:
                return combined

        return "Hemos recibido tu mensaje y continuaremos contigo en breve."

    def _compose_full_response(self, context: BrokyContext) -> str:
        segments: List[str] = []
        base_reply = context.metadata.get("reply") if isinstance(context.metadata, dict) else None
        if isinstance(base_reply, str) and base_reply.strip():
            segments.append(base_reply.strip())

        extras = context.metadata.get("subagent_replies") if isinstance(context.metadata, dict) else None
        if isinstance(extras, list):
            for extra in extras:
                if not isinstance(extra, str):
                    continue
                cleaned = extra.strip()
                if cleaned and cleaned not in segments:
                    segments.append(cleaned)

        combined = "\n\n".join(segments).strip()
        return combined

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

        payload = context.payload if isinstance(context.payload, dict) else {}
        official = payload.get("official_data") if isinstance(payload, dict) else {}
        if not isinstance(official, dict):
            official = {}

        handoff_reply: Optional[str] = None
        if filters.get("filter_desinteres"):
            handoff_reply = process_user_opt_out(context.metadata)
        elif filters.get("filter_contact"):
            handoff_reply = process_contact_request(context.metadata)

        if handoff_reply:
            replies.append(handoff_reply)

        handoff_required = bool(context.metadata.get("handoff_required"))
        handoff_reason = context.metadata.get("handoff_reason")

        broker_assignment = None
        if (
            handoff_required
            and handoff_reason != "desinteres"
            and isinstance(official, dict)
        ):
            broker_assignment = assign_broker_if_needed(
                self._profile_repo,
                self._prospect_repo,
                official_data=official,
            )
            context.metadata.setdefault("assignments", {})["broker"] = broker_assignment

        if isinstance(official, dict):
            notifications = build_notifications(
                official_data=official,
                handoff_reason=handoff_reason,
                filters=filters,
                broker_assignment=broker_assignment,
            )
            if notifications:
                context.metadata.setdefault("notifications", []).extend(notifications)

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
        postprocess: Optional[Dict[str, Any]] = None,
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
        if postprocess:
            metadata["postprocess"] = postprocess
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
