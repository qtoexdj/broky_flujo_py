# Arquitectura Híbrida LangGraph ↔ LangChain

Este documento describe la estructura objetivo para la migración del bot Broky.

## Componentes

- **LangGraph** (`app/workflows` y `broky/core/graph`): mantiene el control del flujo conversacional y orquesta la invocación de agentes LangChain.
- **LangChain** (`broky/agents`, `broky/tools`, `broky/memory`, `broky/runtime`): aloja el Agente Madre y los subagentes (`RAGAgentExecutor`, `ProjectInterestAgentExecutor`, `CalificationAgentExecutor`, `ScheduleAgentExecutor`), con herramientas registradas bajo el namespace `broky.tools.*` y runtimes que coordinan su ejecución desde LangGraph.
- **Memoria persistente** (`broky/memory/supabase.py`): interfaz única hacia Supabase (`SUPABASE_SERVICE_ROLE_KEY` requerido) para compartir historial y snapshots entre agentes.
- **Configuración** (`broky/config`): capa dedicada a credenciales y toggles de LangChain/ LangSmith.

## Flujo de datos

1. LangGraph compila un `BrokyContext` (ver `broky/core/context.py`) con el payload del webhook y datos del inbound pipeline.
2. Cada nodo LangGraph invoca el agente correspondiente (`BrokyAgent`) mediante su `Runnable` de LangChain.
3. `broky/runtime` invoca el Agente Madre y los subagentes LangChain, consulta herramientas registradas en `ToolRegistry` y usa `SupabaseConversationMemory` para snapshots.
4. Los resultados regresan al `BrokyContext`, manteniendo trazabilidad en `context.metadata` y `context.logs`.

## Próximos pasos

- Portar `app/agents/master.py` a `broky/agents/master.py` usando LangChain AgentExecutor.
- Migrar los subagentes actuales a herramientas LangChain y registrarlos en `ToolRegistry`.
- Actualizar los nodos de `app/workflows/inbound.py` para delegar en la nueva capa LangChain.
