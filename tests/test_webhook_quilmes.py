from fastapi.testclient import TestClient

from app.main import app
from broky.runtime.master import MasterAgentOutput


def test_webhook_properties_quilmes(monkeypatch):
    from app.api.routes import webhook as webhook_module

    def fake_workflow_run(*, payload):
        return {
            "payload": payload,
            "normalized": {
                "message": payload["message"],
                "session_id": "session-test",
                "realtor_id": payload.get("realtor_id"),
            },
            "automation_allowed": True,
        }

    def fake_master_run(state):
        return MasterAgentOutput(
            reply="Tenemos varias propiedades disponibles en Quilmes. Te enviaré los detalles enseguida.",
            intents=["busqueda_informacion"],
            filters={"filter_rag": True},
            handoff=False,
            metadata={"intents": ["busqueda_informacion"]},
        )

    monkeypatch.setattr(webhook_module._workflow_service, "run", fake_workflow_run)
    monkeypatch.setattr(webhook_module._master_runtime, "run", fake_master_run)

    client = TestClient(app)
    payload = {
        "from": "usuario_test",
        "message": "Hola, ¿qué propiedades tienen en Quilmes?",
        "realtor_id": "de21b61b-d9b5-437a-9785-5252e680b03c",
    }

    response = client.post("/webhook", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == payload["from"]
    assert "Quilmes" in body["reply"]
