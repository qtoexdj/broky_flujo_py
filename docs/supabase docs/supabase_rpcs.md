# Funciones RPC y triggers en Supabase

Listado de funciones definidas en el esquema `public` que pueden invocarse como RPC desde Supabase o que actúan como triggers auxiliares en la base de datos.

## RPC disponibles
| Nombre | Firma | Retorno | Lenguaje | Detalle |
| --- | --- | --- | --- | --- |
| `charge_credits` | `(realtor_id uuid, value integer, new_plan text \= NULL)` | `void` | plpgsql | Suma o resta créditos a la inmobiliaria y, si se indica, actualiza su plan. |
| `get_distinct_sources` | `(p_realtor_id uuid, p_from timestamptz, p_to timestamptz)` | `TABLE(date date, web bigint, mobile bigint)` | sql | Conteo diario de prospectos creados por fuente (`web`/`mobile`) en un rango. |
| `get_distinct_stages` | `(p_realtor_id uuid, p_from timestamptz, p_to timestamptz)` | `TABLE(stage text, count bigint)` | sql | Agrupa prospectos por etapa dentro de un rango de fechas (creación o agenda). |
| `get_prospects` | `(realtor_id uuid, user_id uuid \= NULL, user_role text \= NULL)` | `TABLE(...)` | sql | Devuelve prospectos activos del realtor, con proyectos asociados y número de followups, filtrando por vendedor cuando es `broker`. |
| `get_realtor_id` | `(uid uuid \= auth.uid())` | `uuid` | sql | Obtiene el `realtor_id` del perfil del usuario autenticado. `SECURITY DEFINER`. |
| `get_used_credits_period` | `(p_from date, p_to date)` | `TABLE(day date, count bigint)` | sql | Cuenta prospectos creados por día en un rango global. |
| `get_used_credits_period` | `(p_realtor_id uuid, p_from date, p_to date)` | `TABLE(day date, count bigint)` | sql | Variante filtrada por inmobiliaria. |
| `get_user_role` | `(uid uuid \= auth.uid())` | `text` | sql | Recupera el rol (`admin`, `manager`, `broker`) del usuario autenticado. `SECURITY DEFINER`. |
| `use_credit` | `(realtor_id uuid)` | `boolean` | plpgsql | Descuenta 1 crédito si hay saldo; retorna `true` si la operación fue exitosa. |

## Funciones de trigger
| Nombre | Disparador previsto | Descripción |
| --- | --- | --- |
| `fn_copy_chat_to_n8n` | `AFTER INSERT ON chats_history` | Replica mensajes nuevos hacia `chats_history_n8n` para integraciones n8n; ignora filas sin `session_id` o `message`. |
| `handle_public_profile` | `AFTER INSERT ON auth.users` | Crea automáticamente el registro en `public.profiles` con `id` y `email` del usuario nuevo. |
| `handle_user_name_update` | `AFTER UPDATE ON auth.users` | Actualiza el nombre visible en `public.profiles` desde `raw_user_meta_data->>'display_name'`. |
| `send_extra_information_webhook` | `AFTER INSERT/UPDATE/DELETE ON extra_information` | Envía webhook a n8n indicando cambios sobre información extra (usa `net.http_post`). |
| `send_project_webhook` | `AFTER INSERT/UPDATE/DELETE ON projects` | Notifica vía webhook (n8n) los cambios en proyectos, indicando operación y `project_id`. |

### Notas adicionales
- Los RPC marcados como `SECURITY DEFINER` (`get_realtor_id`, `get_user_role`) usan el contexto del propietario para consultar perfiles y habilitan su uso desde clientes autenticados sin exponer lectura directa de la tabla.
- Las funciones `get_used_credits_period` existen en dos variantes (global y filtrada por inmobiliaria); Supabase expone ambas como RPC con firmas distintas.
- `charge_credits` y `use_credit` permiten administrar el saldo de créditos de la inmobiliaria de forma atómica dentro de la base de datos.
