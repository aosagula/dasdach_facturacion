import os
import asyncio
from pathlib import Path
import psycopg2
from datetime import datetime
import logging
import shutil
from PIL import Image
import aiofiles

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== DIRECTORIOS PARA GUARDAR ARCHIVOS ====================

# Directorio base para todos los archivos
BASE_DIR = Path("/app")

# Directorios específicos (USAR ESTOS EN TUS SCRIPTS)
PHOTOS_DIR = BASE_DIR / "media" / "photos"      # Para fotos/imágenes
VIDEOS_DIR = BASE_DIR / "media" / "videos"      # Para videos
DATA_DIR = BASE_DIR / "data"                    # Para archivos de datos
TEMP_DIR = BASE_DIR / "temp"                    # Para archivos temporales
UPLOADS_DIR = BASE_DIR / "uploads"              # Para archivos subidos via API

# Crear todos los directorios
def create_directories():
    """Crear estructura de directorios"""
    directories = [PHOTOS_DIR, VIDEOS_DIR, DATA_DIR, TEMP_DIR, UPLOADS_DIR]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"Directorio creado/verificado: {directory}")

# Configuración de base de datos
DB_CONFIG = {
    'host': os.getenv('PGHOST', 'localhost'),
    'port': os.getenv('PGPORT', '5432'),
    'database': os.getenv('PGDATABASE', 'railway'),
    'user': os.getenv('PGUSER', 'postgres'),
    'password': os.getenv('PGPASSWORD', '')
}

async def setup_files_table():
    """Crear tabla para tracking de archivos guardados"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_files (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(500),
                file_type VARCHAR(50),
                file_path TEXT,
                file_size BIGINT,
                script_name VARCHAR(200),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("Tabla de archivos creada/verificada")
    except Exception as e:
        logger.error(f"Error creando tabla: {e}")

async def save_file_record(filename, file_type, file_path, file_size, script_name="unknown"):
    """Guardar registro del archivo en PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO saved_files (filename, file_type, file_path, file_size, script_name)
            VALUES (%s, %s, %s, %s, %s)
        """, (filename, file_type, str(file_path), file_size, script_name))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Registro guardado: {filename}")
    except Exception as e:
        logger.error(f"Error guardando registro: {e}")

# ==================== FUNCIONES PARA USAR EN TUS SCRIPTS ====================

def save_photo(image_data, filename, script_name="playwright_script"):
    """
    Guardar foto/imagen
    
    Args:
        image_data: bytes de la imagen o ruta de archivo temporal
        filename: nombre del archivo (ej: "screenshot_2024.jpg")
        script_name: nombre del script que guarda el archivo
    
    Returns:
        str: ruta completa donde se guardó el archivo
    """
    try:
        file_path = PHOTOS_DIR / filename
        
        # Si image_data es bytes, guardar directamente
        if isinstance(image_data, bytes):
            with open(file_path, 'wb') as f:
                f.write(image_data)
        
        # Si es una ruta de archivo temporal, mover el archivo
        elif isinstance(image_data, (str, Path)):
            shutil.move(str(image_data), str(file_path))
        
        file_size = file_path.stat().st_size
        
        # Guardar registro en base de datos
        asyncio.create_task(save_file_record(
            filename, "photo", file_path, file_size, script_name
        ))
        
        logger.info(f"📸 Foto guardada: {file_path}")
        return str(file_path)
        
    except Exception as e:
        logger.error(f"Error guardando foto: {e}")
        return None

def save_video(video_data, filename, script_name="playwright_script"):
    """
    Guardar video
    
    Args:
        video_data: bytes del video o ruta de archivo temporal
        filename: nombre del archivo (ej: "recording_2024.mp4")
        script_name: nombre del script que guarda el archivo
    
    Returns:
        str: ruta completa donde se guardó el archivo
    """
    try:
        file_path = VIDEOS_DIR / filename
        
        # Si video_data es bytes, guardar directamente
        if isinstance(video_data, bytes):
            with open(file_path, 'wb') as f:
                f.write(video_data)
        
        # Si es una ruta de archivo temporal, mover el archivo
        elif isinstance(video_data, (str, Path)):
            shutil.move(str(video_data), str(file_path))
        
        file_size = file_path.stat().st_size
        
        # Guardar registro en base de datos
        asyncio.create_task(save_file_record(
            filename, "video", file_path, file_size, script_name
        ))
        
        logger.info(f"🎥 Video guardado: {file_path}")
        return str(file_path)
        
    except Exception as e:
        logger.error(f"Error guardando video: {e}")
        return None

def save_data_file(data, filename, script_name="data_script"):
    """
    Guardar archivo de datos (JSON, CSV, TXT, etc.)
    
    Args:
        data: contenido del archivo (str, dict, bytes)
        filename: nombre del archivo (ej: "results.json")
        script_name: nombre del script que guarda el archivo
    
    Returns:
        str: ruta completa donde se guardó el archivo
    """
    try:
        file_path = DATA_DIR / filename
        
        # Guardar según el tipo de datos
        if isinstance(data, bytes):
            with open(file_path, 'wb') as f:
                f.write(data)
        elif isinstance(data, dict):
            import json
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        else:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(str(data))
        
        file_size = file_path.stat().st_size
        
        # Guardar registro en base de datos
        asyncio.create_task(save_file_record(
            filename, "data", file_path, file_size, script_name
        ))
        
        logger.info(f"📄 Archivo de datos guardado: {file_path}")
        return str(file_path)
        
    except Exception as e:
        logger.error(f"Error guardando archivo de datos: {e}")
        return None

def get_temp_path(filename):
    """
    Obtener ruta temporal para archivos temporales
    
    Args:
        filename: nombre del archivo temporal
    
    Returns:
        str: ruta completa del archivo temporal
    """
    return str(TEMP_DIR / filename)

def cleanup_temp_files(older_than_hours=24):
    """
    Limpiar archivos temporales antiguos
    
    Args:
        older_than_hours: eliminar archivos más antiguos que X horas
    """
    try:
        import time
        cutoff_time = time.time() - (older_than_hours * 3600)
        
        for file_path in TEMP_DIR.glob("*"):
            if file_path.stat().st_mtime < cutoff_time:
                file_path.unlink()
                logger.info(f"🗑️ Archivo temporal eliminado: {file_path}")
                
    except Exception as e:
        logger.error(f"Error limpiando archivos temporales: {e}")

def list_saved_files(file_type=None):
    """
    Listar archivos guardados
    
    Args:
        file_type: filtrar por tipo ("photo", "video", "data") o None para todos
    
    Returns:
        list: lista de archivos
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        if file_type:
            cursor.execute("""
                SELECT filename, file_path, file_size, created_at, script_name 
                FROM saved_files 
                WHERE file_type = %s 
                ORDER BY created_at DESC
            """, (file_type,))
        else:
            cursor.execute("""
                SELECT filename, file_path, file_size, created_at, script_name 
                FROM saved_files 
                ORDER BY created_at DESC
            """)
        
        files = cursor.fetchall()
        conn.close()
        
        return files
        
    except Exception as e:
        logger.error(f"Error listando archivos: {e}")
        return []

# ==================== INICIALIZACIÓN ====================

def initialize_file_system():
    """Inicializar sistema de archivos"""
    create_directories()
    asyncio.create_task(setup_files_table())
    logger.info("✅ Sistema de archivos inicializado")

# Ejecutar inicialización al importar el módulo
if __name__ == "__main__":
    initialize_file_system()