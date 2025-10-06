# Broky WhatsApp Bot (base)

Servicio FastAPI que recibe webhooks de WhatsApp, ejecuta el flujo descrito en `docs/flujo.md` y entrega el estado consolidado a un agente maestro (placeholder). Cuando Supabase está configurado, el pipeline normaliza el payload, busca o crea prospectos y determina si se permite continuar la automatización.

## Requisitos

- Python 3.13 (usa el `.venv` ya creado)
- Credenciales de Supabase (`SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY`, o `SUPABASE_ANON_KEY`)
- Variables opcionales de OpenAI (`OPENAI_API_KEY`, etc.) solo si activas los prototipos de `app/experimental`

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
- `app/agents/master.py`: orquestador que lee la memoria en Supabase (`chats_history_n8n`), clasifica intenciones y devuelve salidas estructuradas para los filtros.
- `app/services/chat_history_repository.py`: wrapper simple para leer/escribir el historial de conversación en Supabase.
- `docs/master_agent_prompt.md`: prompt editable del Agente Madre (puedes personalizar tono e instrucciones sin tocar el código).
- `docs/chats_history_n8n_table.md`: referencia de la tabla de memoria usada por el orquestador.

## Zona experimental

El código de ejemplo para el chatbot conversacional y el stack RAG se movió a `app/experimental/`. No se monta en la API por defecto; sirve únicamente como referencia tecnológica.

## Próximos pasos sugeridos

- Conectar el webhook real de WhatsApp (Meta Cloud API) y adaptar el payload.
- Sustituir la lógica heurística de intenciones por prompts/LLM siguiendo las instrucciones de `docs/`.
- Añadir pruebas automatizadas para el flujo inbound, el repositorio de historial y la clasificación de intenciones.
- Activar y conectar los subagentes (RAG, calificación, actualización de proyectos, agenda) detrás de los filtros.
