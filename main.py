import asyncio
import schedule
import time
import logging
from pathlib import Path
from file_manager import cleanup_temp_files
import subprocess
import os

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path("/app/scripts")

async def run_scheduled_scripts():
    """Ejecutar scripts en horarios programados"""
    
    # Ejemplo: ejecutar script cada 30 minutos
    #schedule.every(30).minutes.do(execute_script, "ejemplo_playwright.py")
    
    # Ejemplo: ejecutar script de video cada 2 horas
    #schedule.every(2).hours.do(execute_script, "ejemplo_video.py")
    
    # Limpiar archivos temporales cada 6 horas
    schedule.every(6).hours.do(cleanup_temp_files, 12)  # Archivos más antiguos que 12 horas
    
    logger.info("📅 Scheduler iniciado")
    
    while True:
        schedule.run_pending()
        await asyncio.sleep(60)  # Verificar cada minuto

def execute_script(script_name):
    """Ejecutar un script específico"""
    script_path = SCRIPTS_DIR / script_name
    
    if not script_path.exists():
        logger.warning(f"⚠️ Script no encontrado: {script_name}")
        return
    
    try:
        logger.info(f"🚀 Ejecutando script programado: {script_name}")
        
        env = os.environ.copy()
        env['PLAYWRIGHT_BROWSERS_PATH'] = '/ms-playwright'
        
        result = subprocess.run(
            ["python", str(script_path)],
            capture_output=True,
            text=True,
            env=env,
            timeout=600  # 10 minutos timeout
        )
        
        if result.returncode == 0:
            logger.info(f"✅ Script completado: {script_name}")
            if result.stdout:
                logger.info(f"Output: {result.stdout[:200]}...")  # Primeros 200 chars
        else:
            logger.error(f"❌ Error en script {script_name}: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        logger.error(f"⏰ Timeout en script: {script_name}")
    except Exception as e:
        logger.error(f"❌ Error ejecutando {script_name}: {str(e)}")

async def run_startup_scripts():
    """Ejecutar scripts que deben correrse al inicio"""
    startup_scripts = [
        "ejemplo_playwright.py",  # Cambiar por tus scripts
        # Agregar más scripts aquí si necesitas
    ]
    
    for script_name in startup_scripts:
        script_path = SCRIPTS_DIR / script_name
        if script_path.exists():
            logger.info(f"🎬 Ejecutando script de inicio: {script_name}")
            execute_script(script_name)
            # Esperar entre scripts para no sobrecargar
            await asyncio.sleep(10)

async def monitor_system():
    """Monitorear sistema y recursos"""
    while True:
        try:
            # Información básica del sistema
            import psutil
            
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/app')
            
            logger.info(f"📊 CPU: {cpu_percent}% | RAM: {memory.percent}% | Disco: {disk.percent}%")
            
            # Verificar si hay mucho uso de recursos
            if cpu_percent > 80:
                logger.warning("⚠️ Alto uso de CPU")
            if memory.percent > 85:
                logger.warning("⚠️ Alta uso de memoria")
            if disk.percent > 90:
                logger.warning("⚠️ Poco espacio en disco")
                
        except ImportError:
            # psutil no está instalado, usar método básico
            pass
        except Exception as e:
            logger.error(f"Error monitoreando sistema: {e}")
        
        # Verificar cada 5 minutos
        await asyncio.sleep(300)

async def main():
    """Función principal"""
    logger.info("🚀 Iniciando ejecutor principal de scripts...")
    
    # Crear directorio de scripts si no existe
    SCRIPTS_DIR.mkdir(exist_ok=True)
    
    # Ejecutar scripts de inicio
    await run_startup_scripts()
    
    # Crear tareas asíncronas
    tasks = [
        asyncio.create_task(run_scheduled_scripts()),
        asyncio.create_task(monitor_system())
    ]
    
    # Ejecutar todas las tareas
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("🛑 Ejecutor principal detenido")
    except Exception as e:
        logger.error(f"❌ Error en ejecutor principal: {e}")

if __name__ == "__main__":
    asyncio.run(main())