# Usar una imagen base de Python con soporte para Playwright
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Establecer directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema necesarias para PostgreSQL
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copiar archivos de dependencias
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Instalar navegadores de Playwright
RUN playwright install chromium
RUN playwright install-deps chromium

# Copiar el código de la aplicación
COPY . .

# Crear directorios para archivos
RUN mkdir -p /app/uploads \
    && mkdir -p /app/media/photos \
    && mkdir -p /app/media/videos \
    && mkdir -p /app/data \
    && mkdir -p /app/temp

# Establecer permisos
RUN chmod +x /app/start.sh

# Exponer puerto (Railway asigna automáticamente)
EXPOSE 8000

# Comando de inicio
CMD ["./start.sh"]