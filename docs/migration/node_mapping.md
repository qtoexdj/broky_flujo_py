# Mapeo de nodos LangGraph

| Nodo actual (`app/workflows/inbound.py`) | Responsabilidad | Agente/Herramienta LangChain destino |
| --- | --- | --- |
| `normalize` | Normaliza payload y metadatos | Conservado en LangGraph (preprocesamiento) |
| `realtor` | Busca ficha de inmobiliaria | Tool `broky.tools.supabase.realtor_lookup` (pendiente) |
| `lookup_prospect` | Consulta prospecto por teléfono | Tool `broky.tools.supabase.prospect_lookup` |
| `create_prospect` | Inserta prospecto | Tool `broky.tools.supabase.prospect_create` |
| `load_properties` | Recupera intereses y propiedades | Tool `broky.tools.supabase.properties_by_prospect` |
| `consolidate_official` | Compila datos oficiales | LangGraph conserva la lógica |
| `apply_opt_out` | Detecta opt-out | LangGraph conserva la lógica |
| `apply_automation` | Evalúa banderas de automatización | LangGraph conserva la lógica |

> Este cuadro se expandirá conforme se mapeen subflujos adicionales (calificación, agenda, follow-ups).
