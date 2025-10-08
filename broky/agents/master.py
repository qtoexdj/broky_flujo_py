"""LangChain executor that clasifica intenciones del mensaje actual."""

from __future__ import annotations

import json
import logging
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI

from broky.agents.base import BrokyAgent
from broky.config import get_langchain_settings
from broky.core import BrokyContext

logger = logging.getLogger(__name__)


class MasterAgentExecutor(BrokyAgent):
    """Ejecutor responsable de clasificar intenciones y banderas de flujo."""

    def __init__(self) -> None:
        self._settings = get_langchain_settings()
        self._model: Optional[ChatOpenAI]
        if self._settings.openai_api_key:
            self._model = ChatOpenAI(
                api_key=self._settings.openai_api_key,
                model=self._settings.openai_model,
                temperature=0.2,
                model_kwargs={"response_format": {"type": "json_object"}}
            )
        else:
            logger.warning(
                "OPENAI_API_KEY no configurado; MasterAgentExecutor operará en modo heurístico"
            )
            self._model = None
        self._prompt_text = self._load_prompt()

        super().__init__(runnable=RunnableLambda(self._execute))

    def build_input(self, context: BrokyContext) -> Dict[str, Any]:
        payload = context.payload
        message = self._extract_message(payload)
        history = self._extract_history(context.memory_snapshot)
        compiled_context = self._build_context_block(payload)

        return {
            "session_id": context.session_id,
            "message": message,
            "history": history,
            "context": compiled_context,
            "realtor_id": payload.get("realtor_id") or context.realtor_id,
            "metadata": payload.get("metadata") or {},
        }

    def handle_output(self, context: BrokyContext, result: Dict[str, Any]) -> BrokyContext:
        filters = result.get("filters") or {}
        intents = result.get("intents") or []

        context.metadata.setdefault("master_agent", result)
        context.metadata["intents"] = intents
        context.metadata["filters"] = filters
        context.metadata.setdefault("subagent_replies", [])
        if result.get("handoff"):
            context.metadata["handoff_required"] = True

        context.append_log(
            f"MasterAgent intents={intents} filters={filters} handoff={result.get('handoff')}"
        )
        return context

    # ------------------------------------------------------------------

    def _execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        message: Optional[str] = payload.get("message")
        if not message:
            return self._build_failure_output("missing_message")

        messages = self._build_messages(
            message=message,
            context_block=payload.get("context"),
            history=payload.get("history") or [],
        )

        if not self._model:
            return self._heuristic_output(message)

        try:
            response = self._model.invoke(messages)
        except Exception:  # pragma: no cover - fallback defensivo
            logger.exception("OpenAI falló para el Agente Madre; usando heurística")
            return self._heuristic_output(message)

        content = response.content if isinstance(response, AIMessage) else None
        if not content:
            logger.warning("Respuesta vacía del LLM; usando heurística")
            return self._heuristic_output(message)

        try:
            data = json.loads(content)
            if not isinstance(data, dict):  # pragma: no cover - defensive
                raise ValueError("JSON inválido")
        except Exception:
            logger.exception("No se pudo parsear la salida JSON del Agente Madre")
            return self._heuristic_output(message)

        intents = self._augment_intents(
            self._normalize_intents(self._coerce_intents(data)), message
        )
        data["intents"] = intents

        if "filters" not in data:
            data["filters"] = self._build_filters(intents)

        data.setdefault("handoff", False)
        return data

    def _build_messages(
        self,
        *,
        message: str,
        context_block: Optional[str],
        history: List[Dict[str, Any]],
    ) -> List[Any]:
        messages: List[Any] = [SystemMessage(content=self._prompt_text)]
        if context_block:
            messages.append(SystemMessage(content=context_block))

        for item in history:
            role = item.get("sender_role") or item.get("role")
            content = item.get("message") or item.get("content")
            if not isinstance(content, str):
                continue
            trimmed = content.strip()
            if not trimmed:
                continue
            if role == "assistant":
                messages.append(AIMessage(content=trimmed))
            else:
                messages.append(HumanMessage(content=trimmed))

        messages.append(HumanMessage(content=message))
        return messages

    def _build_context_block(self, payload: Dict[str, Any]) -> Optional[str]:
        official = payload.get("official_data") if isinstance(payload, dict) else None

        base_container = official if isinstance(official, dict) else payload

        realtor = (base_container.get("realtor") or {}).copy() if isinstance(base_container, dict) else {}
        bot_info = (base_container.get("realtor_bot") or {}).copy() if isinstance(base_container, dict) else {}
        properties = base_container.get("properties_interested") if isinstance(base_container, dict) else None
        mentioned = base_container.get("mentioned_properties") if isinstance(base_container, dict) else None

        parts: List[str] = []
        if realtor:
            name = realtor.get("name")
            if name:
                parts.append(f"Inmobiliaria: {name}")
            description = realtor.get("description")
            if description:
                parts.append(f"Descripción: {description}")

        if bot_info:
            if bot_info.get("name"):
                parts.append(f"Nombre del bot: {bot_info['name']}")
            if bot_info.get("personality"):
                parts.append(f"Personalidad: {bot_info['personality']}")
            if bot_info.get("tone"):
                parts.append(f"Tono sugerido: {bot_info['tone']}")

        if properties:
            parts.append(f"Proyectos interesados: {properties}")
        if mentioned:
            parts.append(f"Propiedades mencionadas: {mentioned}")

        return "\n".join(parts) if parts else None

    @staticmethod
    def _extract_history(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not snapshot:
            return []
        messages = snapshot.get("messages")
        if isinstance(messages, list):
            return messages
        return []

    @staticmethod
    def _extract_message(payload: Dict[str, Any]) -> Optional[str]:
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        normalized = payload.get("normalized") or {}
        alt = normalized.get("message") if isinstance(normalized, dict) else None
        if isinstance(alt, str) and alt.strip():
            return alt.strip()
        return None

    def _build_filters(self, intents: List[str]) -> Dict[str, Any]:
        intent_set = set(intents)
        filters = {
            "filter_rag": bool(
                {"busqueda_informacion", "pide_fotos_plano_videos"} & intent_set
            ),
            "filter_intention": "anotar_proyecto" in intent_set,
            "filter_calification": bool({"forma_pago", "fecha_compra"} & intent_set),
            "filter_schedule": "fecha_visita" in intent_set,
            "filter_files": bool(
                {"enviar_archivos", "pide_fotos_plano_videos"} & intent_set
            ),
            "filter_contact": "contacto_humano" in intent_set,
            "filter_desinteres": "desinteres" in intent_set,
        }
        return filters

    def _heuristic_output(self, message: str) -> Dict[str, Any]:
        intents = self._augment_intents(
            self._normalize_intents(self._heuristic_intents(message)), message
        )
        filters = self._build_filters(intents)
        return {
            "intents": intents,
            "filters": filters,
            "handoff": False,
        }

    @staticmethod
    def _heuristic_intents(message: str) -> List[str]:
        text = message.lower()
        intents: List[str] = []
        if any(keyword in text for keyword in ("informacion", "detalle", "proyecto")):
            intents.append("busqueda_informacion")
        if any(keyword in text for keyword in ("foto", "imagenes", "plano")):
            intents.append("pide_fotos_plano_videos")
        if "anotar" in text or "registrar" in text:
            intents.append("anotar_proyecto")
        if any(keyword in text for keyword in ("cuota", "pago", "credito")):
            intents.append("forma_pago")
        if any(keyword in text for keyword in ("comprar", "cuando", "plazo")):
            intents.append("fecha_compra")
        if any(keyword in text for keyword in ("visita", "agendar", "tour")):
            intents.append("fecha_visita")
        if any(keyword in text for keyword in ("enviar", "envia", "enviame", "archivo", "archivos", "foto", "fotos")):
            intents.append("enviar_archivos")
        if any(keyword in text for keyword in ("contacto", "asesor", "vendedor", "humano", "llamar", "telefono", "teléfono")):
            intents.append("contacto_humano")
        if any(keyword in text for keyword in ("no me interesa", "desinteres", "desinterés", "no quiero", "deten", "stop")):
            intents.append("desinteres")

        if not intents:
            intents.append("busqueda_informacion")
        return intents

    @staticmethod
    def _coerce_intents(data: Dict[str, Any]) -> List[str]:
        raw = data.get("intents") or data.get("intencion") or data.get("intenciones")
        if isinstance(raw, str):
            raw = [raw]
        elif isinstance(raw, dict):
            raw = list(raw.values())
        if not isinstance(raw, list):
            return []
        intents: List[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                intents.append(item.strip())
        return intents

    def _augment_intents(self, intents: List[str], message: str) -> List[str]:
        normalized = self._normalize_text(message)
        if any(keyword in normalized for keyword in ("enviar", "archivo", "foto")):
            if "enviar_archivos" not in intents:
                intents.append("enviar_archivos")
        if any(keyword in normalized for keyword in ("contacto", "asesor", "vendedor", "humano", "llamar", "telefono", "telefono")):
            if "contacto_humano" not in intents:
                intents.append("contacto_humano")
        if any(keyword in normalized for keyword in ("no me interesa", "desinteres", "desinterés", "no quiero", "deten", "stop")):
            if "desinteres" not in intents:
                intents.append("desinteres")
        return intents

    @staticmethod
    def _normalize_intents(intents: List[str]) -> List[str]:
        normalized: List[str] = []
        seen: set[str] = set()
        for intent in intents:
            if not isinstance(intent, str):
                continue
            trimmed = intent.strip().lower()
            if not trimmed:
                continue
            aliases = [trimmed]
            if trimmed == "pide_fotos_plano_videos":
                aliases.append("enviar_archivos")
            for alias in aliases:
                if alias not in seen:
                    normalized.append(alias)
                    seen.add(alias)
        return normalized

    def _build_failure_output(self, reason: str) -> Dict[str, Any]:
        logger.warning("MasterAgentExecutor sin mensaje válido | reason=%s", reason)
        filters = {}
        return {
            "intents": [],
            "filters": filters,
            "handoff": True,
            "error": reason,
        }

    def _load_prompt(self) -> str:
        path_candidates = [
            Path("docs/new_prompts/Agente_madre.md"),
            Path("docs/master_agent_prompt.md"),
        ]
        base_path = Path(__file__).resolve().parents[2]
        for candidate in path_candidates:
            path = candidate
            if not path.is_absolute():
                path = base_path / path
            try:
                text = path.read_text(encoding="utf-8")
                stripped = text.strip()
                if stripped:
                    return stripped
            except FileNotFoundError:
                continue
            except Exception:
                logger.exception("Error leyendo el prompt del Agente Madre en %s", path)
                continue

        logger.warning(
            "No se encontró prompt del Agente Madre; usando fallback genérico"
        )
        return (
            "Eres un asistente cordial que responde consultas inmobiliarias "
            "en base al contexto disponible y clasifica intenciones en formato JSON"
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFD", text.lower())
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
