

https://api.teamplace.finneg.com/api/reports/analisisPedidoVenta
pendientes codigo = 2
curl --request GET \
  --url 'https://api.teamplace.finneg.com/api/reports/analisisPedidoVenta?PARAMWEBREPORT_verPendientes=2&ACCESS_TOKEN={{token}}' \
  --header 'Accept: application/json'


Los parametros de fecha son importantes para que traiga todos los pendientes la API sino trae la ultima semana por defecto.



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