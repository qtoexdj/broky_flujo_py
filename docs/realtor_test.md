# Guía rápida de pruebas locales

## Identificadores útiles

- **Parcelas**: `realtor_id=1272b928-a4df-4a7e-8ddc-f7130b06851c`
- **Propiedades (Quilmes)**: `realtor_id=de21b61b-d9b5-437a-9785-5252e680b03c`

## Prueba automatizada disponible

La suite incluye `tests/test_webhook_quilmes.py`, que stubbea Supabase y el runtime LangChain para validar que el endpoint `/webhook` responde a consultas sobre propiedades en Quilmes.

```bash
source .venv/bin/activate
pytest
```

Usa este test como plantilla para agregar escenarios con integración real (Supabase/microservicio vectorial). Ajusta el payload bases del realtor correspondiente y verifica que los subagentes actualicen la base según lo esperado.
