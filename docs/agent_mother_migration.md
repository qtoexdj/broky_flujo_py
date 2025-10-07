# Migración del Agente Madre (n8n → FastAPI)

## Contexto actual
- **Entrada webhook**: FastAPI recibe el payload y ejecuta `app/workflows/inbound.py` para normalizar datos, buscar/crear prospectos y consolidar "datos oficiales" básicos (mensaje, session_id, realtor, banderas de automatización).
- **Agente Madre** (`broky/runtime/master.py`):
  - Carga el prompt desde `docs/master_agent_prompt.md` (configurable vía `MASTER_AGENT_PROMPT_PATH`).
  - Orquesta el flujo LangChain (`broky/agents/master.py`) y delega a los subagentes según los filtros emitidos.
  - Persiste mensaje/respuesta en Supabase mediante `ChatHistoryRepository` y adjunta metadata de subagentes.
- **Memoria**: `chat_history_repository.py` encapsula lectura/escritura en la tabla documentada en `docs/chats_history_n8n_table.md`.
- **Subagentes**: RAG, interés de proyectos, calificación, agenda, archivos, follow-ups y handoff se ejecutan desde LangChain (ver `broky/agents/` y `broky/processes/`). Falta validación end-to-end con Supabase/productivo.

## Objetivo de migración
Replicar el flujo agentic de n8n (`examples/payloads/Agentic-Pdch.json`) dentro del servicio FastAPI, manteniendo:
- Persistencia de memoria y trazabilidad por `session_id`.
- Clasificación de intenciones y ruteo a subagentes.
- Limpieza/validación de salidas para evitar respuestas inválidas.

## Estado del port actual vs. flujo n8n
| Bloque n8n                                   | Situación en código |
| ------------------------------------------- | ------------------- |
| Normalización (`variables_primeras`)        | **Completado** (`normalize_payload` replica followups, configuraciones y `id_vector_project`; `fetch_realtor` añade `bot_name`, `bot_personality`, `bot_tone`). |
| Búsqueda/creación de prospecto              | **Completado** (`lookup_prospect`, `create_prospect`, `hydrate_prospect`). |
| Consolidación de "datos oficiales"         | **Completado** (`consolidate_official_data` deja el sobre listo para agentes). |
| Cheques de automatización/opt-out           | Parcial: se detecta mensaje "0" y `automatization`; pendiente replicar escenarios especiales (bloqueos manuales, opt-outs personalizados). |
| Lectura de memoria (Postgres Chat Memory)   | **Completado** (`ChatHistoryRepository` gestiona `chats_history_n8n`). |
| Agente Madre (prompt + LLM)                 | **Completado**: carga prompt externo, invoca OpenAI (`response_format=json_object`), valida la estructura y cae a heurística en fallback. |
| Structured Output Parser                    | **Completado**: la validación ocurre en `_validate_output`, con limpieza (`delete_last`) si la estructura falla. |
| Chat Memory Manager (reset/clean)           | Parcial: persiste respuestas y elimina el último registro cuando hay errores; resta añadir límites/TTL y políticas de reset extendidas. |
| Filtros y subagentes (RAG, Calificación...) | **Completado** en código: `MasterAgentRuntime` invoca los subagentes LangChain (RAG, interés, calificación, agenda, archivos) y procesos de follow-up/handoff. Falta validación con Supabase y vector service en entornos reales. |
| Armado de respuesta final                   | Parcial: se concatenan aportes de subagentes; requiere pruebas integrales para garantizar orden y deduplicación en producción. |
| Observabilidad / manejo de errores globales | Parcial: logs clave presentes, faltan métricas y rutas de error equivalentes al workflow original. |

### Validaciones recientes
- `filter_rag` consulta el microservicio en `http://localhost:8001/vectors/search`, aplica timeout/retry y cae a `RAG_FAILURE_REPLY` si falla.
- Se probaron payloads de Quilmes (`realtor_id=de21b61b-d9b5-437a-9785-5252e680b03c`) y Parcelas Chile (`realtor_id=05e67a9f-4d46-4dfc-bc2f-51178c21d5e4`) observando respuestas contextualizadas y persistencia de `sources`, `usage`, `status` y `mentioned_properties` en `chats_history_n8n`.
- `filter_intention` vincula proyectos mencionados en la sesión (`ProjectInterestAgentExecutor` + Supabase) y guarda la salida en memoria (`subagents.filter_intention`).
- `tests/test_webhook_quilmes.py` stubbea Supabase/LLM para el realtor de Quilmes y verifica que el endpoint responda correctamente. Útil como plantilla para futuras pruebas E2E.

## Próximos pasos (orden sugerido)
1. **Cerrar normalización/datos oficiales**
   - Mapear todos los campos generados por el nodo `variables_primeras` en `normalized`.
   - Incorporar atributos del realtor relevantes para el prompt (nombre del bot, tono, personalidad).
   - Adjuntar proyectos/intereses y `mentioned_properties` en el objeto consolidado.

2. **Actualizar Agente Madre a LLM real** ✅
   - Prompt cargado desde `docs/master_agent_prompt.md` y consumo de OpenAI (con `response_format=json_object`).
   - Validación estructurada + fallback heurístico + limpieza de memoria implementados.
   - Respuesta y metadata persistidas en `chats_history_n8n`.

2.1 **Migración a LangChain (en progreso)** ✅
   - Se creó el paquete `broky/` con capas para `agents`, `tools`, `memory`, `config` y `core`.
   - `MasterAgentExecutor` ya usa `ChatOpenAI` vía LangChain, mantiene fallback heurístico y produce filtros/intents en formato JSON.
   - `broky/runtime/master.py` expone `MasterAgentRuntime` para ejecutar el agente desde el pipeline inbound con snapshots de memoria Supabase.
   - Se documentó la arquitectura híbrida en `docs/migration/architecture.md` y el mapeo inicial de nodos.
   - El runtime LangChain quedó habilitado por defecto en FastAPI (ya no existe bandera de activación).
   - Nuevos subagentes LangChain: `RAGAgentExecutor` y `ProjectInterestAgentExecutor` se invocan automáticamente desde `MasterAgentRuntime` según los filtros (`filter_rag`, `filter_intention`).
   - Nuevos subagentes y procesos LangChain: `RAGAgentExecutor`, `ProjectInterestAgentExecutor`, `CalificationAgentExecutor`, `ScheduleAgentExecutor`, `FilesAgentExecutor`, los procesos de follow-up (`broky/processes/followups.py`) y handoff (`broky/processes/handoff.py`) se invocan automáticamente desde `MasterAgentRuntime` según los filtros (`filter_rag`, `filter_intention`, `filter_calification`, `filter_schedule`, `filter_files`, `filter_contact`, `filter_desinteres`).
   - Los prompts vigentes se encuentran en `docs/master_agent_prompt.md` (Agente Madre), `docs/prompts/rag_subagent_prompt.md` (RAG), `docs/prompts/calification_subagent_prompt.md` (calificación), `docs/prompts/schedule_subagent_prompt.md` (agenda) y `docs/prompts/files_subagent_prompt.md` (envío de archivos).

3. **Fortalecer gestión de memoria**
   - Añadir límites de historial/TTL y posibilidad de reset parcial cuando se detecten inconsistencias.
   - Documentar y aplicar políticas RLS/sanitización en Supabase.

4. **Validar subagentes con datos reales**
   - Ejecutar pruebas end-to-end con Supabase y el microservicio vectorial para confirmar que calificación, agenda, archivos y follow-ups actualizan tablas y métricas correctamente.
   - Documentar contratos de entrada/salida por subagente y definir casos negativos (timeouts, datos incompletos, stage bloqueada).

5. **Respuesta final y observabilidad**
   - Combinar outputs de subagentes con la respuesta del agente madre asegurando orden, deduplicación y tono consistente.
   - Añadir métricas/logs equivalentes a los nodos de n8n (stats, rutas de error, alertas) y alarmas por fallos de herramientas.

6. **Cobertura de pruebas**
   - Extender la suite de `pytest` para cubrir escenarios felices y fallidos del runtime LangChain (mocks de Supabase/servicio vectorial).
   - Incluir la ejecución de la suite en CI/CD y documentar cómo preparar entornos locales de pruebas.

---
- El prompt del agente madre vive en `docs/master_agent_prompt.md` y puede editarse sin tocar código.
- Esta guía debe actualizarse conforme se completen los bloques para mantener alineada la migración.
