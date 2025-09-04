from fastapi import FastAPI, File, UploadFile, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os
import shutil
import subprocess
from pathlib import Path
from file_manager import list_saved_files, PHOTOS_DIR, VIDEOS_DIR, DATA_DIR

app = FastAPI(
    title="Agentic for Business Scripts Runner",
    description="API para ejecutar scripts Python y gestionar archivos multimedia en Railway",
    version="1.0.0",
    contact={
        "name": "Soporte Técnico",
        "url": "https://github.com/aosagula/"
    }
)

# Servir archivos estÃ¡ticos
app.mount("/media/photos", StaticFiles(directory="/app/media/photos"), name="photos")
app.mount("/media/videos", StaticFiles(directory="/app/media/videos"), name="videos")
app.mount("/data", StaticFiles(directory="/app/data"), name="data")

# Directorio para archivos subidos
UPLOAD_DIR = Path("/app/uploads")
SCRIPTS_DIR = Path("/app/scripts")

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