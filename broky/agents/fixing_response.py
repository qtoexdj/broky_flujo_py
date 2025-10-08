"""Agent that rewrites the response to sound more human and aligned to tone."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI

from broky.agents.base import BrokyAgent
from broky.config import get_langchain_settings
from broky.core import BrokyContext

logger = logging.getLogger(__name__)


class FixingResponseAgentExecutor(BrokyAgent):
    """Reescribe la respuesta base para mantener tono humano y conciso."""

    PROMPT_PATH = Path("docs/new_prompts/fixing_response.md")

    def __init__(self) -> None:
        self._settings = get_langchain_settings()
        if self._settings.openai_api_key:
            self._model: Optional[ChatOpenAI] = ChatOpenAI(
                api_key=self._settings.openai_api_key,
                model=self._settings.openai_model,
                temperature=0.1,
            )
        else:
            logger.warning(
                "OPENAI_API_KEY no configurado; FixingResponseAgentExecutor usará modo pasivo"
            )
            self._model = None

        self._prompt_template = self._load_prompt()

        super().__init__(runnable=RunnableLambda(self._execute))

    def build_input(self, context: BrokyContext) -> Dict[str, Optional[str]]:
        user_message = self._extract_message(context.payload)
        base_reply = context.metadata.get("reply")
        return {
            "user_message": user_message,
            "base_reply": base_reply,
        }

    def handle_output(self, context: BrokyContext, result: Dict[str, Optional[str]]) -> BrokyContext:
        rewritten = (result.get("reply") or context.metadata.get("reply") or "").strip()
        if rewritten:
            context.metadata["reply"] = rewritten
            context.metadata.setdefault("postprocess", {})["humanized_reply"] = rewritten
        return context

    # ------------------------------------------------------------------

    def _execute(self, payload: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
        base_reply = payload.get("base_reply")
        if not base_reply:
            return {"reply": payload.get("base_reply")}

        if not self._model or not self._prompt_template:
            return {"reply": base_reply}

        rendered_prompt = self._render_prompt(
            user_message=payload.get("user_message") or "",
            base_reply=base_reply,
        )

        messages = [SystemMessage(content=rendered_prompt), HumanMessage(content="Reescribe la respuesta.")]

        try:
            response = self._model.invoke(messages)
        except Exception:  # pragma: no cover - safe fallback
            logger.exception("No se pudo humanizar la respuesta; se usará versión original")
            return {"reply": base_reply}

        content = response.content if isinstance(response, AIMessage) else None
        if not content:
            return {"reply": base_reply}

        return {"reply": content.strip()}

    @staticmethod
    def _extract_message(payload: Dict[str, Any]) -> Optional[str]:
        message = payload.get("message") if isinstance(payload, dict) else None
        if isinstance(message, str) and message.strip():
            return message.strip()
        normalized = payload.get("normalized") if isinstance(payload, dict) else None
        if isinstance(normalized, dict):
            alt = normalized.get("message")
            if isinstance(alt, str) and alt.strip():
                return alt.strip()
        return None

    def _render_prompt(self, *, user_message: str, base_reply: str) -> str:
        template = self._prompt_template
        template = template.replace("{{ $('Setear4').item.json.mensaje }}", user_message)
        template = template.replace("{{ $node[\"RESPUESTA\"].json.output }}", base_reply)
        return template

    @staticmethod
    def _load_prompt() -> Optional[str]:
        path = FixingResponseAgentExecutor.PROMPT_PATH
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        try:
            text = path.read_text(encoding="utf-8")
            stripped = text.strip()
            if stripped:
                return stripped
        except FileNotFoundError:
            logger.warning("Prompt fixing_response no encontrado en %s", path)
        except Exception:
            logger.exception("Error leyendo el prompt fixing_response")
        return None
