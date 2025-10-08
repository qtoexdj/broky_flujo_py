"""Agent that checks if a justification note is required after the reply."""

from __future__ import annotations

import json
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


class JustificationAgentExecutor(BrokyAgent):
    """Determina si corresponde generar una justificación para el equipo humano."""

    PROMPT_PATH = Path("docs/new_prompts/Basic LLM Chain5.md")

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
            logger.warning(
                "OPENAI_API_KEY no configurado; JustificationAgentExecutor operará en modo pasivo"
            )
            self._model = None

        self._prompt_template = self._load_prompt()

        super().__init__(runnable=RunnableLambda(self._execute))

    def build_input(self, context: BrokyContext) -> Dict[str, Optional[str]]:
        realtor_name = context.payload.get("official_data", {}).get("realtor", {}).get("name")
        rewritten = context.metadata.get("reply")
        return {
            "realtor_name": realtor_name,
            "reply": rewritten,
        }

    def handle_output(self, context: BrokyContext, result: Dict[str, Any]) -> BrokyContext:
        justification = result.get("justificacion")
        if isinstance(justification, str):
            context.metadata.setdefault("postprocess", {})["justification"] = justification.strip()
        return context

    # ------------------------------------------------------------------

    def _execute(self, payload: Dict[str, Optional[str]]) -> Dict[str, Any]:
        reply = payload.get("reply")
        if not reply:
            return {"justificacion": "No"}

        if not self._model or not self._prompt_template:
            return {"justificacion": "No"}

        rendered_prompt = self._render_prompt(
            realtor_name=payload.get("realtor_name") or "la inmobiliaria",
            reply_text=reply,
        )

        messages = [
            SystemMessage(content=rendered_prompt),
            HumanMessage(content="Evalúa si se requiere justificación."),
        ]

        try:
            response = self._model.invoke(messages)
        except Exception:  # pragma: no cover - fallback controlado
            logger.exception("No se pudo evaluar la justificación; se asumirá 'No'")
            return {"justificacion": "No"}

        content = response.content if isinstance(response, AIMessage) else None
        if not content:
            return {"justificacion": "No"}

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.exception("Salida inválida del agente de justificación")
            return {"justificacion": "No"}

        if not isinstance(data, dict):
            return {"justificacion": "No"}

        justification = data.get("justificacion")
        if isinstance(justification, str) and justification.strip():
            return {"justificacion": justification.strip()}
        return {"justificacion": "No"}

    def _render_prompt(self, *, realtor_name: str, reply_text: str) -> str:
        template = self._prompt_template
        template = template.replace("{{ $node[\"datos_oficiales\"].json.name_realtor }}", realtor_name)
        template = template.replace("{{ $node[\"fixing_response\"].json.text }}", reply_text)
        return template

    @staticmethod
    def _load_prompt() -> Optional[str]:
        path = JustificationAgentExecutor.PROMPT_PATH
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        try:
            text = path.read_text(encoding="utf-8")
            stripped = text.strip()
            if stripped:
                return stripped
        except FileNotFoundError:
            logger.warning("Prompt de justificación no encontrado en %s", path)
        except Exception:
            logger.exception("Error leyendo el prompt de justificación")
        return None

