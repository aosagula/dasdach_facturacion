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
from pathlib import Path
from dotenv import load_dotenv
from file_manager import list_saved_files, PHOTOS_DIR, VIDEOS_DIR, DATA_DIR, BASE_DIR, UPLOADS_DIR, create_directories
from email_service import send_gmail

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
    files = list_saved_files(file_type)
    return {
        "files": files,
        "total": len(files),
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
    files = list_saved_files("photo")
    return {"photos": files, "total": len(files)}

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
    files = list_saved_files("video")
    return {"videos": files, "total": len(files)}

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
    env = os.environ.copy()
    env['PLAYWRIGHT_BROWSERS_PATH'] = '/ms-playwright'
    
    # Agregar variables de entorno personalizadas (nuevo)
    if env_vars:
        env.update(env_vars)
    
    # Construir comando (mejorado)
    command = ["python", script_path]
    if args:
        command.extend([str(arg) for arg in args])  # Convertir todos los args a string
    
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
    email_data: EmailRequest,
    attachment: Optional[UploadFile] = File(None)
):
    """
    Envía un email usando Gmail API.

    **Parámetros del cuerpo JSON:**
    - **to**: Email de destino (requerido)
    - **subject**: Asunto del email (requerido)
    - **body**: Cuerpo del email en HTML o texto plano (requerido)
    - **body_type**: Tipo de cuerpo 'html' o 'text' (opcional, por defecto 'html')

    **Archivo adjunto:**
    - **attachment**: Archivo opcional para adjuntar al email (form-data)

    **Ejemplo de uso con curl:**
    ```bash
    # Sin adjunto
    curl -X POST "http://localhost:8000/send-email/" \
         -H "Content-Type: application/json" \
         -d '{
           "to": "destinatario@email.com",
           "subject": "Prueba de envío",
           "body": "<h1>Hola mundo!</h1><p>Este es un email de prueba.</p>",
           "body_type": "html"
         }'

    # Con adjunto (usando form-data)
    curl -X POST "http://localhost:8000/send-email/" \
         -F 'email_data={"to":"destinatario@email.com","subject":"Con adjunto","body":"<p>Email con archivo adjunto</p>"}' \
         -F 'attachment=@/ruta/al/archivo.pdf'
    ```

    **Configuración requerida en .env:**
    - GMAIL_CLIENT_ID: Client ID de Google Cloud Console
    - GMAIL_CLIENT_SECRET: Client Secret de Google Cloud Console
    - GMAIL_PROJECT_ID: Project ID de Google Cloud Console
    - GMAIL_SENDER_EMAIL: Email del remitente (opcional)
    - GMAIL_TOKEN_PATH: Ruta del archivo de token (opcional)
    """

    try:
        # Validar email de destino
        if not email_data.to or '@' not in email_data.to:
            return JSONResponse(
                status_code=400,
                content={"error": "Email de destino requerido y debe ser válido"}
            )

        # Validar asunto
        if not email_data.subject:
            return JSONResponse(
                status_code=400,
                content={"error": "Asunto del email requerido"}
            )

        # Validar cuerpo
        if not email_data.body:
            return JSONResponse(
                status_code=400,
                content={"error": "Cuerpo del email requerido"}
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

        # Enviar email
        result = send_gmail(
            to=email_data.to,
            subject=email_data.subject,
            body=email_data.body,
            body_type=email_data.body_type,
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
                "message_id": result.get('message_id'),
                "details": {
                    "to": email_data.to,
                    "subject": email_data.subject,
                    "body_type": email_data.body_type,
                    "attachment": attachment_filename
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

    # Crear objeto EmailRequest y reutilizar la lógica existente
    email_data = EmailRequest(
        to=to,
        subject=subject,
        body=body,
        body_type=body_type
    )

    return await send_email_endpoint(email_data, attachment)

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