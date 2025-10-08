from fastapi.testclient import TestClient

from app.main import app


def test_webhook_status_event(monkeypatch):
    from app.api.routes import webhook as webhook_module

    # ensure runtime not invoked
    monkeypatch.setattr(webhook_module, "_workflow_service", None)

    client = TestClient(app)
    payload = {
        "statuses": [
            {
                "id": "abc",
                "status": "delivered",
                "recipient_id": "56999999999@s.whatsapp.net",
            }
        ],
        "event": {"type": "statuses", "event": "post"},
        "channel_id": "ANTMAN-5PA5C",
    }

    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json()["user_id"] == "56999999999@s.whatsapp.net"
    assert response.json()["reply"] == ""
