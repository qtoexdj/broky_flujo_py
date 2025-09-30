import logging

from fastapi import APIRouter, HTTPException
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from app.agents.master import MasterAgent
from app.core.config import get_settings
from app.models.webhook import WebhookPayload, WebhookResponse
from app.workflows.service import InboundWorkflowService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

_settings = get_settings()
_workflow_service = InboundWorkflowService(_settings)
_master_agent = MasterAgent(_settings)


@router.post("", response_model=WebhookResponse)
def handle_webhook(payload: WebhookPayload) -> WebhookResponse:
    user_id = payload.from_user
    logger.info("Procesando mensaje de %s", user_id)

    try:
        workflow_state = _workflow_service.run(
            payload=payload.model_dump(by_alias=True)
        )
        decision = _master_agent.handle(workflow_state)
        reply = decision.reply
    except Exception as exc:  # pragma: no cover - defensive failure path
        logger.exception("Error al invocar el modelo: %s", exc)
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocurrió un error al generar la respuesta",
        ) from exc

    return WebhookResponse(reply=reply, user_id=user_id)
