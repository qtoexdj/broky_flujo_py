# Instrucciones de Docker para Broky WhatsApp Bot

## Archivos creados

1. **Dockerfile**: Imagen base con Python 3.13 y todas las dependencias
2. **.dockerignore**: Excluye archivos innecesarios del build
3. **docker-compose.yml**: Orquestación simplificada del servicio

## Opción 1: Usar Docker Compose (Recomendado)

### Construir y ejecutar:
```bash
docker-compose up --build
```

### Ejecutar en segundo plano:
```bash
docker-compose up -d
```

### Ver logs:
```bash
docker-compose logs -f
```

### Detener el servicio:
```bash
docker-compose down
```

## Opción 2: Usar Docker directamente

### Construir la imagen:
```bash
docker build -t broky-whatsapp-bot .
```

### Ejecutar el contenedor:
```bash
docker run -d \
  --name broky-api \
  -p 8000:8000 \
  --env-file .env \
  broky-whatsapp-bot
```

### Ver logs:
```bash
docker logs -f broky-api
```

### Detener y eliminar:
```bash
docker stop broky-api
docker rm broky-api
```

## Verificar que funciona

Una vez que el contenedor esté corriendo, puedes probar la API:

```bash
curl http://localhost:8000/health
```

O probar el webhook:

```bash
curl --request POST \
  --url http://localhost:8000/webhook \
  --header 'Content-Type: application/json' \
  --data '{
    "from": "usuario_test",
    "message": "Hola, necesito información"
  }'
```

## Notas importantes

1. **Variables de entorno**: Asegúrate de que tu archivo `.env` esté configurado correctamente antes de ejecutar Docker.

2. **Hot-reload en desarrollo**: El `docker-compose.yml` está configurado con `--reload` y volúmenes para desarrollo. Para producción, modifica el comando a:
   ```yaml
   command: uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

3. **Puerto**: La API estará disponible en `http://localhost:8000`

4. **VECTOR_SERVICE_URL**: Si tu servicio vectorial corre en localhost, necesitarás ajustar la URL para que apunte al host de Docker:
   - En Linux: `http://host.docker.internal:8001`
   - O ejecuta el servicio vectorial también en Docker

## Troubleshooting

### El contenedor no inicia:
```bash
docker-compose logs
```

### Reconstruir después de cambios:
```bash
docker-compose up --build --force-recreate
```

### Limpiar todo:
```bash
docker-compose down -v
docker system prune -a
```
