from fastapi.testclient import TestClient

from app.main import app
from broky.runtime.master import MasterAgentOutput


def test_webhook_multi_turn_flow(monkeypatch):
    """Simula una conversación completa asegurando que no se pierde contexto."""

    from app.api.routes import webhook as webhook_module

    messages = [
        "Hola, ¿qué proyectos tienen disponibles?",
        "Me interesa el proyecto Aires de Bolleruca.",
        "¿Puedes mandarme más detalles de ese proyecto?",
        "Perfecto, quiero agendar una visita para este sábado.",
    ]

    expected_replies = [
        "Tenemos varias opciones en la zona, te comparto algunas sugerencias iniciales.",
        "Excelente elección, Aires de Bolleruca tiene parcelas amplias y urbanizadas.",
        "Te envío más detalles y documentos del proyecto para que los revises.",
        "Listo, coordinemos la visita para este sábado a las 11:00 hrs.",
    ]

    intents_seq = [
        ["busqueda_informacion"],
        ["anotar_proyecto"],
        ["busqueda_informacion", "pide_fotos_plano_videos"],
        ["fecha_visita"],
    ]

    filters_seq = [
        {"filter_rag": True},
        {"filter_intention": True},
        {"filter_files": True},
        {"filter_schedule": True},
    ]

    stages = ["new-prospect", "conversation", "conversation", "qualified"]

    call_index = {"value": 0}

    def fake_workflow_run(*, payload):
        idx = call_index["value"]
        stage = stages[min(idx, len(stages) - 1)]
        call_index["value"] += 1
        return {
            "payload": payload,
            "normalized": {
                "message": payload["message"],
                "session_id": "session-123",
                "realtor_id": payload.get("realtor_id"),
                "stage": stage,
            },
            "official_data": {
                "stage": stage,
                "realtor": {"name": "Parcelas Test"},
            },
            "automation_allowed": True,
        }

    class FakeRuntime:
        def __init__(self):
            self.calls = []

        def run(self, state):
            idx = len(self.calls)
            self.calls.append(state)
            stage = stages[min(idx, len(stages) - 1)]
            return MasterAgentOutput(
                reply=expected_replies[idx],
                intents=intents_seq[idx],
                filters=filters_seq[idx],
                handoff=False,
                metadata={
                    "intents": intents_seq[idx],
                    "filters": filters_seq[idx],
                    "stage": stage,
                },
            )

    runtime = FakeRuntime()
    sent_replies = []

    monkeypatch.setattr(webhook_module._workflow_service, "run", fake_workflow_run)
    monkeypatch.setattr(webhook_module, "_master_runtime", runtime)
    monkeypatch.setattr(
        webhook_module._whapi_delivery,
        "send_user_reply",
        lambda *, reply, official_data, messages=None: sent_replies.append(
            messages[0] if messages else reply
        )
        or {"ok": True},
    )
    monkeypatch.setattr(
        webhook_module._whapi_delivery,
        "send_notification",
        lambda **_: {"ok": True},
    )

    client = TestClient(app)

    base_payload = {
        "from": "56955151392",
        "realtor_id": "1272b928-a4df-4a7e-8ddc-f7130b06851c",
        "channel_id": "ANTMAN-5PA5C",
        "chat_id": "56955151392@s.whatsapp.net",
    }

    for idx, message in enumerate(messages):
        payload = {**base_payload, "message": message}
        response = client.post("/webhook", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == base_payload["from"]
        assert body["reply"] == expected_replies[idx]

    assert sent_replies == expected_replies
    assert len(runtime.calls) == len(messages)
    assert {state["payload"]["chat_id"] for state in runtime.calls} == {base_payload["chat_id"]}
