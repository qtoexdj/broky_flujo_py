import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
from pydantic import ValidationError

from app.core.config import get_settings
from app.models.webhook import (
    WebhookPayload,
    WebhookResponse,
    WhatsAppEnvelope,
    WhatsAppMessage,
)
from app.workflows.service import InboundWorkflowService
from app.services.whapi_client import WhapiClient, WhapiDeliveryService
from broky.runtime import MasterAgentRuntime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

_settings = get_settings()
_workflow_service = InboundWorkflowService(_settings)
_master_runtime = MasterAgentRuntime(_settings)
_whapi_delivery = WhapiDeliveryService(
    WhapiClient(
        base_url=str(_settings.whapi_base_url) if _settings.whapi_base_url else "https://gate.whapi.cloud",
        timeout=_settings.whapi_timeout,
    )
)


@router.post("", response_model=WebhookResponse)
async def handle_webhook(request: Request) -> WebhookResponse:
    raw_body = await request.body()
    body_text = raw_body.decode("utf-8", errors="replace")
    logger.info("Webhook recibido | cuerpo crudo=%s", body_text)

    try:
        payload_dict = json.loads(body_text)
    except json.JSONDecodeError as exc:
        logger.warning("Webhook con JSON inválido: %s", body_text)
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_json", "message": str(exc)},
        ) from exc

    if isinstance(payload_dict, dict):
        if payload_dict.get("statuses") and not payload_dict.get("messages"):
            statuses = payload_dict.get("statuses") or []
            recipient = "status"
            if statuses and isinstance(statuses, list):
                recipient = str(statuses[0].get("recipient_id") or recipient)
            logger.info("Webhook de estado recibido; se omite procesamiento | recipient=%s", recipient)
            return WebhookResponse(reply="", user_id=recipient)

        messages = payload_dict.get("messages")
        if messages and isinstance(messages, list):
            first_message = messages[0]
            if isinstance(first_message, dict) and first_message.get("from_me"):
                chat_id = first_message.get("chat_id") or first_message.get("from") or "bot"
                logger.info(
                    "Mensaje emitido por el bot detectado; se omite procesamiento | message_id=%s",
                    first_message.get("id"),
                )
                return WebhookResponse(reply="", user_id=str(chat_id))

    payload = _coerce_payload(payload_dict)

    user_id = payload.from_user
    logger.info("Procesando mensaje de %s", user_id)

    try:
        workflow_state = _workflow_service.run(
            payload=payload.model_dump(by_alias=True)
        )
        official_data = workflow_state.get("official_data")
        if not isinstance(official_data, dict) or not official_data:
            official_data = _build_official_from_state(workflow_state)

        result = _master_runtime.run(workflow_state)
        logger.info(
            "MasterAgentRuntime | intents=%s | filtros=%s | handoff=%s",
            result.intents,
            result.filters,
            result.handoff,
        )
        reply = result.reply
        split_messages: list[str] = []
        justification: Optional[str] = None
        if isinstance(result.metadata, dict):
            metadata_state = result.metadata.get("inbound_state")
            if isinstance(metadata_state, dict):
                runtime_official = metadata_state.get("official_data")
                if isinstance(runtime_official, dict) and runtime_official:
                    official_data = runtime_official
            postprocess = result.metadata.get("postprocess")
            if isinstance(postprocess, dict):
                raw_messages = postprocess.get("split_messages")
                if isinstance(raw_messages, list):
                    split_messages = [
                        str(item).strip()
                        for item in raw_messages
                        if isinstance(item, (str, int, float)) and str(item).strip()
                    ]
                justification = postprocess.get("justification")
                if (
                    isinstance(justification, str)
                    and justification.strip()
                    and justification.strip().lower() != "no"
                ):
                    logger.info("Justificación generada: %s", justification.strip())

        delivery_result = _whapi_delivery.send_user_reply(
            reply=reply,
            official_data=official_data,
            messages=split_messages or None,
        )
        if not delivery_result.get("ok"):
            logger.info("Mensaje no entregado automáticamente | detalle=%s", delivery_result)

        notifications = result.metadata.get("notifications") if isinstance(result.metadata, dict) else None
        if notifications:
            for notification in notifications:
                delivery_info = _whapi_delivery.send_notification(
                    notification=notification,
                    official_data=official_data,
                )
                if not delivery_info.get("ok"):
                    logger.info(
                        "Notificación no enviada | tipo=%s | detalle=%s",
                        notification.get("type"),
                        delivery_info,
                    )
    except Exception as exc:  # pragma: no cover - defensive failure path
        logger.exception("Error al invocar el modelo: %s", exc)
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocurrió un error al generar la respuesta",
        ) from exc

    response_body = reply
    if split_messages:
        response_body = "\n\n".join(split_messages)

    return WebhookResponse(reply=response_body, user_id=user_id)


def _coerce_payload(raw_payload: Dict[str, Any]) -> WebhookPayload:
    """Normaliza el payload recibido a la estructura esperada por el pipeline."""

    try:
        return WebhookPayload.model_validate(raw_payload)
    except ValidationError:
        envelope = WhatsAppEnvelope.model_validate(raw_payload)
        if not envelope.messages:
            raise HTTPException(
                status_code=422,
                detail={"error": "invalid_payload", "issues": ["messages array missing"]},
            )

        message: WhatsAppMessage = envelope.messages[0]
        text_body = ""
        if isinstance(message.text, dict):
            text_body = str(message.text.get("body") or "")

        normalized = {
            "from": message.from_ or message.from_name or "",
            "message": text_body,
            "metadata": raw_payload,
            "realtor_id": raw_payload.get("realtor_id"),
            "channel_id": envelope.channel_id,
            "chat_id": message.chat_id,
            "session_id": raw_payload.get("session_id"),
            "telephone": message.from_ or raw_payload.get("telephone"),
            "name": message.from_name or raw_payload.get("name"),
        }

        try:
            return WebhookPayload.model_validate(normalized)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={"error": "invalid_payload", "issues": exc.errors()},
            ) from exc


def _build_official_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Reconstruye official_data usando la información disponible en el estado."""

    normalized = state.get("normalized") or {}
    realtor = (
        normalized.get("realtor")
        or state.get("realtor")
        or {}
    )
    prospect = state.get("prospect") or {}

    telephone = (
        normalized.get("telephone")
        or state.get("telephone")
        or prospect.get("telephone")
    )

    prospect_summary = {
        "id": normalized.get("prospect_id") or prospect.get("id"),
        "stage": normalized.get("stage") or prospect.get("stage"),
        "automatization": normalized.get("automatization"),
        "vendor_id": normalized.get("vendor_id") or prospect.get("vendor_id"),
        "name": normalized.get("name") or prospect.get("name"),
        "telephone": telephone,
        "observations": normalized.get("observations") or prospect.get("observations"),
        "calification_variables": normalized.get("calification_variables")
        or prospect.get("calification_variables")
        or {},
        "mentioned_properties": normalized.get("mentioned_properties") or [],
        "properties_interested": normalized.get("properties_interested", []),
        "scheduled_at": normalized.get("scheduled_at") or prospect.get("scheduled_at"),
        "created_at": normalized.get("created_at") or prospect.get("created_at"),
        "updated_at": normalized.get("updated_at") or prospect.get("updated_at"),
        "source": normalized.get("source") or prospect.get("source"),
    }

    return {
        "session_id": normalized.get("session_id") or state.get("session_id"),
        "realtor_id": normalized.get("realtor_id") or state.get("realtor_id"),
        "realtor": realtor,
        "realtor_bot": normalized.get("realtor_bot"),
        "realtor_followups": {
            "prospects": realtor.get("followups_prospects"),
            "brokers": realtor.get("followups_brokers"),
        },
        "token_whapi": realtor.get("token_whapi"),
        "realtor_location": realtor.get("location"),
        "realtor_description": realtor.get("description"),
        "prospect_id": normalized.get("prospect_id") or prospect.get("id"),
        "telephone": telephone,
        "name": normalized.get("name") or state.get("name"),
        "channel_id": normalized.get("channel_id") or state.get("channel_id"),
        "chat_id": normalized.get("chat_id") or state.get("chat_id"),
        "message": normalized.get("message") or state.get("message"),
        "followup_configuration": normalized.get("followup_configuration") or [],
        "notifications_brokers_configurations": normalized.get(
            "notifications_brokers_configurations"
        )
        or {},
        "id_vector_project": normalized.get("id_vector_project"),
        "properties_interested": normalized.get("properties_interested", []),
        "mentioned_properties": normalized.get("mentioned_properties", []),
        "stage": normalized.get("stage"),
        "prospect": prospect_summary,
        "raw_prospect": prospect if isinstance(prospect, dict) else None,
    }
