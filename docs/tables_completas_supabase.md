# Tabla `public.profiles`

- Comentario: Usuarios (brokers, managers, admin)
- Filas aproximadas: 22
- Reglas RLS: habilitadas
- Llave primaria: `id`

## Columnas
| Columna           | Tipo         | Nulo | Default                | Notas |
|-------------------|--------------|------|------------------------|-------|
| id                | uuid         | No   |                        | Identificador único |
| email             | text         | No   |                        | Email del usuario (único) |
| name              | text         | Sí   |                        | Nombre completo |
| telephone         | text         | Sí   |                        | Teléfono |
| realtor_id        | uuid         | Sí   |                        | Referencia a `realtors.id` |
| role              | role (enum)  | No   | 'broker'::role         | admin, manager, broker |
| status            | status (enum)| No   | 'invite'::status       | active, invite, inactive |
| avatar            | text         | Sí   |                        | URL de avatar |
| available_times   | jsonb        | Sí   |                        | Horarios disponibles |
| created_at        | timestamptz  | No   | now()                  | Fecha de creación |
| updated_at        | timestamptz  | Sí   |                        | Última actualización |

## Restricciones e índices
- Llave primaria `profiles_pkey` sobre `id`.
- Llave foránea `profiles_realtor_id_fkey` → `realtors.id`.
- Llave foránea `profiles_id_fkey` → `auth.users.id`.
- Único en `email`.

## Políticas RLS
- Acceso restringido por rol y realtor.

## Relaciones externas relevantes
- Referencias desde `prospects`, `followups`, `realtor_invitations`, `vendor_assigned_projects`.

---
# Tabla `public.realtors`

- Comentario: Inmobiliarias
- Filas aproximadas: 10
- Reglas RLS: habilitadas
- Llave primaria: `id`

## Columnas
| Columna             | Tipo         | Nulo | Default                | Notas |
|---------------------|--------------|------|------------------------|-------|
| id                  | uuid         | No   | gen_random_uuid()      | Identificador único |
| name                | text         | No   |                        | Nombre comercial |
| email               | text         | No   |                        | Email |
| telephone           | text         | No   |                        | Teléfono |
| plan                | varchar      | No   | 'trial'                | Plan actual |
| credits             | numeric      | No   | '100'                  | Créditos disponibles |
| billing_at          | timestamptz  | Sí   |                        | Fecha de facturación |
| website             | text         | Sí   |                        | Web |
| social              | jsonb        | Sí   |                        | Redes sociales |
| opening_hours       | jsonb        | Sí   |                        | Horarios de atención |
| avatar              | text         | Sí   |                        | URL de avatar |
| bot_name            | text         | Sí   |                        | Nombre del bot |
| bot_personality     | text         | Sí   |                        | Personalidad del bot |
| bot_tone            | text         | Sí   |                        | Tono del bot |
| followups_prospects | jsonb        | Sí   |                        | Configuración de seguimientos |
| followups_brokers   | jsonb        | Sí   |                        | Configuración de seguimientos |
| webhook_url         | text         | Sí   |                        | URL de webhook |
| token_whapi         | text         | Sí   |                        | Token WhatsApp API |
| created_at          | timestamptz  | No   | now()                  | Fecha de creación |
| updated_at          | timestamptz  | Sí   |                        | Última actualización |
| location            | text         | Sí   |                        | Ubicación |
| description         | text         | Sí   |                        | Descripción |
| rating_fields       | jsonb        | No   | '[]'                   | Campos de rating |
| active              | boolean      | No   | false                  | Estado activo |

## Restricciones e índices
- Llave primaria `realtors_pkey` sobre `id`.
- Llave foránea `realtors_plan_fkey` → `plans.id`.

## Políticas RLS
- Acceso restringido por rol.

## Relaciones externas relevantes
- Referencias desde `projects`, `prospects`, `followups`, `profiles`, `extra_information`, `push_campaigns`.

---
# Tabla `public.project_files`

- Comentario: Archivos relacionados con los proyectos
- Filas aproximadas: 6777
- Reglas RLS: habilitadas
- Llave primaria: `id`

## Columnas
| Columna     | Tipo        | Nulo | Default           | Notas |
|-------------|-------------|------|-------------------|-------|
| id          | uuid        | No   | gen_random_uuid() | Identificador único |
| project_id  | uuid        | No   | gen_random_uuid() | Referencia a `projects.id` |
| name        | text        | No   |                   | Nombre del archivo |
| url         | text        | No   |                   | URL del archivo |
| type        | text        | No   |                   | Tipo de archivo |
| featured    | boolean     | No   | false             | Destacado |
| created_at  | timestamptz | No   | now()             | Fecha de creación |

## Restricciones e índices
- Llave primaria `project_files_pkey` sobre `id`.
- Llave foránea `project_files_project_id_fkey` → `projects.id`.

## Políticas RLS
- Acceso restringido por rol y proyecto.

## Relaciones externas relevantes
- Referencias desde `projects`.

---
# Tabla `public.followups`

- Comentario: Seguimientos de prospectos
- Filas aproximadas: 2102
- Reglas RLS: habilitadas
- Llave primaria: `id`

## Columnas
| Columna                | Tipo        | Nulo | Default           | Notas |
|------------------------|-------------|------|-------------------|-------|
| id                     | uuid        | No   | gen_random_uuid() | Identificador único |
| prospect_id            | uuid        | No   |                   | Referencia a `prospects.id` |
| realtor_id             | uuid        | No   |                   | Referencia a `realtors.id` |
| broker_id              | uuid        | Sí   |                   | Referencia a `profiles.id` |
| type                   | text        | No   |                   | Tipo de seguimiento |
| type_followup          | numeric     | Sí   |                   | Número de seguimiento (1,2,3) |
| completed              | boolean     | No   | false             | Completado |
| created_at             | timestamptz | No   | now()             | Fecha de creación |
| date_followup_scheduled| timestamptz | Sí   |                   | Fecha agendada |

## Restricciones e índices
- Llave primaria `followups_pkey` sobre `id`.
- Llaves foráneas: `prospect_followups_prospect_id_fkey` → `prospects.id`, `prospect_followups_realtor_id_fkey` → `realtors.id`, `followups_broker_id_fkey` → `profiles.id`.

## Políticas RLS
- Acceso restringido por rol y prospecto.

## Relaciones externas relevantes
- Referencias desde `prospects`, `realtors`, `profiles`.

---
# Tabla `public.vendor_assigned_projects`

- Comentario: Asignación de proyectos a vendedores
- Filas aproximadas: 251
- Reglas RLS: habilitadas
- Llave primaria: `id`

## Columnas
| Columna     | Tipo        | Nulo | Default           | Notas |
|-------------|-------------|------|-------------------|-------|
| id          | uuid        | No   | gen_random_uuid() | Identificador único |
| vendor_id   | uuid        | No   |                   | Referencia a `profiles.id` |
| project_id  | uuid        | No   |                   | Referencia a `projects.id` |
| created_at  | timestamptz | No   | now()             | Fecha de asignación |

## Restricciones e índices
- Llave primaria `vendor_assigned_projects_pkey` sobre `id`.
- Llaves foráneas: `vendor_assigned_projects_vendor_id_fkey` → `profiles.id`, `vendor_assigned_projects_project_id_fkey` → `projects.id`.

## Políticas RLS
- Acceso restringido por rol y vendedor.

## Relaciones externas relevantes
- Referencias desde `profiles`, `projects`.

---
# Tabla `public.push_campaigns`

- Comentario: Campañas publicitarias
- Filas aproximadas: 7
- Reglas RLS: habilitadas
- Llave primaria: `id`

## Columnas
| Columna         | Tipo        | Nulo | Default           | Notas |
|-----------------|-------------|------|-------------------|-------|
| id              | uuid        | No   | gen_random_uuid() | Identificador único |
| realtor_id      | uuid        | No   |                   | Referencia a `realtors.id` |
| name            | text        | No   |                   | Nombre de la campaña |
| description     | text        | No   |                   | Descripción |
| content         | text        | No   |                   | Contenido |
| filters         | jsonb       | No   |                   | Filtros aplicados |
| scheduled_at    | timestamptz | Sí   |                   | Fecha de envío programado |
| last_scheduled_at| timestamptz| Sí   |                   | Última fecha de envío |
| created_at      | timestamptz | No   | now()             | Fecha de creación |
| updated_at      | timestamptz | Sí   |                   | Última actualización |
| webhook_url     | text        | Sí   |                   | URL de webhook |
| type            | text        | No   |                   | Tipo de campaña |
| files_campaigns | text        | Sí   |                   | Archivos asociados |

## Restricciones e índices
- Llave primaria `push_campaigns_pkey` sobre `id`.
- Llave foránea `push_campaign_realtor_id_fkey` → `realtors.id`.

## Políticas RLS
- Acceso restringido por rol y realtor.

## Relaciones externas relevantes
- Referencias desde `push_campaigns_history`, `realtors`.

---
# Tabla `public.push_campaigns_history`

- Comentario: Historial de envíos de campañas
- Filas aproximadas: 1401
- Reglas RLS: habilitadas
- Llave primaria: `id`

## Columnas
| Columna         | Tipo        | Nulo | Default           | Notas |
|-----------------|-------------|------|-------------------|-------|
| id              | uuid        | No   | gen_random_uuid() | Identificador único |
| push_campaign_id| uuid        | No   |                   | Referencia a `push_campaigns.id` |
| prospect_id     | uuid        | No   |                   | Referencia a `prospects.id` |
| sent_in         | timestamptz | No   |                   | Fecha de envío |

## Restricciones e índices
- Llave primaria `push_campaigns_history_pkey` sobre `id`.
- Llaves foráneas: `push_campaign_history_push_campaign_id_fkey` → `push_campaigns.id`, `push_campaign_history_prospect_id_fkey` → `prospects.id`.

## Políticas RLS
- Acceso restringido por rol y campaña.

## Relaciones externas relevantes
- Referencias desde `push_campaigns`, `prospects`.

---
# Tabla `public.realtor_invitations`

- Comentario: Invitaciones a brokers/managers
- Filas aproximadas: 0
- Reglas RLS: habilitadas
- Llave primaria: `id`

## Columnas
| Columna     | Tipo        | Nulo | Default           | Notas |
|-------------|-------------|------|-------------------|-------|
| id          | uuid        | No   | gen_random_uuid() | Identificador único |
| realtor_id  | uuid        | No   |                   | Referencia a `realtors.id` |
| from_id     | uuid        | No   |                   | Referencia a `profiles.id` |
| to_id       | uuid        | No   |                   | Referencia a `profiles.id` (único) |
| created_at  | timestamptz | No   | now()             | Fecha de invitación |

## Restricciones e índices
- Llave primaria `realtor_invitations_pkey` sobre `id`.
- Llaves foráneas: `realtor_invitations_realtor_id_fkey` → `realtors.id`, `realtor_invitations_from_id_fkey` → `profiles.id`, `realtor_invitations_to_id_fkey` → `profiles.id`.

## Políticas RLS
- Acceso restringido por rol y realtor.

## Relaciones externas relevantes
- Referencias desde `realtors`, `profiles`.

---
# Tabla `public.transaction_history`

- Comentario: Historial de transacciones
- Filas aproximadas: 2
- Reglas RLS: habilitadas
- Llave primaria: `id`

## Columnas
| Columna     | Tipo        | Nulo | Default           | Notas |
|-------------|-------------|------|-------------------|-------|
| id          | uuid        | No   | gen_random_uuid() | Identificador único |
| realtor_id  | uuid        | No   |                   | Referencia a `realtors.id` |
| name        | varchar     | No   |                   | Nombre de la transacción |
| type        | varchar     | No   |                   | Tipo de transacción |
| price       | float4      | No   |                   | Monto |
| status      | varchar     | No   | 'pending'         | Estado |
| created_at  | timestamptz | No   | now()             | Fecha de creación |
| updated_at  | timestamp   | Sí   |                   | Última actualización |
| merchant_id | varchar     | No   |                   | ID del comercio |

## Restricciones e índices
- Llave primaria `transaction_history_pkey` sobre `id`.
- Llave foránea `transaction_history_realtor_id_fkey` → `realtors.id`.

## Políticas RLS
- Acceso restringido por rol y realtor.

## Relaciones externas relevantes
- Referencias desde `realtors`.

---
# Tabla `public.plans`

- Comentario: Planes de suscripción
- Filas aproximadas: 10
- Reglas RLS: habilitadas
- Llave primaria: `id`

## Columnas
| Columna     | Tipo        | Nulo | Default           | Notas |
|-------------|-------------|------|-------------------|-------|
| id          | varchar     | No   |                   | Identificador único |
| name        | varchar     | No   |                   | Nombre del plan |
| price       | numeric     | No   | '0'               | Precio |
| max_credits | numeric     | Sí   |                   | Créditos máximos |

## Restricciones e índices
- Llave primaria `plans_pkey` sobre `id`.
- Llave foránea `realtors_plan_fkey` → `realtors.plan`.

## Políticas RLS
- Acceso restringido por rol.

## Relaciones externas relevantes
- Referencias desde `realtors`.

---
# Tabla `public.extra_information`

- Comentario: Información adicional de inmobiliarias
- Filas aproximadas: 28
- Reglas RLS: habilitadas
- Llave primaria: `id`

## Columnas
| Columna               | Tipo        | Nulo | Default           | Notas |
|-----------------------|-------------|------|-------------------|-------|
| id                    | uuid        | No   | gen_random_uuid() | Identificador único |
| realtor_id            | uuid        | No   |                   | Referencia a `realtors.id` |
| name_extra_information| text        | No   |                   | Nombre de la información |
| description           | text        | No   |                   | Descripción |
| created_at            | timestamptz | No   | now()             | Fecha de creación |

## Restricciones e índices
- Llave primaria `extra_information_pkey` sobre `id`.
- Llave foránea `extra_information_realtor_id_fkey` → `realtors.id`.

## Políticas RLS
- Acceso restringido por rol y realtor.

## Relaciones externas relevantes
- Referencias desde `realtors`.

---
# Tabla `public.landing_events`

- Comentario: Eventos de landing (tracking web)
- Filas aproximadas: 2511
- Reglas RLS: habilitadas
- Llave primaria: `id`

## Columnas
| Columna     | Tipo        | Nulo | Default           | Notas |
|-------------|-------------|------|-------------------|-------|
| id          | uuid        | No   | gen_random_uuid() | Identificador único |
| event_type  | text        | No   |                   | page_view, click, chat, form |
| session_id  | text        | No   |                   | Sesión |
| page        | text        | No   |                   | Página |
| path        | text        | Sí   |                   | Ruta |
| referrer    | text        | Sí   |                   | Referencia externa |
| utm         | jsonb       | Sí   |                   | Parámetros UTM |
| user_agent  | text        | Sí   |                   | User agent |
| created_at  | timestamptz | No   | (now() AT TIME ZONE 'America/Santiago') | Fecha de creación |
| button_id   | text        | Sí   |                   | ID de botón |
| button_text | text        | Sí   |                   | Texto de botón |
| variant     | text        | Sí   |                   | Variante |
| message     | text        | Sí   |                   | Mensaje (máx 2000 chars) |
| form_id     | text        | Sí   |                   | ID de formulario |
| fields      | jsonb       | Sí   |                   | Campos del formulario |
| meta        | jsonb       | Sí   |                   | Metadatos |

## Restricciones e índices
- Llave primaria `landing_events_pkey` sobre `id`.

## Políticas RLS
- Acceso restringido por rol y sesión.

---
# Tabla `public.vector_projects`

- Comentario: Embeddings de proyectos para RAG
- Filas aproximadas: 362
- Reglas RLS: habilitadas
- Llave primaria: `id`

## Columnas
| Columna   | Tipo        | Nulo | Default           | Notas |
|-----------|-------------|------|-------------------|-------|
| id        | uuid        | No   | gen_random_uuid() | Identificador único |
| embedding | vector      | Sí   |                   | Embedding vector |
| content   | text        | Sí   |                   | Contenido |
| metadata  | jsonb       | Sí   |                   | Metadatos |

## Restricciones e índices
- Llave primaria `vector_projects_pkey` sobre `id`.

## Políticas RLS
- Acceso restringido por rol y proyecto.

---
# Tabla `public.chats_history`

- Comentario: Historial conversacional principal
- Filas aproximadas: 27543
- Reglas RLS: habilitadas
- Llave primaria: `id`

## Columnas
| Columna     | Tipo        | Nulo | Default           | Notas |
|-------------|-------------|------|-------------------|-------|
| id          | uuid        | No   | gen_random_uuid() | Identificador único |
| realtor_id  | uuid        | No   |                   | Referencia a `realtors.id` |
| telephone   | text        | Sí   |                   | Teléfono |
| session_id  | text        | No   |                   | Sesión |
| message     | jsonb       | No   |                   | Mensaje (jsonb) |
| manager_id  | uuid        | Sí   |                   | Referencia a `profiles.id` |
| timestamp   | timestamptz | No   |                   | Fecha y hora |

## Restricciones e índices
- Llave primaria `chats_history_pkey` sobre `id`.
- Llaves foráneas: `chat_history_realtor_id_fkey` → `realtors.id`, `chat_history_manager_id_fkey` → `profiles.id`.

## Políticas RLS
- Acceso restringido por rol y sesión.

## Relaciones externas relevantes
- Referencias desde `realtors`, `profiles`, `prospects`.

---
# Tabla `public.realtor_requests`

- Comentario: Solicitudes de inmobiliarias
- Filas aproximadas: 0
- Reglas RLS: habilitadas
- Llave primaria: `id`

## Columnas
| Columna     | Tipo        | Nulo | Default           | Notas |
|-------------|-------------|------|-------------------|-------|
| id          | uuid        | No   | gen_random_uuid() | Identificador único |
| realtor_id  | uuid        | No   |                   | Referencia a `realtors.id` |
| created_at  | timestamptz | No   | now()             | Fecha de solicitud |

## Restricciones e índices
- Llave primaria `realtor_requests_pkey` sobre `id`.
- Llave foránea `realtor_requests_realtor_id_fkey` → `realtors.id`.

## Políticas RLS
- Acceso restringido por rol y realtor.

## Relaciones externas relevantes
- Referencias desde `realtors`.
