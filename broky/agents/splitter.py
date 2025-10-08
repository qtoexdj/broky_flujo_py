"""Agent that splits a long reply into WhatsApp-sized messages."""

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

logger = logging.getLogger(__name__)


class SplitResponseAgentExecutor(BrokyAgent):
    """Divide la respuesta final en fragmentos coherentes menores a 400 caracteres."""

    PROMPT_PATH = Path("docs/new_prompts/Basic LLM Chain.md")
    MAX_LENGTH = 400

    def __init__(self) -> None:
        self._settings = get_langchain_settings()
        if self._settings.openai_api_key:
            self._model: Optional[ChatOpenAI] = ChatOpenAI(
                api_key=self._settings.openai_api_key,
                model=self._settings.openai_model,
                temperature=0,
                model_kwargs={"response_format": {"type": "json_object"}},
            )
        else:
            logger.warning("OPENAI_API_KEY no configurado; SplitResponseAgent deshabilitado")
            self._model = None

        self._prompt_template = self._load_prompt()

        super().__init__(runnable=RunnableLambda(self._execute))

    def build_input(self, context: BrokyContext) -> Dict[str, Optional[str]]:
        user_message = self._extract_message(context.payload)
        rewritten = context.metadata.get("reply")
        return {
            "user_message": user_message,
            "rewritten_reply": rewritten,
        }

    def handle_output(self, context: BrokyContext, result: Dict[str, Any]) -> BrokyContext:
        messages = result.get("messages")
        if isinstance(messages, list):
            cleaned = [
                str(item).strip()
                for item in messages
                if isinstance(item, (str, int, float)) and str(item).strip()
            ]
            if cleaned:
                context.metadata.setdefault("postprocess", {})["split_messages"] = cleaned
        return context

    # ------------------------------------------------------------------

    def _execute(self, payload: Dict[str, Optional[str]]) -> Dict[str, Any]:
        rewritten = payload.get("rewritten_reply")
        if not rewritten:
            return {"messages": []}

        if not self._model or not self._prompt_template:
            return {"messages": self._enforce_length([rewritten])}

        rendered_prompt = self._render_prompt(
            user_message=payload.get("user_message") or "",
            rewritten_reply=rewritten,
        )

        messages = [
            SystemMessage(content=rendered_prompt),
            HumanMessage(content="Genera los mensajes segmentados."),
        ]

        try:
            response = self._model.invoke(messages)
        except Exception:  # pragma: no cover - fallback seguro
            logger.exception("No se pudo dividir el mensaje; se enviará completo")
            return {"messages": self._enforce_length([rewritten])}

        content = response.content if isinstance(response, AIMessage) else None
        if not content:
            return {"messages": [rewritten]}

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.exception("Salida inválida del splitter; usando mensaje original")
            return {"messages": [rewritten]}

        messages_out = data.get("messages") if isinstance(data, dict) else None
        if not isinstance(messages_out, list):
            return {"messages": [rewritten]}

        cleaned = [
            str(item).strip()
            for item in messages_out
            if isinstance(item, (str, int, float)) and str(item).strip()
        ]
        enforced = self._enforce_length(cleaned or [rewritten])
        return {"messages": enforced}

    @staticmethod
    def _extract_message(payload: Dict[str, Any]) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        normalized = payload.get("normalized")
        if isinstance(normalized, dict):
            alt = normalized.get("message")
            if isinstance(alt, str) and alt.strip():
                return alt.strip()
        return None

    def _enforce_length(self, messages: List[str]) -> List[str]:
        enforced: List[str] = []
        for message in messages:
            chunks = self._chunk_message(message, self.MAX_LENGTH)
            enforced.extend(chunks)
        return enforced

    def _chunk_message(self, text: str, limit: int) -> List[str]:
        stripped = text.strip()
        if not stripped:
            return []
        if len(stripped) <= limit:
            return [stripped]

        chunks: List[str] = []
        remaining = stripped
        while remaining:
            if len(remaining) <= limit:
                chunks.append(remaining.strip())
                break

            slice_candidate = remaining[:limit]
            break_index = max(
                slice_candidate.rfind("\n\n"),
                slice_candidate.rfind("\n"),
                slice_candidate.rfind(". "),
                slice_candidate.rfind("; "),
                slice_candidate.rfind(", "),
            )
            if break_index == -1 or break_index < limit * 0.4:
                break_index = limit
            fragment = remaining[: break_index + 1].strip()
            if fragment:
                chunks.append(fragment)
            remaining = remaining[break_index + 1 :].lstrip()
        return chunks

    def _render_prompt(self, *, user_message: str, rewritten_reply: str) -> str:
        template = self._prompt_template
        template = template.replace("{{ $('Setear4').item.json.mensaje }}", user_message)
        template = template.replace("{{ $node[\"fixing_response\"].json.text }}", rewritten_reply)
        return template

    @staticmethod
    def _load_prompt() -> Optional[str]:
        path = SplitResponseAgentExecutor.PROMPT_PATH
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        try:
            text = path.read_text(encoding="utf-8")
            stripped = text.strip()
            if stripped:
                return stripped
        except FileNotFoundError:
            logger.warning("Prompt de splitter no encontrado en %s", path)
        except Exception:
            logger.exception("Error leyendo el prompt del splitter")
        return None
