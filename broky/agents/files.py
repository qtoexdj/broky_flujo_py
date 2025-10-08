"""LangChain-based subagent to retrieve project files."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI

from broky.agents.base import BrokyAgent
from broky.config import get_langchain_settings
from broky.core import BrokyContext
from broky.tools import ProjectFilesTool, ProjectsListTool

logger = logging.getLogger(__name__)


class FilesAgentExecutor(BrokyAgent):
    """Subagente que localiza y entrega archivos solicitados por el usuario."""

    PROMPT_PATH = Path("docs/prompts/files_subagent_prompt.md")
    SUPPORTED_TYPES = {"image", "video", "kmz", "document"}

    def __init__(
        self,
        projects_tool: ProjectsListTool,
        files_tool: ProjectFilesTool,
    ) -> None:
        self._settings = get_langchain_settings()
        self._projects_tool = projects_tool
        self._files_tool = files_tool
        if self._settings.openai_api_key:
            self._model = ChatOpenAI(
                api_key=self._settings.openai_api_key,
                model=self._settings.openai_model,
                temperature=0,
                model_kwargs={"response_format": {"type": "json_object"}}
            )
        else:
            logger.warning(
                "OPENAI_API_KEY no configurado; FilesAgentExecutor operará con heurística"
            )
            self._model = None

        self._prompt_text = self._load_prompt()

        super().__init__(runnable=RunnableLambda(self._execute))

    def build_input(self, context: BrokyContext) -> Dict[str, Any]:
        payload = context.payload
        normalized = payload.get("normalized") if isinstance(payload, dict) else {}
        message = self._extract_message(normalized, payload)
        history = context.memory_snapshot.get("messages") if context.memory_snapshot else []
        realtor_id = context.realtor_id or normalized.get("realtor_id") or payload.get("realtor_id")

        return {
            "message": message,
            "history": history,
            "realtor_id": realtor_id,
        }

    def handle_output(self, context: BrokyContext, result: Dict[str, Any]) -> BrokyContext:
        context.metadata.setdefault("subagents", {})["filter_files"] = result
        reply = result.get("reply")
        if reply:
            context.metadata.setdefault("subagent_replies", []).append(reply)
        links = result.get("links")
        if links:
            context.metadata.setdefault("files_links", links)
        return context

    # ------------------------------------------------------------------

    def _execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        message = payload.get("message")
        realtor_id = payload.get("realtor_id")
        if not message or not realtor_id:
            return {
                "reply": "¿Podrías indicar qué archivos necesitas y para qué proyecto?",
                "links": [],
                "status": "missing_inputs",
            }

        structured = self._invoke_llm(
            message=message,
            history=payload.get("history") or [],
        )

        if not structured:
            structured = self._heuristic_output(message)

        file_types = self._coerce_types(structured.get("types") or structured.get("type"))
        projects_requested = self._coerce_projects(structured.get("projects"))
        reply = structured.get("reply") or "Estoy recopilando los archivos solicitados."

        if not file_types:
            return {
                "reply": "¿Necesitas fotos, videos u otro documento? Indícamelo para ayudarte.",
                "links": [],
                "status": "pending_type",
            }

        if not projects_requested:
            return {
                "reply": "¿Para qué proyecto necesitas los archivos? Necesito el nombre exacto.",
                "links": [],
                "status": "pending_project",
            }

        catalog = self._projects_tool.invoke({"realtor_id": realtor_id})
        matches = self._match_projects(projects_requested, catalog)

        if not matches:
            return {
                "reply": "No reconocí el nombre exacto del proyecto. ¿Podrías confirmarlo?",
                "links": [],
                "status": "unknown_project",
            }

        links: List[Dict[str, str]] = []
        for project_name, project_id in matches.items():
            for file_type in file_types:
                files = self._files_tool.invoke(
                    {
                        "project_id": project_id,
                        "file_type": file_type,
                    }
                )
                for file_entry in files:
                    links.append(
                        {
                            "project": project_name,
                            "type": file_type,
                            "url": file_entry.get("url", ""),
                        }
                    )

        if not links:
            return {
                "reply": "No encontré archivos del tipo solicitado para ese proyecto. ¿Quieres intentar con otro tipo o proyecto?",
                "links": [],
                "status": "not_found",
            }

        summary = self._compose_reply(reply, links)

        return {
            "reply": summary,
            "links": links,
            "status": "ok",
        }

    def _invoke_llm(
        self,
        *,
        message: str,
        history: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not self._model or not self._prompt_text:
            return None

        messages = [SystemMessage(content=self._prompt_text)]
        for item in history:
            role = item.get("sender_role") or item.get("role")
            content = item.get("message") or item.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            if role == "assistant":
                messages.append(AIMessage(content=content.strip()))
            else:
                messages.append(HumanMessage(content=content.strip()))

        messages.append(HumanMessage(content=message))

        try:
            response = self._model.invoke(messages)
        except Exception:
            logger.exception("Error llamando a OpenAI desde FilesAgentExecutor")
            return None

        content = response.content if isinstance(response, AIMessage) else None
        if not content:
            return None

        try:
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError
        except Exception:
            logger.exception("No se pudo parsear la salida JSON del subagente de archivos")
            return None

        if not isinstance(data.get("reply"), str):
            data["reply"] = "Enseguida busco los archivos solicitados."
        return data

    @staticmethod
    def _load_prompt() -> Optional[str]:
        path = FilesAgentExecutor.PROMPT_PATH
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        try:
            text = path.read_text(encoding="utf-8")
            stripped = text.strip()
            if stripped:
                return stripped
        except FileNotFoundError:
            logger.warning("Prompt de archivos no encontrado en %s", path)
        except Exception:
            logger.exception("Error leyendo el prompt de archivos")
        return None

    @staticmethod
    def _extract_message(normalized: Dict[str, Any], payload: Dict[str, Any]) -> Optional[str]:
        message = normalized.get("message") if isinstance(normalized, dict) else None
        if isinstance(message, str) and message.strip():
            return message.strip()
        raw = payload.get("message") if isinstance(payload, dict) else None
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return None

    def _coerce_types(self, raw: Any) -> List[str]:
        types: List[str] = []
        if isinstance(raw, str):
            raw = [raw]
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, str):
                    continue
                value = item.strip().lower()
                if value in self.SUPPORTED_TYPES and value not in types:
                    types.append(value)
        return types

    @staticmethod
    def _coerce_projects(raw: Any) -> List[str]:
        projects: List[str] = []
        if isinstance(raw, str):
            raw = [raw]
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    projects.append(item.strip())
        return projects

    @staticmethod
    def _match_projects(requested: List[str], catalog: List[Dict[str, str]]) -> Dict[str, str]:
        matches: Dict[str, str] = {}
        index = {
            (entry.get("name") or "").strip().lower(): str(entry.get("id"))
            for entry in catalog
            if entry.get("id") and entry.get("name")
        }
        for name in requested:
            key = name.strip().lower()
            project_id = index.get(key)
            if project_id:
                matches[name] = project_id
        return matches

    @staticmethod
    def _compose_reply(reply: str, links: List[Dict[str, str]]) -> str:
        grouped: Dict[str, List[str]] = {}
        for link in links:
            project = link.get("project") or "Proyecto"
            grouped.setdefault(project, []).append(link.get("url") or "")

        summary_lines: List[str] = [reply.strip()]
        for project, urls in grouped.items():
            filtered = [url for url in urls if url]
            if filtered:
                summary_lines.append(f"{project}: " + ", ".join(filtered))
        return "\n".join(summary_lines)

    @staticmethod
    def _heuristic_output(message: str) -> Dict[str, Any]:
        reply = "Estoy identificando qué archivos necesitas. ¿Podrías confirmarme el nombre exacto del proyecto?"
        types: List[str] = []
        text = message.lower()
        if "foto" in text or "imagen" in text:
            types.append("image")
        if "video" in text:
            types.append("video")
        if "kmz" in text:
            types.append("kmz")
        if "documento" in text or "pdf" in text:
            types.append("document")
        return {
            "reply": reply,
            "types": types,
            "projects": [],
            "status": "heuristic",
        }
