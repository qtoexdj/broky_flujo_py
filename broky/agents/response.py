"""LangChain executor que genera la respuesta final para el usuario."""

from __future__ import annotations

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


class ResponseAgentExecutor(BrokyAgent):
    """Genera respuestas breves y consistentes con la etapa del prospecto."""

    MAX_HISTORY_MESSAGES = 6

    def __init__(self) -> None:
        self._settings = get_langchain_settings()
        if self._settings.openai_api_key:
            self._model: Optional[ChatOpenAI] = ChatOpenAI(
                api_key=self._settings.openai_api_key,
                model=self._settings.openai_model,
                temperature=0.2,
            )
        else:
            logger.warning(
                "OPENAI_API_KEY no configurado; ResponseAgentExecutor operará con heurística"
            )
            self._model = None

        self._prompt_template = self._load_prompt()

        super().__init__(runnable=RunnableLambda(self._execute))

    def build_input(self, context: BrokyContext) -> Dict[str, Any]:
        payload = context.payload
        message = self._extract_message(payload)
        history = self._extract_history(context.memory_snapshot)
        official = self._extract_official(payload)

        stage = self._resolve_stage(context, official)
        stage_instruction = self._stage_instruction(stage)
        additional_info = self._build_additional_info(context, official)
        system_prompt = self._render_prompt(
            bot_name=self._resolve_bot_name(official),
            realtor_name=official.get("realtor", {}).get("name"),
            bot_personality=self._resolve_bot_personality(official),
            bot_tone=self._resolve_bot_tone(official),
            stage_instruction=stage_instruction,
            additional_info=additional_info,
        )

        context_block = self._build_context_block(official, context)

        return {
            "message": message,
            "history": history,
            "system_prompt": system_prompt,
            "context_block": context_block,
            "stage": stage,
        }

    def handle_output(self, context: BrokyContext, result: Dict[str, Any]) -> BrokyContext:
        reply = (result.get("reply") or "").strip()
        if not reply:
            reply = self._fallback_reply(context)

        reply = self._apply_special_cases(reply, context)
        reply = self._trim_reply(reply)

        context.metadata["reply"] = reply
        context.metadata.setdefault("response_agent", {})["stage"] = result.get("stage")
        context.append_log(f"ResponseAgent reply_length={len(reply)}")
        return context

    # ------------------------------------------------------------------

    def _execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        message = payload.get("message")
        system_prompt = payload.get("system_prompt")
        if not message or not system_prompt:
            return {"reply": None, "stage": payload.get("stage")}

        messages = [SystemMessage(content=system_prompt)]
        context_block = payload.get("context_block")
        if context_block:
            messages.append(SystemMessage(content=context_block))

        for item in payload.get("history") or []:
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

        if not self._model:
            return {"reply": None, "stage": payload.get("stage")}

        try:
            response = self._model.invoke(messages)
        except Exception:  # pragma: no cover - fallback heurístico
            logger.exception("OpenAI falló para ResponseAgent; usando fallback")
            return {"reply": None, "stage": payload.get("stage")}

        content = response.content if isinstance(response, AIMessage) else None
        if not content:
            logger.warning("ResponseAgent recibió contenido vacío; se usará fallback")
            return {"reply": None, "stage": payload.get("stage")}

        return {"reply": content.strip(), "stage": payload.get("stage")}

    # ------------------------------------------------------------------

    @staticmethod
    def _extract_official(payload: Dict[str, Any]) -> Dict[str, Any]:
        official = payload.get("official_data")
        if isinstance(official, dict):
            return official
        return {}

    def _render_prompt(
        self,
        *,
        bot_name: Optional[str],
        realtor_name: Optional[str],
        bot_personality: Optional[str],
        bot_tone: Optional[str],
        stage_instruction: str,
        additional_info: str,
    ) -> str:
        bot = bot_name or "el asistente virtual"
        realtor = realtor_name or "la inmobiliaria"
        personality = bot_personality or "profesional y cordial"
        tone = bot_tone or "cálido"
        template = self._prompt_template

        replacements = {
            "{{BOT_NAME}}": bot,
            "{{REALTOR_NAME}}": realtor,
            "{{BOT_PERSONALITY}}": personality,
            "{{BOT_TONE}}": tone,
            "{{STAGE_INSTRUCTION}}": stage_instruction.strip(),
            "{{ADDITIONAL_INFO}}": additional_info.strip(),
        }

        rendered = template
        for placeholder, value in replacements.items():
            rendered = rendered.replace(placeholder, value or "")
        return rendered

    def _build_context_block(self, official: Dict[str, Any], context: BrokyContext) -> str:
        lines: List[str] = []
        realtor = official.get("realtor") or {}
        prospect = official.get("prospect") or {}

        if realtor.get("name"):
            lines.append(f"Inmobiliaria: {realtor['name']}")
        if realtor.get("description"):
            lines.append(f"Descripción: {realtor['description']}")
        if official.get("stage"):
            lines.append(f"Stage actual: {official['stage']}")
        elif prospect.get("stage"):
            lines.append(f"Stage actual: {prospect['stage']}")

        if prospect.get("name"):
            lines.append(f"Prospecto: {prospect['name']}")
        if prospect.get("telephone"):
            lines.append(f"Teléfono prospecto: {prospect['telephone']}")

        properties_interested = official.get("properties_interested")
        if properties_interested:
            lines.append(f"Proyectos interesados: {properties_interested}")

        mentioned = official.get("mentioned_properties")
        if mentioned:
            lines.append(f"Propiedades mencionadas: {mentioned}")

        followups = official.get("realtor_followups") or {}
        if followups.get("prospects"):
            lines.append("Configuración follow-up prospecto disponible")
        if followups.get("brokers"):
            lines.append("Configuración follow-up broker disponible")

        subagent_replies = context.metadata.get("subagent_replies") or []
        if subagent_replies:
            summary = " | ".join(reply for reply in subagent_replies if reply)
            if summary:
                lines.append(f"Respuestas de subagentes: {summary}")

        return "\n".join(lines)

    def _build_additional_info(
        self,
        context: BrokyContext,
        official: Dict[str, Any],
    ) -> str:
        fragments: List[str] = []

        user_message = self._extract_message(context.payload)
        if user_message:
            fragments.append(f"Último mensaje del usuario: {user_message}")

        subagents = context.metadata.get("subagents") or {}

        rag_result = subagents.get("filter_rag")
        if isinstance(rag_result, dict):
            response = rag_result.get("response")
            if response:
                fragments.append(f"Contexto relevante: {response}")

        calification = context.metadata.get("calification_variables") or {}
        cal_lines: List[str] = []
        if isinstance(calification, dict):
            forma_pago = calification.get("forma_pago")
            fecha = calification.get("fecha_compra_estimativa")
            notas = calification.get("notas_adicionales")
            if forma_pago:
                cal_lines.append(f"Forma de pago: {forma_pago}")
            if fecha:
                cal_lines.append(f"Fecha estimada de compra: {fecha}")
            if notas:
                cal_lines.append(f"Notas financieras: {notas}")
        if cal_lines:
            fragments.append("Información de calificación: " + " | ".join(cal_lines))

        scheduled = context.metadata.get("scheduled_visit") or {}
        if isinstance(scheduled, dict):
            date = scheduled.get("date") or scheduled.get("scheduled_at")
            if date:
                fragments.append(f"Visita propuesta: {date}")

        files_links = context.metadata.get("files_links") or []
        if files_links:
            links_summary = []
            for entry in files_links:
                if not isinstance(entry, dict):
                    continue
                project = entry.get("project") or "proyecto"
                file_type = entry.get("type") or "archivo"
                url = entry.get("url")
                if url:
                    links_summary.append(f"{project} - {file_type}: {url}")
            if links_summary:
                fragments.append("Archivos listos: " + " | ".join(links_summary))

        if context.metadata.get("handoff_required"):
            reason = context.metadata.get("handoff_reason") or "contacto_humano"
            fragments.append(f"Escalamiento activado por: {reason}")

        notifications = context.metadata.get("notifications") or []
        if notifications:
            fragments.append("Se prepararon notificaciones adicionales para el equipo interno.")

        if not fragments:
            fragments.append("Sin información adicional relevante.")

        return "\n".join(fragments)

    @staticmethod
    def _extract_history(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not snapshot:
            return []
        messages = snapshot.get("messages")
        if not isinstance(messages, list):
            return []
        if len(messages) <= ResponseAgentExecutor.MAX_HISTORY_MESSAGES:
            return messages
        return messages[-ResponseAgentExecutor.MAX_HISTORY_MESSAGES :]

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

    @staticmethod
    def _resolve_bot_name(official: Dict[str, Any]) -> Optional[str]:
        bot = official.get("realtor_bot") or {}
        name = bot.get("name")
        if name:
            return name
        return None

    @staticmethod
    def _resolve_bot_personality(official: Dict[str, Any]) -> Optional[str]:
        bot = official.get("realtor_bot") or {}
        personality = bot.get("personality")
        if isinstance(personality, str) and personality.strip():
            return personality.strip()
        return None

    @staticmethod
    def _resolve_bot_tone(official: Dict[str, Any]) -> Optional[str]:
        bot = official.get("realtor_bot") or {}
        tone = bot.get("tone")
        if isinstance(tone, str) and tone.strip():
            return tone.strip()
        return None

    @staticmethod
    def _resolve_stage(context: BrokyContext, official: Dict[str, Any]) -> str:
        metadata_stage = context.metadata.get("stage")
        if isinstance(metadata_stage, str) and metadata_stage:
            return metadata_stage
        official_stage = official.get("stage")
        if isinstance(official_stage, str) and official_stage:
            return official_stage
        prospect = official.get("prospect") or {}
        prospect_stage = prospect.get("stage")
        if isinstance(prospect_stage, str) and prospect_stage:
            return prospect_stage
        return "new-prospect"

    @staticmethod
    def _stage_instruction(stage: str) -> str:
        stage_clean = (stage or "").strip().lower()
        mapping = {
            "new-prospect": (
                "- Descripción: aún no sabes qué propiedad le interesa al usuario.\n"
                "- Objetivo: identifica primero la propiedad de interés antes de avanzar.\n"
                "- Nota: si el usuario quiere visitar, pregunta primero qué proyecto le interesa."
            ),
            "conversation": (
                "- Descripción: entrega información y resuelve dudas.\n"
                "- Objetivo: si desea avanzar, indaga de forma sutil en forma de pago y fecha estimada de compra.\n"
                "- Nota: nunca confundas fechas de visita con fechas de compra."
            ),
            "qualified": (
                "- Descripción: el prospecto está listo para coordinar visita.\n"
                "- Objetivo: solicita fecha y hora para VISITAR el proyecto.\n"
                "- Nota: distingue claramente entre fecha de compra y de visita."
            ),
            "not-qualified": (
                "- Descripción: el prospecto no cumple condiciones para visitar ahora.\n"
                "- Objetivo: responde con empatía y explica por qué no puede visitarse todavía.\n"
                "- Nota: ofrece seguimiento futuro acorde al motivo (forma de pago o fecha lejana)."
            ),
            "scheduled": (
                "- Descripción: ya existe una visita propuesta pendiente de confirmación humana.\n"
                "- Objetivo: cierra la conversación indicando que un ejecutivo confirmará la cita."
            ),
        }
        return mapping.get(stage_clean, "Consulta la información disponible y responde con cortesía.")

    def _fallback_reply(self, context: BrokyContext) -> str:
        filters = context.metadata.get("filters") or {}
        fragments: List[str] = []

        if filters.get("filter_rag"):
            fragments.append("Estoy revisando la información solicitada para responderte con precisión.")
        if filters.get("filter_intention"):
            fragments.append("Registraré tu interés para mantenerlo actualizado.")
        if filters.get("filter_calification"):
            fragments.append("Gracias por los datos; los compartiré con un asesor.")
        if filters.get("filter_schedule"):
            fragments.append("Coordinaré con el equipo para proponerte una fecha de visita.")
        if filters.get("filter_files"):
            fragments.append("Te enviaré los archivos solicitados en cuanto estén listos.")
        if filters.get("filter_contact"):
            fragments.append("Un asesor humano se pondrá en contacto contigo a la brevedad.")
        if filters.get("filter_desinteres"):
            fragments.append("Detendré los mensajes automáticos, pero seguiré atento por si necesitas algo más.")

        subagent_replies = context.metadata.get("subagent_replies") or []
        for extra in subagent_replies:
            if extra:
                fragments.append(extra)

        if not fragments:
            fragments.append("Hemos recibido tu mensaje y continuaremos contigo en breve.")

        combined = " ".join(fragments).strip()
        return self._trim_reply(combined)

    @staticmethod
    def _trim_reply(reply: str) -> str:
        max_length = 1200
        if len(reply) <= max_length:
            return reply
        return reply[: max_length - 3].rstrip() + "..."

    def _apply_special_cases(self, reply: str, context: BrokyContext) -> str:
        original = reply or ""
        normalized_reply = original.lower()
        user_message = (self._extract_message(context.payload) or "").lower()
        combined = f"{normalized_reply} {user_message}"

        requires_contact = any(
            token in combined for token in ("post venta", "postventa", "las palmas")
        )
        if requires_contact:
            contact_line = (
                "Si necesitas apoyo prioritario puedes escribir a monica.gonzalez@parcelasdechile.cl "
                "o al +569 8642 1063."
            )
            if contact_line.lower() not in normalized_reply:
                updated = f"{original} {contact_line}".strip()
                return updated
        return original

    def _load_prompt(self) -> str:
        """Carga y adapta el prompt de respuesta templado para su uso en Python."""

        base_path = Path(__file__).resolve().parents[2]
        candidate = base_path / "docs/new_prompts/RESPUESTA.md"
        try:
            raw = candidate.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("Prompt RESPUESTA no encontrado; se usará plantilla fija")
            return self._default_prompt()
        except Exception:
            logger.exception("Error leyendo el prompt RESPUESTA; se usará plantilla fija")
            return self._default_prompt()

        template = self._normalize_template(raw)
        if not template.strip():
            return self._default_prompt()
        return template

    @staticmethod
    def _normalize_template(text: str) -> str:
        """Remplaza los placeholders de n8n por tokens simples."""

        replacements = {
            '{{ $node["datos_oficiales"].json.name_bot }}': "{{BOT_NAME}}",
            '{{ $node["datos_oficiales"].json.name_realtor }}': "{{REALTOR_NAME}}",
            '{{ $node["datos_oficiales"].json.personality_bot }}': "{{BOT_PERSONALITY}}",
            '{{ $node["datos_oficiales"].json.tone_bot }}': "{{BOT_TONE}}",
            '{{ $node["prompt_etapa"].json.instruccion_etapa }}': "{{STAGE_INSTRUCTION}}",
            '{{ $node["unir_variables"].json.enviado }}': "{{ADDITIONAL_INFO}}",
            '{{ ( $node["unir_variables"].json.informacion_para_responder || '' )\n        .replace(/{/g, '')\n        .replace(/}/g, '') }}': "",
            '{{ ( $node["unir_variables"].json.informacion_para_responder || '' )        .replace(/{/g, '')        .replace(/}/g, '') }}': "",
            '{{ $node["unir_variables"].json.calificacion_para_una_visita }}': "",
            '{{ $node["unir_variables"].json.estado_del_agendamiento }}': "",
            '{{ $node["unir_variables"].json.vendedor_contactado }}': "",
            '{{ $node["unir_variables"].json.anotar_desinteres }}': "",
        }

        normalized = text
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)

        return normalized

    @staticmethod
    def _default_prompt() -> str:
        return (
            "Eres {{BOT_NAME}}, asistente virtual de \"{{REALTOR_NAME}}\"."
            " Tu personalidad base es: {{BOT_PERSONALITY}}."
            " Mantén un tono {{BOT_TONE}} mientras respondes de forma breve (máximo 400 caracteres),"
            " profesional y alineada a la etapa del prospecto.\n\n"
            "<instrucciones_etapa>\n{{STAGE_INSTRUCTION}}\n</instrucciones_etapa>\n\n"
            "Considera también esta información adicional: {{ADDITIONAL_INFO}}"
        )
