from fastapi import FastAPI, File, UploadFile, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os
import shutil
import subprocess
from pathlib import Path
from file_manager import list_saved_files, PHOTOS_DIR, VIDEOS_DIR, DATA_DIR

app = FastAPI(title="Railway Python Scripts Runner")

# Servir archivos estáticos
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
        "message": "Railway Python Scripts Runner está funcionando",
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
    """Descargar archivo específico"""
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
                content={"error": "Tipo de archivo no válido. Usar: photo, video, data"}
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

@app.post("/run-script/{script_name}")
async def run_script_endpoint(script_name: str):
    """Ejecutar un script específico"""
    script_path = SCRIPTS_DIR / script_name
    
    if not script_path.exists():
        return JSONResponse(
            status_code=404,
            content={"error": "Script no encontrado"}
        )
    
    try:
        result = await run_python_script(str(script_path))
        return {"message": "Script ejecutado", "output": result}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error al ejecutar script: {str(e)}"}
        )

async def run_python_script(script_path: str):
    """Ejecutar script Python con playwright headless"""
    env = os.environ.copy()
    env['PLAYWRIGHT_BROWSERS_PATH'] = '/ms-playwright'
    
    try:
        result = subprocess.run(
            ["python", script_path],
            capture_output=True,
            text=True,
            env=env,
            timeout=300  # 5 minutos timeout
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"error": "Script timeout"}
    except Exception as e:
        return {"error": str(e)}

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
    """Información sobre el almacenamiento utilizado"""
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