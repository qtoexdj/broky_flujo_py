"""Master agent orchestrator that classifies intent and manages chat memory."""

from __future__ import annotations

import json
import logging
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from app.core.config import Settings
from app.agents.subagents import (
    RAGSubAgent,
    RAGSubAgentResult,
    ProjectInterestSubAgent,
    ProjectInterestSubAgentResult,
)
from app.services.chat_history_repository import ChatHistoryRepository
from app.services.supabase_client import get_supabase_client
from app.services.project_interest_service import ProjectInterestService
from app.workflows.inbound import InboundState

try:  # pragma: no cover - openai client available en runtime
    from openai import OpenAI
except Exception:  # pragma: no cover - fallback sin LLM
    OpenAI = None  # type: ignore

logger = logging.getLogger(__name__)

# Intent labels the downstream filters understand
PrimaryIntent = str

_INTENT_KEYWORDS: Dict[PrimaryIntent, Iterable[str]] = {
    "busqueda_informacion": (
        "informacion",
        "información",
        "detalle",
        "detalles",
        "saber",
        "datos",
        "info",
        "proyecto",
        "quilmes",
    ),
    "pide_fotos_plano_videos": (
        "foto",
        "fotos",
        "imagen",
        "imágenes",
        "imagenes",
        "plano",
        "planos",
        "render",
        "video",
        "videos",
        "tour",
    ),
    "anotar_proyecto": (
        "anotar",
        "registrar",
        "guardar",
        "apartar",
        "inscribir",
        "sumar",
        "agregar",
    ),
    "forma_pago": (
        "pago",
        "pagar",
        "cuota",
        "pie",
        "credito",
        "crédito",
        "financiamiento",
        "dividendo",
        "abono",
    ),
    "fecha_compra": (
        "comprar",
        "compra",
        "cuando",
        "cuándo",
        "plazo",
        "meses",
        "tiempo",
    ),
    "fecha_visita": (
        "visita",
        "visitar",
        "agendar",
        "agenda",
        "coordinar",
        "recorrer",
        "tour",
        "recorrido",
    ),
}

_DEFAULT_INTENT = "busqueda_informacion"
_ALLOWED_CALIFICATION_STAGES = {"conversation", "qualified"}
_ALLOWED_SCHEDULE_STAGE = {"qualified"}


@dataclass
class AgentDecision:
    """Structured decision emitted by the master agent."""

    reply: str
    output: List[PrimaryIntent]
    metadata: Dict[str, Any] = field(default_factory=dict)
    handoff: bool = False


class MasterAgent:
    """Router that loads memory, classifies intent and orchestrates sub agents."""

    def __init__(self, settings: Settings, history_limit: int = 30) -> None:
        self._settings = settings
        client = get_supabase_client(settings)
        self._history_repo = ChatHistoryRepository(client) if client else None
        self._project_interest_service = (
            ProjectInterestService(client) if client else None
        )
        self._history_limit = history_limit
        self._prompt = self._load_prompt()
        self._llm_client = (
            OpenAI(api_key=settings.openai_api_key) if OpenAI is not None else None
        )
        self._rag_agent = RAGSubAgent(settings)
        self._project_interest_agent = ProjectInterestSubAgent(
            settings, self._project_interest_service
        )

        logger.info(
            "Agente Madre inicializado | prompt_path=%s | history_repo=%s",
            settings.master_agent_prompt_path,
            bool(self._history_repo),
        )

    def handle(self, state: InboundState) -> AgentDecision:
        """Entry point from FastAPI after inbound workflow."""

        if not state.get("automation_allowed", True):
            reason = state.get("handoff_reason") or "automation_disabled"
            return AgentDecision(
                reply=(
                    "Gracias por tu mensaje. Un miembro del equipo te contactará en breve "
                    "para continuar la conversación."
                ),
                output=[],
                metadata={"handoff_reason": reason, "logs": state.get("logs", [])},
                handoff=True,
            )

        normalized = state.get("normalized") or {}
        payload = state.get("payload") or {}

        message = self._extract_message(normalized, payload)
        if not message:
            return AgentDecision(
                reply="No identifiqué tu mensaje. ¿Puedes repetirlo?",
                output=[],
                metadata={"error": "empty_message"},
                handoff=True,
            )

        if message.strip() == "0":
            return AgentDecision(
                reply="Hemos desactivado las respuestas automáticas. Un asesor continuará contigo.",
                output=[],
                metadata={"handoff_reason": "user_opt_out"},
                handoff=True,
            )

        session_id = normalized.get("session_id") or payload.get("session_id")
        if not session_id:
            return AgentDecision(
                reply="Necesito reiniciar la conversación para continuar. ¿Puedes intentarlo nuevamente?",
                output=[],
                metadata={"error": "missing_session_id"},
                handoff=True,
            )

        history = self._load_history(session_id)

        llm_payload = self._build_llm_payload(
            message=message,
            history=history,
            normalized=normalized,
            official=state.get("official_data"),
        )

        structured_output = self._invoke_llm(llm_payload)
        if structured_output is None:
            logger.info("Agente Madre usando heurística de intenciones")
            intents = self._detect_intents(message, history)
            stage = self._extract_stage(state, normalized)
            filters = self._build_filters(intents, stage)
            reply = self._craft_reply(filters)
            structured_output = {
                "reply": reply,
                "intents": intents,
                "analysis": self._summarize_intents(intents, message),
                "filters": filters,
                "next_actions": self._build_next_actions(intents, stage),
            }
        else:
            intents = self._extract_intents(structured_output)
            stage = self._extract_stage(state, normalized)
            filters = self._build_filters(intents, stage)
            structured_output["filters"] = filters
            reply = structured_output.get("reply") or self._craft_reply(filters)
            structured_output.setdefault(
                "next_actions", self._build_next_actions(intents, stage)
            )

        if not self._validate_output(structured_output):
            self._cleanup_history(session_id)
            return AgentDecision(
                reply="Necesito un momento para organizar la información. En breve te respondo.",
                output=[],
                metadata={"error": "invalid_structure", "session_id": session_id},
                handoff=True,
            )

        realtor_id = normalized.get("realtor_id") or payload.get("realtor_id")
        prospect_id = self._extract_prospect_id(state, normalized)

        subagent_outputs: Dict[str, Any] = {}
        subagent_replies: List[str] = []

        if filters.get("filter_rag"):
            rag_result = self._run_rag_subagent(
                message=message,
                history=history,
                realtor_id=realtor_id,
            )
            if rag_result:
                subagent_outputs["filter_rag"] = rag_result.to_dict()
                structured_output.setdefault("subagents", {})[
                    "filter_rag"
                ] = rag_result.to_dict()
                if rag_result.reply:
                    subagent_replies.append(rag_result.reply)
                self._merge_mentioned_properties(
                    normalized=normalized,
                    official=state.get("official_data"),
                    new_mentions=rag_result.mentioned_properties,
                )

        if filters.get("filter_intention"):
            interest_result = self._run_project_interest_subagent(
                prospect_id=prospect_id,
                realtor_id=realtor_id,
                mentioned_projects=self._extract_mentioned_projects(
                    normalized, state.get("official_data")
                ),
            )
            if interest_result:
                subagent_outputs["filter_intention"] = interest_result.to_dict()
                structured_output.setdefault("subagents", {})[
                    "filter_intention"
                ] = interest_result.to_dict()
                if interest_result.reply:
                    subagent_replies.append(interest_result.reply)
                self._merge_properties_interested(
                    normalized=normalized,
                    official=state.get("official_data"),
                    new_projects=interest_result.added_projects,
                )

        final_reply = (
            " ".join(reply_part for reply_part in subagent_replies if reply_part)
            if subagent_replies
            else reply
        )

        self._persist_interaction(
            session_id=session_id,
            user_message=message,
            agent_reply=final_reply,
            intents=intents,
            structured_output=structured_output,
        )

        metadata = {
            "session_id": session_id,
            "realtor_id": normalized.get("realtor_id") or payload.get("realtor_id"),
            "prospect_id": self._extract_prospect_id(state, normalized),
            "stage": stage,
            "filters": filters,
            "history_length": len(history),
            "structured_output": structured_output,
            "logs": state.get("logs", []),
            "prompt_excerpt": self._prompt[:160] if self._prompt else None,
            "subagents": subagent_outputs,
        }

        return AgentDecision(reply=final_reply, output=intents, metadata=metadata)

    # --- Helpers ---------------------------------------------------------

    def _load_history(self, session_id: str) -> List[Dict[str, Any]]:
        if not self._history_repo:
            return []
        history = self._history_repo.fetch_history(session_id, limit=self._history_limit)
        logger.info(
            "Historial cargado para session_id=%s (mensajes=%d)",
            session_id,
            len(history),
        )
        return history

    def _invoke_llm(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self._llm_client or not self._prompt:
            return None

        messages = [
            {"role": "system", "content": self._prompt},
        ]

        context = payload.get("context")
        if context:
            messages.append({"role": "system", "content": context})

        history_messages = payload.get("history") or []
        messages.extend(history_messages)
        messages.append({"role": "user", "content": payload["message"]})

        try:
            response = self._llm_client.chat.completions.create(
                model=self._settings.openai_model,
                messages=messages,
                temperature=0.2,
                max_tokens=500,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                return None

            data = json.loads(content)
            return data
        except Exception:  # pragma: no cover - degradación controlada
            logger.exception("LLM del Agente Madre retornó error; usando heurística")
            return None

    def _build_llm_payload(
        self,
        *,
        message: str,
        history: Sequence[Dict[str, Any]],
        normalized: Dict[str, Any],
        official: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        compiled_history: List[Dict[str, str]] = []
        for entry in history:
            role = entry.get("sender_role") or entry.get("role")
            msg = entry.get("message") or entry.get("content")
            if role not in {"user", "assistant"} or not isinstance(msg, str):
                continue
            compiled_history.append({"role": role, "content": msg})

        context_parts: List[str] = []
        if official:
            realtor = official.get("realtor") or {}
            bot_info = official.get("realtor_bot") or {}
            if realtor:
                context_parts.append(f"Inmobiliaria: {realtor.get('name')}")
            if bot_info.get("name"):
                context_parts.append(f"Nombre del bot: {bot_info['name']}")
            if bot_info.get("personality"):
                context_parts.append(f"Personalidad: {bot_info['personality']}")
            if bot_info.get("tone"):
                context_parts.append(f"Tono sugerido: {bot_info['tone']}")
            if official.get("properties_interested"):
                context_parts.append(
                    f"Proyectos de interés: {official['properties_interested']}"
                )
            if official.get("mentioned_properties"):
                context_parts.append(
                    f"Propiedades mencionadas: {official['mentioned_properties']}"
                )

        return {
            "history": compiled_history,
            "message": message,
            "context": "\n".join(context_parts) if context_parts else None,
            "prospect_name": normalized.get("name"),
        }

    def _persist_interaction(
        self,
        *,
        session_id: str,
        user_message: str,
        agent_reply: str,
        intents: Sequence[str],
        structured_output: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._history_repo:
            return

        history = self._history_repo.fetch_history(session_id, limit=5)
        last_entry = history[-1] if history else None
        if not last_entry or last_entry.get("message") != user_message or last_entry.get("sender_role") != "user":
            self._history_repo.append_message(
                session_id=session_id,
                sender_role="user",
                message=user_message,
                metadata={"source": "webhook"},
            )

        self._history_repo.append_message(
            session_id=session_id,
            sender_role="assistant",
            message=agent_reply,
            metadata=self._build_message_metadata(intents, structured_output),
        )

    def _cleanup_history(self, session_id: str) -> None:
        if not self._history_repo:
            return
        self._history_repo.delete_last(session_id)

    @staticmethod
    def _build_message_metadata(
        intents: Sequence[str], structured_output: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "intents": list(intents),
        }
        if structured_output is not None:
            metadata["structured_output"] = structured_output
            subagents = structured_output.get("subagents") if isinstance(structured_output, dict) else None
            if isinstance(subagents, dict) and subagents:
                metadata["subagents"] = subagents
        return metadata

    def _run_rag_subagent(
        self,
        *,
        message: str,
        history: Sequence[Dict[str, Any]],
        realtor_id: Optional[str],
    ) -> Optional[RAGSubAgentResult]:
        try:
            return self._rag_agent.run(
                message=message,
                history=history,
                realtor_id=realtor_id,
            )
        except ValueError:
            logger.warning("El subagente RAG rechazó la consulta por mensaje vacío")
            return None

    def _run_project_interest_subagent(
        self,
        *,
        prospect_id: Optional[str],
        realtor_id: Optional[str],
        mentioned_projects: Sequence[str] | None,
    ) -> Optional[ProjectInterestSubAgentResult]:
        return self._project_interest_agent.run(
            prospect_id=prospect_id,
            realtor_id=realtor_id,
            mentioned_projects=mentioned_projects,
        )

    @staticmethod
    def _merge_mentioned_properties(
        *,
        normalized: Dict[str, Any],
        official: Optional[Dict[str, Any]],
        new_mentions: Sequence[str],
    ) -> None:
        if not new_mentions:
            return

        def _merge(existing: Any) -> List[str]:
            base: List[Any]
            if isinstance(existing, (list, tuple)):
                base = list(existing)
            elif existing:
                base = [existing]
            else:
                base = []

            merged: List[str] = []
            for item in base + list(new_mentions):
                if not item:
                    continue
                value = str(item)
                if value not in merged:
                    merged.append(value)
            return merged

        normalized["mentioned_properties"] = _merge(
            normalized.get("mentioned_properties")
        )

        if isinstance(official, dict):
            official["mentioned_properties"] = _merge(
                official.get("mentioned_properties")
            )

    @staticmethod
    def _merge_properties_interested(
        *,
        normalized: Dict[str, Any],
        official: Optional[Dict[str, Any]],
        new_projects: Sequence[Dict[str, Any]],
    ) -> None:
        if not new_projects:
            return

        def _merge(existing: Any) -> List[Dict[str, Any]]:
            merged: List[Dict[str, Any]] = []
            seen: set[str] = set()
            if isinstance(existing, list):
                for item in existing:
                    if not isinstance(item, dict):
                        continue
                    project_id = str(item.get("id")) if item.get("id") else None
                    if project_id and project_id not in seen:
                        seen.add(project_id)
                        merged.append(item)
            for project in new_projects:
                if not isinstance(project, dict):
                    continue
                project_id = str(project.get("id")) if project.get("id") else None
                if project_id and project_id not in seen:
                    seen.add(project_id)
                    merged.append(project)
            return merged

        normalized["properties_interested"] = _merge(
            normalized.get("properties_interested")
        )

        if isinstance(official, dict):
            official["properties_interested"] = _merge(
                official.get("properties_interested")
            )

    @staticmethod
    def _extract_mentioned_projects(
        normalized: Dict[str, Any],
        official: Optional[Dict[str, Any]],
    ) -> List[str]:
        candidates: List[str] = []
        for container in (normalized, official or {}):
            values = container.get("mentioned_properties") if isinstance(container, dict) else None
            if isinstance(values, list):
                for value in values:
                    if value and value not in candidates:
                        candidates.append(str(value))
        return candidates

    @staticmethod
    def _extract_message(
        normalized: Dict[str, Any], payload: Dict[str, Any]
    ) -> Optional[str]:
        message = normalized.get("message") or payload.get("message")
        if isinstance(message, str):
            cleaned = message.strip()
            return cleaned if cleaned else None
        return None

    @staticmethod
    def _extract_stage(state: InboundState, normalized: Dict[str, Any]) -> str:
        prospect = state.get("prospect") or {}
        stage = prospect.get("stage") or normalized.get("stage") or ""
        return str(stage).lower()

    @staticmethod
    def _extract_prospect_id(state: InboundState, normalized: Dict[str, Any]) -> Optional[str]:
        prospect = state.get("prospect") or {}
        return prospect.get("id") or normalized.get("prospect_id")

    def _detect_intents(
        self,
        message: str,
        history: Sequence[Dict[str, Any]] | None = None,
    ) -> List[PrimaryIntent]:
        text = self._normalize_text(message)
        detected: Set[PrimaryIntent] = set()

        for intent, keywords in _INTENT_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                detected.add(intent)

        if not detected and history:
            # simple heuristic: if recent history mentions visitas, keep that context
            for item in reversed(history):
                prev_message = item.get("message")
                if not isinstance(prev_message, str):
                    continue
                normalized = self._normalize_text(prev_message)
                if "visita" in normalized:
                    detected.add("fecha_visita")
                    break

        if not detected:
            detected.add(_DEFAULT_INTENT)

        return sorted(detected)

    @staticmethod
    def _extract_intents(structured_output: Dict[str, Any]) -> List[PrimaryIntent]:
        candidates = structured_output.get("intents")
        if not candidates:
            candidates = structured_output.get("intencion")
        if isinstance(candidates, str):
            candidates = [candidates]
        if not isinstance(candidates, list):
            return []
        intents: List[PrimaryIntent] = []
        for item in candidates:
            if isinstance(item, str) and item:
                intents.append(item)
        return intents

    @staticmethod
    def _build_filters(intents: Iterable[PrimaryIntent], stage: str) -> Dict[str, Any]:
        intent_set = set(intents)

        rag_required = bool(
            {"busqueda_informacion", "pide_fotos_plano_videos"} & intent_set
        )
        update_required = "anotar_proyecto" in intent_set

        calification_required = bool(
            {"forma_pago", "fecha_compra"} & intent_set
        )
        calification_allowed = stage in _ALLOWED_CALIFICATION_STAGES
        calification_block_reason = None
        if calification_required and not calification_allowed:
            calification_required = False
            calification_block_reason = "stage_not_allowed"

        schedule_required = "fecha_visita" in intent_set
        schedule_allowed = stage in _ALLOWED_SCHEDULE_STAGE
        schedule_block_reason = None
        if schedule_required and not schedule_allowed:
            schedule_required = False
            schedule_block_reason = "stage_not_allowed"

        return {
            "filter_rag": rag_required,
            "filter_intention": update_required,
            "filter_calification": calification_required,
            "filter_schedule": schedule_required,
            "calification_block_reason": calification_block_reason,
            "schedule_block_reason": schedule_block_reason,
        }

    @staticmethod
    def _craft_reply(filters: Dict[str, Any]) -> str:
        fragments: List[str] = []
        if filters.get("filter_rag"):
            fragments.append(
                "Revisaré la información disponible para responder con detalles claros."
            )
        if filters.get("filter_intention"):
            fragments.append("Registraré tu interés en el proyecto para mantenerlo actualizado.")
        if filters.get("filter_calification"):
            fragments.append("Consideraré tu información para la calificación del prospecto.")
        if filters.get("filter_schedule"):
            fragments.append("Coordinaré opciones para agendar una visita.")

        if not fragments:
            return (
                "Hemos recibido tu mensaje y lo estamos procesando. "
                "En breve continuaré con los siguientes pasos."
            )

        return " ".join(fragments)

    def _craft_reply_from_intents(self, intents: Sequence[str], stage: str) -> str:
        filters = self._build_filters(intents, stage)
        return self._craft_reply(filters)

    def _build_next_actions(self, intents: Sequence[str], stage: str) -> List[str]:
        filters = self._build_filters(intents, stage)
        actions: List[str] = []
        if filters.get("filter_rag"):
            actions.append("filter_rag")
        if filters.get("filter_calification"):
            actions.append("filter_calification")
        if filters.get("filter_intention"):
            actions.append("filter_intention")
        if filters.get("filter_schedule"):
            actions.append("filter_schedule")
        return actions

    @staticmethod
    def _summarize_intents(intents: Sequence[str], message: str) -> str:
        intent_list = ", ".join(intents)
        return f"Intenciones detectadas: {intent_list}. Último mensaje: '{message}'."

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFD", text.lower())
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")

    @staticmethod
    def _validate_output(structured_output: Dict[str, Any]) -> bool:
        intents = structured_output.get("intents") or structured_output.get("intencion")
        if isinstance(intents, str):
            intents = [intents]
        if not isinstance(intents, list) or not all(
            isinstance(item, str) for item in intents
        ):
            logger.warning("Salida del Agente Madre sin intents válidos: %s", structured_output)
            return False
        filters = structured_output.get("filters")
        if not isinstance(filters, dict):
            logger.warning("Salida del Agente Madre sin filtros válidos: %s", structured_output)
            return False
        return True

    def _load_prompt(self) -> Optional[str]:
        prompt_path = self._settings.master_agent_prompt_path
        try:
            path = Path(prompt_path)
            if not path.is_absolute():
                path = Path(__file__).resolve().parents[2] / prompt_path
            text = path.read_text(encoding="utf-8")
            return text.strip()
        except FileNotFoundError:
            logger.warning(
                "No se encontró el prompt del Agente Madre en %s", prompt_path
            )
        except Exception:
            logger.exception(
                "Error leyendo el prompt del Agente Madre en %s", prompt_path
            )
        return None


__all__ = ["AgentDecision", "MasterAgent"]
