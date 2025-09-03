from fastapi import FastAPI, File, UploadFile, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os
import shutil
import subprocess
from pathlib import Path
from file_manager import list_saved_files, PHOTOS_DIR, VIDEOS_DIR, DATA_DIR

app = FastAPI(title="Railway Python Scripts Runner")

# Servir archivos estÃ¡ticos
app.mount("/media/photos", StaticFiles(directory="/app/media/photos"), name="photos")
app.mount("/media/videos", StaticFiles(directory="/app/media/videos"), name="videos")
app.mount("/data", StaticFiles(directory="/app/data"), name="data")

# Directorio para archivos subidos
UPLOAD_DIR = Path("/app/uploads")
SCRIPTS_DIR = Path("/app/scripts")

@app.get("/")
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

@app.get("/files/")
async def list_files(file_type: str = None):
    """Listar archivos guardados por tipo"""
    files = list_saved_files(file_type)
    return {
        "files": files,
        "total": len(files),
        "file_type": file_type or "all"
    }

@app.get("/files/photos/")
async def list_photos():
    """Listar todas las fotos guardadas"""
    files = list_saved_files("photo")
    return {"photos": files, "total": len(files)}

@app.get("/files/videos/")
async def list_videos():
    """Listar todos los videos guardados"""
    files = list_saved_files("video")
    return {"videos": files, "total": len(files)}

@app.get("/download/{file_type}/{filename}")
async def download_file(file_type: str, filename: str):
    """Descargar archivo especÃ­fico"""
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

@app.post("/upload-script/")
async def upload_script(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """Subir y ejecutar scripts Python"""
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
@app.get("/run-script/{script_name}")
async def run_script_get(
    script_name: str, 
    args: str = None, 
    timeout: int = 300
):
    """
    Ejecutar script con parámetros via GET (más simple)
    
    Ejemplo:
    GET /run-script/mi_script.py?args=param1,param2,param3&timeout=600
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
@app.post("/run-script/{script_name}")
async def run_script_endpoint(script_name: str, parameters: dict = None):
    """
    Ejecutar un script específico con parámetros (MÉTODO ORIGINAL MEJORADO)
    
    Body JSON ejemplo:
    {
        "args": ["parametro1", "parametro2"],
        "env_vars": {"MI_VAR": "valor"},
        "timeout": 300
    }
    
    Si no envías parámetros, funciona como antes (retrocompatibilidad)
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
    Ejecutar script Python con playwright headless (FUNCIÓN ORIGINAL MEJORADA)
    
    Args:
        script_path: ruta del script
        args: lista de argumentos para el script
        env_vars: variables de entorno adicionales 
        timeout: timeout en segundos
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

@app.get("/storage-info/")
async def storage_info():
    """InformaciÃ³n sobre el almacenamiento utilizado"""
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