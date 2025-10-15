from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import base64

import httpx
from httpx import Response, TimeoutException
import json
import time

logger = logging.getLogger(__name__)


class WhapiClient:
    """Pequeño cliente HTTP para interactuar con la API de Whapi."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 5.0,
        *,
        connect_timeout: Optional[float] = None,
        max_retries: int = 2,
        backoff_factor: float = 0.4,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        default_timeout = timeout if connect_timeout is None else httpx.Timeout(timeout, connect=connect_timeout)
        self._client = httpx.Client(base_url=self._base_url, timeout=default_timeout)
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor

    def close(self) -> None:
        self._client.close()

    def send_text(
        self,
        *,
        token: str,
        to: str,
        body: str,
        typing_time: Optional[int] = None,
        link_preview: Optional[bool] = None,
        ephemeral: Optional[int] = None,
        quoted: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"to": to, "body": body}
        if typing_time is not None:
            payload["typing_time"] = typing_time
        if link_preview is not None:
            payload["link_preview"] = link_preview
        if ephemeral is not None:
            payload["ephemeral"] = ephemeral
        if quoted:
            payload["quoted"] = quoted
        return self._post(token=token, endpoint="/messages/text", payload=payload)

    def send_media(
        self,
        *,
        token: str,
        to: str,
        media_url: str,
        media_type: str = "image",
        caption: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"to": to, "media": media_url}
        if isinstance(caption, str) and caption.strip():
            payload["caption"] = caption
        if isinstance(filename, str) and filename.strip():
            payload["filename"] = filename
        return self._post(
            token=token,
            endpoint=f"/messages/{media_type}",
            payload=payload,
        )

    def set_typing(
        self,
        *,
        token: str,
        chat_id: str,
        presence: str = "typing",
        delay: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"presence": presence}
        if delay is not None:
            payload["delay"] = delay
        return self._put(token=token, endpoint=f"/presences/{chat_id}", payload=payload)

    def _post(self, *, token: str, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request(method="POST", token=token, endpoint=endpoint, payload=payload)

    def _put(self, *, token: str, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request(method="PUT", token=token, endpoint=endpoint, payload=payload)

    def _request(
        self,
        *,
        method: str,
        token: str,
        endpoint: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        url = endpoint
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        attempt = 0
        last_exception: Optional[Exception] = None
        while attempt <= self._max_retries:
            try:
                response = self._client.request(method, url, json=payload, headers=headers)
                response.raise_for_status()
                return {"ok": True, "status": response.status_code, "data": self._safe_json(response)}
            except (httpx.HTTPStatusError, TimeoutException) as exc:  # pragma: no cover - logging only
                last_exception = exc
                status = getattr(exc, "response", None).status_code if hasattr(exc, "response") else None
                body = getattr(exc, "response", None).text if hasattr(exc, "response") else str(exc)
                logger.warning(
                    "Whapi error | method=%s | status=%s | endpoint=%s | payload=%s | body=%s | attempt=%s",
                    method,
                    status,
                    url,
                    payload,
                    body,
                    attempt + 1,
                )
                if status and status >= 500 or isinstance(exc, TimeoutException):
                    if attempt < self._max_retries:
                        time.sleep(self._backoff_factor * (2 ** attempt))
                        attempt += 1
                        continue
                return {"ok": False, "status": status, "error": body}
            except Exception as exc:  # pragma: no cover - logging only
                last_exception = exc
                logger.exception(
                    "Error enviando petición a Whapi | method=%s | endpoint=%s | payload=%s",
                    method,
                    url,
                    payload,
                )
                if attempt < self._max_retries:
                    time.sleep(self._backoff_factor * (2 ** attempt))
                    attempt += 1
                    continue
                return {"ok": False, "status": None, "error": str(exc)}
        # si se agotan reintentos y last_exception se mantiene
        if last_exception:
            return {"ok": False, "status": None, "error": str(last_exception)}
        return {"ok": False, "status": None, "error": "unknown"}

    @staticmethod
    def _safe_json(response: Response) -> Any:
        try:
            return response.json()
        except json.JSONDecodeError:
            return {"raw": response.text}


class WhapiDeliveryService:
    """Coordina el envío de mensajes al usuario final y notificaciones internas."""

    def __init__(self, client: WhapiClient, media_proxy_base: Optional[str] = None) -> None:
        self._client = client
        self._media_proxy_base = media_proxy_base.rstrip("/") if media_proxy_base else None

    def send_user_reply(
        self,
        *,
        reply: str,
        official_data: Dict[str, Any],
        messages: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        typing_time: int | None = 4,
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
        delay_ms: Optional[int]
        if typing_time is not None and typing_time > 0:
            delay_ms = typing_time * 1000
        else:
            delay_ms = None
        for message in message_batch:
            set_typing = getattr(self._client, "set_typing", None)
            if callable(set_typing):
                try:
                    set_typing(token=token, chat_id=destination, delay=delay_ms)
                except Exception:  # pragma: no cover - logging only
                    logger.warning("Fallo al enviar presencia typing", exc_info=True)
            response = self._client.send_text(
                token=token,
                to=destination,
                body=message,
                typing_time=typing_time,
            )
            deliveries.append(response)
            if not response.get("ok"):
                overall_ok = False

        if attachments:
            attachment_deliveries = self._send_attachments(
                token=token,
                to=destination,
                attachments=attachments,
                prospect_name=prospect.get("name") or official_data.get("name"),
            )
            deliveries.extend(attachment_deliveries)
            if not all(entry.get("ok") for entry in attachment_deliveries):
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

    def _send_attachments(
        self,
        *,
        token: str,
        to: str,
        attachments: List[Dict[str, Any]],
        prospect_name: Optional[str],
    ) -> List[Dict[str, Any]]:
        deliveries: List[Dict[str, Any]] = []
        seen_urls: set[str] = set()
        for entry in attachments:
            if not isinstance(entry, dict):
                continue
            url = entry.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            media_url = self._proxy_url(url)
            media_type = self._map_media_type(entry.get("type"))
            caption = None
            filename = None

            response = self._client.send_media(
                token=token,
                to=to,
                media_url=media_url,
                media_type=media_type,
                caption=caption,
                filename=filename,
            )
            deliveries.append(response)
        return deliveries

    def _proxy_url(self, url: Optional[str]) -> Optional[str]:
        if not url or not self._media_proxy_base:
            return url
        if url.startswith(self._media_proxy_base):
            return url
        token = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")
        return f"{self._media_proxy_base}/media/{token}"

    @staticmethod
    def _map_media_type(file_type: Optional[str]) -> str:
        normalized = (file_type or "").lower()
        mapping = {
            "image": "image",
            "photo": "image",
            "gif": "gif",
            "video": "video",
            "short-video": "short-video",
            "ptv": "short-video",
            "audio": "audio",
            "voice": "voice",
            "document": "document",
            "pdf": "document",
            "sticker": "sticker",
        }
        if normalized in mapping:
            return mapping[normalized]
        if normalized == "kmz":
            return "document"
        return "document"


__all__ = ["WhapiClient", "WhapiDeliveryService"]
