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
        aggregated = context.metadata.get("aggregated_context") or {}
        if isinstance(aggregated, dict):
            context.metadata.setdefault("contexto_adicional", aggregated)
        additional_info = self._build_additional_info(context, official, aggregated)
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
        reply = self._append_file_links(reply, context)
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
        interested_labels: List[str] = []
        if isinstance(properties_interested, list):
            for item in properties_interested:
                if isinstance(item, dict):
                    label = (
                        item.get("name_property")
                        or item.get("project_name")
                        or item.get("name")
                        or item.get("title")
                    )
                    if label:
                        interested_labels.append(str(label).strip())
                elif isinstance(item, str) and item.strip():
                    interested_labels.append(item.strip())
        if interested_labels:
            lines.append("Proyectos interesados: " + ", ".join(dict.fromkeys(interested_labels)))

        mentioned = official.get("mentioned_properties")
        mentioned_labels: List[str] = []
        if isinstance(mentioned, list):
            for item in mentioned:
                if isinstance(item, dict):
                    label = (
                        item.get("name_property")
                        or item.get("project_name")
                        or item.get("name")
                        or item.get("title")
                    )
                    if label:
                        mentioned_labels.append(str(label).strip())
                elif isinstance(item, str) and item.strip():
                    mentioned_labels.append(item.strip())
        if mentioned_labels:
            lines.append("Propiedades mencionadas: " + ", ".join(dict.fromkeys(mentioned_labels)))

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
        aggregated: Dict[str, str],
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

        if aggregated:
            for key, value in aggregated.items():
                if not value:
                    continue
                fragments.append(value)

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
                "- Descripción de la etapa: Aún no sabes qué propiedad le interesa al usuario.\n"
                "- Objetivo: Tienes que reconocer el o las propiedades de interés del usuario antes de avanzar. No puedes agendar visita en esta etapa aún.\n"
                "- Nota: Si el usuario te dice que desea visitar, debes preguntarle primero qué propiedad le interesa."
            ),
            "conversation": (
                "- *Descripción de la etapa*: Debes proporcionar toda la información y responder a sus dudas, SOLO cuando el usuario quiera avanzar a coordinar una visita, debes incluir preguntas que respondan lo siguiente:\n"
                "  1. Fecha en la que desea o planea comprar o adquirir la propiedad.\n"
                "  2. Forma en la que piensa o puede pagar o adquirir la propiedad.\n"
                "  (Debes ser sutil y nunca insistente al pedir esta información)\n"
                "  Cuando obtengas alguna de esta información, recibirás en “información adicional” qué información falta del usuario con el fin de guiar tus preguntas.\n"
                "  Notas importantes:\n"
                "  Nunca asumas que una fecha mencionada para visitar la propiedad es igual a una fecha de compra. Considera únicamente fechas que se refieran explícitamente a la intención de adquirir o comprar la propiedad."
            ),
            "qualified": (
                "- *Descripción de la etapa*: Cuando el usuario está calificado para visitar presencialmente nuestros proyectos y queremos coordinar una visita.\n"
                "- *Cómo guiar tu respuesta*: Tienes que consultarle una fecha en la que desea VISITAR y coordinarla.\n"
                "             - NUNCA debes confundir cuando el usuario se refiere a una fecha en la que desea “COMPRAR”, a una en la que desea “VISITAR”. Son cosas diferentes que no deben ser confundidas. Debes reconocer a qué se refiere el usuario según el contexto de la conversación."
            ),
            "not-qualified": (
                "- *Descripción de la etapa*: Cuando el usuario no está apto o “calificado” para una visita dado que la fecha de compra es superior a 1 mes o la forma de pago no es aceptable por nuestra empresa.\n"
                "- *Cómo guiar tu respuesta*: Debes responder a sus dudas, ser empático y explicarle al usuario que no puede visitar en estos momentos por las siguientes razones:\n"
                "        a) Si es por forma de pago: Explicarle que no aceptamos otras formas de pago.\n"
                "        b) Si es por fecha de compra mayor a un mes: Explicale que, vamos a contactar al usuario cerca de la fecha de compra para agendar una visita, ya que si visita en estos momentos puede ser que después cuando quiera comprar la parcela ya esté vendida."
            ),
            "scheduled": (
                "- *Descripción de la etapa*: Cuando el usuario ya ha sido agendado para una visita presencial con un vendedor, pero aún la visita no está confirmada.\n"
                "- *Cómo guiar tu respuesta*: Terminar sutilmente la conversación con el usuario, diciéndole que vas a contactar a un ejecutivo para que confirme la disponibilidad de la fecha de visita, el ejecutivo se pondrá en contacto con el usuario a la brevedad posible para confirmar la visita."
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

    def _append_file_links(self, reply: str, context: BrokyContext) -> str:
        links = context.metadata.get("files_links") or []
        if not isinstance(links, list) or not links:
            return reply

        # Los archivos se envían como adjuntos; evitamos duplicar enlaces en el texto.
        return reply

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
