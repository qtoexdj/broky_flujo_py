from fastapi.testclient import TestClient

from app.main import app


def test_webhook_whatsapp_envelope(monkeypatch):
    from app.api.routes import webhook as webhook_module

    def fake_workflow_run(*, payload):
        return {
            "payload": payload,
            "normalized": {
                "message": payload["message"],
                "session_id": payload.get("session_id"),
                "realtor_id": payload.get("realtor_id"),
            },
            "automation_allowed": True,
        }

    def fake_master_run(state):
        from broky.runtime.master import MasterAgentOutput

        return MasterAgentOutput(
            reply="Recibimos tu mensaje.",
            intents=["busqueda_informacion"],
            filters={},
            handoff=False,
            metadata={},
        )

    monkeypatch.setattr(webhook_module._workflow_service, "run", fake_workflow_run)
    monkeypatch.setattr(webhook_module._master_runtime, "run", fake_master_run)
    monkeypatch.setattr(webhook_module._whapi_delivery, "send_user_reply", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(webhook_module._whapi_delivery, "send_notification", lambda **kwargs: {"ok": True})

    client = TestClient(app)

    payload = {
        "messages": [
            {
                "id": "abc",
                "from": "56999999999",
                "from_name": "Matías",
                "chat_id": "56999999999@s.whatsapp.net",
                "text": {"body": "Hola"},
            }
        ],
        "event": {"type": "messages", "event": "post"},
        "channel_id": "ANTMAN-5PA5C",
    }

    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["reply"] == "Recibimos tu mensaje."
