 1. Construir la imagen Docker

  docker build -t ventas-app .

  2. Ejecutar el contenedor

  docker run -p 8000:8000 --env-file .env ventas-app

  3. Alternativa con variables de entorno específicas

  docker run -p 8000:8000 \
    -e PORT=8000 \
    -e UVICORN_TIMEOUT=1200 \
    -e DB_HOST=tu_host_db \
    -e DB_PORT=5432 \
    -e DB_NAME=tu_db \
    -e DB_USER=tu_usuario \
    -e DB_PASSWORD=tu_password \
    ventas-app

  4. Para desarrollo con volúmenes montados

  docker run -p 8000:8000 \
    --env-file .env \
    -v $(pwd):/app \
    ventas-app

  Notas importantes:
  - El puerto 8000 se expone automáticamente
  - El archivo .env debe estar presente para las variables de
  entorno
  - El UVICORN_TIMEOUT=1200 (20 minutos) está configurado en tu        
  .env
  - Una vez ejecutando, puedes probar el endpoint de timeout:
  http://localhost:8000/test-timeout/25