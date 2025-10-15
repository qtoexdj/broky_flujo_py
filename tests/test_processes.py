from typing import Any, Dict

from broky.processes.assignment import assign_broker_if_needed
from broky.processes.notifications import build_notifications
from app.services.whapi_client import WhapiDeliveryService, WhapiClient


class _FakeProfileRepo:
    def __init__(self, brokers):
        self._brokers = brokers

    def list_active_brokers(self, realtor_id: str):
        return list(self._brokers)


class _FakeProspectRepo:
    def __init__(self):
        self.calls = []

    def assign_vendor(self, prospect_id, vendor_id):
        self.calls.append((prospect_id, vendor_id))
        return {"id": prospect_id, "vendor_id": vendor_id}


def test_assign_broker_if_needed_assigns_first_available():
    profile_repo = _FakeProfileRepo(
        [
            {"id": "broker-2", "name": "Beta Broker", "email": "beta@example.com"},
            {"id": "broker-1", "name": "Alpha Broker", "email": "alpha@example.com"},
        ]
    )
    prospect_repo = _FakeProspectRepo()
    official_data = {
        "realtor_id": "realtor-123",
        "prospect": {"id": "prospect-1", "vendor_id": None},
    }

    result = assign_broker_if_needed(
        profile_repo,
        prospect_repo,
        official_data=official_data,
    )

    assert result["performed"] is True
    assert result["vendor"]["id"] == "broker-2"
    assert prospect_repo.calls == [("prospect-1", "broker-2")]


def test_build_notifications_handles_handoff():
    official_data = {
        "realtor_id": "realtor-123",
        "message": "Necesito hablar con alguien",
        "prospect": {"id": "prospect-1", "name": "Jane", "telephone": "123"},
        "realtor": {"name": "Realtor Test"},
        "notifications_brokers_configurations": {"channel": "whatsapp"},
    }

    notifications = build_notifications(
        official_data=official_data,
        handoff_reason="contacto_humano",
        filters={"filter_contact": True},
        broker_assignment={"vendor": {"id": "broker-99"}},
    )

    assert len(notifications) == 1
    notif = notifications[0]
    assert notif["type"] == "broker_handoff"
    assert notif["channel"] == "whatsapp"
    assert notif["vendor"]["id"] == "broker-99"


def test_whapi_delivery_send_user_reply(monkeypatch):
    recorded = {}

    class _DummyClient:
        def send_text(self, *, token, to, body, **kwargs):
            recorded["token"] = token
            recorded["to"] = to
            recorded["body"] = body
            recorded["extra"] = kwargs
            return {"ok": True}

    delivery = WhapiDeliveryService(_DummyClient())
    result = delivery.send_user_reply(
        reply="Hola",
        official_data={
            "realtor": {"token_whapi": "secret-token"},
            "prospect": {"telephone": "56912345678"},
            "message": "Hola",
        },
    )

    assert result["ok"] is True
    assert recorded == {
        "token": "secret-token",
        "to": "56912345678",
        "body": "Hola",
        "extra": {"typing_time": 4},
    }


def test_whapi_delivery_send_user_reply_batch(monkeypatch):
    calls: list[Dict[str, str]] = []

    class _DummyClient:
        def send_text(self, *, token, to, body, **kwargs):
            calls.append({"token": token, "to": to, "body": body})
            return {"ok": True}

    delivery = WhapiDeliveryService(_DummyClient())
    result = delivery.send_user_reply(
        reply="",
        official_data={
            "realtor": {"token_whapi": "secret-token"},
            "prospect": {"telephone": "56900000000"},
        },
        messages=["Primer mensaje", "Segundo mensaje"],
    )

    assert result["ok"] is True
    assert len(result["deliveries"]) == 2
    assert [call["body"] for call in calls] == ["Primer mensaje", "Segundo mensaje"]


def test_whapi_delivery_send_user_reply_attachments(monkeypatch):
    sent_text: list[Dict[str, Any]] = []
    sent_media: list[Dict[str, Any]] = []

    class _DummyClient:
        def send_text(self, *, token, to, body, **kwargs):
            sent_text.append({"token": token, "to": to, "body": body, "extra": kwargs})
            return {"ok": True}

        def send_media(self, *, token, to, media_url, media_type="image", caption=None, filename=None):
            sent_media.append(
                {
                    "token": token,
                    "to": to,
                    "media_url": media_url,
                    "media_type": media_type,
                    "caption": caption,
                    "filename": filename,
                }
            )
            return {"ok": True}

    delivery = WhapiDeliveryService(_DummyClient())
    result = delivery.send_user_reply(
        reply="Te envío las fotos solicitadas.",
        official_data={
            "realtor": {"token_whapi": "secret-token"},
            "prospect": {"telephone": "56912345678", "name": "Matías"},
        },
        attachments=[
            {"url": "https://example.com/foto1.jpg", "type": "image", "name": "Imagen 1", "project": "Proyecto X"},
            {"url": "https://example.com/foto2.jpg", "type": "kmz", "name": "Plano", "project": "Proyecto X"},
        ],
    )

    assert result["ok"] is True
    assert len(sent_text) == 1
    assert len(sent_media) == 2
    assert sent_media[0]["media_type"] == "image"
    assert sent_media[0]["filename"] is None
    assert sent_media[0]["media_url"] == "https://example.com/foto1.jpg"
    assert sent_media[1]["media_type"] == "document"
    assert sent_media[1]["filename"] is None
    assert sent_media[1]["media_url"] == "https://example.com/foto2.jpg"


def test_whapi_client_send_text_options():
    recorded: Dict[str, Any] = {}

    class _DummyClient:
        def request(self, method, url, json, headers):
            recorded["method"] = method
            recorded["url"] = url
            recorded["payload"] = json
            recorded["headers"] = headers

            class _DummyResponse:
                status_code = 200

                @staticmethod
                def raise_for_status():
                    return None

                @staticmethod
                def json():
                    return {"message_id": "abc"}

            return _DummyResponse()

        def close(self):
            pass

    client = WhapiClient.__new__(WhapiClient)  # type: ignore
    client._base_url = "https://example.com"  # type: ignore[attr-defined]
    client._client = _DummyClient()  # type: ignore[attr-defined]
    client._max_retries = 0  # type: ignore[attr-defined]
    client._backoff_factor = 0.0  # type: ignore[attr-defined]

    client.send_text(
        token="token",
        to="56912345678",
        body="Hola",
        typing_time=3,
        link_preview=False,
        ephemeral=60,
        quoted="msg-123",
    )

    assert recorded["payload"]["typing_time"] == 3
    assert recorded["payload"]["link_preview"] is False
    assert recorded["payload"]["ephemeral"] == 60
    assert recorded["payload"]["quoted"] == "msg-123"


def test_whapi_media_type_mapping():
    assert WhapiDeliveryService._map_media_type("image") == "image"
    assert WhapiDeliveryService._map_media_type("voice") == "voice"
    assert WhapiDeliveryService._map_media_type("kmz") == "document"
    assert WhapiDeliveryService._map_media_type("gif") == "gif"
    assert WhapiDeliveryService._map_media_type(None) == "document"
