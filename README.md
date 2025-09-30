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

- `app/api/routes/webhook.py`: expone `/webhook`, ejecuta el pipeline inbound y delega la respuesta en `MasterAgent`.
- `app/workflows/inbound.py`: implementación del flujo descrito en `docs/flujo.md`.
- `app/workflows/service.py`: cachea el grafo de LangGraph y ofrece un fallback limitado cuando Supabase no está disponible.
- `app/agents/master.py`: agente maestro temporal que emitirá la respuesta mientras se implementan los agentes especializados.

## Zona experimental

El código de ejemplo para el chatbot conversacional y el stack RAG se movió a `app/experimental/`. No se monta en la API por defecto; sirve únicamente como referencia tecnológica.

## Próximos pasos sugeridos

- Conectar el webhook real de WhatsApp (Meta Cloud API) y adaptar el payload.
- Implementar el agente maestro definitivo usando las instrucciones definidas en `docs/`.
- Añadir pruebas automatizadas para el flujo inbound y los repositorios de Supabase.
- Incorporar almacenamiento persistente de historiales si se reactiva el chatbot conversacional.
