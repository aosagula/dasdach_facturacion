
from datetime import datetime
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

def parse_fecha(value: Any) -> Optional[datetime]:
    """
    Parsea fechas comunes y retorna un datetime o None.
    Soporta: ISO 8601 (incluyendo sufijo 'Z'), 'YYYY-MM-DD', 'DD/MM/YYYY',
    y 'YYYY-MM-DDTHH:MM:SS'. Optimizado para decisiones rápidas.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None

        # ISO 8601 rápido (maneja 'Z' como UTC)
        if 'T' in s:
            if s.endswith('Z'):
                try:
                    return datetime.fromisoformat(s.replace('Z', '+00:00'))
                except Exception:
                    pass
            # 'YYYY-MM-DDTHH:MM:SS' (y posibles offsets)
            if len(s) >= 19 and s[4:5] == '-' and s[7:8] == '-' and s[10:11] == 'T':
                try:
                    return datetime.fromisoformat(s)
                except Exception:
                    try:
                        return datetime.strptime(s[:19], '%Y-%m-%dT%H:%M:%S')
                    except Exception:
                        pass

        # 'YYYY-MM-DD'
        if len(s) == 10 and s[4:5] == '-' and s[7:8] == '-':
            try:
                return datetime.strptime(s, '%Y-%m-%d')
            except Exception:
                pass

        # 'DD/MM/YYYY'
        if len(s) == 10 and s[2:3] == '/' and s[5:6] == '/':
            try:
                return datetime.strptime(s, '%d/%m/%Y')
            except Exception:
                pass

    return None

def timestamp() -> str:
    """Retorna el timestamp actual formateado"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

def print_with_time(message: str) -> None:
    """Print con timestamp automático"""
    print(f"[{timestamp()}] {message}")
    
def show_comprobante(page, texto):
    page.evaluate(f"window.__hud && window.__hud.set('{texto}')")

def hide_comprobante(page):
    page.evaluate("window.__hud && window.__hud.hide()")
def install_hud(context):
    context.add_init_script("""
        window.__hud = (function(){
      const ID='a4b-hud-banner';
      function ensure(){
        let el = document.getElementById(ID);
        if (!el) {
          el = document.createElement('div');
          el.id = ID;
          el.style.cssText = [
            'position:fixed',
            'top:20px',
            'left:50%',
            'transform:translateX(-50%)',
            'background:rgba(0,0,0,0.8)',
            'color:#fff',
            'padding:10px 20px',
            'border-radius:12px',
            'font:600 15px system-ui, sans-serif',
            'z-index:2147483647',
            'pointer-events:none',
            'border:3px solid #02ceff',         /* 🔹 RECUADRO CELESTE */
            'box-shadow:0 4px 20px rgba(0,0,0,.6)',
            'backdrop-filter: blur(2px)',
            'text-align:center',
            'max-width:70vw'
          ].join(';');
          el.setAttribute('aria-live','polite');
          document.body.appendChild(el);
        }
        return el;
      }
      return {
        set(text){
          const el = ensure();
          el.textContent = text || '';
        },
        hide(){
          const el = document.getElementById(ID);
          if (el) el.remove();
        }
      };
    })();
    """)
    
def save_screenshot(image_bytes, filename):
    """Guardar screenshot usando la ruta del .env"""
    try:
        load_dotenv()
        photo_path = os.getenv('LOG_PHOTO_PATH', './media/photos/')
        
        # Crear el directorio si no existe
        Path(photo_path).mkdir(parents=True, exist_ok=True)
        
        # Crear la ruta completa del archivo
        full_path = Path(photo_path) / filename
        
        # Guardar el archivo
        with open(full_path, 'wb') as f:
            f.write(image_bytes)
        
        print_with_time(f"Screenshot guardado en: {full_path}")
        return str(full_path)

    
    except Exception as e:
        print_with_time(f"Error guardando screenshot: {e}")
        return None
    
def get_video_path():
    """Obtener la ruta para guardar videos"""
    load_dotenv()            
    video_dir = os.getenv('LOG_VIDEO_PATH', './media/videos/')
    Path(video_dir).mkdir(parents=True, exist_ok=True)
    
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    video_filename = f"finnegans_session_{timestamp_str}.webm"
    return Path(video_dir) / video_filename