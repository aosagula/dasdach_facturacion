pendientes codigo = 2

pip install playwright
playwright install

pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib


pip install requests

1. Instalación de dependencias:
bashpip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
2. Configuración de credenciales:

Ve a Google Cloud Console
Crea un proyecto nuevo o selecciona uno existente
Habilita la Google Drive API
Crea credenciales (OAuth 2.0 Client ID)
Descarga el archivo JSON y guárdalo como credentials.json en el mismo directorio del script

3. Configuración del script:

FOLDER_ID: Ya está configurado con tu ID
DOWNLOAD_DIRECTORY: Cambia la ruta donde quieres descargar los archivos

4. Ejecución:
bashpython gdrive_downloader.py




pip install psycopg2-binary


python -m playwright codegen https://services.finneg.com/login  --target=python