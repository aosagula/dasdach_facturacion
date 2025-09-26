#!/bin/bash

# Función para leer variables del .env
get_env_var() {
    # Extract first match for key and strip Windows carriage returns
    grep -m1 "^$1=" .env | sed 's/^[^=]*=//' | tr -d '\r'
}

# Cargar variables PostgreSQL del archivo .env
if [ -f .env ]; then
    PGHOST=$(get_env_var "PGHOST")
    PGPORT=$(get_env_var "PGPORT")
    PGUSER=$(get_env_var "PGUSER")
    PGDATABASE=$(get_env_var "PGDATABASE")

    # Exportar las variables
    export PGHOST PGPORT PGDATABASE PGUSER 

    echo "Variables PostgreSQL cargadas desde .env:"
    echo "PGHOST: $PGHOST"
    echo "PGPORT: $PGPORT"
    echo "PGUSER: $PGUSER"
    
else
    echo "Archivo .env no encontrado"
    exit 1
fi
# Esperar a que PostgreSQL esté disponible (si usas Railway PostgreSQL)
echo "Esperando conexión a PostgreSQL..."

while ! pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER"; do
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
