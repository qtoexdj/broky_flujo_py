# Flujo de Webhook Inmobiliario

Describe el pipeline basado en LangGraph que prepara cada webhook antes de llegar al motor conversacional. Implementación en `app/workflows/inbound.py`.

## Pasos del flujo

1. **Recepción (`init`)**  
   Valida que exista `payload`, registra el evento y arranca con `automation_allowed = True`, `handoff_required = False`.

2. **Normalización (`normalize`)**  
   Extrae el sobre completo: `realtor_id`, `telephone`, `session_id`, `name`, `channel_id`, `chat_id`, `message`, `followup_configuration`, `notifications_brokers_configurations`, `id_vector_project`. Si falta `id_vector_project`, se genera con la convención `vector_projects_<nombre>_<uuid>`.

3. **Lookup de inmobiliaria (`realtor`)**  
   Consulta `realtors` por `channel_id`, agrega la ficha completa (nombre, descripción, configuraciones, etc.) al estado junto con la configuración del bot (`bot_name`, `bot_personality`, `bot_tone`).

4. **Lookup de prospecto (`lookup_prospect`)**  
   Busca en `prospects` por `(realtor_id, telephone)`. Marca `prospect_exists` y guarda el registro si lo encuentra.

5. **Creación de prospecto (`create_prospect`)** *(solo rama "no existe")*  
   Inserta un prospecto base: `automatization = true`, `stage = 'new-prospect'`, `calification_variables = {}`, `mentioned_properties = []`, `source = 'webhook'`. Devuelve el registro completo.

6. **Consolidación (`hydrate_prospect`)**  
   Asegura que `normalized` contenga `prospect_id`, `automatization` y copia `mentioned_properties` desde la fila de `prospects`.

7. **Proyectos asociados (`load_properties`)**  
   - Lee `prospect_project_interests` para obtener `project_id` vinculados.  
   - Recupera los detalles en la tabla `projects` y los deja en `properties_interested`.  
   - Combina con `mentioned_properties` almacenadas en `prospects` para conservar todo el contexto.

7.1. **Consolidación de datos oficiales (`consolidate_official`)**  
   Crea un objeto `official_data` con todos los valores relevantes (`session_id`, `realtor_id`, configuraciones del realtor, followups, proyectos/intereses, etc.) para consumo del Agente Madre y subagentes.

8. **Filtro opt-out (`apply_opt_out`)**  
   Si el mensaje recibido es exactamente `"0"`, desactiva automatización (`automation_allowed = False`), marca `handoff_required = True` y setea `handoff_reason = 'opt_out'`.

9. **Filtro automatización (`apply_automation`)**  
   Respeta `normalized["automatization"]`: si está en `False`, fuerza hand-off con `handoff_reason = 'automatizacion_desactivada'`; de lo contrario deja constancia de que el bot puede continuar.

## Resultado del pipeline

Al terminar `apply_automation`, el estado incluye:
- `payload` original y `logs` con cada paso registrado.  
- Bloque `normalized` con: datos del prospecto, inmobiliaria, contacto, mensaje, `properties_interested`, `mentioned_properties`.  
- Flags: `automation_allowed`, `handoff_required`, `handoff_reason` (si aplica).  
- Referencias a `prospect` e `realtor` para cualquier paso posterior (notificaciones, motor LLM, etc.).

## Arquitectura de módulos

- `app/workflows/inbound.py`: define el grafo y nodos.  
- `app/services/realtor_repository.py`: consulta `realtors` por `channel_id`.  
- `app/services/prospect_repository.py`: búsqueda/creación de prospectos.  
- `app/services/project_repository.py`: une `prospect_project_interests` con `projects`.  
- `app/services/supabase_client.py`: gestiona la sesión con Supabase.

## Ejemplo rápido

```python
from app.core.config import get_settings
from app.workflows.inbound import build_inbound_workflow

payload = {
    "realtor_id": "...",
    "telephone": "...",
    "session_id": "...",
    "name": "...",
    "channel_id": "...",
    "chat_id": "...",
    "message": "..."
}

workflow = build_inbound_workflow(get_settings())
state = workflow.invoke({"payload": payload})
print(state["logs"])
print(state["automation_allowed"], state["handoff_required"], state.get("handoff_reason"))
```

Con esto, cada webhook sale del pipeline con prospecto consolidado, inmobiliaria identificada, contexto de proyectos y reglas de automatización resueltas.
