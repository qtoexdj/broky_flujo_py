# Broky WhatsApp Bot (base)

Servicio FastAPI que recibe webhooks de WhatsApp, ejecuta el flujo descrito en `docs/flujo.md` y entrega el estado consolidado a un agente maestro (placeholder). Cuando Supabase está configurado, el pipeline normaliza el payload, busca o crea prospectos y determina si se permite continuar la automatización.

## Requisitos

- Python 3.13 (usa el `.venv` ya creado)
- Credenciales de Supabase (`SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY`, o `SUPABASE_ANON_KEY`)
- Variables opcionales de OpenAI (`OPENAI_API_KEY`, etc.) para habilitar el Agente Madre y el subagente RAG

## Configuración inicial

1. Copia `.env.example` a `.env` y reemplaza las claves por tus valores reales.
2. Activa el entorno virtual e instala dependencias:

   ```bash
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

## Ejecutar en local

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

La API queda disponible en `http://127.0.0.1:8000`.

## Probar con curl

Modo reducido (sin Supabase configurado):

```bash
curl --request POST \
  --url http://127.0.0.1:8000/webhook \
  --header 'Content-Type: application/json' \
  --data '{
    "from": "usuario_test",
    "message": "Hola, necesito información"
  }'
```

Flujo completo con Supabase (ejemplo):

```bash
curl --request POST \
  --url http://127.0.0.1:8000/webhook \
  --header 'Content-Type: application/json' \
  --data '{
    "from": "usuario_test",
    "message": "¿Qué proyectos tengo disponibles?",
    "realtor_id": "abc123",
    "telephone": "56999999999"
  }'
```

## Componentes principales

- `app/api/routes/webhook.py`: expone `/webhook`, ejecuta el pipeline inbound y delega la decisión al Agente Madre.
- `app/workflows/inbound.py`: implementación del flujo descrito en `docs/flujo.md` para normalizar prospecto, sesión y flags de automatización.
- `app/workflows/service.py`: cachea el grafo de LangGraph y ofrece un fallback reducido cuando Supabase no está disponible.
- `broky/runtime/master.py`: runtime que lee la memoria en Supabase (`chats_history_n8n`), clasifica intenciones con LangChain y coordina los subagentes.
- `app/services/chat_history_repository.py`: wrapper simple para leer/escribir el historial de conversación en Supabase.
- `docs/master_agent_prompt.md`: prompt editable del Agente Madre (puedes personalizar tono e instrucciones sin tocar el código).
- `docs/chats_history_n8n_table.md`: referencia de la tabla de memoria usada por el orquestador.
- `broky/`: nueva capa híbrida (LangChain) con agentes, herramientas, memoria y runtimes que conectan con LangGraph (incluye subagentes de RAG, proyectos, calificación, agenda y envío de archivos).

El runtime de LangChain está activo por defecto; no se necesita ninguna bandera adicional para habilitarlo.

## Pruebas automatizadas

```bash
source .venv/bin/activate
pytest
```

La suite incluye `tests/test_webhook_quilmes.py`, que stubbea el pipeline para el realtor `de21b61b-d9b5-437a-9785-5252e680b03c` y valida que el bot responda a consultas sobre propiedades en Quilmes. Usa esto como plantilla para agregar escenarios reales con Supabase y el microservicio vectorial activos.

## Próximos pasos sugeridos

- Conectar el webhook real de WhatsApp (Meta Cloud API) y adaptar el payload.
- Ejecutar pruebas end-to-end con Supabase y el servicio vectorial para validar subagentes (calificación, agenda, archivos, follow-ups).
- Extender la suite de `pytest` con mocks/fixtures que cubran rutas negativas y métricas de observabilidad.
