import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import AuthenticatedUser, get_current_user
from app.core.config import get_settings
from app.models.chat import ChatHistoryMessage, ChatRequest, ChatResponse, ChatSource
from app.experimental.rag.service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

_settings = get_settings()
_rag_service = RAGService(_settings)


def _dump_history(messages: List[ChatHistoryMessage] | None) -> List[Dict[str, Any]]:
    if not messages:
        return []
    return [message.model_dump() for message in messages]


@router.post("/ask", response_model=ChatResponse)
def ask_chat(
    payload: ChatRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ChatResponse:
    logger.info(
        "Solicitud de chat RAG | user_id=%s | realtor_id=%s",
        current_user.user_id,
        current_user.realtor_id,
    )

    try:
        rag_result = _rag_service.answer_query(
            message=payload.message,
            realtor_id=current_user.realtor_id,
            history=_dump_history(payload.history),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive failure path
        logger.exception("Error procesando la consulta RAG")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No pudimos generar una respuesta en este momento",
        ) from exc

    sources = [ChatSource(**source) for source in rag_result.get("sources", [])]

    return ChatResponse(
        response=rag_result["response"],
        sources=sources,
        sources_count=rag_result.get("sources_count", len(sources)),
        timestamp=rag_result["timestamp"],
    )
