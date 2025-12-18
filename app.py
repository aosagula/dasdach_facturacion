from fastapi import FastAPI, File, UploadFile, BackgroundTasks, Query, Form, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
import shutil
import subprocess
import psycopg2
import asyncio
import time
import threading
import requests
import io
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from file_manager import PHOTOS_DIR, VIDEOS_DIR, DATA_DIR, BASE_DIR, UPLOADS_DIR, create_directories
from email_service import send_email_smtp
from smtp_standalone import send_smtp_standalone

# Cargar variables de entorno
load_dotenv()

# Crear directorios necesarios
create_directories()

# Middleware de timeout
class TimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, timeout: int = 30):
        super().__init__(app)
        self.timeout = timeout

    async def dispatch(self, request: Request, call_next):
        try:
            return await asyncio.wait_for(call_next(request), timeout=self.timeout)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=408,
                content={"error": f"Request timeout after {self.timeout} seconds"}
            )

# Configuración de base de datos
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'railway'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '')
}

# Modelos Pydantic
class CuitRequest(BaseModel):
    cuits: List[str]

class CuitResponse(BaseModel):
    cuit: str
    alicuota: Optional[float]
    vigencia_desde: Optional[str]
    vigencia_hasta: Optional[str]
    fecha_emision: Optional[str]
    encontrado: bool

class EmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    body_type: Optional[str] = 'html'  # 'html' o 'text'

app = FastAPI(
    title="Agentic for Business Scripts Runner",
    description="API para ejecutar scripts Python y gestionar archivos multimedia en Railway",
    version="1.0.0",
    contact={
        "name": "Soporte Técnico",
        "url": "https://github.com/aosagula/"
    }
)

# Agregar middleware de timeout (obtener valor desde .env)
timeout_seconds = int(os.getenv('UVICORN_TIMEOUT', '30'))
app.add_middleware(TimeoutMiddleware, timeout=timeout_seconds)

# Servir archivos estáticos usando las rutas dinámicas del file_manager
app.mount("/media/photos", StaticFiles(directory=str(PHOTOS_DIR)), name="photos")
app.mount("/media/videos", StaticFiles(directory=str(VIDEOS_DIR)), name="videos")
app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")

# Directorio para archivos subidos - usar base dinámico
UPLOAD_DIR = UPLOADS_DIR  # Ya viene del file_manager
SCRIPTS_DIR = BASE_DIR / "scripts"

@app.get("/",
    summary="Estado del servidor",
    description="Verifica que el servidor esté funcionando correctamente y muestra la configuración de directorios",
    response_description="Estado del servidor y configuración de directorios",
    responses={
        200: {
            "description": "Servidor funcionando correctamente",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "message": "Railway Python Scripts Runner está funcionando",
                        "directories": {
                            "photos": "/app/media/photos",
                            "videos": "/app/media/videos",
                            "data": "/app/data",
                            "scripts": "/app/scripts"
                        }
                    }
                }
            }
        }
    })
async def health_check():
    return {
        "status": "healthy", 
        "message": "Railway Python Scripts Runner estÃ¡ funcionando",
        "directories": {
            "photos": str(PHOTOS_DIR),
            "videos": str(VIDEOS_DIR),
            "data": str(DATA_DIR),
            "scripts": str(SCRIPTS_DIR)
        }
    }

@app.get("/files/",
    summary="Listar archivos por tipo",
    description="Lista archivos guardados, opcionalmente filtrados por tipo (photo, video, data)",
    response_description="Lista de archivos con información de conteo",
    responses={
        200: {
            "description": "Lista de archivos obtenida exitosamente",
            "content": {
                "application/json": {
                    "examples": {
                        "todos_los_archivos": {
                            "summary": "Obtener todos los archivos",
                            "description": "GET /files/ - Sin parámetros devuelve todos los archivos",
                            "value": {
                                "files": [
                                    {"name": "imagen1.jpg", "type": "photo", "url": "/media/photos/imagen1.jpg"},
                                    {"name": "video1.mp4", "type": "video", "url": "/media/videos/video1.mp4"}
                                ],
                                "total": 2,
                                "file_type": "all"
                            }
                        },
                        "solo_fotos": {
                            "summary": "Filtrar solo fotos",
                            "description": "GET /files/?file_type=photo - Solo archivos de tipo foto",
                            "value": {
                                "files": [
                                    {"name": "imagen1.jpg", "type": "photo", "url": "/media/photos/imagen1.jpg"},
                                    {"name": "imagen2.png", "type": "photo", "url": "/media/photos/imagen2.png"}
                                ],
                                "total": 2,
                                "file_type": "photo"
                            }
                        }
                    }
                }
            }
        }
    })
async def list_files(file_type: str = None):
    """Listar archivos guardados por tipo (photo, video, data). Si no se especifica tipo, devuelve todos."""

    def scan_directory_files(directory, file_type, url_prefix):
        files = []
        if directory.exists():
            for file_path in directory.iterdir():
                if file_path.is_file():
                    files.append({
                        "name": file_path.name,
                        "type": file_type,
                        "url": f"{url_prefix}/{file_path.name}",
                        "size": file_path.stat().st_size,
                        "modified": file_path.stat().st_mtime
                    })
        return files

    all_files = []

    if file_type == "photo" or file_type is None:
        all_files.extend(scan_directory_files(PHOTOS_DIR, "photo", "/media/photos"))

    if file_type == "video" or file_type is None:
        all_files.extend(scan_directory_files(VIDEOS_DIR, "video", "/media/videos"))

    if file_type == "data" or file_type is None:
        all_files.extend(scan_directory_files(DATA_DIR, "data", "/data"))

    # Ordenar por fecha de modificación (más recientes primero)
    all_files.sort(key=lambda x: x["modified"], reverse=True)

    return {
        "files": all_files,
        "total": len(all_files),
        "file_type": file_type or "all"
    }

@app.get("/files/photos/",
    summary="Listar todas las fotos",
    description="Obtiene una lista completa de todas las fotos almacenadas en el servidor",
    response_description="Lista de fotos disponibles",
    responses={
        200: {
            "description": "Lista de fotos obtenida exitosamente",
            "content": {
                "application/json": {
                    "example": {
                        "photos": [
                            {"name": "paisaje.jpg", "type": "photo", "url": "/media/photos/paisaje.jpg"},
                            {"name": "retrato.png", "type": "photo", "url": "/media/photos/retrato.png"},
                            {"name": "screenshot.webp", "type": "photo", "url": "/media/photos/screenshot.webp"}
                        ],
                        "total": 3
                    }
                }
            }
        }
    })
async def list_photos():
    """Lista todas las fotos guardadas en formato JPG, PNG, WebP, etc."""
    photos = []
    if PHOTOS_DIR.exists():
        for file_path in PHOTOS_DIR.iterdir():
            if file_path.is_file():
                photos.append({
                    "name": file_path.name,
                    "type": "photo",
                    "url": f"/media/photos/{file_path.name}",
                    "size": file_path.stat().st_size,
                    "modified": file_path.stat().st_mtime
                })

    # Ordenar por fecha de modificación (más recientes primero)
    photos.sort(key=lambda x: x["modified"], reverse=True)

    return {"photos": photos, "total": len(photos)}

@app.get("/files/videos/",
    summary="Listar todos los videos",
    description="Obtiene una lista completa de todos los videos almacenados en el servidor",
    response_description="Lista de videos disponibles",
    responses={
        200: {
            "description": "Lista de videos obtenida exitosamente",
            "content": {
                "application/json": {
                    "example": {
                        "videos": [
                            {"name": "presentacion.mp4", "type": "video", "url": "/media/videos/presentacion.mp4"},
                            {"name": "demo.webm", "type": "video", "url": "/media/videos/demo.webm"},
                            {"name": "tutorial.mov", "type": "video", "url": "/media/videos/tutorial.mov"}
                        ],
                        "total": 3
                    }
                }
            }
        }
    })
async def list_videos():
    """Lista todos los videos guardados en formato MP4, WebM, MOV, etc."""
    videos = []
    if VIDEOS_DIR.exists():
        for file_path in VIDEOS_DIR.iterdir():
            if file_path.is_file():
                videos.append({
                    "name": file_path.name,
                    "type": "video",
                    "url": f"/media/videos/{file_path.name}",
                    "size": file_path.stat().st_size,
                    "modified": file_path.stat().st_mtime
                })

    # Ordenar por fecha de modificación (más recientes primero)
    videos.sort(key=lambda x: x["modified"], reverse=True)

    return {"videos": videos, "total": len(videos)}

@app.get("/download/{file_type}/{filename}",
    summary="Descargar archivo",
    description="Descarga un archivo específico por tipo y nombre de archivo",
    response_description="Archivo descargado o mensaje de error",
    responses={
        200: {
            "description": "Archivo descargado exitosamente",
            "content": {
                "application/octet-stream": {
                    "example": "[Contenido binario del archivo]"
                }
            }
        },
        400: {
            "description": "Tipo de archivo inválido",
            "content": {
                "application/json": {
                    "example": {
                        "error": "Tipo de archivo no válido. Usar: photo, video, data"
                    }
                }
            }
        },
        404: {
            "description": "Archivo no encontrado",
            "content": {
                "application/json": {
                    "example": {
                        "error": "Archivo no encontrado"
                    }
                }
            }
        }
    })
async def download_file(file_type: str, filename: str):
    """
    Descarga un archivo por tipo y nombre.
    
    - **file_type**: Tipo de archivo (photo, video, data)
    - **filename**: Nombre del archivo a descargar
    
    Ejemplos de uso:
    - GET /download/photo/imagen.jpg
    - GET /download/video/video.mp4
    - GET /download/data/archivo.json
    """
    try:
        if file_type == "photo":
            file_path = PHOTOS_DIR / filename
        elif file_type == "video":
            file_path = VIDEOS_DIR / filename
        elif file_type == "data":
            file_path = DATA_DIR / filename
        else:
            return JSONResponse(
                status_code=400,
                content={"error": "Tipo de archivo no vÃ¡lido. Usar: photo, video, data"}
            )
        
        if not file_path.exists():
            return JSONResponse(
                status_code=404,
                content={"error": "Archivo no encontrado"}
            )
        
        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type='application/octet-stream'
        )
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error descargando archivo: {str(e)}"}
        )

@app.post("/upload-script/",
    summary="Subir script Python",
    description="Sube un archivo .py al servidor y opcionalmente lo ejecuta en segundo plano",
    response_description="Confirmación de subida del script",
    responses={
        200: {
            "description": "Script subido exitosamente",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Script mi_script.py subido exitosamente"
                    }
                }
            }
        },
        500: {
            "description": "Error al subir el script",
            "content": {
                "application/json": {
                    "example": {
                        "error": "Error al subir script: [detalle del error]"
                    }
                }
            }
        }
    })
async def upload_script(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """
    Sube un script Python (.py) al servidor.
    
    - **file**: Archivo .py a subir
    - **background_tasks**: Si está presente, ejecuta el script en segundo plano automáticamente
    
    El archivo se guarda en /app/scripts/ y puede ejecutarse posteriormente con los endpoints de ejecución.
    """
    try:
        # Guardar archivo
        file_path = SCRIPTS_DIR / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Ejecutar script en background si se especifica
        if background_tasks:
            background_tasks.add_task(run_python_script, str(file_path))
        
        return {"message": f"Script {file.filename} subido exitosamente"}
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error al subir script: {str(e)}"}
        )

# ============= NUEVO: ENDPOINT GET PARA PARÁMETROS SIMPLES =============
@app.get("/run-script/{script_name}",
    summary="Ejecutar script vía GET (simple)",
    description="Ejecuta un script con parámetros simples vía URL. Método simplificado para ejecuciones rápidas",
    response_description="Resultado de la ejecución del script",
    responses={
        200: {
            "description": "Script ejecutado exitosamente",
            "content": {
                "application/json": {
                    "examples": {
                        "sin_argumentos": {
                            "summary": "Ejecución sin argumentos",
                            "description": "GET /run-script/script.py",
                            "value": {
                                "message": "Script ejecutado",
                                "script": "script.py",
                                "args": [],
                                "output": {
                                    "stdout": "Resultado del script",
                                    "stderr": "",
                                    "returncode": 0,
                                    "command": "python /app/scripts/script.py"
                                }
                            }
                        },
                        "con_argumentos": {
                            "summary": "Ejecución con argumentos",
                            "description": "GET /run-script/process_data.py?args=archivo1.csv,output.json&timeout=600",
                            "value": {
                                "message": "Script ejecutado",
                                "script": "process_data.py",
                                "args": ["archivo1.csv", "output.json"],
                                "output": {
                                    "stdout": "Procesando archivo1.csv...\nGuardado en output.json",
                                    "stderr": "",
                                    "returncode": 0,
                                    "command": "python /app/scripts/process_data.py archivo1.csv output.json"
                                }
                            }
                        }
                    }
                }
            }
        },
        404: {
            "description": "Script no encontrado",
            "content": {
                "application/json": {
                    "example": {
                        "error": "Script no encontrado"
                    }
                }
            }
        }
    })
async def run_script_get(
    script_name: str, 
    args: str = None, 
    timeout: int = 300
):
    """
    Ejecuta un script Python vía GET con parámetros simples.
    
    - **script_name**: Nombre del script a ejecutar (debe existir en /app/scripts/)
    - **args**: Argumentos separados por comas (opcional). Ejemplo: "param1,param2,param3"
    - **timeout**: Timeout en segundos (por defecto 300 = 5 minutos)
    
    Ejemplos de uso:
    - GET /run-script/mi_script.py
    - GET /run-script/process.py?args=input.txt,output.txt
    - GET /run-script/long_task.py?timeout=1800&args=config.json
    """
    script_path = SCRIPTS_DIR / script_name
    
    if not script_path.exists():
        return JSONResponse(
            status_code=404,
            content={"error": "Script no encontrado"}
        )
    
    try:
        # Parsear argumentos separados por comas
        script_args = []
        if args:
            script_args = [arg.strip() for arg in args.split(",")]
        
        result = await run_python_script(str(script_path), script_args, timeout=timeout)
        return {
            "message": "Script ejecutado", 
            "script": script_name,
            "args": script_args,
            "output": result
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error al ejecutar script: {str(e)}"}
        )

# ============= ACTUALIZADO: ENDPOINT POST CON PARÁMETROS =============
@app.post("/run-script/{script_name}",
    summary="Ejecutar script vía POST (avanzado)",
    description="Ejecuta un script con parámetros avanzados vía JSON. Soporta argumentos, variables de entorno y timeout personalizado",
    response_description="Resultado de la ejecución con detalles completos",
    responses={
        200: {
            "description": "Script ejecutado exitosamente",
            "content": {
                "application/json": {
                    "examples": {
                        "simple": {
                            "summary": "Ejecución simple",
                            "description": "POST sin parámetros adicionales",
                            "value": {
                                "message": "Script ejecutado",
                                "output": {
                                    "stdout": "Hello World",
                                    "stderr": "",
                                    "returncode": 0,
                                    "command": "python /app/scripts/hello.py"
                                }
                            }
                        },
                        "con_parametros": {
                            "summary": "Ejecución con parámetros",
                            "description": "POST con args, env_vars y timeout",
                            "value": {
                                "message": "Script ejecutado",
                                "args": ["input.csv", "processed"],
                                "env_vars": {"API_KEY": "secret123"},
                                "timeout": 600,
                                "output": {
                                    "stdout": "Archivo procesado exitosamente",
                                    "stderr": "",
                                    "returncode": 0,
                                    "command": "python /app/scripts/process.py input.csv processed"
                                }
                            }
                        }
                    }
                }
            }
        },
        404: {
            "description": "Script no encontrado",
            "content": {
                "application/json": {
                    "example": {
                        "error": "Script no encontrado"
                    }
                }
            }
        }
    })
async def run_script_endpoint(script_name: str, parameters: dict = None):
    """
    Ejecuta un script con parámetros avanzados vía POST.
    
    - **script_name**: Nombre del script a ejecutar
    - **parameters** (opcional): JSON con:
      - **args**: Lista de argumentos para el script
      - **env_vars**: Diccionario de variables de entorno
      - **timeout**: Timeout en segundos (por defecto 300)
    
    Ejemplo de body JSON:
    ```json
    {
        "args": ["archivo_entrada.txt", "archivo_salida.json"],
        "env_vars": {
            "API_KEY": "mi_clave_secreta",
            "DEBUG": "true"
        },
        "timeout": 600
    }
    ```
    
    Si no se envían parámetros, el script se ejecuta sin argumentos adicionales.
    """
    script_path = SCRIPTS_DIR / script_name
    
    if not script_path.exists():
        return JSONResponse(
            status_code=404,
            content={"error": "Script no encontrado"}
        )
    
    try:
        # Parsear parámetros del body (nuevo)
        args = []
        env_vars = {}
        timeout = 300  # default 5 minutos
        
        if parameters:
            args = parameters.get("args", [])
            env_vars = parameters.get("env_vars", {})
            timeout = parameters.get("timeout", 300)
        
        # Usar la función actualizada
        result = await run_python_script(str(script_path), args, env_vars, timeout)
        
        # Respuesta mejorada con información de parámetros
        response = {"message": "Script ejecutado", "output": result}
        
        if args:
            response["args"] = args
        if env_vars:
            response["env_vars"] = env_vars
        if timeout != 300:
            response["timeout"] = timeout
            
        return response
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error al ejecutar script: {str(e)}"}
        )

# ============= ACTUALIZADA: FUNCIÓN PARA EJECUTAR SCRIPTS =============
async def run_python_script(script_path: str, args: list = None, env_vars: dict = None, timeout: int = 300):
    """
    Ejecuta un script Python con soporte completo para argumentos y variables de entorno.

    Args:
        script_path: Ruta completa al script Python
        args: Lista de argumentos para pasar al script
        env_vars: Diccionario de variables de entorno adicionales
        timeout: Timeout máximo de ejecución en segundos

    Returns:
        dict: Resultado con stdout, stderr, returncode y comando ejecutado
    """
    loop = asyncio.get_running_loop()

    env = os.environ.copy()
    env['PLAYWRIGHT_BROWSERS_PATH'] = '/ms-playwright'

    # Agregar variables de entorno personalizadas (nuevo)
    if env_vars:
        env.update(env_vars)

    # Construir comando (mejorado)
    command = ["python", script_path]
    if args:
        command.extend([str(arg) for arg in args])  # Convertir todos los args a string

    def _run():
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout
            )

            # Respuesta mejorada con información del comando
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "command": " ".join(command)  # nuevo: mostrar comando ejecutado
            }

        except subprocess.TimeoutExpired:
            return {
                "error": f"Script timeout ({timeout}s)",
                "command": " ".join(command)
            }
        except Exception as e:
            return {
                "error": str(e),
                "command": " ".join(command)
            }

    return await loop.run_in_executor(None, _run)



@app.get("/scripts/")
async def list_scripts():
    """Listar scripts disponibles"""
    try:
        scripts = [f.name for f in SCRIPTS_DIR.glob("*.py")]
        return {"scripts": scripts}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

# ============= ENDPOINTS PARA CONSULTA DE ALÍCUOTAS POR CUIT =============

@app.get("/alicuota/{cuit}",
    summary="Consultar alícuota por CUIT individual",
    description="Obtiene la alícuota de un CUIT específico desde el padrón RGS",
    response_description="Información de alícuota para el CUIT consultado",
    responses={
        200: {
            "description": "Consulta realizada exitosamente",
            "content": {
                "application/json": {
                    "examples": {
                        "encontrado": {
                            "summary": "CUIT encontrado",
                            "value": {
                                "cuit": "20123456784",
                                "alicuota": 10.5,
                                "vigencia_desde": "2025-01-01",
                                "vigencia_hasta": "2025-12-31",
                                "fecha_emision": "2025-01-01",
                                "encontrado": True
                            }
                        },
                        "no_encontrado": {
                            "summary": "CUIT no encontrado",
                            "value": {
                                "cuit": "20999999999",
                                "alicuota": None,
                                "vigencia_desde": None,
                                "vigencia_hasta": None,
                                "fecha_emision": None,
                                "encontrado": False
                            }
                        }
                    }
                }
            }
        },
        400: {
            "description": "CUIT inválido",
            "content": {
                "application/json": {
                    "example": {
                        "error": "CUIT debe tener 11 dígitos"
                    }
                }
            }
        }
    })
async def get_alicuota_cuit(cuit: str):
    """
    Consulta la alícuota de un CUIT específico.
    
    - **cuit**: CUIT de 11 dígitos (solo números)
    
    Retorna la alícuota vigente más reciente del CUIT consultado.
    """
    # Validar formato CUIT
    cuit_clean = cuit.replace("-", "").replace(" ", "")
    if not cuit_clean.isdigit() or len(cuit_clean) != 11:
        return JSONResponse(
            status_code=400,
            content={"error": "CUIT debe tener 11 dígitos"}
        )
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # Consultar alícuota más reciente para el CUIT
        cur.execute("""
            SELECT cuit, alicuota, vigencia_desde, vigencia_hasta, fecha_emision
            FROM padron_rgs 
            WHERE cuit = %s 
            ORDER BY fecha_emision DESC, vigencia_desde DESC
            LIMIT 1
        """, (cuit_clean,))
        
        result = cur.fetchone()
        conn.close()
        
        if result:
            return CuitResponse(
                cuit=result[0],
                alicuota=float(result[1]) if result[1] is not None else None,
                vigencia_desde=result[2].strftime('%Y-%m-%d') if result[2] else None,
                vigencia_hasta=result[3].strftime('%Y-%m-%d') if result[3] else None,
                fecha_emision=result[4].strftime('%Y-%m-%d') if result[4] else None,
                encontrado=True
            )
        else:
            return CuitResponse(
                cuit=cuit_clean,
                alicuota=None,
                vigencia_desde=None,
                vigencia_hasta=None,
                fecha_emision=None,
                encontrado=False
            )
            
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error consultando base de datos: {str(e)}"}
        )

@app.post("/alicuotas/",
    summary="Consultar alícuotas por lista de CUITs",
    description="Obtiene las alícuotas de múltiples CUITs de una sola vez",
    response_description="Lista con información de alícuota para cada CUIT consultado",
    responses={
        200: {
            "description": "Consulta realizada exitosamente",
            "content": {
                "application/json": {
                    "example": {
                        "resultados": [
                            {
                                "cuit": "20123456784",
                                "alicuota": 10.5,
                                "vigencia_desde": "2025-01-01",
                                "vigencia_hasta": "2025-12-31",
                                "fecha_emision": "2025-01-01",
                                "encontrado": True
                            },
                            {
                                "cuit": "20999999999",
                                "alicuota": None,
                                "vigencia_desde": None,
                                "vigencia_hasta": None,
                                "fecha_emision": None,
                                "encontrado": False
                            }
                        ],
                        "total_consultados": 2,
                        "encontrados": 1,
                        "no_encontrados": 1
                    }
                }
            }
        },
        400: {
            "description": "Lista de CUITs inválida",
            "content": {
                "application/json": {
                    "example": {
                        "error": "Debe proporcionar al menos un CUIT"
                    }
                }
            }
        }
    })
async def get_alicuotas_multiple(request: CuitRequest):
    """
    Consulta las alícuotas de múltiples CUITs.
    
    Body JSON:
    ```json
    {
        "cuits": ["20123456784", "27987654321", "30555666777"]
    }
    ```
    
    Retorna la alícuota vigente más reciente para cada CUIT consultado.
    """
    if not request.cuits:
        return JSONResponse(
            status_code=400,
            content={"error": "Debe proporcionar al menos un CUIT"}
        )
    
    # Validar y limpiar CUITs
    cuits_clean = []
    for cuit in request.cuits:
        cuit_clean = cuit.replace("-", "").replace(" ", "")
        if not cuit_clean.isdigit() or len(cuit_clean) != 11:
            return JSONResponse(
                status_code=400,
                content={"error": f"CUIT inválido: {cuit} (debe tener 11 dígitos)"}
            )
        cuits_clean.append(cuit_clean)
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        resultados = []
        encontrados = 0
        
        for cuit in cuits_clean:
            # Consultar alícuota más reciente para cada CUIT
            cur.execute("""
                SELECT cuit, alicuota, vigencia_desde, vigencia_hasta, fecha_emision
                FROM padron_rgs 
                WHERE cuit = %s 
                ORDER BY fecha_emision DESC, vigencia_desde DESC
                LIMIT 1
            """, (cuit,))
            
            result = cur.fetchone()
            
            if result:
                resultados.append(CuitResponse(
                    cuit=result[0],
                    alicuota=float(result[1]) if result[1] is not None else None,
                    vigencia_desde=result[2].strftime('%Y-%m-%d') if result[2] else None,
                    vigencia_hasta=result[3].strftime('%Y-%m-%d') if result[3] else None,
                    fecha_emision=result[4].strftime('%Y-%m-%d') if result[4] else None,
                    encontrado=True
                ))
                encontrados += 1
            else:
                resultados.append(CuitResponse(
                    cuit=cuit,
                    alicuota=None,
                    vigencia_desde=None,
                    vigencia_hasta=None,
                    fecha_emision=None,
                    encontrado=False
                ))
        
        conn.close()
        
        return {
            "resultados": resultados,
            "total_consultados": len(cuits_clean),
            "encontrados": encontrados,
            "no_encontrados": len(cuits_clean) - encontrados
        }
            
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error consultando base de datos: {str(e)}"}
        )

@app.get("/alicuotas/",
    summary="Consultar alícuotas por CUITs vía GET",
    description="Obtiene las alícuotas de múltiples CUITs mediante parámetros GET",
    response_description="Lista con información de alícuota para cada CUIT consultado",
    responses={
        200: {
            "description": "Consulta realizada exitosamente",
            "content": {
                "application/json": {
                    "example": {
                        "resultados": [
                            {
                                "cuit": "20123456784",
                                "alicuota": 10.5,
                                "encontrado": True
                            }
                        ],
                        "total_consultados": 1,
                        "encontrados": 1
                    }
                }
            }
        }
    })
async def get_alicuotas_get(cuits: List[str] = Query(..., description="Lista de CUITs separados por comas")):
    """
    Consulta las alícuotas de múltiples CUITs vía GET.

    Ejemplo de uso:
    - GET /alicuotas/?cuits=20123456784&cuits=27987654321&cuits=30555666777
    """
    return await get_alicuotas_multiple(CuitRequest(cuits=cuits))

# ============= ENDPOINT PARA ENVÍO DE EMAILS =============

@app.post("/send-email/",
    summary="Enviar email vía Gmail",
    description="Envía un email usando Gmail API con soporte para adjuntos",
    response_description="Confirmación del envío del email",
    responses={
        200: {
            "description": "Email enviado exitosamente",
            "content": {
                "application/json": {
                    "examples": {
                        "sin_adjunto": {
                            "summary": "Envío sin adjunto",
                            "description": "Email enviado solo con texto/HTML",
                            "value": {
                                "success": True,
                                "message": "Email enviado exitosamente a usuario@ejemplo.com",
                                "message_id": "1234567890abcdef",
                                "details": {
                                    "to": "usuario@ejemplo.com",
                                    "subject": "Asunto del email",
                                    "body_type": "html",
                                    "attachment": None
                                }
                            }
                        },
                        "con_adjunto": {
                            "summary": "Envío con adjunto",
                            "description": "Email enviado con archivo adjunto",
                            "value": {
                                "success": True,
                                "message": "Email enviado exitosamente a cliente@empresa.com",
                                "message_id": "0987654321fedcba",
                                "details": {
                                    "to": "cliente@empresa.com",
                                    "subject": "Factura Electrónica",
                                    "body_type": "html",
                                    "attachment": "factura_001.pdf"
                                }
                            }
                        }
                    }
                }
            }
        },
        400: {
            "description": "Parámetros inválidos",
            "content": {
                "application/json": {
                    "example": {
                        "error": "Email de destino requerido"
                    }
                }
            }
        },
        500: {
            "description": "Error al enviar email",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "error": "Error de Gmail API: credenciales inválidas"
                    }
                }
            }
        }
    })
async def send_email_endpoint(
    request: Request,
    attachment: Optional[UploadFile] = File(None)
):
    """
    Envía un email usando SMTP standalone (modificado para evitar problemas con Gmail API).
    Acepta tanto JSON como form-data.

    **Modo 1 - JSON (Content-Type: application/json):**
    ```json
    {
        "to": "destinatario@email.com",
        "subject": "Asunto",
        "body": "Mensaje",
        "body_type": "html"
    }
    ```

    **Modo 2 - Form-data:**
    - to: Email destino
    - subject: Asunto
    - body: Mensaje
    - body_type: html/text
    - attachment: archivo (opcional)

    **Configuración requerida en .env:**
    ```
    SMTP_SERVER=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USERNAME=tu-email@gmail.com
    SMTP_PASSWORD=tu-app-password
    SMTP_SENDER_EMAIL=tu-email@gmail.com
    ```
    """

    try:
        # Detectar tipo de contenido
        content_type = request.headers.get("content-type", "").lower()

        if "application/json" in content_type:
            # Modo JSON
            try:
                json_data = await request.json()
                to = json_data.get('to')
                subject = json_data.get('subject')
                body = json_data.get('body')
                body_type = json_data.get('body_type', 'html')
            except Exception as e:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": f"Error parseando JSON: {str(e)}",
                        "endpoint": "send-email"
                    }
                )
        else:
            # Modo form-data
            try:
                form_data = await request.form()
                to = form_data.get('to')
                subject = form_data.get('subject')
                body = form_data.get('body')
                body_type = form_data.get('body_type', 'html')
            except Exception as e:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": f"Error parseando form-data: {str(e)}",
                        "endpoint": "send-email"
                    }
                )

        # Validar parámetros
        if not to or '@' not in to:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Email de destino requerido y debe ser válido",
                    "endpoint": "send-email"
                }
            )

        if not subject:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Asunto del email requerido",
                    "endpoint": "send-email"
                }
            )

        if not body:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Cuerpo del email requerido",
                    "endpoint": "send-email"
                }
            )

        attachment_path = None
        attachment_filename = None

        # Procesar archivo adjunto si se proporciona
        if attachment:
            # Crear directorio temporal para adjuntos
            temp_dir = Path("/tmp/email_attachments")
            temp_dir.mkdir(exist_ok=True)

            # Guardar archivo temporal
            attachment_path = temp_dir / attachment.filename
            attachment_filename = attachment.filename

            with open(attachment_path, "wb") as buffer:
                shutil.copyfileobj(attachment.file, buffer)

        # Enviar email usando SMTP standalone para evitar problemas OAuth
        result = send_smtp_standalone(
            to=to,
            subject=subject,
            body=body,
            body_type=body_type,
            attachment_path=str(attachment_path) if attachment_path else None
        )

        # Limpiar archivo temporal
        if attachment_path and attachment_path.exists():
            try:
                attachment_path.unlink()
            except:
                pass  # Ignorar errores de limpieza

        # Preparar respuesta
        if result.get('success'):
            response_data = {
                "success": True,
                "message": result.get('message'),
                "smtp_server": result.get('smtp_server'),
                "sender": result.get('sender'),
                "method": result.get('method'),
                "endpoint": "send-email",
                "details": {
                    "to": to,
                    "subject": subject,
                    "body_type": body_type,
                    "attachment": attachment_filename,
                    "content_type_detected": content_type
                }
            }
            return response_data
        else:
            error_response = {
                "success": False,
                "error": result.get('error'),
                "endpoint": "send-email",
                "smtp_error_type": result.get('smtp_error'),
                "details": result.get('details')
            }

            if result.get('missing_config'):
                error_response["suggestion"] = "Configura SMTP_USERNAME y SMTP_PASSWORD en .env"
            elif result.get('smtp_error') == 'authentication':
                error_response["suggestion"] = "Genera App Password en Gmail y úsala en SMTP_PASSWORD"

            return JSONResponse(
                status_code=500,
                content=error_response
            )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Error inesperado: {str(e)}",
                "endpoint": "send-email",
                "exception_type": type(e).__name__
            }
        )

@app.post("/send-email-form/",
    summary="Enviar email vía formulario (compatible con n8n)",
    description="Envía email usando parámetros de formulario, ideal para integraciones con n8n HTTP Request nodes",
    response_description="Confirmación del envío del email"
)
async def send_email_form(
    to: str = Form(..., description="Email de destino"),
    subject: str = Form(..., description="Asunto del email"),
    body: str = Form(..., description="Cuerpo del email en HTML o texto"),
    body_type: str = Form('html', description="Tipo de cuerpo: 'html' o 'text'"),
    attachment: Optional[UploadFile] = File(None, description="Archivo adjunto opcional")
):
    """
    Versión alternativa del endpoint de email que acepta parámetros via form-data.
    Especialmente útil para integraciones con n8n HTTP Request nodes.

    **Parámetros de formulario:**
    - **to**: Email de destino
    - **subject**: Asunto del email
    - **body**: Cuerpo del email
    - **body_type**: 'html' o 'text' (opcional, por defecto 'html')
    - **attachment**: Archivo adjunto (opcional)

    **Configuración en n8n HTTP Request:**
    - Method: POST
    - URL: http://tu-servidor:8000/send-email-form/
    - Body Content Type: Form-Data
    - Parameters:
      - to: {{ $json.email }}
      - subject: {{ $json.subject }}
      - body: {{ $json.html_content }}
      - body_type: html
      - attachment: [archivo desde nodo anterior]
    """

    # Usar el mismo código que send-email-n8n para evitar conflictos con Gmail API
    try:
        # Validar parámetros básicos
        if not to or '@' not in to:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Email de destino requerido y debe ser válido",
                    "endpoint": "send-email-form"
                }
            )

        if not subject:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Asunto del email requerido",
                    "endpoint": "send-email-form"
                }
            )

        if not body:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Cuerpo del email requerido",
                    "endpoint": "send-email-form"
                }
            )

        attachment_path = None
        attachment_filename = None

        # Procesar archivo adjunto si se proporciona
        if attachment:
            # Crear directorio temporal para adjuntos
            temp_dir = Path("/tmp/email_attachments")
            temp_dir.mkdir(exist_ok=True)

            # Guardar archivo temporal
            attachment_path = temp_dir / attachment.filename
            attachment_filename = attachment.filename

            with open(attachment_path, "wb") as buffer:
                shutil.copyfileobj(attachment.file, buffer)

        # Enviar email usando el servicio standalone
        result = send_smtp_standalone(
            to=to,
            subject=subject,
            body=body,
            body_type=body_type,
            attachment_path=str(attachment_path) if attachment_path else None
        )

        # Limpiar archivo temporal
        if attachment_path and attachment_path.exists():
            try:
                attachment_path.unlink()
            except:
                pass  # Ignorar errores de limpieza

        # Preparar respuesta
        if result.get('success'):
            response_data = {
                "success": True,
                "message": result.get('message'),
                "smtp_server": result.get('smtp_server'),
                "sender": result.get('sender'),
                "method": result.get('method'),
                "endpoint": "send-email-form",
                "details": {
                    "to": to,
                    "subject": subject,
                    "body_type": body_type,
                    "attachment": attachment_filename
                }
            }
            return response_data
        else:
            # Agregar información de debug
            error_response = {
                "success": False,
                "error": result.get('error'),
                "endpoint": "send-email-form",
                "smtp_error_type": result.get('smtp_error'),
                "details": result.get('details')
            }

            # Agregar sugerencias según el tipo de error
            if result.get('missing_config'):
                error_response["suggestion"] = "Configura SMTP_USERNAME y SMTP_PASSWORD en .env"
            elif result.get('smtp_error') == 'authentication':
                error_response["suggestion"] = "Genera App Password en Gmail y úsala en SMTP_PASSWORD"

            return JSONResponse(
                status_code=500,
                content=error_response
            )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Error inesperado: {str(e)}",
                "endpoint": "send-email-form",
                "exception_type": type(e).__name__
            }
        )

@app.post("/send-email-smtp/",
    summary="Enviar email vía SMTP (ideal para n8n)",
    description="Envía email usando SMTP con Gmail. Configuración simple para n8n HTTP Request nodes",
    response_description="Confirmación del envío del email vía SMTP"
)
async def send_email_smtp_endpoint(
    to: str = Form(..., description="Email de destino"),
    subject: str = Form(..., description="Asunto del email"),
    body: str = Form(..., description="Cuerpo del email en HTML o texto"),
    body_type: str = Form('html', description="Tipo de cuerpo: 'html' o 'text'"),
    attachment: Optional[UploadFile] = File(None, description="Archivo adjunto opcional")
):
    """
    Envía un email usando SMTP (Simple Mail Transfer Protocol).
    Ideal para integración con n8n y configuración más simple que Gmail API.

    **Parámetros de formulario:**
    - **to**: Email de destino (ej: pepe@gmail.com)
    - **subject**: Asunto del email
    - **body**: Cuerpo del email (puede ser HTML o texto plano)
    - **body_type**: 'html' o 'text' (opcional, por defecto 'html')
    - **attachment**: Archivo adjunto (opcional)

    **Configuración requerida en .env:**
    ```
    SMTP_SERVER=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USERNAME=tu-email@gmail.com
    SMTP_PASSWORD=tu-app-password
    SMTP_SENDER_EMAIL=tu-email@gmail.com  # opcional, usa SMTP_USERNAME por defecto
    ```

    **Para Gmail, necesitas usar App Password:**
    1. Activar autenticación de 2 factores en tu cuenta Google
    2. Ir a https://myaccount.google.com/apppasswords
    3. Generar una contraseña de aplicación
    4. Usar esa contraseña en SMTP_PASSWORD

    **Configuración en n8n HTTP Request:**
    - Method: POST
    - URL: http://tu-servidor:8000/send-email-smtp/
    - Body Content Type: Form-Data
    - Parameters:
      - to: {{ $json.destinatario }}
      - subject: {{ $json.asunto }}
      - body: {{ $json.mensaje }}
      - body_type: html
      - attachment: [archivo desde nodo anterior si es necesario]

    **Ejemplo con curl:**
    ```bash
    curl -X POST "http://localhost:8000/send-email-smtp/" \\
         -F "to=pepe@gmail.com" \\
         -F "subject=Prueba desde API" \\
         -F "body=<h1>Hola!</h1><p>Este es un mensaje de prueba.</p>" \\
         -F "body_type=html"
    ```

    **Con adjunto:**
    ```bash
    curl -X POST "http://localhost:8000/send-email-smtp/" \\
         -F "to=pepe@gmail.com" \\
         -F "subject=Con adjunto" \\
         -F "body=<p>Email con archivo adjunto</p>" \\
         -F "attachment=@/ruta/al/archivo.pdf"
    ```
    """

    try:
        # Validar email de destino
        if not to or '@' not in to:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Email de destino requerido y debe ser válido"}
            )

        # Validar asunto
        if not subject:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Asunto del email requerido"}
            )

        # Validar cuerpo
        if not body:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Cuerpo del email requerido"}
            )

        attachment_path = None
        attachment_filename = None

        # Procesar archivo adjunto si se proporciona
        if attachment:
            # Crear directorio temporal para adjuntos
            temp_dir = Path("/tmp/email_attachments")
            temp_dir.mkdir(exist_ok=True)

            # Guardar archivo temporal
            attachment_path = temp_dir / attachment.filename
            attachment_filename = attachment.filename

            with open(attachment_path, "wb") as buffer:
                shutil.copyfileobj(attachment.file, buffer)

        # Enviar email vía SMTP
        result = send_email_smtp(
            to=to,
            subject=subject,
            body=body,
            body_type=body_type,
            attachment_path=str(attachment_path) if attachment_path else None
        )

        # Limpiar archivo temporal
        if attachment_path and attachment_path.exists():
            try:
                attachment_path.unlink()
            except:
                pass  # Ignorar errores de limpieza

        # Preparar respuesta
        if result.get('success'):
            response_data = {
                "success": True,
                "message": result.get('message'),
                "smtp_server": result.get('smtp_server'),
                "details": {
                    "to": to,
                    "subject": subject,
                    "body_type": body_type,
                    "attachment": attachment_filename,
                    "method": "SMTP"
                }
            }
            return response_data
        else:
            return JSONResponse(
                status_code=500,
                content=result
            )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Error inesperado: {str(e)}"
            }
        )

@app.post("/send-email-n8n/",
    summary="Enviar email para n8n (SMTP puro)",
    description="Endpoint SMTP completamente independiente, ideal para n8n sin conflictos con Gmail API",
    response_description="Confirmación del envío del email"
)
async def send_email_n8n_endpoint(
    request: Request,
    to: str = Form(..., description="Email de destino"),
    subject: str = Form(..., description="Asunto del email"),
    body: str = Form(..., description="Cuerpo del email en HTML o texto"),
    body_type: str = Form('html', description="Tipo de cuerpo: 'html' o 'text'"),
    attachment: Optional[UploadFile] = File(None, description="Archivo adjunto opcional")
):
    """
    Endpoint SMTP completamente independiente para n8n.
    No usa Gmail API, solo SMTP puro.

    **Configuración requerida en .env:**
    ```
    SMTP_SERVER=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USERNAME=tu-email@gmail.com
    SMTP_PASSWORD=tu-app-password
    SMTP_SENDER_EMAIL=tu-email@gmail.com
    ```

    **Configuración en n8n HTTP Request:**
    - Method: POST
    - URL: http://tu-servidor:8000/send-email-n8n/
    - Body Content Type: Form-Data
    - Parameters:
      - to: pepe@gmail.com
      - subject: Asunto del email
      - body: Mensaje del email
      - body_type: html (opcional)
      - attachment: archivo (opcional)

    **Diferencias con otros endpoints:**
    - Este endpoint NO usa Gmail API
    - Es completamente independiente
    - Ideal para Docker/contenedores
    - Sin conflictos de autenticación OAuth
    """

    try:
        # Logging para debug de n8n
        print(f"[DEBUG] /send-email-n8n/ POST recibido")
        print(f"[DEBUG] Method: {request.method}")
        print(f"[DEBUG] URL: {request.url}")
        print(f"[DEBUG] Headers: {dict(request.headers)}")
        print(f"[DEBUG] Parámetros: to={to}, subject={subject}")

        # Validar parámetros básicos
        if not to or '@' not in to:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Email de destino requerido y debe ser válido",
                    "endpoint": "send-email-n8n"
                }
            )

        if not subject:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Asunto del email requerido",
                    "endpoint": "send-email-n8n"
                }
            )

        if not body:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Cuerpo del email requerido",
                    "endpoint": "send-email-n8n"
                }
            )

        attachment_path = None
        attachment_filename = None

        # Procesar archivo adjunto si se proporciona
        if attachment:
            # Crear directorio temporal para adjuntos
            temp_dir = Path("/tmp/email_attachments")
            temp_dir.mkdir(exist_ok=True)

            # Guardar archivo temporal
            attachment_path = temp_dir / attachment.filename
            attachment_filename = attachment.filename

            with open(attachment_path, "wb") as buffer:
                shutil.copyfileobj(attachment.file, buffer)

        # Enviar email usando el servicio standalone
        result = send_smtp_standalone(
            to=to,
            subject=subject,
            body=body,
            body_type=body_type,
            attachment_path=str(attachment_path) if attachment_path else None
        )

        # Limpiar archivo temporal
        if attachment_path and attachment_path.exists():
            try:
                attachment_path.unlink()
            except:
                pass  # Ignorar errores de limpieza

        # Preparar respuesta
        if result.get('success'):
            response_data = {
                "success": True,
                "message": result.get('message'),
                "smtp_server": result.get('smtp_server'),
                "sender": result.get('sender'),
                "method": result.get('method'),
                "endpoint": "send-email-n8n",
                "details": {
                    "to": to,
                    "subject": subject,
                    "body_type": body_type,
                    "attachment": attachment_filename
                }
            }
            return response_data
        else:
            # Agregar información de debug
            error_response = {
                "success": False,
                "error": result.get('error'),
                "endpoint": "send-email-n8n",
                "smtp_error_type": result.get('smtp_error'),
                "details": result.get('details')
            }

            # Agregar sugerencias según el tipo de error
            if result.get('missing_config'):
                error_response["suggestion"] = "Configura SMTP_USERNAME y SMTP_PASSWORD en .env"
            elif result.get('smtp_error') == 'authentication':
                error_response["suggestion"] = "Genera App Password en Gmail y úsala en SMTP_PASSWORD"

            return JSONResponse(
                status_code=500,
                content=error_response
            )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Error inesperado: {str(e)}",
                "endpoint": "send-email-n8n",
                "exception_type": type(e).__name__
            }
        )

@app.api_route("/send-email-n8n-hybrid/", methods=["GET", "POST"],
    summary="Endpoint híbrido para n8n (GET y POST)",
    description="Endpoint que maneja tanto GET como POST para n8n"
)
async def send_email_n8n_hybrid(request: Request):
    """
    Endpoint híbrido que maneja GET y POST.
    Útil cuando n8n hace redirects que cambian el método.
    """

    method = request.method
    print(f"[DEBUG] /send-email-n8n-hybrid/ {method} recibido")
    print(f"[DEBUG] URL: {request.url}")

    # Variables para los parámetros
    to = None
    subject = None
    body = None
    body_type = 'html'
    attachment = None

    try:
        if method == "GET":
            # Obtener parámetros desde query params
            query_params = dict(request.query_params)
            to = query_params.get('to')
            subject = query_params.get('subject')
            body = query_params.get('body')
            body_type = query_params.get('body_type', 'html')

            print(f"[DEBUG] GET params: {query_params}")

            if not to or not subject or not body:
                return {
                    "error": "Parámetros faltantes en GET",
                    "message": "Para GET usa: /send-email-n8n-hybrid/?to=email&subject=asunto&body=mensaje",
                    "received_params": query_params,
                    "required_params": ["to", "subject", "body"],
                    "optional_params": ["body_type"]
                }

        elif method == "POST":
            # Obtener parámetros desde form data
            try:
                form_data = await request.form()
                to = form_data.get('to')
                subject = form_data.get('subject')
                body = form_data.get('body')
                body_type = form_data.get('body_type', 'html')
                attachment = form_data.get('attachment')

                print(f"[DEBUG] POST form data keys: {list(form_data.keys())}")

            except Exception as e:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": f"Error procesando form data: {str(e)}",
                        "method": method,
                        "endpoint": "send-email-n8n-hybrid"
                    }
                )

    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": f"Error procesando request: {str(e)}",
                "method": method,
                "endpoint": "send-email-n8n-hybrid"
            }
        )

    # Validar parámetros
    if not to or '@' not in to:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "Email de destino requerido y debe ser válido",
                "method": method,
                "endpoint": "send-email-n8n-hybrid"
            }
        )

    if not subject:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "Asunto del email requerido",
                "method": method,
                "endpoint": "send-email-n8n-hybrid"
            }
        )

    if not body:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "Cuerpo del email requerido",
                "method": method,
                "endpoint": "send-email-n8n-hybrid"
            }
        )

    try:
        # Procesar archivo adjunto solo en POST
        attachment_path = None
        attachment_filename = None

        if method == "POST" and attachment and hasattr(attachment, 'filename'):
            temp_dir = Path("/tmp/email_attachments")
            temp_dir.mkdir(exist_ok=True)
            attachment_path = temp_dir / attachment.filename
            attachment_filename = attachment.filename
            with open(attachment_path, "wb") as buffer:
                shutil.copyfileobj(attachment.file, buffer)

        # Enviar email
        result = send_smtp_standalone(
            to=to,
            subject=subject,
            body=body,
            body_type=body_type,
            attachment_path=str(attachment_path) if attachment_path else None
        )

        # Limpiar archivo temporal
        if attachment_path and attachment_path.exists():
            try:
                attachment_path.unlink()
            except:
                pass

        # Preparar respuesta
        if result.get('success'):
            return {
                "success": True,
                "message": result.get('message'),
                "method": method,
                "endpoint": "send-email-n8n-hybrid",
                "details": {
                    "to": to,
                    "subject": subject,
                    "body_type": body_type,
                    "attachment": attachment_filename
                }
            }
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": result.get('error'),
                    "method": method,
                    "endpoint": "send-email-n8n-hybrid"
                }
            )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Error inesperado: {str(e)}",
                "method": method,
                "endpoint": "send-email-n8n-hybrid"
            }
        )

@app.get("/send-email-get/",
    summary="Enviar email vía GET (para n8n con redirects)",
    description="Endpoint GET puro para n8n cuando hay problemas con POST/redirects"
)
async def send_email_get(
    request: Request,
    to: str = Query(..., description="Email de destino"),
    subject: str = Query(..., description="Asunto del email"),
    body: str = Query(..., description="Cuerpo del email"),
    body_type: str = Query('html', description="Tipo de cuerpo: html o text")
):
    """
    Endpoint GET puro para enviar emails.
    Ideal para n8n cuando hay problemas con POST o redirects.

    Uso:
    GET /send-email-get/?to=email@destino.com&subject=Asunto&body=Mensaje
    """

    print(f"[DEBUG] /send-email-get/ GET recibido")
    print(f"[DEBUG] URL: {request.url}")
    print(f"[DEBUG] Parámetros: to={to}, subject={subject}")

    try:
        # Validar parámetros
        if not to or '@' not in to:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Email de destino requerido y debe ser válido",
                    "endpoint": "send-email-get"
                }
            )

        if not subject:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Asunto del email requerido",
                    "endpoint": "send-email-get"
                }
            )

        if not body:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Cuerpo del email requerido",
                    "endpoint": "send-email-get"
                }
            )

        # Enviar email (sin adjuntos en GET)
        result = send_smtp_standalone(
            to=to,
            subject=subject,
            body=body,
            body_type=body_type,
            attachment_path=None
        )

        # Preparar respuesta
        if result.get('success'):
            return {
                "success": True,
                "message": result.get('message'),
                "method": "GET",
                "endpoint": "send-email-get",
                "details": {
                    "to": to,
                    "subject": subject,
                    "body_type": body_type,
                    "attachment": None
                }
            }
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": result.get('error'),
                    "method": "GET",
                    "endpoint": "send-email-get"
                }
            )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Error inesperado: {str(e)}",
                "method": "GET",
                "endpoint": "send-email-get"
            }
        )

# @app.get("/send-email-n8n/",
#     summary="Endpoint GET para send-email-n8n (redirect info)",
#     description="Endpoint informativo para cuando se accede vía GET en lugar de POST"
# )
# async def send_email_n8n_get():
#     """
#     Endpoint GET informativo para send-email-n8n.
#     Ayuda cuando n8n hace un redirect o GET accidental.
#     """
#     return {
#         "error": "Método incorrecto",
#         "message": "Este endpoint requiere método POST, no GET",
#         "endpoint": "/send-email-n8n/",
#         "method_required": "POST",
#         "content_type": "multipart/form-data",
#         "alternative_endpoints": {
#             "hybrid": "/send-email-n8n-hybrid/ (acepta GET y POST)",
#             "get_only": "/send-email-get/ (solo GET, más simple)"
#         },
#         "parameters": {
#             "to": "email@destino.com",
#             "subject": "Asunto del email",
#             "body": "Cuerpo del email",
#             "body_type": "html (opcional)",
#             "attachment": "archivo (opcional)"
#         },
#         "n8n_config": {
#             "method": "POST",
#             "url": "{{$node[\"Webhook\"].json[\"base_url\"]}}/send-email-n8n/",
#             "body_content_type": "Form-Data",
#             "note": "Asegúrate de usar POST, no GET. O usa /send-email-n8n-hybrid/"
#         }
#     }

@app.get("/smtp-config/",
    summary="Verificar configuración SMTP",
    description="Endpoint para verificar que las variables SMTP estén configuradas correctamente",
    response_description="Estado de configuración SMTP"
)
async def check_smtp_config():
    """
    Verifica que las variables de entorno SMTP estén configuradas.
    Útil para debugging en Railway/producción.
    """

    # Variables SMTP requeridas
    smtp_vars = {
        'SMTP_SERVER': os.getenv('SMTP_SERVER'),
        'SMTP_PORT': os.getenv('SMTP_PORT'),
        'SMTP_USERNAME': os.getenv('SMTP_USERNAME'),
        'SMTP_PASSWORD': os.getenv('SMTP_PASSWORD'),
        'SMTP_SENDER_EMAIL': os.getenv('SMTP_SENDER_EMAIL')
    }

    config_status = {}
    missing_vars = []

    for var_name, var_value in smtp_vars.items():
        if var_value:
            if var_name == 'SMTP_PASSWORD':
                # No mostrar la contraseña, solo confirmar que existe
                config_status[var_name] = "✅ CONFIGURADA (oculta por seguridad)"
            else:
                config_status[var_name] = f"✅ {var_value}"
        else:
            config_status[var_name] = "❌ NO CONFIGURADA"
            missing_vars.append(var_name)

    # Detectar entorno
    environment = "Railway" if os.getenv('RAILWAY_ENVIRONMENT') else "Local"

    response = {
        "environment": environment,
        "smtp_config": config_status,
        "all_configured": len(missing_vars) == 0,
        "missing_variables": missing_vars
    }

    # Agregar información específica de Railway
    if os.getenv('RAILWAY_ENVIRONMENT'):
        response["railway_environment"] = os.getenv('RAILWAY_ENVIRONMENT')
        response["railway_service"] = os.getenv('RAILWAY_SERVICE_NAME', 'N/A')

    # Agregar sugerencias si faltan variables
    if missing_vars:
        response["suggestions"] = {
            "message": "Configura las variables faltantes en Railway > Variables",
            "required_vars": {
                "SMTP_SERVER": "smtp.gmail.com",
                "SMTP_PORT": "587",
                "SMTP_USERNAME": "tu-email@gmail.com",
                "SMTP_PASSWORD": "tu-app-password-de-gmail",
                "SMTP_SENDER_EMAIL": "tu-email@gmail.com"
            },
            "gmail_app_password_url": "https://myaccount.google.com/apppasswords"
        }

    return response

@app.get("/storage-info/",
    summary="Información de almacenamiento",
    description="Obtiene estadísticas detalladas sobre el uso de almacenamiento por tipo de archivo",
    response_description="Estadísticas de uso de almacenamiento",
    responses={
        200: {
            "description": "Información de almacenamiento obtenida exitosamente",
            "content": {
                "application/json": {
                    "example": {
                        "photos": {
                            "size_bytes": 15728640,
                            "size_mb": 15.0,
                            "count": 8
                        },
                        "videos": {
                            "size_bytes": 104857600,
                            "size_mb": 100.0,
                            "count": 3
                        },
                        "data": {
                            "size_bytes": 2097152,
                            "size_mb": 2.0,
                            "count": 12
                        },
                        "total": {
                            "size_bytes": 122683392,
                            "size_mb": 117.0,
                            "count": 23
                        }
                    }
                }
            }
        },
        500: {
            "description": "Error al calcular el almacenamiento",
            "content": {
                "application/json": {
                    "example": {
                        "error": "No se pudo acceder a los directorios de almacenamiento"
                    }
                }
            }
        }
    })
async def storage_info():
    """
    Proporciona información detallada sobre el uso del almacenamiento.
    
    Calcula el tamaño total y número de archivos para:
    - Fotos (imágenes)
    - Videos
    - Datos (archivos de datos generados por scripts)
    - Total general
    
    Los tamaños se muestran tanto en bytes como en megabytes para facilitar la lectura.
    """
    try:
        def get_directory_size(path):
            total = 0
            count = 0
            for file_path in Path(path).rglob('*'):
                if file_path.is_file():
                    total += file_path.stat().st_size
                    count += 1
            return total, count
        
        photos_size, photos_count = get_directory_size(PHOTOS_DIR)
        videos_size, videos_count = get_directory_size(VIDEOS_DIR)
        data_size, data_count = get_directory_size(DATA_DIR)
        
        return {
            "photos": {
                "size_bytes": photos_size,
                "size_mb": round(photos_size / (1024*1024), 2),
                "count": photos_count
            },
            "videos": {
                "size_bytes": videos_size,
                "size_mb": round(videos_size / (1024*1024), 2),
                "count": videos_count
            },
            "data": {
                "size_bytes": data_size,
                "size_mb": round(data_size / (1024*1024), 2),
                "count": data_count
            },
            "total": {
                "size_bytes": photos_size + videos_size + data_size,
                "size_mb": round((photos_size + videos_size + data_size) / (1024*1024), 2),
                "count": photos_count + videos_count + data_count
            }
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.get("/test-timeout/{delay_minutes}",
    summary="Probar timeout del servidor",
    description="Endpoint de prueba que espera un número específico de minutos para probar el comportamiento del timeout",
    response_description="Respuesta exitosa si el endpoint completa antes del timeout",
    responses={
        200: {
            "description": "Endpoint completado exitosamente",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Completado exitosamente",
                        "delay_minutes": 5,
                        "delay_seconds": 300,
                        "start_time": "2025-01-20T10:30:00",
                        "end_time": "2025-01-20T10:35:00",
                        "elapsed_seconds": 300.1
                    }
                }
            }
        },
        408: {
            "description": "Timeout del servidor",
            "content": {
                "application/json": {
                    "example": {
                        "error": "Request timeout"
                    }
                }
            }
        }
    })
async def test_timeout(delay_minutes: float):
    """
    Endpoint para probar el comportamiento del timeout del servidor.

    - **delay_minutes**: Número de minutos que debe esperar el endpoint (puede ser decimal, ej: 1.5 = 1 minuto 30 segundos)

    Casos de uso:
    - GET /test-timeout/0.5 - Espera 30 segundos
    - GET /test-timeout/1 - Espera 1 minuto
    - GET /test-timeout/25 - Espera 25 minutos (debería superar el timeout de 20 minutos si está configurado así)

    Este endpoint permite verificar si el timeout configurado en uvicorn está funcionando correctamente.
    Si el delay supera el timeout configurado, el servidor debería cortar la conexión.
    """
    try:
        start_time = time.time()
        delay_seconds = delay_minutes * 60

        # Información inicial
        start_time_str = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(start_time))

        # Log del inicio
        print(f"[TIMEOUT TEST] Iniciando delay de {delay_minutes} minutos ({delay_seconds} segundos)")
        print(f"[TIMEOUT TEST] Hora de inicio: {start_time_str}")

        # Esperar el tiempo especificado usando asyncio.sleep
        await asyncio.sleep(delay_seconds)

        # Calcular tiempo transcurrido
        end_time = time.time()
        elapsed_seconds = end_time - start_time
        end_time_str = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(end_time))

        # Log del fin
        print(f"[TIMEOUT TEST] Delay completado exitosamente")
        print(f"[TIMEOUT TEST] Hora de fin: {end_time_str}")
        print(f"[TIMEOUT TEST] Tiempo transcurrido: {elapsed_seconds:.1f} segundos")

        return {
            "message": "Completado exitosamente",
            "delay_minutes": delay_minutes,
            "delay_seconds": delay_seconds,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "elapsed_seconds": round(elapsed_seconds, 1)
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Error durante el delay: {str(e)}",
                "delay_minutes": delay_minutes
            }
        )

# ============= ENDPOINT ASÍNCRONO PARA FINNEGANS LOGIN =============

class FinnegansRequest(BaseModel):
    company: str
    webhook_url: Optional[str] = None

class FinnegansJobResponse(BaseModel):
    job_id: str
    status: str
    message: str
    company: str
    webhook_url: Optional[str]

# Almacenamiento en memoria de trabajos (en producción usar Redis)
jobs_storage = {}

class LogCapture:
    """Clase para capturar logs de stdout/stderr"""
    def __init__(self):
        self.logs = []
        self.original_stdout = None
        self.original_stderr = None

    def start(self):
        """Inicia la captura de logs"""
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        sys.stdout = self
        sys.stderr = self

    def stop(self):
        """Detiene la captura de logs"""
        if self.original_stdout:
            sys.stdout = self.original_stdout
        if self.original_stderr:
            sys.stderr = self.original_stderr

    def write(self, text):
        """Captura el texto escrito"""
        if text and text.strip():
            self.logs.append({
                'timestamp': datetime.now().isoformat(),
                'message': text.strip()
            })
        # También escribir al stdout original para mantener logs en consola
        if self.original_stdout:
            self.original_stdout.write(text)

    def flush(self):
        """Método requerido para compatibilidad con stdout"""
        if self.original_stdout:
            self.original_stdout.flush()

    def get_logs(self):
        """Obtiene todos los logs capturados"""
        return self.logs

    def get_logs_text(self):
        """Obtiene los logs como texto plano"""
        return '\n'.join([log['message'] for log in self.logs])

def run_finnegans_process(job_id: str, company: str, webhook_url: Optional[str] = None):
    """Ejecuta el proceso de facturación en background y notifica vía webhook"""

    # Capturar logs
    log_capture = LogCapture()
    log_capture.start()

    inicio = datetime.now()

    try:
        # Actualizar estado del job
        jobs_storage[job_id] = {
            'status': 'running',
            'company': company,
            'started_at': inicio.isoformat(),
            'logs': []
        }

        print(f"[{job_id}] Iniciando proceso de facturación para {company}")

        # Ejecutar el script de finnegans
        env = os.environ.copy()
        env['PLAYWRIGHT_BROWSERS_PATH'] = '/ms-playwright'

        script_path = SCRIPTS_DIR / "finnegans_login.py"

        result = subprocess.run(
            ["python", str(script_path), "--company", company],
            capture_output=True,
            text=True,
            env=env,
            timeout=1800  # 30 minutos timeout
        )

        # Detener captura de logs
        log_capture.stop()

        fin = datetime.now()
        duracion = (fin - inicio).total_seconds()

        # Determinar si fue exitoso
        success = result.returncode == 0

        # Parsear el output para extraer estadísticas
        log_completo = result.stdout + "\n" + result.stderr

        # Buscar el resumen en el log
        resumen = {
            'total_remitos': 0,
            'exitosos': 0,
            'fallidos': 0,
            'no_procesados': 0
        }

        for line in log_completo.split('\n'):
            if 'Total de remitos encontrados:' in line:
                try:
                    resumen['total_remitos'] = int(line.split(':')[-1].strip())
                except:
                    pass
            elif 'Remitos procesados exitosamente:' in line:
                try:
                    resumen['exitosos'] = int(line.split(':')[-1].strip())
                except:
                    pass
            elif 'Remitos con errores:' in line:
                try:
                    resumen['fallidos'] = int(line.split(':')[-1].strip())
                except:
                    pass
            elif 'Remitos no procesados:' in line:
                try:
                    resumen['no_procesados'] = int(line.split(':')[-1].strip())
                except:
                    pass

        # Actualizar job con resultado
        jobs_storage[job_id] = {
            'status': 'completed' if success else 'failed',
            'company': company,
            'started_at': inicio.isoformat(),
            'finished_at': fin.isoformat(),
            'duration_seconds': duracion,
            'success': success,
            'returncode': result.returncode,
            'resumen': resumen,
            'logs': log_capture.get_logs(),
            'log_completo': log_completo
        }

        # Notificar vía webhook si se proporcionó
        if webhook_url:
            try:
                webhook_payload = {
                    'job_id': job_id,
                    'status': 'completed' if success else 'failed',
                    'company': company,
                    'started_at': inicio.isoformat(),
                    'finished_at': fin.isoformat(),
                    'duration_seconds': duracion,
                    'success': success,
                    'resumen': resumen,
                    'logs': log_capture.get_logs(),
                    'log_completo': log_completo
                }

                print(f"[{job_id}] Enviando notificación a webhook: {webhook_url}")

                response = requests.post(
                    webhook_url,
                    json=webhook_payload,
                    timeout=30
                )

                if response.status_code == 200:
                    print(f"[{job_id}] Webhook notificado exitosamente")
                    jobs_storage[job_id]['webhook_notified'] = True
                else:
                    print(f"[{job_id}] Error al notificar webhook: {response.status_code}")
                    jobs_storage[job_id]['webhook_error'] = f"HTTP {response.status_code}"

            except Exception as e:
                print(f"[{job_id}] Error enviando webhook: {str(e)}")
                jobs_storage[job_id]['webhook_error'] = str(e)

        print(f"[{job_id}] Proceso finalizado. Status: {'exitoso' if success else 'fallido'}")

    except subprocess.TimeoutExpired:
        log_capture.stop()
        fin = datetime.now()
        duracion = (fin - inicio).total_seconds()

        jobs_storage[job_id] = {
            'status': 'timeout',
            'company': company,
            'started_at': inicio.isoformat(),
            'finished_at': fin.isoformat(),
            'duration_seconds': duracion,
            'error': 'Proceso excedió el tiempo límite de 30 minutos',
            'logs': log_capture.get_logs()
        }

        # Notificar timeout vía webhook
        if webhook_url:
            try:
                requests.post(
                    webhook_url,
                    json=jobs_storage[job_id],
                    timeout=30
                )
            except:
                pass

    except Exception as e:
        log_capture.stop()
        fin = datetime.now()
        duracion = (fin - inicio).total_seconds()

        jobs_storage[job_id] = {
            'status': 'error',
            'company': company,
            'started_at': inicio.isoformat(),
            'finished_at': fin.isoformat(),
            'duration_seconds': duracion,
            'error': str(e),
            'logs': log_capture.get_logs()
        }

        # Notificar error vía webhook
        if webhook_url:
            try:
                requests.post(
                    webhook_url,
                    json=jobs_storage[job_id],
                    timeout=30
                )
            except:
                pass

@app.post("/finnegans/start",
    summary="Iniciar proceso de facturación Finnegans (async)",
    description="Inicia el proceso de facturación de forma asíncrona. Retorna inmediatamente un job_id y notifica vía webhook cuando finaliza.",
    response_model=FinnegansJobResponse,
    responses={
        200: {
            "description": "Proceso iniciado exitosamente",
            "content": {
                "application/json": {
                    "example": {
                        "job_id": "finn_20250117_123456_abc123",
                        "status": "started",
                        "message": "Proceso iniciado en background",
                        "company": "Das Dach",
                        "webhook_url": "https://n8n.tudominio.com/webhook/finnegans-result"
                    }
                }
            }
        }
    })
async def start_finnegans_process(
    request: FinnegansRequest,
    background_tasks: BackgroundTasks
):
    """
    Inicia el proceso de facturación de Finnegans de forma asíncrona.

    **Parámetros:**
    - **company**: Nombre de la empresa a procesar (ej: "Das Dach", "AVIANCA")
    - **webhook_url** (opcional): URL de webhook para recibir notificación cuando finalice

    **Funcionamiento:**
    1. El endpoint retorna inmediatamente con un `job_id`
    2. El proceso se ejecuta en background
    3. Cuando finaliza (exitoso o con error), envía los resultados al `webhook_url`

    **Payload del webhook:**
    ```json
    {
        "job_id": "finn_20250117_123456_abc123",
        "status": "completed",
        "company": "Das Dach",
        "started_at": "2025-01-17T12:34:56",
        "finished_at": "2025-01-17T12:45:23",
        "duration_seconds": 627.5,
        "success": true,
        "resumen": {
            "total_remitos": 15,
            "exitosos": 14,
            "fallidos": 1,
            "no_procesados": 0
        },
        "logs": [...],
        "log_completo": "..."
    }
    ```

    **Ejemplo de uso desde n8n:**

    Nodo 1 - HTTP Request (Iniciar proceso):
    - Method: POST
    - URL: https://tu-servidor.com/finnegans/start
    - Body (JSON):
      ```json
      {
          "company": "Das Dach",
          "webhook_url": "{{$node["Webhook"].json["webhook_url"]}}"
      }
      ```

    Nodo 2 - Webhook (Recibir resultado):
    - Webhook URL: capturar y pasar al nodo anterior
    - Este webhook recibirá el resultado cuando finalice el proceso
    """

    # Generar job_id único
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    import uuid
    job_id = f"finn_{timestamp}_{str(uuid.uuid4())[:8]}"

    # Validar company
    if not request.company:
        raise HTTPException(status_code=400, detail="Company es requerido")

    # Iniciar proceso en background usando threading
    # (BackgroundTasks no funciona bien para procesos muy largos)
    thread = threading.Thread(
        target=run_finnegans_process,
        args=(job_id, request.company, request.webhook_url),
        daemon=True
    )
    thread.start()

    return FinnegansJobResponse(
        job_id=job_id,
        status="started",
        message="Proceso iniciado en background. Recibirás notificación en el webhook cuando finalice.",
        company=request.company,
        webhook_url=request.webhook_url
    )

@app.get("/finnegans/status/{job_id}",
    summary="Consultar estado de un job de facturación",
    description="Obtiene el estado actual y logs de un proceso de facturación",
    responses={
        200: {
            "description": "Estado del job obtenido exitosamente",
            "content": {
                "application/json": {
                    "examples": {
                        "running": {
                            "summary": "Proceso en ejecución",
                            "value": {
                                "job_id": "finn_20250117_123456_abc123",
                                "status": "running",
                                "company": "Das Dach",
                                "started_at": "2025-01-17T12:34:56",
                                "logs": []
                            }
                        },
                        "completed": {
                            "summary": "Proceso completado",
                            "value": {
                                "job_id": "finn_20250117_123456_abc123",
                                "status": "completed",
                                "company": "Das Dach",
                                "started_at": "2025-01-17T12:34:56",
                                "finished_at": "2025-01-17T12:45:23",
                                "duration_seconds": 627.5,
                                "success": True,
                                "resumen": {
                                    "total_remitos": 15,
                                    "exitosos": 14,
                                    "fallidos": 1,
                                    "no_procesados": 0
                                }
                            }
                        }
                    }
                }
            }
        },
        404: {
            "description": "Job no encontrado"
        }
    })
async def get_finnegans_job_status(job_id: str):
    """
    Consulta el estado de un proceso de facturación.

    **Parámetros:**
    - **job_id**: ID del job retornado al iniciar el proceso

    **Estados posibles:**
    - `running`: Proceso en ejecución
    - `completed`: Proceso finalizado exitosamente
    - `failed`: Proceso finalizado con errores
    - `timeout`: Proceso excedió el tiempo límite
    - `error`: Error inesperado durante la ejecución

    Útil para hacer polling desde n8n si no se quiere usar webhook.
    """

    if job_id not in jobs_storage:
        raise HTTPException(status_code=404, detail="Job no encontrado")

    job_data = jobs_storage[job_id]
    job_data['job_id'] = job_id

    return job_data

@app.get("/finnegans/jobs",
    summary="Listar todos los jobs de facturación",
    description="Obtiene la lista de todos los jobs ejecutados")
async def list_finnegans_jobs():
    """
    Lista todos los jobs de facturación ejecutados.

    Útil para debugging y monitoreo.
    """

    jobs_list = []
    for job_id, job_data in jobs_storage.items():
        jobs_list.append({
            'job_id': job_id,
            'status': job_data.get('status'),
            'company': job_data.get('company'),
            'started_at': job_data.get('started_at'),
            'finished_at': job_data.get('finished_at'),
            'success': job_data.get('success')
        })

    # Ordenar por fecha de inicio descendente
    jobs_list.sort(key=lambda x: x.get('started_at', ''), reverse=True)

    return {
        'total': len(jobs_list),
        'jobs': jobs_list
    }