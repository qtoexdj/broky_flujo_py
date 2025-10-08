from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class WhapiClient:
    """Pequeño cliente HTTP para interactuar con la API de Whapi."""

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def send_text(self, *, token: str, to: str, body: str) -> Dict[str, Any]:
        return self._post(
            token=token,
            endpoint="/messages/text",
            payload={"to": to, "body": body},
        )

    def send_media(
        self,
        *,
        token: str,
        to: str,
        media_url: str,
        media_type: str = "image",
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"to": to, "media": media_url}
        if caption:
            payload["caption"] = caption
        return self._post(
            token=token,
            endpoint=f"/messages/{media_type}",
            payload=payload,
        )

    def _post(self, *, token: str, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self._base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=self._timeout)
            response.raise_for_status()
            return {"ok": True, "status": response.status_code, "data": response.json()}
        except httpx.HTTPStatusError as exc:  # pragma: no cover - logging only
            logger.warning(
                "Whapi devolvió estado %s | url=%s | payload=%s | body=%s",
                exc.response.status_code,
                url,
                payload,
                exc.response.text,
            )
            return {"ok": False, "status": exc.response.status_code, "error": exc.response.text}
        except Exception:  # pragma: no cover - logging only
            logger.exception("Error enviando petición a Whapi | url=%s | payload=%s", url, payload)
            return {"ok": False, "status": None, "error": "exception"}


class WhapiDeliveryService:
    """Coordina el envío de mensajes al usuario final y notificaciones internas."""

    def __init__(self, client: WhapiClient) -> None:
        self._client = client

    def send_user_reply(
        self,
        *,
        reply: str,
        official_data: Dict[str, Any],
        messages: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        message_batch: List[str] = []
        if messages:
            message_batch = [text.strip() for text in messages if isinstance(text, str) and text.strip()]
        if not message_batch:
            if not reply or not reply.strip():
                return {"ok": False, "reason": "empty_reply"}
            message_batch = [reply.strip()]

        realtor = official_data.get("realtor") or {}
        token = (
            realtor.get("token_whapi")
            or official_data.get("token_whapi")
            or official_data.get("realtor_token")
        )
        if not token:
            logger.info(
                "Realtor sin token Whapi; no se envía respuesta automática | data=%s",
                official_data,
            )
            return {"ok": False, "reason": "missing_token"}

        prospect = official_data.get("prospect") or {}
        to = prospect.get("telephone") or official_data.get("telephone")
        if not to:
            logger.info("Sin teléfono del prospecto; no se envía respuesta")
            return {"ok": False, "reason": "missing_telephone"}
        destination = self._format_destination(to)
        deliveries: List[Dict[str, Any]] = []
        overall_ok = True
        for message in message_batch:
            response = self._client.send_text(token=token, to=destination, body=message)
            deliveries.append(response)
            if not response.get("ok"):
                overall_ok = False
        return {"ok": overall_ok, "deliveries": deliveries}

    def send_notification(self, *, notification: Dict[str, Any], official_data: Dict[str, Any]) -> Dict[str, Any]:
        realtor = official_data.get("realtor") or {}
        token = (
            realtor.get("token_whapi")
            or official_data.get("token_whapi")
            or official_data.get("realtor_token")
        )
        if not token:
            return {"ok": False, "reason": "missing_token"}

        to = notification.get("telephone") or notification.get("vendor", {}).get("telephone")
        if not to:
            return {"ok": False, "reason": "missing_destination"}

        body = notification.get("message")
        if not body:
            body = self._build_notification_message(notification, official_data)

        return self._client.send_text(token=token, to=self._format_destination(to), body=body)

    @staticmethod
    def _build_notification_message(notification: Dict[str, Any], official_data: Dict[str, Any]) -> str:
        prospect = official_data.get("prospect") or {}
        template = (
            "Hola {name},\n\n"
            "El prospecto {prospect_name} (tel: +{prospect_phone}) solicitó contacto humano.\n"
            "Último mensaje: \"{message}\""
        )
        return template.format(
            name=notification.get("vendor", {}).get("name", "equipo"),
            prospect_name=prospect.get("name") or official_data.get("name") or "prospecto",
            prospect_phone=prospect.get("telephone") or official_data.get("telephone") or "",
            message=official_data.get("message") or "",
        )

    @staticmethod
    def _format_destination(raw: Any) -> str:
        number = str(raw).strip()
        if not number:
            return number
        if number.endswith("@s.whatsapp.net"):
            return number
        if number.startswith("+"):
            number = number[1:]
        number = number.replace(" ", "")
        return number


__all__ = ["WhapiClient", "WhapiDeliveryService"]
