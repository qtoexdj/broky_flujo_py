"""LangChain-based subagent for project interest management."""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableLambda

from broky.agents.base import BrokyAgent
from broky.core import BrokyContext
from broky.tools import ProjectInterestLinkTool
from broky.tools.projects import ProjectsListTool


class ProjectInterestAgentExecutor(BrokyAgent):
    """Actualiza intereses de proyectos mediante herramientas LangChain."""

    def __init__(
        self,
        tool: ProjectInterestLinkTool,
        projects_tool: Optional[ProjectsListTool] = None,
    ) -> None:
        self._tool = tool
        self._projects_tool = projects_tool
        super().__init__(runnable=RunnableLambda(self._invoke_tool))

    def build_input(self, context: BrokyContext) -> Dict[str, Any]:
        prospect_id = context.prospect_id or context.payload.get("prospect_id")
        realtor_id = context.realtor_id or context.payload.get("realtor_id")
        message = self._extract_message(context)
        projects = self._collect_project_ids(context, message)

        return {
            "prospect_id": prospect_id,
            "realtor_id": realtor_id,
            "project_ids": projects,
        }

    def handle_output(self, context: BrokyContext, result: Dict[str, Any]) -> BrokyContext:
        context.metadata.setdefault("subagents", {})["filter_intention"] = result
        reply = self._compose_reply(result)
        if reply:
            context.metadata.setdefault("subagent_replies", []).append(reply)
        if result.get("project_records"):
            context.metadata.setdefault("projects_added", result["project_records"])
        return context

    def _invoke_tool(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        prospect_id = payload.get("prospect_id")
        project_ids: List[str] = payload.get("project_ids") or []
        realtor_id = payload.get("realtor_id")

        if not prospect_id or not project_ids:
            return {
                "status": "skipped",
                "reason": "missing_inputs",
                "added": [],
                "skipped": project_ids,
                "project_records": [],
            }

        response = self._tool.invoke(
            {
                "prospect_id": prospect_id,
                "project_ids": project_ids,
                "realtor_id": realtor_id,
            }
        )
        return response

    def _collect_project_ids(self, context: BrokyContext, message: Optional[str]) -> List[str]:
        official = context.payload.get("official_data") or {}
        normalized = context.payload.get("normalized") or {}

        mentioned = self._extract_ids(official, normalized)

        rag_mentions = (
            context.metadata.get("subagents", {})
            .get("filter_rag", {})
            .get("mentioned_properties")
        )
        if isinstance(rag_mentions, list):
            for item in rag_mentions:
                if isinstance(item, str) and item not in mentioned:
                    mentioned.append(item)

        if not mentioned and self._projects_tool:
            fallback_ids = self._infer_from_text(
                message=message,
                realtor_id=context.realtor_id
                or normalized.get("realtor_id")
                or context.payload.get("realtor_id"),
            )
            for project_id in fallback_ids:
                if project_id not in mentioned:
                    mentioned.append(project_id)

        return mentioned

    @staticmethod
    def _extract_ids(official: Dict[str, Any], normalized: Dict[str, Any]) -> List[str]:
        collected: List[str] = []
        for container in (official, normalized):
            if not isinstance(container, dict):
                continue
            mentioned = container.get("mentioned_properties")
            if isinstance(mentioned, list):
                for value in mentioned:
                    if isinstance(value, str) and value not in collected:
                        collected.append(value)
        return collected

    @staticmethod
    def _compose_reply(result: Dict[str, Any]) -> Optional[str]:
        status = result.get("status")
        if status == "skipped":
            return None
        added = result.get("added") or []
        skipped = result.get("skipped") or []
        if added:
            return "He guardado tus proyectos de interés."
        if skipped and not added:
            return (
                "No pude guardar algunos proyectos. Un asesor revisará tu solicitud."
            )
        return None

    def _infer_from_text(self, message: Optional[str], realtor_id: Optional[str]) -> List[str]:
        if not message or not realtor_id or not self._projects_tool:
            return []

        catalog = self._projects_tool.invoke({"realtor_id": realtor_id})
        if not isinstance(catalog, list):
            return []

        index: Dict[str, Dict[str, str]] = {}
        for entry in catalog:
            project_id = entry.get("id")
            name = entry.get("name_property") or entry.get("name") or ""
            normalized = self._normalize_token(name)
            if project_id and normalized:
                index[normalized] = {"id": str(project_id), "name": name}

        normalized_message = self._normalize_token(message)
        matches: List[str] = []
        for key, entry in index.items():
            if key and key in normalized_message:
                matches.append(entry["id"])

        if matches:
            return matches

        closest = difflib.get_close_matches(
            normalized_message, list(index.keys()), n=1, cutoff=0.65
        )
        if closest:
            entry = index.get(closest[0])
            if entry:
                return [entry["id"]]

        return []

    @staticmethod
    def _normalize_token(value: str) -> str:
        normalized = unicodedata.normalize("NFD", value or "")
        without_accents = "".join(
            ch for ch in normalized if unicodedata.category(ch) != "Mn"
        )
        lowered = without_accents.lower()
        return re.sub(r"[^a-z0-9]+", "", lowered)

    @staticmethod
    def _extract_message(context: BrokyContext) -> Optional[str]:
        payload = context.payload
        if isinstance(payload, dict):
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
            normalized = payload.get("normalized")
            if isinstance(normalized, dict):
                alt = normalized.get("message")
                if isinstance(alt, str) and alt.strip():
                    return alt.strip()
        return None
