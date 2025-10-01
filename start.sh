#!/bin/bash

# Esperar a que PostgreSQL esté disponible (si usas Railway PostgreSQL)
echo "Esperando conexión a PostgreSQL..."
while ! pg_isready -h $PGHOST -p $PGPORT -U $PGUSER; do
  echo "PostgreSQL no está listo - esperando..."
  sleep 2
done

echo "PostgreSQL está listo!"

# Ejecutar migraciones o setup inicial si es necesario
#python setup_db.py

# Iniciar el watcher de archivos en background
python file_watcher.py &

# Ejecutar scripts principales
python main.py &

# Iniciar servidor web para Railway (debe mantener el contenedor activo)
uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-keep-alive ${UVICORN_TIMEOUT:-30} --timeout-graceful-shutdown 5 --limit-max-requests 4096