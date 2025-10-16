# Usa una imagen base de Python 3.13 slim para reducir el tamaño
FROM python:3.13-slim

# Establece el directorio de trabajo en el contenedor
WORKDIR /app

# Instala dependencias del sistema si son necesarias
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copia el archivo de requerimientos primero para aprovechar la caché de Docker
COPY requirements.txt .

# Instala las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo el código del proyecto al contenedor
COPY . .

# Expone el puerto 8000 para la API
EXPOSE 8000

# Variable de entorno para Python (opcional, evita .pyc y buffer)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Comando para ejecutar la aplicación con uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
