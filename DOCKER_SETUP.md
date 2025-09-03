# Configuración de Credenciales de Google en Docker

Para usar las credenciales de Google Drive API en Docker sin exponerlas en GitHub, sigue estos pasos:

## Opción 1: Variables de entorno (Recomendada)

### 1. Obtener las credenciales JSON
1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea o selecciona un proyecto
3. Habilita Google Drive API
4. Crear credenciales → OAuth client ID → Desktop application
5. Descarga el archivo JSON

### 2. Configurar en .env local
```bash
# Copia el contenido completo del archivo JSON en una sola línea
GOOGLE_CREDENTIALS_JSON={"installed":{"client_id":"123...","project_id":"mi-proyecto","client_secret":"abc...",...}}
```

### 3. Para Docker Compose
```yaml
version: '3.8'
services:
  app:
    build: .
    environment:
      - GOOGLE_CREDENTIALS_JSON=${GOOGLE_CREDENTIALS_JSON}
    volumes:
      - ./downloads:/app/downloads
```

### 4. Para Docker run
```bash
docker run -e GOOGLE_CREDENTIALS_JSON="${GOOGLE_CREDENTIALS_JSON}" -v ./downloads:/app/downloads mi-app
```

## Opción 2: Docker Secrets (Para producción)

### 1. Crear el secret
```bash
echo '{"installed":{"client_id":"...","project_id":"..."}}' | docker secret create google_creds -
```

### 2. Usar en docker-compose.yml
```yaml
version: '3.8'
services:
  app:
    build: .
    secrets:
      - google_creds
    environment:
      - GOOGLE_CREDENTIALS_FILE=/run/secrets/google_creds

secrets:
  google_creds:
    external: true
```

## Opción 3: Volume mount (Para desarrollo)

### 1. Estructura de directorios
```
proyecto/
├── credentials/          # Esta carpeta NO se sube a GitHub
│   └── credentials.json  # Archivo de credenciales
├── .gitignore           # Incluye credentials/
└── docker-compose.yml
```

### 2. Docker compose con volume
```yaml
version: '3.8'
services:
  app:
    build: .
    volumes:
      - ./credentials:/app/credentials:ro  # Solo lectura
      - ./downloads:/app/downloads
```

## Configuración en Railway/Heroku

### Railway
1. Ve a tu proyecto en Railway
2. Variables → New Variable
3. Nombre: `GOOGLE_CREDENTIALS_JSON`
4. Valor: El contenido completo del JSON (en una línea)

### Heroku
```bash
heroku config:set GOOGLE_CREDENTIALS_JSON='{"installed":{"client_id":"..."}}'
```

## Verificación
El script detectará automáticamente si usar:
1. Variable de entorno `GOOGLE_CREDENTIALS_JSON`
2. Archivo local `./credentials/credentials.json`

## Seguridad
- ✅ `.env` está en `.gitignore`
- ✅ `credentials/` está en `.gitignore`
- ✅ `*.json` está en `.gitignore`
- ✅ Variables de entorno no se exponen en logs
- ✅ Archivos temporales se eliminan automáticamente