"""LangChain-based subagent to schedule property visits."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI

from broky.agents.base import BrokyAgent
from broky.config import get_langchain_settings
from broky.core import BrokyContext
from broky.tools import ScheduleVisitTool

logger = logging.getLogger(__name__)


class ScheduleAgentExecutor(BrokyAgent):
    """Subagente responsable de registrar visitas agendadas."""

    PROMPT_PATH = Path("docs/prompts/schedule_subagent_prompt.md")

    def __init__(self, tool: ScheduleVisitTool) -> None:
        self._settings = get_langchain_settings()
        self._tool = tool
        if self._settings.openai_api_key:
            self._model = ChatOpenAI(
                api_key=self._settings.openai_api_key,
                model=self._settings.openai_model,
                temperature=0,
                model_kwargs={"response_format": {"type": "json_object"}}
            )
        else:
            logger.warning(
                "OPENAI_API_KEY no configurado; ScheduleAgentExecutor operará con heurística"
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
        prospect_id = context.prospect_id or normalized.get("prospect_id")
        scheduled_at = payload.get("official_data", {}).get("scheduled_at") if isinstance(payload, dict) else None

        return {
            "message": message,
            "history": history,
            "stage": stage,
            "prospect_id": prospect_id,
            "scheduled_at": scheduled_at,
            "current_date": date.today().isoformat(),
        }

    def handle_output(self, context: BrokyContext, result: Dict[str, Any]) -> BrokyContext:
        context.metadata.setdefault("subagents", {})["filter_schedule"] = result
        reply = result.get("reply")
        if reply:
            context.metadata.setdefault("subagent_replies", []).append(reply)
        visit = result.get("visit")
        if visit:
            context.metadata.setdefault("scheduled_visit", visit)
        if result.get("stage"):
            context.metadata["stage"] = result["stage"]
        return context

    # ------------------------------------------------------------------

    def _execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        stage = (payload.get("stage") or "").strip().lower()
        if stage not in {"qualified", "scheduled"}:
            return {
                "reply": "Para coordinar una visita, primero necesito completar tu calificación. ¿Podemos revisar tus datos de compra?",
                "visit": None,
                "stage": stage or None,
                "status": "blocked",
            }

        message = payload.get("message")
        prospect_id = payload.get("prospect_id")
        if not message or not prospect_id:
            return {
                "reply": "¿Podrías indicarme cuándo te gustaría agendar la visita?",
                "visit": None,
                "stage": stage or None,
                "status": "pending",
            }

        structured = self._invoke_llm(
            message=message,
            history=payload.get("history") or [],
            current_date=payload.get("current_date") or date.today().isoformat(),
        )

        if not structured:
            structured = self._heuristic_output(message)

        visit = self._coerce_visit(
            structured.get("visit"),
            current_date=payload.get("current_date") or date.today().isoformat(),
        )
        structured["visit"] = visit
        if structured.get("stage") is None:
            structured["stage"] = "scheduled" if visit.get("date") else stage

        if visit.get("date"):
            try:
                self._tool.invoke(
                    {
                        "prospect_id": prospect_id,
                        "scheduled_at": visit["date"],
                        "stage": structured.get("stage") or "scheduled",
                    }
                )
                structured["status"] = "scheduled"
            except Exception:  # pragma: no cover - log y continuar
                logger.exception("No se pudo registrar la visita en Supabase")
                structured.setdefault("status", "error")
        else:
            structured.setdefault("status", "pending")

        return structured

    def _invoke_llm(
        self,
        *,
        message: str,
        history: List[Dict[str, Any]],
        current_date: str,
    ) -> Optional[Dict[str, Any]]:
        if not self._model or not self._prompt_text:
            return None

        messages = [SystemMessage(content=self._prompt_text)]
        messages.append(
            SystemMessage(
                content=f"Fecha actual: {current_date}. Debes devolver fechas en formato YYYY-MM-DD."
            )
        )

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
            logger.exception("Error llamando a OpenAI desde ScheduleAgentExecutor")
            return None

        content = response.content if isinstance(response, AIMessage) else None
        if not content:
            return None

        try:
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError
        except Exception:
            logger.exception("No se pudo parsear la salida JSON del subagente de agenda")
            return None

        if not isinstance(data.get("reply"), str):
            data["reply"] = "Gracias, revisaré los horarios disponibles y te confirmo en breve."
        data["visit"] = self._coerce_visit(
            data.get("visit"),
            current_date=current_date,
        )
        stage = data.get("stage")
        if isinstance(stage, str):
            stage = stage.strip().lower()
            if stage not in {"scheduled", "qualified", "conversation"}:
                stage = None
        else:
            stage = None
        data["stage"] = stage or ("scheduled" if data["visit"].get("date") else None)
        return data

    @staticmethod
    def _load_prompt() -> Optional[str]:
        path = ScheduleAgentExecutor.PROMPT_PATH
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        try:
            text = path.read_text(encoding="utf-8")
            stripped = text.strip()
            if stripped:
                return stripped
        except FileNotFoundError:
            logger.warning("Prompt de agenda no encontrado en %s", path)
        except Exception:
            logger.exception("Error leyendo el prompt de agenda")
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
    def _coerce_visit(raw: Any, *, current_date: str) -> Dict[str, Any]:
        visit = {
            "date": "",
            "notes": "",
        }
        if isinstance(raw, dict):
            date_value = raw.get("date") or raw.get("scheduled_at")
            if isinstance(date_value, str):
                adjusted = ScheduleAgentExecutor._adjust_visit_date(
                    date_value.strip(), current_date
                )
                visit["date"] = adjusted
            notes_value = raw.get("notes")
            if isinstance(notes_value, str):
                visit["notes"] = notes_value.strip()
        return visit

    @staticmethod
    def _heuristic_output(message: str) -> Dict[str, Any]:
        reply = "¿Qué día te acomoda para coordinar la visita? Puedo ayudarte a registrarla."
        visit: Dict[str, Any] = {
            "date": "",
            "notes": "",
        }
        text = message.lower()
        candidates: List[tuple[int, str]] = []
        if "mañana" in text:
            candidates.append((1, "Mañana"))
        if "próxima semana" in text or "proxima semana" in text:
            candidates.append((7, "Próxima semana"))
        if candidates:
            days = min(offset for offset, _ in candidates)
            visit_date = date.today() + timedelta(days=days)
            visit_date = ScheduleAgentExecutor._adjust_visit_date(
                visit_date.isoformat(), date.today().isoformat()
            )
            visit["date"] = visit_date
            reply = f"Perfecto, puedo agendar la visita para el {visit['date']}. ¿Te parece bien?"
        return {
            "reply": reply,
            "visit": visit,
            "stage": "scheduled" if visit["date"] else None,
            "status": "heuristic" if visit["date"] else "pending",
        }

    @staticmethod
    def _adjust_visit_date(raw_date: str, current_date: str) -> str:
        """Ensure the visit date is in the future and not on Sunday."""

        try:
            current = datetime.strptime(current_date, "%Y-%m-%d").date()
        except ValueError:
            current = date.today()

        try:
            visit_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            return ""

        if visit_date <= current:
            visit_date = current + timedelta(days=1)

        if visit_date.weekday() == 6:  # Sunday -> move to Monday
            visit_date += timedelta(days=1)

        return visit_date.isoformat()
