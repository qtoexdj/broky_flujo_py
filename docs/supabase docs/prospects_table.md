# Tabla `public.prospects`

- Comentario: Prospectos
- Filas aproximadas: 5707 (dato reportado por Supabase)
- Reglas RLS: habilitadas (4 políticas activas)
- Llave primaria: `id`

## Columnas
| Columna | Tipo | Nulo | Default | Notas |
| --- | --- | --- | --- | --- |
| id | uuid | No | `gen_random_uuid()` | Identificador único |
| realtor_id | uuid | No | — | Referencia a `realtors.id` |
| vendor_id | uuid | Sí | — | Referencia opcional a `profiles.id` |
| name | text | Sí | — | Nombre del prospecto |
| stage | stage (enum) | No | `'new-prospect'::stage` | Valores: `new-prospect`, `conversation`, `qualified`, `not-qualified`, `scheduled`, `not-interested` |
| automatization | boolean | No | `true` | Indica si el flujo automático está activo |
| telephone | text | No | — | Se usa junto con `realtor_id` para unicidad |
| calification_variables | jsonb | Sí | — | Variables de calificación |
| observations | text | Sí | — | Comentarios libres |
| scheduled_at | timestamptz | Sí | — | Próxima gestión agendada |
| created_at | timestamptz | No | `now()` | Fecha de creación |
| updated_at | timestamptz | Sí | — | Última actualización |
| source | text | Sí | — | Fuente de la oportunidad |
| deleted | boolean | No | `false` | Soft delete |
| mentioned_properties | jsonb[] | Sí | `'{}'::jsonb[]` | Referencias a propiedades mencionadas |

## Restricciones e índices
- Restricción primaria `prospects_pkey` sobre `id`.
- Única `unique_realtor_telephone` exige que `(realtor_id, telephone)` no se repita.
- llaves foráneas: `realtor_id` → `realtors.id`, `vendor_id` → `profiles.id`.
- Índices adicionales: `prospects_realtor_id_idx`, `idx_prospects_vendor_id`, `prospects_scheduled_at_idx`, `prospects_created_at_idx`, `prospects_telephone_idx`.

## Políticas RLS
- `Admin has full access`: usuarios autenticados con rol `admin` pueden realizar `ALL`.
- `Broker have access to view information of his realtor`: rol `broker` puede leer filas de su misma inmobiliaria (`get_realtor_id() = realtor_id`).
- `Broker has access to update information of a prospect of his realtor`: rol `broker` puede actualizar filas de su inmobiliaria.
- `Manager has full access in his realtor`: rol `manager` tiene permisos `ALL` sobre filas de su inmobiliaria.

## Relaciones externas relevantes
- Referencias entrantes desde `followups`, `prospect_project_interests`, `push_campaigns_history` y `chats_history`.
- No se encontraron triggers asociados a la tabla.
