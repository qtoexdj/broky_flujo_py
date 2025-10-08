from typing import Dict

from broky.processes.assignment import assign_broker_if_needed
from broky.processes.notifications import build_notifications
from app.services.whapi_client import WhapiDeliveryService


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
        def send_text(self, *, token, to, body):
            recorded["token"] = token
            recorded["to"] = to
            recorded["body"] = body
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
    }


def test_whapi_delivery_send_user_reply_batch(monkeypatch):
    calls: list[Dict[str, str]] = []

    class _DummyClient:
        def send_text(self, *, token, to, body):
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
