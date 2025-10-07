# Plan de Implementación de Subagentes (Agente Madre → Filtros)

> **Versión alineada al flujo `Agentic-Pdch.json` y al microservicio RAG ya operativo**. El objetivo es que cualquier agente (humano o IA) pueda implementar sin interpretar ambigüedades.

## Contexto general

El **Agente Madre** clasifica intenciones a partir del mensaje normalizado que entrega el pipeline inbound (`app/workflows/inbound.py`). Con esas intenciones habilita **compuertas de ruteo** que derivan hasta nueve ramas posteriores:

1. `followup_prospect`
2. `followup_broker`
3. `agente actualizar prospecto`
4. `agente de RAG`
5. `agente de calificación`
6. `agente agendar visita`
7. `agente enviar archivos`
8. `proceso de desinterés`
9. `contacto humano`

Las cuatro primeras compuertas técnicas (`filter_rag`, `filter_intention`, `filter_calification`, `filter_schedule`) se complementan con filtros utilitarios (`filter_files`, `filter_desinteres`, controles de follow-up y hand-off). Toda la conversación se persiste en Supabase (`chats_history_n8n`) y se limpia selectivamente mediante el "Chat Memory Manager" nativo del flujo de n8n.

> **Nota LangChain**: los subagentes se reescribirán como `AgentExecutor` dentro de `broky/agents/` y sus dependencias (Supabase, RAG, HTTP) se expondrán como `broky.tools.*`. LangGraph seguirá activando cada filter, delegando la ejecución real a la nueva capa.

Herramientas ya disponibles en `broky.tools`:
- `broky.tools.realtor_lookup`
- `broky.tools.prospect_lookup`
- `broky.tools.prospect_create`
- `broky.tools.properties_by_prospect`
- `broky.tools.rag_search`
- `broky.tools.project_interest_link`
- `broky.tools.calification_update`
- `broky.tools.schedule_visit`

La ejecución desde LangGraph se gestionará con `MasterAgentRuntime` (`broky/runtime/master.py`), el cual hidrata el contexto, invoca al agente y persiste memoria en Supabase.

Prompts activos:
- `docs/master_agent_prompt.md`
- `docs/prompts/rag_subagent_prompt.md`
- `docs/prompts/calification_subagent_prompt.md`
- `docs/prompts/schedule_subagent_prompt.md`

## Estado de implementación

- **`filter_rag`** — ✅ Completado: subagente integrado en FastAPI; consume el microservicio vectorial con timeout/retry, genera respuesta estructurada y persiste `sources`/`mentioned_properties` y `usage` en `chats_history_n8n`. **Migración LangChain**: `RAGAgentExecutor` (`broky/agents/rag.py`) ejecuta el flujo mediante `broky.tools.rag_search` dentro del runtime activo por defecto.
- **`filter_intention`** — ✅ Completado: `ProjectInterestSubAgent` + `ProjectInterestService` enlazan proyectos mencionados en Supabase (`prospect_project_interests`), aplican idempotencia y registran la respuesta en `chats_history_n8n`. **Migración LangChain**: `ProjectInterestAgentExecutor` (`broky/agents/project_interest.py`) usa la herramienta `broky.tools.project_interest_link` para el runtime híbrido.
- **`filter_calification`** — ✅ Implementado en LangChain (`CalificationAgentExecutor` + `broky.tools.calification_update`). Falta validar con Supabase real, normalizar métricas y cubrir casos negativos (datos incompletos, stage bloqueada).
- **`filter_schedule`** — ✅ Implementado en LangChain (`ScheduleAgentExecutor` + `broky.tools.schedule_visit`). Requiere pruebas end-to-end con Supabase y servicio de agenda, además de reglas de feriados/notificaciones.
- **`filter_files`** — ✅ Implementado en LangChain (`FilesAgentExecutor`, `broky.tools.projects_list`, `broky.tools.project_files`). Pendiente validar múltiples proyectos, performance y métricas de entrega.
- **Procesos utilitarios**
  - `followup_prospect` y `followup_broker` — ✅ Lógica portada en `broky/processes/followups.py`. Falta instrumentación, idempotencia extendida y pruebas de regresión integradas.
  - `filter_desinteres` y hand-off humano — ✅ Implementado en `broky/processes/handoff.py`. Pendiente integrar notificaciones externas y métricas de opt-out.

> Las secciones siguientes describen el diseño funcional original y sirven como checklist de validación. Contrasta cada punto con la implementación actual (`broky/agents`, `broky/tools`, `broky/processes`) y registra los casos cubiertos en pruebas automatizadas.

## 0. Estado actual confirmado

- El Agente Madre usa un LLM (Claude/OpenAI) para detectar intenciones y generar el array de salida; **no ejecuta lógica de negocio**.
- Las compuertas (`filter_*`) ya están calculadas y conectadas en FastAPI. `MasterAgentRuntime` invoca secuencialmente todos los subagentes LangChain (RAG, proyectos, calificación, agenda, archivos) y procesos utilitarios; falta validar su comportamiento con datos reales y tolerancia a errores.
- `chats_history_n8n` está disponible para registrar todo intercambio (Agente Madre y subagentes). No se maneja TTL global, solo borrado puntual de registros conflictivos.
- El microservicio de vectores (`POST /vectors/search`) corre en Docker, listo para consumo externo; no es necesario generar embeddings desde FastAPI.

> **Formato obligatorio de salida del Agente Madre**: array de strings (`["intencion1", "intencion2"]`). Si el LLM devuelve otro formato, se normaliza antes de evaluar filtros.

## 1. Subagente RAG (`filter_rag`)

### Intenciones
- `busqueda_informacion`
- `pide_fotos_plano_videos`

### Referencia n8n
Rama `Setear → RAG → Chat Memory Manager1 → output_rag`, la cual actualiza `mentioned_properties`.

### Fuente de contexto
- **Microservicio de vectores** (`http://localhost:8001/vectors/search`). Entrada: `{"query", "realtor_id", "limit", "threshold"}`. Salida: lista de resultados con `project_id`, `score`, `metadata`, `content`.

### Implementación
1. **Contexto y request**
   - Crear `RAGSubAgent.run(message, official_data, history, settings)`.
   - Invocar `POST /vectors/search` con `query=message`, `realtor_id=official_data.realtor_id`, `limit` y `threshold` por defecto (`5`, `0.7`) parametrizables por env.
2. **Respuesta estructurada**
   - Mapear `results` a `{project_id, score, snippet, metadata}`.
   - Enriquecer `mentioned_properties` y `sources` con la información retornada.
   - Preparar `{reply, sources, usage, mentioned_properties}`. `reply` puede provenir del mismo subagente (prompt específico) o del Agente Madre extendido con contexto.
   - El prompt del subagente se lee desde `docs/prompts/rag_subagent_prompt.md` (configurable con `RAG_PROMPT_PATH`); si falta, usa `RAG_SYSTEM_PROMPT` del entorno.
3. **Persistencia**
   - Registrar en `chats_history_n8n` como mensaje del asistente incluyendo metadata (`project_id`, `score`, `source_uri`).
4. **Fallback y observabilidad**
   - Ante error HTTP o lista vacía: devolver respuesta segura (“Estamos revisando la información…”) y marcar incidente en logs/metrics. No romper la conversación.

### Criterios de éxito
- Multi-tenancy garantizada (todas las consultas usan `realtor_id`).
- Latencia total < **3 segundos** por consulta.
- Respuestas consistentes con la información del microservicio.
- Instrumentación de métricas: latencia, número de fuentes, tasa de errores.

## 2. Subagente de actualización de proyectos (`filter_intention`)

### Intención
- `anotar_proyecto`

### Referencia n8n
Rama `Filter_intention → Setear1 → ACTUALIZAR_PROYECTO` con memoria y parser estructurado.

### Estado
- Implementado en `app/agents/subagents/project_interest.py` (subagente) y `app/services/project_interest_service.py` (servicio Supabase).
- Persistencia validada: los IDs mencionados por RAG se vinculan en `prospect_project_interests`, se evita duplicar registros y se guarda la salida en `chats_history_n8n`.
- Pendientes: habilitar eliminación (`unlink`) y exponer métricas/dashboards de seguimiento.

### Implementación
1. **Servicio base**
   - `ProjectInterestService` consulta `projects` filtrando por `realtor_id`, detecta vínculos existentes e inserta únicamente los faltantes (con lotes idempotentes).
   - Métodos disponibles: `link_projects` (activo) y `unlink_projects` (definido para implementarse cuando se requiera).
2. **Interfaz**
   - `ProjectInterestSubAgent.run(prospect_id, realtor_id, mentioned_projects, action="link")` usa los IDs suministrados (actualmente provenientes de `mentioned_properties`).
   - Respuesta estructurada con `{reply, status, added_projects, skipped, removed}` para escritura en memoria/analytics.
3. **Integración**
   - El Agente Madre invoca el subagente cuando `filter_intention` es `True`, combina la respuesta con el mensaje final y actualiza `normalized/official_data['properties_interested']` sin duplicados.
4. **Validaciones y respuesta**
   - Multi-tenant: solo se vinculan proyectos cuyo `realtor_id` coincide.
   - Mensajes cubren casos `ok`, `noop` (ya existían) y fallbacks si el servicio no está disponible.
   - Persistencia en `chats_history_n8n` incluye `subagents.filter_intention` con los proyectos agregados/skipped.

### Pruebas mínimas
- `link` nuevo → persistencia correcta.
- `unlink` existente → elimina relación. *(pendiente de habilitar en el subagente)*
- Proyecto inexistente → mensaje de error sin romper hilo.
- Idempotencia: repetir `link` no duplica registros (probado en entorno local por duplicación controlada).

## 3. Subagente de calificación (`filter_calification`)

### Intenciones
- `forma_pago`
- `fecha_compra`

### Referencia n8n
Rama `Filter_calification → filtro_etapa → Setear2 → CALIFICAR_USUARIO` combinando MCP + parser + memoria.

### Implementación
1. **Servicio base**
   - Implementar `ProspectQualificationAgent.qualify(prospect_id, message, official_data, history)`.
   - Definir prompt en `docs/subagent_calification_prompt.md` para estructurar datos (monto disponible, tipo de financiamiento, horizonte de compra, etc.).
2. **Reglas de negocio**
   - `filtro_etapa` valida stages permitidos (`conversation`, `qualified`, `new-prospect`). Si no cumple, devolver mensaje guiando al prospecto.
   - Normalizar datos numéricos (montos, cuotas, porcentajes) y fechas en formato ISO antes de guardar.
   - Actualizar `prospects.calification_variables` (JSONB), `prospects.stage`, `prospects.updated_at`.
3. **Respuesta**
   - Retornar `{updates, next_stage, reply, followup_needed}`.
   - Guardar en memoria el mensaje y metadata (`variables_capturadas`, `stage_previo`, `stage_nuevo`).
4. **Errores**
   - Si el modelo no logra extraer datos, solicitar aclaraciones en la respuesta. Registrar evento para evaluación manual.

### Pruebas mínimas
- Captura completa (pie + fecha estimada) → stage actualizado.
- Información parcial → solicita datos faltantes.
- Prospecto en stage bloqueado → mensaje de rechazo y sin cambios.

## 4. Subagente de agenda (`filter_schedule`)

### Intención y gating
- Intención `fecha_visita` **y** `prospect.stage == "qualified"` (validado por `filter_schedule` + `Setear3`).

### Referencia n8n
Rama `Filter_schedule → Setear3 → AGENDAR_VISITA` con utilidades de fecha (`fecha_actual`, `poner_fecha_visita`).

### Implementación
1. **Servicio**
   - `SchedulingAgent.schedule_visit(prospect, message, official_data, settings)`.
   - Fuente de disponibilidad configurable (Supabase, Google Calendar o servicio propio). Documentar en `docs/subagent_schedule_prompt.md`.
2. **Flujo**
   - Si `stage != qualified`: responder instrucción de completar calificación (sin tocar agenda).
   - Si `qualified`: buscar horarios disponibles, confirmar con el usuario (loop si necesario) y crear evento (`visits` o `prospects.scheduled_at`).
3. **Persistencia y notificaciones**
   - Registrar en memoria el resultado (`scheduled_at`, `location`, `notes`).
   - Opcional: disparar webhook/notification al broker.
4. **Fallbacks**
   - Si no hay disponibilidad, ofrecer alternativas o canal humano.

### Pruebas mínimas
- Prospecto calificado → agenda exitosa.
- Prospecto no calificado → rechazo controlado.
- Reprogramar fecha → actualiza registro existente.

## 5. Procesos derivados obligatorios

Además de los cuatro subagentes, el plan debe cubrir las ramas utilitarias del JSON:

- **`followup_prospect`**: eliminar follow-up activo (si existe) y crear el siguiente según `followup_configuration`. Operación transaccional en Supabase para evitar duplicidades. Registrar en memoria (`tipo`, `scheduled_for`).
- **`followup_broker`**: similar al anterior, pero usando `notifications_brokers_configurations`. Puede requerir insertar en tabla `broker_notifications` o disparar webhook.
- **`agente enviar archivos` (`filter_files`)**: resolver recursos solicitados (plantillas, PDFs, planos). Mantener repositorio central o endpoint firmado. Loguear archivo entregado.
- **`proceso de desinterés` (`filter_desinteres`)**: marcar opt-out (`automation_allowed=False`, `handoff_required=True`, `handoff_reason='opt_out'`), registrar en memoria y notificar al área comercial.
- **`contacto humano` (hand-off)**: crear tarea/notificación hacia CRM o Slack; asegurar que `automation_allowed=False` para futuros mensajes hasta intervención humana.

Cada proceso debe exponer funciones claras (p.ej., `FollowupService.schedule_next(...)`, `FilesAgent.send_assets(...)`) y operar con idempotencia.

## 6. Orquestación general

1. El Agente Madre entrega `intenciones` (array) y metadata mínima (`session_id`, `prospect_id`, `realtor_id`, `message`, `payload_ts`).
2. Para cada filtro que resulte `true`, un nodo `Setear*` prepara las claves necesarias (`official_data`, `history`, `contexto_prompt`).
3. Se ejecuta el subagente/proceso correspondiente. Cada bloque **debe** escribir su acción en `chats_history_n8n` con metadata específica.
4. Los resultados parciales se combinan mediante nodos de `Merge` (`output_rag`, `output_calification`, `output_scheduled`, `unir_variables`, etc.) sin prioridad fija; la respuesta final concatena los mensajes relevantes.
5. Ante cualquier excepción, se captura, se responde con fallback controlado y se registra el error (logging + observabilidad). No se debe interrumpir el hilo ni perder el contexto de memoria.

## 7. Tareas globales pendientes

- Definir prompts dedicados: `docs/subagent_rag_prompt.md`, `docs/subagent_calification_prompt.md`, `docs/subagent_schedule_prompt.md`, `docs/subagent_followup_prompt.md` (si se requiere LLM para estimar tiempos).
- Preparar pruebas unitarias/integración por bloque, simulando llamadas a Supabase y al microservicio RAG (fixtures + mocks). Incluir casos negativos.
- Documentar credenciales/endpoints externos: microservicio de vectores, agenda, notificaciones.
- Instrumentar métricas (latencia por subagente, tasa de éxito, `intent_coverage`). Configurar alertas de error.
- Mantener actualizado `docs/agent_mother_migration.md` con el estado de implementación (checklist).

## 8. Checklist operativo para el equipo de implementación

- [ ] Normalizar la salida del Agente Madre a un array de strings antes del ruteo.
- [ ] Garantizar que cada subagente reciba `session_id`, `realtor_id`, `prospect_id`, `message` (inyectados por nodos `Setear`).
- [ ] Consumir el microservicio RAG sin generar embeddings locales; parámetros por defecto `limit=5`, `threshold=0.7`.
- [ ] Mapear `results` de RAG a `mentioned_properties` y `sources`; persistir metadata en memoria.
- [ ] Asegurar seguridad multi-tenant (`realtor_id`) en todas las consultas/actualizaciones (Supabase + microservicio).
- [ ] Implementar operaciones idempotentes para follow-ups, proyectos, agenda y envío de archivos.
- [ ] Aplicar `filtro_etapa` antes de calificación; agenda solo con stage `qualified`.
- [ ] Manejar opt-out (`filter_desinteres`) y hand-off humano dejando constancia en memoria y desactivando automatización.
- [ ] Registrar métricas y logs estructurados por subagente/proceso.
- [ ] Crear suite de pruebas que cubra los casos descritos (RAG, proyecto, calificación, agenda, follow-ups, archivos, opt-out, hand-off).

## 9. Casos de prueba mínimos (por rama)

- **RAG**: intención `busqueda_informacion` → llamada al microservicio → `mentioned_properties` poblado → persistencia con metadata.
- **Actualizar proyecto**: `anotar_proyecto` con `link`, `unlink`, proyecto inexistente e idempotencia.
- **Calificación**: mensajes `forma_pago` / `fecha_compra` con datos completos, incompletos y bloqueo por stage.
- **Agenda**: `fecha_visita` con `qualified` (agenda) y sin `qualified` (rechazo). Reprogramación incluida.
- **Follow-ups**: creación del próximo follow-up tras borrar el previo; validar registro en memoria.
- **Enviar archivos**: solicitud de archivo existente/no existente; respuesta con URL o mensaje de error más registro en memoria.
- **Desinterés**: mensaje de opt-out → `automation_allowed=False`, `handoff_required=True` y notificación.
- **Contacto humano**: intención de asesor → creación de tarea/notificación y cierre temporal de automatización.

---
Este plan deja el flujo sin ambigüedades, listo para ejecución incremental y pruebas automatizadas, manteniendo paridad con lo modelado en `Agentic-Pdch.json`.

## 10. Contratos operativos y configuración extendida

1. **Contratos y errores**
   - RAG: declarar timeout duro de 1200 ms al microservicio, con política de reintento (1 retry con backoff exponencial). Si ambos intentos fallan, responder con mensaje seguro (“Estamos consultando la información, un asesor te apoyará”) y loggear el incidente.
   - Agenda/Files: estandarizar la salida en `{ok, message, metadata}` para que el repositorio de memoria almacene siempre el mismo shape y facilite trazabilidad.

2. **Configuración centralizada**
   - Definir variables de entorno por subagente (`RAG_URL`, `RAG_LIMIT`, `RAG_THRESHOLD`, `FOLLOWUP_T+N`, `SCHEDULE_PROVIDER`, etc.) y documentar valores por entorno en `docs/defaults.md` (dev / prod).

3. **Idempotencia y llaves**
   - Follow-ups: usar `idempotency_key = f"{prospect_id}:{tipo}:{scheduled_for}"` al crear tareas para evitar duplicados.
   - Actualizar proyecto: garantizar que la tabla tenga restricción única `(prospect_id, project_id)` y aplicar `ON CONFLICT DO NOTHING`.

4. **Seguridad y multi-tenancy**
   - En Files y Update Projects: verificar siempre que el recurso a entregar/actualizar pertenezca al `realtor_id` del contexto antes de operar.
   - Hand-off: al activar contacto humano, setear `automation_allowed = False` y registrar `handoff_reason` en memoria y Supabase.

5. **Métricas y trazabilidad**
   - Propagar `session_id` y un `trace_id` generado por petición en todos los logs/subagentes.
   - Medir KPIs mínimos: latencia p95 por subagente, tasa de error y `intent_coverage` semanal (porcentaje de intenciones atendidas con acciones).

6. **Ensamble de respuesta**
   - Regla de composición: `reply_final = ' '.join(filter(None, [rag.reply, calification.reply, schedule.reply, files.reply]))` para evitar conflictos entre mensajes y mantener orden consistente.
