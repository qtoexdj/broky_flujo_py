# Tabla `chats_history_n8n`

Repositorio de memoria conversacional persistente utilizado por el Agente Madre y los subagentes.

## Propósito
- Guardar todos los mensajes intercambiados en una conversación (por `session_id`).
- Permitir que el Agente Madre recupere historial para clasificar intenciones con contexto.
- Mantener trazabilidad de lo que respondió el sistema vs. lo que dijo el usuario.

## Estructura sugerida
| Columna        | Tipo        | Nulo | Default          | Descripción |
| -------------- | ----------- | ---- | ---------------- | ----------- |
| `id`           | uuid        | No   | `gen_random_uuid()` | Identificador único del mensaje. |
| `session_id`   | text        | No   | —                | Identificador de conversación (formato `telefono:realtor_id`). |
| `sender_role`  | text        | No   | —                | Rol que emitió el mensaje (`user`, `assistant`, `system`). |
| `message`      | text        | No   | —                | Contenido del mensaje en texto plano. |
| `metadata`     | jsonb       | Sí   | `'{}'::jsonb`    | Datos auxiliares (`intents`, `source`, timestamps externos, etc.). |
| `created_at`   | timestamptz | No   | `now()`          | Momento en que se insertó el registro. |

> Ajusta los tipos a tu esquema real si difieren. El repositorio Python asume nombres como los anteriores.

## Índices recomendados
- `idx_chats_history_n8n_session_id` sobre `session_id` para recuperar la conversación rápidamente.
- Índice compuesto `(session_id, created_at)` si se esperan consultas ordenadas por tiempo.

## Uso actual en la app
- `ChatHistoryRepository.fetch_history(session_id)` hace `select * ... order(created_at asc) limit N`.
- `ChatHistoryRepository.append_message(...)` inserta registros con `sender_role` y `metadata` opcional.
- `ChatHistoryRepository.delete_last(session_id)` busca el último mensaje por `created_at desc` y lo elimina para limpiar salidas inválidas.

## Recomendaciones operativas
- Configura retención (por ejemplo, borrar conversaciones antiguas después de X días si no son necesarias).
- Asegura políticas RLS por `realtor_id`/`session_id` para mantener el aislamiento multi-tenant.
- Replica los mensajes críticos a `chats_history` original si otras integraciones dependen de ese pipeline.
