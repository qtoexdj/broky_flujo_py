# Migración del Agente Madre (n8n → FastAPI)

## Contexto actual
- **Entrada webhook**: FastAPI recibe el payload y ejecuta `app/workflows/inbound.py` para normalizar datos, buscar/crear prospectos y consolidar "datos oficiales" básicos (mensaje, session_id, realtor, banderas de automatización).
- **Agente Madre** (`app/agents/master.py`):
  - Carga el prompt desde `docs/master_agent_prompt.md` (editable, configurable con `MASTER_AGENT_PROMPT_PATH`).
  - Recupera historial de `chats_history_n8n` mediante `ChatHistoryRepository` y clasifica intenciones con una heurística inicial.
  - Persiste mensaje/respuesta en Supabase y devuelve metadata con filtros (`filter_rag`, `filter_calification`, etc.).
- **Memoria**: `chat_history_repository.py` encapsula lectura/escritura en la tabla documentada en `docs/chats_history_n8n_table.md`.
- **Rutas activas**: el endpoint `/webhook` registra la decisión del agente y responde al usuario. Los subagentes (RAG, calificación, agenda, actualización de proyectos) aún no están integrados.

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
| Cheques de automatización/opt-out           | Parcial: se detecta mensaje "0" y `automatization`, falta replicar otros escenarios especiales del flujo original. |
| Lectura de memoria (Postgres Chat Memory)   | **Completado** (`ChatHistoryRepository` gestiona `chats_history_n8n`). |
| Agente Madre (prompt + LLM)                 | **Completado**: carga prompt externo, invoca OpenAI (`response_format=json_object`), valida la estructura y cae a heurística en fallback. |
| Structured Output Parser                    | **Completado**: la validación ocurre en `_validate_output`, con limpieza (`delete_last`) si la estructura falla. |
| Chat Memory Manager (reset/clean)           | Parcial: persiste respuestas y elimina el último registro cuando hay errores; resta añadir límites/TTL y políticas de reset extendidas. |
| Filtros y subagentes (RAG, Calificación...) | En progreso: `filter_rag` + `filter_intention` integrados (RAG responde con contexto y `ProjectInterestSubAgent` vincula proyectos en Supabase); calificación, agenda, archivos y follow-ups aún pendientes. |
| Armado de respuesta final                   | Parcial: devuelve la respuesta del agente madre y los filtros, falta integrar subagentes y combinar mensajes. |
| Observabilidad / manejo de errores globales | Parcial: logs clave presentes, faltan métricas y rutas de error equivalentes al workflow original. |

### Validaciones recientes
- `filter_rag` consulta el microservicio en `http://localhost:8001/vectors/search`, aplica timeout/retry y cae a `RAG_FAILURE_REPLY` si falla.
- Se probaron los payloads de quilmes (`realtor_id=de21b61b-d9b5-437a-9785-5252e680b03c`) y Parcelas Chile (`realtor_id=05e67a9f-4d46-4dfc-bc2f-51178c21d5e4`), observando respuestas contextualizadas y persistencia de `sources`, `usage`, `status` y `mentioned_properties` en `chats_history_n8n`.
- `filter_intention` vincula proyectos mencionados en la sesión (`ProjectInterestSubAgent` + Supabase) y guarda la salida en memoria (`subagents.filter_intention`).

## Próximos pasos (orden sugerido)
1. **Cerrar normalización/datos oficiales**
   - Mapear todos los campos generados por el nodo `variables_primeras` en `normalized`.
   - Incorporar atributos del realtor relevantes para el prompt (nombre del bot, tono, personalidad).
   - Adjuntar proyectos/intereses y `mentioned_properties` en el objeto consolidado.

2. **Actualizar Agente Madre a LLM real** ✅
   - Prompt cargado desde `docs/master_agent_prompt.md` y consumo de OpenAI (con `response_format=json_object`).
   - Validación estructurada + fallback heurístico + limpieza de memoria implementados.
   - Respuesta y metadata persistidas en `chats_history_n8n`.
 
3. **Fortalecer gestión de memoria**
   - Añadir límites de historial/TTL y posibilidad de reset parcial cuando se detecten inconsistencias.
   - Documentar y aplicar políticas RLS/sanitización en Supabase.

4. **Implementar filtros y subagentes**
   - Completar `filter_calification`, `filter_schedule`, `filter_files` y procesos utilitarios (follow-ups, desinterés, hand-off). `filter_rag` y `filter_intention` ya consultan microservicio + Supabase y escriben resultados en memoria.

5. **Respuesta final y observabilidad**
   - Combinar outputs de subagentes con la respuesta del agente madre.
   - Añadir métricas/logs equivalentes a los nodos de n8n (stats, rutas de error, alertas).

---
- El prompt del agente madre vive en `docs/master_agent_prompt.md` y puede editarse sin tocar código.
- Esta guía debe actualizarse conforme se completen los bloques para mantener alineada la migración.
