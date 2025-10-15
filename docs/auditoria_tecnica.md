# 📋 Resumen General
> El servicio articula FastAPI, LangGraph y LangChain con una capa de repositorios Supabase bien encapsulada y prompts versionados. Sin embargo, la configuración obliga a usar la service role key y expone el webhook sin autenticación ni sanitización, generando riesgos críticos de seguridad y multi-tenancy. El runtime LangChain opera de forma completamente síncrona dentro del endpoint async, bloqueando el event loop y dificultando la escalabilidad. La cobertura de pruebas y la observabilidad son superficiales, lo que deja sin validar los subagentes, el microservicio RAG y los flujos multi-turno reales.

---

# 🗺️ Mapa del Sistema
FastAPI recibe los webhooks y normaliza el payload; InboundWorkflow (LangGraph) consulta/crea prospectos en Supabase; el estado consolidado pasa al MasterAgentRuntime (LangChain) que ejecuta el agente maestro y subagentes (RAG, calificación, agenda, archivos) apoyados en herramientas Supabase y un microservicio vectorial; finalmente WhapiDeliveryService envía respuestas/notificaciones vía Whapi. Supabase también guarda la memoria conversacional y follow-ups.

```
WhatsApp Webhook
      |
      v
FastAPI /webhook (app/api/routes/webhook.py)
      |
      v
InboundWorkflow (LangGraph) ──> Supabase repos (prospects/projects/chat_history)
      |
      v
MasterAgentRuntime (LangChain)
      |         |---------\
      |         |          -> RAGService -> VectorSearchClient -> Qdrant microservicio
      |         |          -> Project/Calification/Schedule/Files tools (Supabase)
      |         \-> Follow-up/Notifications helpers
      |
      v
WhapiDeliveryService -> Whapi API
```

---

# 🧩 Hallazgos Técnicos

| Categoría | Severidad | Descripción | Archivo/Línea afectada |
|------------|------------|--------------|--------------------------|
| Seguridad | Alta | El webhook acepta payloads sin validar firma ni origen y registra el cuerpo crudo con PII (teléfonos, mensajes). | app/api/routes/webhook.py:39 |
| Supabase | Alta | La configuración prioriza `SUPABASE_SERVICE_ROLE_KEY`, lo que entrega a las herramientas LangChain un cliente que ignora RLS; cualquier prompt puede manipular datos de otros tenant. | app/core/config.py:75, broky/tools/registry.py:59 |
| Arquitectura | Alta | Toda la orquestación LangChain/RAG se ejecuta de forma síncrona dentro del endpoint async y usa `time.sleep`, bloqueando el event loop bajo carga. | broky/runtime/master.py:127, app/services/rag/vector_client.py:89 |
| RAG | Media | El servicio RAG inserta el texto del usuario directamente en el prompt sin sanitización ni filtros adicionales, exponiéndose a prompt injection y respuestas alucinadas. | app/services/rag/service.py:82 |
| Pruebas | Media | La suite solo stubbea el webhook; no hay tests que ejecuten los subagentes, llamadas reales a Supabase ni al microservicio vectorial, dejando sin cubrir los caminos críticos. | tests/test_webhook_quilmes.py:5 |

---

# 🧠 Análisis de RAG

| Parámetro | Valor / Estado | Comentario |
|------------|----------------|-------------|
| Motor vectorial | Microservicio HTTP (`VectorSearchClient`) contra Qdrant local | Configurado vía `VECTOR_SERVICE_URL`, sin fallback si el servicio está caído. |
| Dimensión embeddings | 1536 | Usa `text-embedding-3-small` por defecto (`app/core/config.py:16`). |
| Chunk size | No definido | El cliente no controla chunking; depende del microservicio, no documentado. |
| Filtros activos | `realtor_id`, `limit`, `threshold` | No se agrega `updated_at` ni filtros de visibilidad adicionales (`app/services/rag/vector_client.py:67`). |
| Evaluación | Manual | No hay métricas de calidad ni feedback loops para validar respuestas (`app/services/rag/service.py:100`). |

---

# 🗄️ Evaluación de Supabase

| Aspecto | Estado | Observaciones |
|----------|---------|---------------|
| Tablas clave | prospects, projects, chats_history_n8n | El flujo depende de estas tablas y de `prospect_project_interests` (`app/workflows/inbound.py:143`). |
| Políticas RLS | ⚠️ Incompletas | El uso obligatorio de service role deja RLS inoperante para la API y agentes (`app/core/config.py:75`). |
| Índices | Parcial | El catálogo documenta índices en tablas principales, pero no se cubren intereses/seguimientos a alta escala (`docs/tables_completas_supabase.md:1`). |
| Funciones SQL | Parcial | El RPC `get_properties_for_prospect` se invoca sin validaciones de tenant ni manejo de errores avanzado (`app/services/property_repository.py:23`). |

---

# 🔐 Seguridad y Configuración

| Riesgo | Descripción | Severidad | Recomendación |
|---------|--------------|------------|----------------|
| Autenticación webhook | No se valida firma/Facebook token; cualquier actor puede disparar el flujo. | Alta | Implementar challenge Meta o HMAC compartido y rechazar payloads no firmados (`app/api/routes/webhook.py:35`). |
| Logs con PII | Se persiste el cuerpo completo del mensaje en INFO, exponiendo teléfonos y texto sensible. | Alta | Redactar campos sensibles o cambiar a logging estructurado con hash (`app/api/routes/webhook.py:39`). |
| Uso de service role | La API y los agentes operan con la clave que desactiva RLS. | Alta | Introducir claves scoped por tenant y ejecutar las herramientas con credenciales con RLS (`app/core/config.py:75`). |

---

# 📊 Observabilidad

| Métrica | Estado | Comentario |
|----------|---------|-------------|
| Logs estructurados | Parcial | Solo se usa `logging` plano sin IDs de sesión ni niveles consistentes. |
| Trazas distribuidas | ❌ | No hay integración con OpenTelemetry o LangSmith tracing (`app/main.py:1`). |
| Métricas LLM | ❌ | No se registran tokens, costos ni tasas de éxito del runtime (`broky/runtime/master.py:142`). |

---

# 🚀 Plan de Acción Sugerido

| Prioridad | Tarea | Impacto | Esfuerzo |
|------------|--------|----------|-----------|
| 1 | Añadir verificación del webhook y anonimizar logs de entrada | Alta | 4h |
| 2 | Reemplazar el uso de la service role por credenciales con RLS y validaciones explícitas en herramientas | Alta | 8h |
| 3 | Desacoplar subagentes/RAG a workers async (asyncio.to_thread, colas) y eliminar `time.sleep` | Alta | 6h |
| 4 | Endurecer RAG (sanitización, filtros adicionales, evaluación automática de respuestas) | Media | 5h |
| 5 | Instrumentar logging estructurado, métricas y tracing mínimo | Media | 6h |

---

# 🧭 Notas Finales
- No se auditó el microservicio RAG ni la configuración real de Qdrant; se asume que sigue la convención descrita en `.env.example`.
- Las conclusiones sobre RLS parten de la documentación incluida y el uso de la service role; se recomienda confirmar políticas directamente en Supabase antes de cambios mayores.
