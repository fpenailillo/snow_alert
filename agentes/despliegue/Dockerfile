FROM python:3.11-slim

# Metadatos
LABEL maintainer="fpenailillom@correo.uss.cl"
LABEL descripcion="Sistema Multi-Agente snow_alert — Cloud Run Job"
LABEL version="3.0"

# Variables de entorno base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar y instalar dependencias Python
COPY agentes/despliegue/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
# analizador_avalanchas/ se copia al mismo nivel que agentes/ para que
# el path 'datos/' funcione igual que en desarrollo local
COPY agentes/ /app/agentes/
COPY datos/analizador_avalanchas/ /app/datos/analizador_avalanchas/

# Asegurar que el módulo analizador_avalanchas sea importable
# (se añade /app/datos al PYTHONPATH)
ENV PYTHONPATH=/app:/app/datos

# Usuario no-root por seguridad
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# El Job de Cloud Run ejecuta generar_todos.py
ENTRYPOINT ["python", "agentes/scripts/generar_todos.py"]
