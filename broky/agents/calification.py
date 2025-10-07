"""LangChain-based subagent for prospect calification."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI

from broky.agents.base import BrokyAgent
from broky.config import get_langchain_settings
from broky.core import BrokyContext
from broky.tools import CalificationUpdateTool

logger = logging.getLogger(__name__)


class CalificationAgentExecutor(BrokyAgent):
    """Subagente que resume información financiera del prospecto."""

    PROMPT_PATH = Path("docs/prompts/calification_subagent_prompt.md")

    def __init__(self, tool: CalificationUpdateTool) -> None:
        self._settings = get_langchain_settings()
        self._tool = tool
        if self._settings.openai_api_key:
            self._model = ChatOpenAI(
                api_key=self._settings.openai_api_key,
                model=self._settings.openai_model,
                temperature=0,
                response_format={"type": "json_object"},
            )
        else:
            logger.warning(
                "OPENAI_API_KEY no configurado; CalificationAgentExecutor operará con heurística"
            )
            self._model = None

        self._prompt_text = self._load_prompt()

        super().__init__(runnable=RunnableLambda(self._execute))

    def build_input(self, context: BrokyContext) -> Dict[str, Any]:
        payload = context.payload
        normalized = payload.get("normalized") if isinstance(payload, dict) else {}
        message = self._extract_message(normalized, payload)
        history = context.memory_snapshot.get("messages") if context.memory_snapshot else []
        stage = context.metadata.get("stage") or normalized.get("stage")
        realtor = payload.get("official_data", {}).get("realtor") if isinstance(payload, dict) else None

        return {
            "message": message,
            "history": history,
            "stage": stage,
            "realtor": realtor,
            "prospect_id": context.prospect_id or normalized.get("prospect_id"),
        }

    def handle_output(self, context: BrokyContext, result: Dict[str, Any]) -> BrokyContext:
        context.metadata.setdefault("subagents", {})["filter_calification"] = result
        reply = result.get("reply")
        if reply:
            context.metadata.setdefault("subagent_replies", []).append(reply)
        calification = result.get("calification")
        if calification and any(value for value in calification.values()):
            context.metadata.setdefault("calification_variables", calification)
        if result.get("stage"):
            context.metadata["stage"] = result["stage"]
        return context

    # ------------------------------------------------------------------

    def _execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        message = payload.get("message")
        prospect_id = payload.get("prospect_id")
        if not message or not prospect_id:
            return {
                "status": "skipped",
                "reason": "missing_inputs",
                "reply": None,
            }

        structured = self._invoke_llm(
            message=message,
            history=payload.get("history") or [],
            stage=payload.get("stage"),
            realtor=payload.get("realtor") or {},
        )

        if not structured:
            structured = self._heuristic_output(message)

        calification = self._coerce_calification(structured.get("calification"))
        stage = self._normalize_stage(structured.get("stage"))
        structured["calification"] = calification
        structured["stage"] = stage

        has_data = any(isinstance(value, str) and value.strip() for value in calification.values())
        if stage is None:
            stage = self._auto_stage(calification)
            structured["stage"] = stage

        if has_data:
            try:
                self._tool.invoke(
                    {
                        "prospect_id": prospect_id,
                        "calification": calification,
                        "stage": stage,
                    }
                )
                structured["status"] = "ok"
            except Exception:  # pragma: no cover - log y continuar
                logger.exception("No se pudo actualizar la calificación en Supabase")
                structured.setdefault("status", "error")
        else:
            structured.setdefault("status", "noop")

        return structured

    def _invoke_llm(
        self,
        *,
        message: str,
        history: List[Dict[str, Any]],
        stage: Optional[str],
        realtor: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self._model or not self._prompt_text:
            return None

        messages = [SystemMessage(content=self._prompt_text)]
        context_lines: List[str] = []
        if realtor:
            name = realtor.get("name")
            if name:
                context_lines.append(f"Nombre inmobiliaria: {name}")
        if stage:
            context_lines.append(f"Stage actual del prospecto: {stage}")
        if context_lines:
            messages.append(SystemMessage(content="\n".join(context_lines)))

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
            logger.exception("Error llamando a OpenAI desde CalificationAgentExecutor")
            return None

        content = response.content if isinstance(response, AIMessage) else None
        if not content:
            return None

        try:
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError
        except Exception:
            logger.exception("No se pudo parsear la salida JSON del subagente de calificación")
            return None

        data["calification"] = self._coerce_calification(data.get("calification"))
        if not isinstance(data.get("reply"), str):
            data["reply"] = "Gracias por la información. La compartiré con un asesor."
        data["stage"] = self._normalize_stage(data.get("stage"))
        return data

    @staticmethod
    def _load_prompt() -> Optional[str]:
        path = CalificationAgentExecutor.PROMPT_PATH
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        try:
            text = path.read_text(encoding="utf-8")
            stripped = text.strip()
            if stripped:
                return stripped
        except FileNotFoundError:
            logger.warning("Prompt de calificación no encontrado en %s", path)
        except Exception:
            logger.exception("Error leyendo el prompt de calificación")
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

    @staticmethod
    def _heuristic_output(message: str) -> Dict[str, Any]:
        reply = (
            "Gracias por compartir tus planes de compra. Un asesor revisará tus datos "
            "de financiamiento para ayudarte con la calificación."
        )
        calification = {
            "forma_pago": "",
            "fecha_compra_estimativa": "",
            "notas_adicionales": "",
        }
        text = message.lower()
        if "contado" in text or "efectivo" in text or "transferencia" in text or "vale vista" in text:
            calification["forma_pago"] = "contado"
        if "credito" in text or "crédito" in text:
            calification["forma_pago"] = "credito_consumo"
        return {
            "reply": reply,
            "calification": calification,
            "stage": self._auto_stage(calification),
            "status": "heuristic",
        }

    @staticmethod
    def _coerce_calification(raw: Any) -> Dict[str, Any]:
        base = {
            "forma_pago": "",
            "fecha_compra_estimativa": "",
            "notas_adicionales": "",
        }
        if isinstance(raw, dict):
            for key in base:
                value = raw.get(key)
                if isinstance(value, str):
                    base[key] = value.strip()
        return base

    @staticmethod
    def _normalize_stage(raw: Any) -> Optional[str]:
        if isinstance(raw, str):
            value = raw.strip().lower()
            if value in {"qualified", "conversation", "not-qualified"}:
                return value
        return None

    @staticmethod
    def _auto_stage(calification: Dict[str, Any]) -> Optional[str]:
        forma = calification.get("forma_pago")
        fecha = calification.get("fecha_compra_estimativa")

        if not isinstance(forma, str) or not forma.strip():
            return None

        forma = forma.strip().lower()
        if forma == "otro":
            return "not-qualified"

        if not isinstance(fecha, str) or not fecha.strip():
            return None

        try:
            fecha_compra = datetime.strptime(fecha.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None

        today = date.today()
        delta = (fecha_compra - today).days
        if delta <= 30:
            return "qualified"
        return "not-qualified"
