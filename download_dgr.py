import os
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import io
from datetime import datetime

# Configuración
FOLDER_ID = '1_jqN8hfdHGbGW4uQYOjIqK6jVnZBJWDa'
DOWNLOAD_DIRECTORY = './downloads'  # Cambia por tu directorio preferido
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

class GoogleDriveDownloader:
    def __init__(self, credentials_file='./credentials/credentials.json', token_file='token.json'):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None
        
    def authenticate(self):
        """Autentica con Google Drive API"""
        creds = None
        
        # El archivo token.json almacena los tokens de acceso y actualización del usuario
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
            
        # Si no hay credenciales válidas disponibles, permite al usuario autenticarse
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
                
            # Guarda las credenciales para la próxima ejecución
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
                
        self.service = build('drive', 'v3', credentials=creds)
        
    def get_latest_file_from_folder(self, folder_id):
        """Obtiene el archivo más reciente de la carpeta especificada"""
        try:
            # Buscar archivos en la carpeta especificada, ordenados por fecha de modificación
            query = f"'{folder_id}' in parents and trashed=false"
            results = self.service.files().list(
                q=query,
                orderBy='modifiedTime desc',  # Más reciente primero
                pageSize=10,  # Solo necesitamos unos pocos
                fields="files(id, name, mimeType, modifiedTime, size)"
            ).execute()
            
            files = results.get('files', [])
            
            if not files:
                print('No se encontraron archivos en la carpeta.')
                return None
                
            # Tomar el primer archivo (más reciente)
            latest_file = files[0]
            print(f"Archivo más reciente encontrado:")
            print(f"  Nombre: {latest_file['name']}")
            print(f"  ID: {latest_file['id']}")
            print(f"  Fecha de modificación: {latest_file['modifiedTime']}")
            print(f"  Tamaño: {latest_file.get('size', 'N/A')} bytes")
            
            return latest_file
            
        except Exception as error:
            print(f'Ocurrió un error al buscar archivos: {error}')
            return None
    
    def download_file(self, file_id, file_name, download_path):
        """Descarga el archivo especificado"""
        try:
            # Crear directorio si no existe
            os.makedirs(download_path, exist_ok=True)
            
            # Ruta completa del archivo
            file_path = os.path.join(download_path, file_name)
            
            # Solicitar el archivo
            request = self.service.files().get_media(fileId=file_id)
            file_io = io.BytesIO()
            downloader = MediaIoBaseDownload(file_io, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
                print(f"Descarga {int(status.progress() * 100)}% completada.")
            
            # Escribir el archivo al disco
            with open(file_path, 'wb') as f:
                f.write(file_io.getvalue())
                
            print(f"Archivo descargado exitosamente: {file_path}")
            return file_path
            
        except Exception as error:
            print(f'Ocurrió un error durante la descarga: {error}')
            return None
    
    def run(self, folder_id, download_directory):
        """Ejecuta el proceso completo"""
        print("Iniciando proceso de descarga...")
        
        # Autenticar
        print("Autenticando con Google Drive...")
        self.authenticate()
        
        # Obtener archivo más reciente
        print(f"Buscando archivo más reciente en la carpeta {folder_id}...")
        latest_file = self.get_latest_file_from_folder(folder_id)
        
        if latest_file:
            # Descargar archivo
            print("Iniciando descarga...")
            downloaded_path = self.download_file(
                latest_file['id'], 
                latest_file['name'], 
                download_directory
            )
            
            if downloaded_path:
                print(f"¡Proceso completado exitosamente!")
                print(f"Archivo guardado en: {downloaded_path}")
                return downloaded_path
            else:
                print("Error durante la descarga.")
                return None
        else:
            print("No se pudo obtener el archivo más reciente.")
            return None

def main():
    # Crear instancia del descargador
    downloader = GoogleDriveDownloader()
    
    # Ejecutar descarga
    result = downloader.run(FOLDER_ID, DOWNLOAD_DIRECTORY)
    
    if result:
        print(f"\n=== RESUMEN ===")
        print(f"Archivo descargado en: {result}")
        print(f"Fecha y hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()