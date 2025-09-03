import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PythonFileHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_modified = {}
        self.debounce_seconds = 2  # Evitar ejecuciones múltiples
    
    def on_modified(self, event):
        if event.is_directory:
            return
            
        if event.src_path.endswith('.py'):
            current_time = time.time()
            
            # Debouncing para evitar múltiples ejecuciones
            if (event.src_path in self.last_modified and 
                current_time - self.last_modified[event.src_path] < self.debounce_seconds):
                return
                
            self.last_modified[event.src_path] = current_time
            
            logger.info(f"Archivo Python modificado: {event.src_path}")
            self.run_script(event.src_path)
    
    def run_script(self, script_path):
        """Ejecutar script Python con configuración para Playwright headless"""
        try:
            env = os.environ.copy()
            env['PLAYWRIGHT_BROWSERS_PATH'] = '/ms-playwright'
            env['DISPLAY'] = ':99'  # Display virtual para headless
            
            logger.info(f"Ejecutando script: {script_path}")
            
            result = subprocess.run(
                ["python", script_path],
                capture_output=True,
                text=True,
                env=env,
                timeout=300
            )
            
            if result.returncode == 0:
                logger.info(f"Script ejecutado exitosamente: {script_path}")
                if result.stdout:
                    logger.info(f"Output: {result.stdout}")
            else:
                logger.error(f"Error en script {script_path}: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout en script: {script_path}")
        except Exception as e:
            logger.error(f"Error ejecutando script {script_path}: {str(e)}")

def start_file_watcher():
    """Iniciar el monitor de archivos"""
    scripts_dir = "/app/scripts"
    
    # Crear directorio si no existe
    os.makedirs(scripts_dir, exist_ok=True)
    
    event_handler = PythonFileHandler()
    observer = Observer()
    observer.schedule(event_handler, scripts_dir, recursive=True)
    
    observer.start()
    logger.info(f"File watcher iniciado. Monitoreando: {scripts_dir}")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("File watcher detenido")
    
    observer.join()

if __name__ == "__main__":
    start_file_watcher()