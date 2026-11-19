# Imagen base: Linux pequeño con Python 3.12
FROM python:3.12-slim

WORKDIR /app
# Permite que los scripts de pruebas/ importen los módulos de app/
ENV PYTHONPATH=/app

# Las librerías se instalan solas al construir la imagen
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/
COPY pruebas/ /app/pruebas/

# Por defecto corre el ingestor; la API cambia este comando en docker-compose.yml
CMD ["python", "ingestor.py"]
