import os
from dotenv import load_dotenv
from playwright.sync_api import Playwright, sync_playwright
import time
import re
import sys
import os
import requests
import psycopg2
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import threading
import traceback
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Excepción específica para abortar la facturación completa
class FacturacionAbortada(Exception):
    pass

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

def get_token() -> str:
    """Obtiene el token de autenticación desde la variable de entorno"""
    load_dotenv()
    
    client_id = os.getenv('FINNEGANS_CLIENT_ID', '')
    client_secret = os.getenv('FINNEGANS_SECRET', '')
    url=f"https://api.teamplace.finneg.com/api/oauth/token?grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}"
    
    if not client_id or not client_secret:
        print_with_time("Error: FINNEGANS_CLIENT_ID and FINNEGANS_SECRET must be set in .env file")
        exit(1)
    
    response = requests.get(url)
    if response.status_code == 200:
        data = response.text
        return data
    else:
        print_with_time(f"Error al obtener el token: {response.status_code} - {response.text}")
        exit(1)
        
        
def _coalesce(d: Dict[str, Any], *keys: str) -> Optional[Any]:
    """Devuelve el primer valor no nulo/no vacío encontrado en d para las claves dadas."""
    for k in keys:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return None

def resumir_transacciones(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Agrupa por COMPROBANTE y suma los importes de todos los ítems de ese comprobante.
    Devuelve por cada comprobante: comprobante, docnroint, fecha_comprobante, total_bruto,
    total_conceptos, total, cliente, condicion_pago, provincia_destino, identificacion_tributaria,
    nro_de_identificacion, importe (suma de "IMPORTE"), importe_gravado (suma de "GRAVADO"),
    e importe_no_gravado (suma de "NO GRAVADO").
    """

    def _to_float(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            s = value.strip()
            # intento directo (p.ej. "1234.56")
            try:
                return float(s)
            except Exception:
                # intento con formato local (p.ej. "1.234,56")
                s2 = s.replace(".", "").replace(",", ".")
                try:
                    return float(s2)
                except Exception:
                    return 0.0
        return 0.0

    resumen_por_comp: Dict[str, Dict[str, Any]] = {}

    for row in items:
        comp = row.get("COMPROBANTE")
        ## solo debug de un caso
        # if row.get("COMPROBANTE") == "R-0001-00010529":
        #     pass
        if not comp:
            continue

        identificacion_tributaria = _coalesce(
            row,
            "INDENTIFICACIONTRIBUTARIA",
            "IDENTIFICACIONTRIBUTARIA",
        )

        provincia_destino = _coalesce(
            row,
            "PROVINCIADESTINO",       # a nivel cabecera
            "PROVINCIADESTINOITEM",   # a nivel ítem
        )

        if comp not in resumen_por_comp:
            resumen_por_comp[comp] = {
                "comprobante": comp,
                "docnroint": row.get("DOCNROINT"),
                "fecha_comprobante": row.get("FECHACOMPROBANTE"),
                "total_bruto": row.get("TOTALBRUTO"),
                "total_conceptos": row.get("TOTALCONCEPTOS"),
                "total": row.get("TOTAL"),
                "cliente": row.get("CLIENTE"),
                "condicion_pago": row.get("CONDICIONPAGO"),
                "provincia_destino": provincia_destino,
                "identificacion_tributaria": identificacion_tributaria,
                "nro_de_identificacion": row.get("NRODEIDENTIFICACION"),
                # acumuladores
                "importe": 0.0,
                "importe_gravado": 0.0,
                "importe_no_gravado": 0.0,
            }

        # acumular importes por comprobante
        resumen_por_comp[comp]["importe"] += _to_float(row.get("IMPORTE"))
        resumen_por_comp[comp]["importe_gravado"] += _to_float(row.get("GRAVADO"))
        resumen_por_comp[comp]["importe_no_gravado"] += _to_float(row.get("NO GRAVADO"))

    # devolver como lista ordenada por comprobante
    return [resumen_por_comp[k] for k in sorted(resumen_por_comp.keys(), key=lambda x: str(x))]


def get_remitos_pendientes(company: str) -> list:
    """Obtiene la lista de remitos pendientes desde la variable de entorno"""
    load_dotenv()
    token=get_token()
    print_with_time(f"Obteniendo remitos pendientes para la empresa: {company}")
    
    url = f"https://api.teamplace.finneg.com/api/reports/analisisDespachoVenta?PARAMWEBREPORT_verPendientes=2&ACCESS_TOKEN={token}"
    
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        remitos_company = [r for r in data if r.get('EMPRESA') == company]
        return remitos_company
    else:
        print_with_time(f"Error al obtener los remitos: {response.status_code} - {response.text}")
    
    
        return []
    
    
def get_remito_detalle(DOCNROINT) -> list:
    """Obtiene el detalle de un remito del numero interno de finnegans"""
    load_dotenv()
    token=get_token()
    print_with_time(f"Obteniendo remitos pendientes para la empresa: {DOCNROINT}")
    
    url = f"https://api.teamplace.finneg.com/api/pedidoVenta/{DOCNROINT}?ACCESS_TOKEN={token}"
    
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        
        return data
    else:
        print_with_time(f"Error al obtener los remitos: {response.status_code} - {response.text}")
    
    
        return []
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

# ==================== PostgreSQL logging de facturas ====================
# Config DB igual a otros módulos (usando mismas variables que carga_padron_dgr.py)
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'railway'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', '')
}

def get_db_config() -> dict:
    """Carga .env y retorna la configuración de conexión a Postgres."""
    load_dotenv()
    return {
        'host': os.getenv('DB_HOST', DB_CONFIG.get('host')),
        'port': os.getenv('DB_PORT', DB_CONFIG.get('port')),
        'database': os.getenv('DB_NAME', DB_CONFIG.get('database')),
        'user': os.getenv('DB_USER', DB_CONFIG.get('user')),
        'password': os.getenv('DB_PASSWORD', DB_CONFIG.get('password')),
    }

_FACT_TABLE_INITED = False
_FACT_LOCK = threading.Lock()

def _ensure_facturas_table():
    global _FACT_TABLE_INITED
    if _FACT_TABLE_INITED:
        return
    with _FACT_LOCK:
        if _FACT_TABLE_INITED:
            return
        conn = None
        try:
            conn = psycopg2.connect(**get_db_config())
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS facturas_generadas (
                    id SERIAL PRIMARY KEY,
                    fecha_hora TIMESTAMP NOT NULL,
                    comprobante VARCHAR(100) NOT NULL,
                    cuit VARCHAR(20),
                    empresa VARCHAR(200),
                    provincia_destino VARCHAR(100),
                    alicuota NUMERIC(10,4),
                    numero_factura VARCHAR(100),
                    nro_cae VARCHAR(100),
                    estado VARCHAR(30) NOT NULL DEFAULT 'Generado',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # Ensure column exists for existing installations
            cur.execute("ALTER TABLE facturas_generadas ADD COLUMN IF NOT EXISTS nro_cae VARCHAR(100)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_facturas_estado ON facturas_generadas(estado)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_facturas_comprobante ON facturas_generadas(comprobante)")
            conn.commit()
            _FACT_TABLE_INITED = True
            print_with_time("Tabla facturas_generadas creada/verificada")
        except Exception as e:
            print_with_time(f"Error creando/verificando tabla facturas_generadas: {e}")
        finally:
            if conn:
                conn.close()

def guardar_factura_generada(
    fecha_hora: datetime,
    comprobante: str,
    cuit: str | None,
    empresa: str | None,
    provincia_destino: str | None,
    alicuota: float | None,
    numero_factura: str | None,
    nro_cae: str | None,
    estado: str = 'Generado'
):
    _ensure_facturas_table()
    conn = None
    try:
        #print_with_time(DB_CONFIG)
        conn = psycopg2.connect(**get_db_config())
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO facturas_generadas
            (fecha_hora, comprobante, cuit, empresa, provincia_destino, alicuota, numero_factura, nro_cae, estado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                fecha_hora,
                comprobante,
                cuit,
                empresa,
                provincia_destino,
                alicuota,
                numero_factura,
                nro_cae,
                estado,
            )
        )
        conn.commit()
        print_with_time("Factura registrada en PostgreSQL con estado Generado")
    except Exception as e:
        print_with_time(f"Error registrando factura en PostgreSQL: {e}")
    finally:
        if conn:
            conn.close()

def get_video_path():
    """Obtener la ruta para guardar videos"""
    load_dotenv()            
    video_dir = os.getenv('LOG_VIDEO_PATH', './media/videos/')
    Path(video_dir).mkdir(parents=True, exist_ok=True)
    
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    video_filename = f"finnegans_session_{timestamp_str}.webm"
    return Path(video_dir) / video_filename

def run_finnegans_login(playwright: Playwright) -> tuple:
    load_dotenv()
    
    username = os.getenv('USER_FINNEGANS')
    password = os.getenv('PASSWORD_FINNEGANS')
    workspace = os.getenv('WORKSPACE_FINNEGANS', '')
    webpage = os.getenv('WEBPAGE_FINNEGANS', 'https://services.finneg.com/login')
    
    if not username or not password:
        print_with_time("Error: USER_FINNEGANS and PASSWORD_FINNEGANS must be set in .env file")
        return None, None, None
    
    # Configurar grabación de video opcional
    enable_video = os.getenv('ENABLE_VIDEO_RECORDING', 'false').lower() == 'true'
    context_options = {}
    
    if enable_video:
        video_path = get_video_path()
        print_with_time(f"Video recording enabled - se guardará en: {video_path}")
        context_options = {

            "record_video_dir": str(video_path.parent),
            "record_video_size": {"width": 1280, "height": 720},
            "no_viewport": True,
            "user_agent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36',
            "extra_http_headers": {
                'Referer': 'https://core-web.finneg.com/',
                'Origin': 'https://core-web.finneg.com',
            }

        }
    else:
        print_with_time("Video recording disabled")
        context_options = {

            "no_viewport": True,
            "user_agent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36',
            "extra_http_headers": {
                'Referer': 'https://core-web.finneg.com/',
                'Origin': 'https://core-web.finneg.com',
            }

        }
    
    # Configurar modo headless desde variable de entorno
    headless_mode = os.getenv('HEADLESS', 'true').lower() == 'true'
    browser = playwright.chromium.launch(
        headless=headless_mode,
        args=['--start-maximized']
    )
    context = browser.new_context(**context_options)
    page = context.new_page()
    install_hud(context)
    try:
        print_with_time("Navigating to Finnegans login page...")
        page.goto(webpage)
        
        print_with_time("Waiting for page to load...")
        #page.wait_for_load_state('networkidle')
        
       
        
        print_with_time("Looking for login form elements...")
        page.wait_for_timeout(2000)
        
        username_element = 'input[name="userName"]'
        password_element = 'input[name="password"]'
        company_element = 'input[name="empresa"]'
        
        print_with_time("Filling credentials...")
        page.fill(username_element, username)
        page.fill(password_element, password)
        
        if workspace:
            print_with_time(f"Filling company field with: {workspace}")
            page.fill(company_element, workspace)
        
        print_with_time("Submitting login form...")
        submit_button = page.locator('input[name="standardSubmit"]')
        print_with_time("Taking screenshot for debugging...")
        screenshot_bytes = page.screenshot()
        save_screenshot(screenshot_bytes, "finnegans_login_page.png")
        
        submit_button.click()
        
        print_with_time("Waiting for login to complete...")
        
        # Esperar a que la URL cambie después del login
        try:
            page.wait_for_url(lambda url: 'login' not in url.lower(), timeout=15000)
            current_url = page.url
            print_with_time(f"Login successful! Redirected to: {current_url}")
            
            # Tomar screenshot de la página después del login
            screenshot_bytes = page.screenshot()
            save_screenshot(screenshot_bytes, "finnegans_post_login_page.png")
            
            # Esperar a que la página se cargue completamente
            page.wait_for_load_state('networkidle', timeout=10000)
            
        except Exception as redirect_error:
            current_url = page.url
            print_with_time(f"Login redirect timeout. Current URL: {current_url}")
            if 'login' in current_url.lower():
                print_with_time("Login may have failed - still on login page")
                screenshot_bytes = page.screenshot()
                save_screenshot(screenshot_bytes, "finnegans_login_failed_page.png")
                return None, None, None
            
        time.sleep(1)
        return browser, context, page
        
    except Exception as e:
        print_with_time(f"Error during login: {e}")
        if context:
            context.close()
        if browser:
            browser.close()
        return None, None, None

def select_company( page, company_labels, company_checkboxs, company_checkboxes_angular, target_company: str) -> bool:
    """
    Selecciona la compañía especificada en la lista
    """
    for i in range(company_labels.count()):
        company = company_labels.nth(i).inner_text().strip()
        checked = company_checkboxs.nth(i).is_checked()
        
        print_with_time(f"Found company: {company} (checked: {checked})")
        
        if company == target_company:
            if not checked:
                print_with_time(f"Selecting company: {company}")
                company_checkboxes_angular.nth(i).click()
                time.sleep(1)  # Esperar un momento para que el cambio se registre
            else:
                print_with_time(f"Company {company} is already selected")
                page.keyboard.press("Escape")
            return True
    
    print_with_time(f"Company {target_company} not found in the list")
    return False

def select_company_action(page, target_company: str) -> bool:
    print_with_time("Selecting company...")
    page.get_by_text('Empresa', exact=True).click()
    time.sleep(1)
    
    dialog = page.locator('.mdc-dialog__container')
    company_labels = dialog.locator("label")
    print_with_time(f"Found {company_labels.count()} companies in the list")
    
    company_checkboxs = dialog.locator("input[type='checkbox']")
    company_checkboxs_angular = dialog.locator(".p-checkbox-box")
    select_company(page, company_labels, company_checkboxs, company_checkboxs_angular, target_company)
    print_with_time("Company selected")
    
def navigate_to_section(page, section_name: str) -> bool:
    
    time.sleep(2)
    print_with_time(f"Trying to navigate to: {section_name}")
    
    try:
        print_with_time(f"Navigating to {section_name} section...")
        page.locator("#menu_button i").click()
        
        page.get_by_role("button", name="Favoritos").click()
        #page.get_by_text("Ventas", exact=True).click()
        
        page.get_by_text(section_name, exact=True).click()
        #new_page = new_page_info.value
        time.sleep(1)
        #page.wait_for_load_state('networkidle', timeout=10000)
        print_with_time(f"Navigated to {section_name} section")
        screenshot_bytes = page.screenshot()
        save_screenshot(screenshot_bytes, "finnegans_facturacion_loaded.png")
        
    
        return True
    except Exception as e:
        print_with_time(f"Error navigating to {section_name}: {e}")
        return False
def create_new_invoice(page, remito):
    print_with_time(f"Creating new invoice for remito: {remito['comprobante']}")
    # Aquí se pueden agregar los pasos para crear una nueva factura usando los datos del remito
    # Por ejemplo, llenar formularios, seleccionar opciones, etc.
    # Esto dependerá de la estructura específica de la página y los datos disponibles en `remito`
    

    time.sleep(1)
    print_with_time("Nueva Factura button is visible")
    screenshot_bytes = page.screenshot()
    save_screenshot(screenshot_bytes, "finnegans_facturacion_nueva_factura_1.png")
    
    frame = page.frames[1] # Ajusta el índice según sea necesario
    
    print_with_time("Presionar boton nueva factura")
    btn_nueva_factura = frame.locator("#ActionNewDF")
    btn_nueva_factura.click()
    
    current_company = page.locator(".current-empresa-name-container").inner_text()
    
    if "AVIANCA" not in current_company:
    
        elemento = frame.locator("ul >> text=Factura de Venta Electrónica 0005")
    else:
        elemento = frame.locator("ul >> text=Cotizacion sin Stock")
        
    elemento.click()
    
    print_with_time("seleccion del tipo de factura ")
    time.sleep(2)
    print_with_time("Nueva Factura button is visible")
    screenshot_bytes = page.screenshot()
    save_screenshot(screenshot_bytes, "finnegans_facturacion_nueva_factura_2.png")
    
    asistente = frame.locator("input[type=radio][name='WizardWorkflowSelect'][value='160']")
    asistente.click()
    time.sleep(1)
    print_with_time("Nueva Factura button is visible")
    screenshot_bytes = page.screenshot()
    save_screenshot(screenshot_bytes, "finnegans_facturacion_nueva_factura_3.png")
    
    frame.locator('#OPERACIONSIGUIENTEPASO1_0').click()
    time.sleep(1)
    return frame

def search_and_make_invoice_avianca(page, frame, remito, company) -> None:
    
    print_with_time("Exploring navigation to add remito details...")
        
    frame.locator("button[onclick^='VRefrescarOperaciones']").click()
    time.sleep(2)
    
    
    grid_bodys = frame.locator("div.webix_ss_body")
    
    for i in range(grid_bodys.count()):
        if grid_bodys.nth(i).is_visible() == True:
            grid_body = grid_bodys.nth(i)
            break
            
    time.sleep(1)
    
    cells = grid_body.locator("div.webix_cell")
    
    print_with_time(f"Found {cells.count()} cells in the grid")
    
    print_with_time(f"Filtering for remito: {remito['comprobante']}")
    if cells.count() > 0:
        print_with_time(f"Se encontraron registros {cells.count()}")
        filters = frame.locator("input.TOOLBARTooltipSearch")
        filters.nth(6).fill(remito["comprobante"])
        filters.nth(6).press('Enter')
        time.sleep(2)
        grid_bodys = frame.locator("div.webix_ss_body")
    
        for i in range(grid_bodys.count()):
            if grid_bodys.nth(i).is_visible() == True:
                grid_body = grid_bodys.nth(i)
                break
        
        cantidad_registros = grid_body.locator("div.webix_cell")
        if cantidad_registros.count() >0:
            frame.locator("input.mainCheckbox").nth(1).check()
            time.sleep(1)
            frame.locator('#OPERACIONSIGUIENTEPASO2_0').click()
            time.sleep(1)
            frame.locator('#OPERACIONFINALIZAR_0').click()
            time.sleep(3)
            
            print_with_time("Ingresando al detalle de la factura")
            
            # Hay dos botones con el mismo id, se toma el segundo que es el boton con la palabra "Guardar "
            boton_guardar = frame.locator("#_onSave")
            print_with_time("Guardando la factura")
            boton_guardar.nth(1).click()
            time.sleep(5)

            # Intentar leer el nro de factura asignado
            nro_factura = None
            try:
                widget_doc = frame.locator('div.widget[name="wdg_NumeroDocumento"]')
                if widget_doc.is_visible() == True:
                    nro_factura = frame.locator('div.widget[name="wdg_NumeroDocumento"] >> input[type="textbox"]').input_value()
                    print_with_time(f"Nro de factura asignado: {nro_factura}")
            except Exception:
                pass

            # Registrar en PostgreSQL con estado Generado
            cuit = re.sub(r'\D', '', remito.get('nro_de_identificacion', '') or '')
            provincia = remito.get('provincia_destino')
            alicuota = None
            if cuit:
                info = get_alicuotas([cuit])
                if info.get('encontrados', 0) > 0:
                    alicuota = info.get('resultados', [{}])[0].get('alicuota')
            if alicuota is None:
                if provincia == 'Buenos Aires':
                    alicuota = 8.0
                else:
                    alicuota = 0.0
            guardar_factura_generada(
                datetime.now(),
                remito.get('comprobante'),
                cuit,
                company,
                provincia,
                float(alicuota) if alicuota is not None else None,
                nro_factura,
                None,
                'Generado'
            )

            boton_cerrar = frame.locator("#close")
            boton_cerrar.nth(1).click()
            time.sleep(1)
            popup = frame.locator("div.fafpopup")
            if popup.is_visible() == True:
                close_button = frame.locator("#showAskPopupNoButton")
                close_button.click()
                time.sleep(3)
            pass
        else:
            print_with_time("No se encontraron registros para el remito")
        pass
   
def get_alicuotas(cuits: List[str]) -> Dict[str, Any]:
    """Consulta el endpoint de alícuotas para una lista de CUITs"""
    load_dotenv()
    url_alicuotas = os.getenv('FINNEGANS_ALICUOTAS_URL', 'http://localhost:8000/alicuotas/')
    url = f"{url_alicuotas}?cuits={','.join(cuits)}"
    
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print_with_time(f"Error al obtener las alícuotas: {response.status_code} - {response.text}")
        return {}
    
def wait_for_widget_value(element, widget_name, timeout=15000):
    selector = f'div.widget[name="{widget_name}"] input'
    element.wait_for_function(
        f"""() => {{
            const el = document.querySelector('{selector}');
            return el && el.value && el.value.trim() !== "" && el.value.trim() !== "0.00";
        }}""",
        timeout=timeout
    )
    # devolver valor una vez que está disponible
    return element.locator(selector).get_attribute("value")

def search_and_make_invoice_dasdach(page, frame, remito, company) -> None:
    
    print_with_time("Exploring navigation to add remito details...")
        
    frame.locator("button[onclick^='VRefrescarOperaciones']").click()
    time.sleep(2)
    
    
    grid_bodys = frame.locator("div.webix_ss_body")
    
    for i in range(grid_bodys.count()):
        if grid_bodys.nth(i).is_visible() == True:
            grid_body = grid_bodys.nth(i)
            break
            
    time.sleep(1)
    
    cells = grid_body.locator("div.webix_cell")
    
    print_with_time(f"Found {cells.count()} cells in the grid")
    
    print_with_time(f"Filtering for remito: {remito['comprobante']}")
    if cells.count() > 0:
        print_with_time(f"Se encontraron registros {cells.count()}")
        filters = frame.locator("input.TOOLBARTooltipSearch")
        filters.nth(6).fill(remito["comprobante"])
        filters.nth(6).press('Enter')
        time.sleep(2)
        cantidad_registros = grid_body.locator("div.webix_cell")
        if cantidad_registros.count() >0:
            frame.locator("input.mainCheckbox").nth(1).check()
            time.sleep(1)
            frame.locator('#OPERACIONSIGUIENTEPASO2_0').click()
            time.sleep(1)
            frame.locator('#OPERACIONFINALIZAR_0').click()
            time.sleep(6)
            #frame = page.wait_for_event("frameattached", timeout=10000)
            total_bruto = wait_for_widget_value(frame, "wdg_TotalBruto")
            
            if total_bruto is None or total_bruto == '' or float(total_bruto.replace(",", "")) == 0.0:
                print_with_time("Imposible generar factura: Total Bruto es cero o nulo")
                raise ValueError("Imposible generar factura: Total Bruto es cero o nulo")
            
            print_with_time("Ingresando al detalle de la factura")
            
            save_screenshot(page.screenshot(), f"finnegans_facturacion_factura_por_generar{remito['comprobante']}.png")
            
            
            if remito['identificacion_tributaria'] == 'C.U.I.T.' or remito['identificacion_tributaria'] == 'CUIT':
                cuit = re.sub(r'\D', '', remito['nro_de_identificacion'])
                alicuotas_info = get_alicuotas([cuit])
                
                encontrado = alicuotas_info.get('encontrados', 0)
                no_encontrado = alicuotas_info.get('no_encontrados', 0)
                
                if encontrado > 0:
                    alicuotas_a_cobrar = alicuotas_info.get('resultados')[0]['alicuota']
                else:
                    if remito['provincia_destino'] == 'Buenos Aires':
                        alicuotas_a_cobrar = 8.0  # default si no se encuentra
                        customer_update( frame, percepcion_valor, remito['nro_de_identificacion'])
                        raise ValueError("Se actualizó el cliente con la percepción por defecto del 8%")
                    else:
                        alicuotas_a_cobrar = 0.0  # default si no se encuentra
                
                percepcion_valor = remito['importe_no_gravado'] * alicuotas_a_cobrar / 100
                
                print_with_time(f"CUIT: {cuit} - Alicuota a cobrar: {alicuotas_a_cobrar}% - Percepcion valor: {percepcion_valor:.2f} - Provincia: {remito['provincia_destino']}")
                
                percepcion_calculada_text = frame.locator('div.widget[name="wdg_TotalRetenciones"] >> input').input_value()
                # Convertir texto a float (maneja formatos como "1.234,56" o "1234.56")
                percepcion_calculada_text = percepcion_calculada_text.replace(",", "")
                percepcion_calculada_float = round(float(percepcion_calculada_text), 2)
                percepcion_valor_float = round(float(percepcion_valor), 2)
                if percepcion_valor_float != percepcion_calculada_float:
                    print_with_time(f"Percepcion calculada no coincide con la esperada: en Finnegans {percepcion_calculada_float:.2f} vs del padron {percepcion_valor_float:.2f} Provincia: {remito['provincia_destino']}")
                    raise ValueError(f"Percepcion calculada no coincide con la esperada: en Finnegans {percepcion_calculada_float:.2f} vs del padron {percepcion_valor_float:.2f} Provincia: {remito['provincia_destino']}")
            else:
                print_with_time(f"Identificacion tributaria no es CUIT, no se agrega percepcion")
                alicuotas_a_cobrar = 0.0
                percepcion_valor = 0.0
                
            # Flag Obtener CEA Automatico al Guardar
            widget = frame.locator('div.widget[name="wdg_CAEAutomatico"]')
            if widget.is_visible() == True:
                checkbox = widget.locator('input[type="checkbox"]')
                checkbox.check()
                time.sleep(3)
            try:
                # TODO: Guardar Documento
                # Hay dos botones con el mismo id, se toma el segundo que es el boton con la palabra "Guardar "
                boton_guardar = frame.locator("#_onSave")
                print_with_time("Guardando la factura")
                boton_guardar.nth(1).click()
                time.sleep(7)
                
                
                valor_factura_comprobante = wait_for_widget_value(frame, "wdg_NumeroDocumento")
                save_screenshot(page.screenshot(), f"finnegans_facturacion_factura_guardada{remito['comprobante']}.png")
                
                # Busco numero de comprobante y lo guardo en nro_factura
                widget_doc = frame.locator('div.widget[name="wdg_NumeroDocumento"]')
                if widget_doc.is_visible() == True:
                    print_with_time("Guardando el numero de factura")
                    nro_factura = frame.locator('div.widget[name="wdg_NumeroDocumento"] >> input[type="textbox"]').input_value()
                    print_with_time(f"Nro de factura asignado: {nro_factura}")
                else:
                    nro_factura = None
                if nro_factura is None or nro_factura == '':
                    print_with_time("No se obtuvo numero de factura, la factura no fue generada correctamente")
                    raise ValueError("No se obtuvo numero de factura, la factura no fue generada correctamente")
                time.sleep(5)
                nro_cae = None
                for intento in range(3):
                    frame.locator('div.tab[name="OperacioninformacionFiscalTab"]').click()
                    widget_cae = frame.locator('div.widget[name="wdg_cai"]')
                    if widget_cae.is_visible() == True:
                        print_with_time("Obtengo el CAI/CAE")
                        nro_cae = frame.locator('div.widget[name="wdg_cai"] >> input[type="textbox"]').input_value()
                        print_with_time(f"Nro de CAI: {nro_cae}")
                        if nro_cae is not None and nro_cae != '':
                            break
                    if intento < 2:
                        print_with_time(f"Reintentando obtener CAE ({intento+1}/3)")
                        time.sleep(3)
                    
                if nro_cae is None or nro_cae == '':
                    print_with_time("No se obtuvo CAE, la factura no fue generada correctamente")
                    raise FacturacionAbortada("No se obtuvo CAE, la factura no fue generada correctamente")
                
                # Registrar en PostgreSQL con estado Generado (después del guardado real)
                try:
                    cuit = re.sub(r'\D', '', remito.get('nro_de_identificacion', '') or '')
                    provincia = remito.get('provincia_destino')
                    guardar_factura_generada(
                        datetime.now(),
                        remito.get('comprobante'),
                        cuit,
                        company,
                        provincia,
                        float(alicuotas_a_cobrar) if 'alicuotas_a_cobrar' in locals() else None,
                        nro_factura,
                        nro_cae,
                        'Generado'
                    )
                except Exception as e:
                    print_with_time(f"No se pudo registrar la factura: {e}")
            except Exception as e:
                print_with_time(f"Error al guardar la factura: {e}")
                raise FacturacionAbortada("Error al guardar la factura {e}")
            
            
            
            boton_cerrar = frame.locator("#close")
            boton_cerrar.nth(1).click()
            time.sleep(3)
            popup = frame.locator("div.fafpopup")
            if popup.is_visible() == True:
                close_button = frame.locator("#showAskPopupNoButton")
                close_button.click()
                time.sleep(3)
            pass
        else:
            print_with_time("No se encontraron registros para el remito")
        pass

def agregar_percepcion(frame, percepcion_valor):
    print_with_time(f"Agregando percepción por valor de: {percepcion_valor:.2f}")
    time.sleep(1)
    # Navegar a la pestaña de percepciones
    frame.locator('div.tab[name="Retenciones y Percepciones"]').click()
    time.sleep(1)
    
    # Hacer clic en el botón "Agregar Percepción"
    boton_agregar = frame.locator('div[name="Retenciones y Percepciones"] >> div.newButton')
    boton_agregar.click()
    time.sleep(1)
    
    
    tipo_percepcion= "Percepcion IIBB BAs (Padrón)"
    
    tipo_rercepcion_input = frame.locator('div.widget[name="wdg_RetencionTipoID"] >> input[type="textbox"]')
    tipo_rercepcion_input.fill(tipo_percepcion)
    tipo_rercepcion_input.press('Enter')
    time.sleep(1)
    tipo_rercepcion_input.press('Enter')
    
    
    retencion = "Percepción IIBB Buenos Aires" 
    retencion_input = frame.locator('div.widget[name="wdg_RetencionID"] >> input[type="textbox"]')
    retencion_input.fill(retencion)
    
    retencion_input.press('Enter')
    time.sleep(1)
    retencion_input.press('Enter')
    importe = percepcion_valor
    
    frame.locator('div.widget[name="wdg_ExcepcionPorcentaje"] >> input[type="textbox"]').fill(f"{importe:.2f}")
    
    hoy = datetime.now()
    
    #dia = f"{hoy.day:02d}"
    dia = '01'
    mes = f"{hoy.month:02d}"
    anio = str(hoy.year)

    # llenar los tres inputs
    frame.locator('div.widget[name="wdg_ExcepcionFechaDesde"] input[name="day"]').fill(dia)
    frame.locator('div.widget[name="wdg_ExcepcionFechaDesde"] input[name="month"]').fill(mes)
    frame.locator('div.widget[name="wdg_ExcepcionFechaDesde"] input[name="year"]').fill(anio)

    # Calcular el último día del mes en curso
    import calendar
    ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]
    dia_hasta = f"{ultimo_dia:02d}"

    frame.locator('div.widget[name="wdg_ExcepcionFechaHasta"] input[name="day"]').fill(dia_hasta)
    frame.locator('div.widget[name="wdg_ExcepcionFechaHasta"] input[name="month"]').fill(mes)
    frame.locator('div.widget[name="wdg_ExcepcionFechaHasta"] input[name="year"]').fill(anio)
    
    boton_agregar = frame.locator('a.WIDGETWidgetButton', has_text="Nuevo")
    boton_agregar.click()
    
    #TODO: capturar pantalla y guardar
    screenshot_bytes = frame.page.screenshot()
    save_screenshot(screenshot_bytes, "finnegans_facturacion_percepcion_1.png")
    
    boton_aceptar = frame.locator('#aceptar')
    boton_aceptar.click()
    
   
    time.sleep(2)
    
    print_with_time("Percepción agregada exitosamente")

def ejecutar_factura(page, remito, company) -> None:
    try:
        # Navegar a la sección de facturación
        time.sleep(2)
        if not navigate_to_section(page, "Facturas de Venta - Das Dach"):
            raise Exception("Failed to navigate to Facturación section")
        time.sleep(4)
        frame = create_new_invoice(page, remito)
        if not frame:
            raise Exception("Failed to create new invoice frame")
        if company == "AVIANCA":
            search_and_make_invoice_avianca(page, frame, remito, company)
        else:
            search_and_make_invoice_dasdach(page, frame, remito, company)
        print_with_time(f"Invoice created successfully for remito: {remito['comprobante']}")

    except Exception as e:
        print_with_time(f"Error processing remito {remito['comprobante']}: {e}")
        # Re-raise the exception to be caught by the calling function
        raise
    
def run_finnegans_facturacion(browser, context, page, company, resumen) -> tuple:
    if not page:
        print_with_time("Error: No active page session")
        return 0, 0, [], []

    print_with_time("=== FACTURACION MODULE ===")
    current_url = page.url
    print_with_time(f"Current URL: {current_url}")

    # Tomar screenshot del estado actual
    screenshot_bytes = page.screenshot()
    save_screenshot(screenshot_bytes, "finnegans_facturacion_start.png")
    select_company_action(page, company)

    # Contadores de éxito y error
    remitos_exitosos = 0
    remitos_fallidos = 0
    remitos_no_procesados = 0

    # Listas para tracking detallado
    remitos_exitosos_lista = []
    remitos_fallidos_lista = []
    remitos_no_procesados_lista = []    
    
    # Flag para abortar proceso completo si falta CAE
    abort_process = False

    # Buscar elementos de navegación o menús
    for i, remito in enumerate(resumen, 1):
        try:
            print_with_time(f"Processing remito {i}/{len(resumen)}: {remito['comprobante']} for client {remito['cliente']} CUIT: {remito['nro_de_identificacion']}")
            show_comprobante(page, f"Procesando remito: {remito['comprobante']} ({i}/{len(resumen)})")
            if remito['importe'] in (0, None, ''):
                remitos_no_procesados += 1
                remitos_no_procesados_lista.append({'comprobante': remito['comprobante'], 'razon': 'Monto 0'})
                print_with_time(f"Remito {remito['comprobante']} tiene monto 0, no se procesa")
                #continue
            else:
                
                if company == "AVIANCA":
                    ejecutar_factura(page, remito, company)
                    remitos_exitosos += 1
                    remitos_exitosos_lista.append(remito['comprobante'])
                    print_with_time(f"-> Remito {remito['comprobante']} procesado exitosamente")
                else:
                    remito_detalle = get_remito_detalle(remito['docnroint'])
                    
                    
                    # Parsear y validar fecha de entrega menor a la fecha actual
                    fecha_entrega_dt = None
                    if remito_detalle is not None:
                        fecha_raw = remito_detalle.get('USR_FechaEntrega')
                        print_with_time(f"Remito {remito['comprobante']} USR_FechaEntrega: {fecha_raw}")
                        if fecha_raw is not None:
                            fecha_entrega_dt = parse_fecha(fecha_raw)

                    if remito_detalle is not None and fecha_entrega_dt is not None and fecha_entrega_dt.date() < datetime.now().date():
                        # Solo por Debug
                        #if remito['comprobante'] == 'R-0001-00010644':
                        print_with_time(f"Remito {remito['comprobante']} tiene fecha de entrega {fecha_raw}, se intenta procesar")
                        ejecutar_factura(page, remito, company)
                        remitos_exitosos += 1
                        remitos_exitosos_lista.append(remito['comprobante'])
                        print_with_time(f"-> Remito {remito['comprobante']} Fecha Salida {fecha_raw} procesado exitosamente")
                    else:
                        print_with_time(f"Remito {remito['comprobante']} no tiene fecha de salida registrada, no se procesa")
                        remitos_no_procesados += 1
                        remitos_no_procesados_lista.append({'comprobante': remito['comprobante'], 'razon': 'Fecha de entrega no registrada o inválida'})
                        #continue  # Saltar al siguiente remito
                        
            
            
        except Exception as e:
            remitos_fallidos += 1
            error_trace = traceback.format_exc()
            error_msg = f"{str(e)}\n{error_trace}"
            remitos_fallidos_lista.append({'comprobante': remito['comprobante'], 'error': error_msg})
            print_with_time(f"!! Error procesando remito {remito['comprobante']}: {str(e)}")
            print_with_time(f"Stack trace:\n{error_trace}")
            # Si no se obtuvo CAE, marcar para abortar proceso completo
            if isinstance(e, FacturacionAbortada) or 'No se obtuvo CAE' in str(e):
                print_with_time("Abortando proceso de facturación por CAE faltante")
                abort_process = True
            # Continuar con el siguiente remito sin interrumpir el proceso
        finally:
            hide_comprobante(page)
            page.goto(page.url)
            if abort_process:
                print_with_time("Proceso de facturación abortado. No se procesarán más remitos.")
                break
            

    return remitos_exitosos, remitos_fallidos, remitos_exitosos_lista, remitos_fallidos_lista, remitos_no_procesados, remitos_no_procesados_lista

def run_finnegans_reports(browser, context, page) -> None:
    if not page:
        print_with_time("Error: No active page session")
        return
        
    print_with_time("=== REPORTS MODULE ===")
    current_url = page.url
    print_with_time(f"Current URL: {current_url}")
    
    screenshot_bytes = page.screenshot()
    save_screenshot(screenshot_bytes, "finnegans_reports_start.png")
    print_with_time("Ready for reports operations...")


    
def close_finnegans_session(browser, context):
    if context:
        # Obtener el path del video antes de cerrar el contexto (solo si está habilitado)
        enable_video = os.getenv('ENABLE_VIDEO_RECORDING', 'false').lower() == 'true'
        if enable_video:
            try:
                pages = context.pages
                for page in pages:
                    if hasattr(page, 'video') and page.video:
                        video_path = page.video.path()
                        if video_path:
                            print_with_time(f"Video grabado guardado en: {video_path}")
                            break
            except Exception as e:
                print_with_time(f"Error obteniendo path del video: {e}")
            
            print_with_time("Video recording stopped")
        
        context.close()
    if browser:
        browser.close()
    print_with_time("Session closed")

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
    
def show_comprobante(page, texto):
    page.evaluate(f"window.__hud && window.__hud.set('{texto}')")

def hide_comprobante(page):
    page.evaluate("window.__hud && window.__hud.hide()")
    
def process_company(company: str) -> None:
    inicio = datetime.now()
    print_with_time("Starting Finnegans login automation...")
    print_with_time(f"Fecha y hora de inicio: {inicio.strftime('%Y-%m-%d %H:%M:%S')}")


    remitos = get_remitos_pendientes(company)

    resumen = resumir_transacciones(remitos)
    print_with_time(f"Found {len(resumen)} unique remitos to process")

    remitos_exitosos = 0
    remitos_fallidos = 0
    remitos_no_procesados = 0
    remitos_exitosos_lista = []
    remitos_fallidos_lista = []
    remitos_no_procesados_lista = []            
    print_with_time("Remitos to be processed:")
    for remito in resumen:
        provincia = remito.get('provincia_destino', 'N/A')
        print_with_time(f" - {remito['comprobante']} for client {remito['cliente']} CUIT: {remito['nro_de_identificacion']} Provincia: {provincia}")
    
     # Solo proceder si hay remitos para procesar
    
    if len(resumen) > 0 and resumen is not None:
        with sync_playwright() as playwright:
            browser, context, page = run_finnegans_login(playwright)

            if browser and context and page:
                print_with_time(f"=== POST-LOGIN URL: {page.url} ===")

                # Ejecutar diferentes módulos
                remitos_exitosos, remitos_fallidos, remitos_exitosos_lista, remitos_fallidos_lista, remitos_no_procesados, remitos_no_procesados_lista = run_finnegans_facturacion(browser, context, page, company, resumen)

                # Opcional: ejecutar otros módulos
                # run_finnegans_reports(browser, context, page)

                #input("\nPress Enter to close browser...")
                close_finnegans_session(browser, context)
            else:
                print_with_time("Login failed, skipping additional operations")
                remitos_fallidos = len(resumen)
                remitos_fallidos_lista = [{'comprobante': r['comprobante'], 'error': 'Login failed'} for r in resumen]
            
    else:
        print_with_time("No remitos found to process")

    fin = datetime.now()
    tiempo_transcurrido = fin - inicio
    print_summary(remitos_exitosos, remitos_fallidos, remitos_exitosos_lista, remitos_fallidos_lista, remitos_no_procesados, remitos_no_procesados_lista, resumen, inicio, fin, fin - inicio)

def print_summary(remitos_exitosos, remitos_fallidos, remitos_exitosos_lista, remitos_fallidos_lista, remitos_no_procesados, remitos_no_procesados_lista, resumen, inicio, fin, tiempo_transcurrido):
    print_with_time("=" * 50)
    print_with_time("INICIO BODY")
    print_with_time("REPORTE FINAL DE PROCESAMIENTO")
    print_with_time("=" * 50)
    print_with_time(f"Total de remitos encontrados: {len(resumen)}")
    print_with_time(f"Remitos procesados exitosamente: {remitos_exitosos}")
    print_with_time(f"Remitos no procesados: {remitos_no_procesados}")
    print_with_time(f"Remitos con errores: {remitos_fallidos}")
    if len(resumen) > 0:
        porcentaje_exito = (remitos_exitosos / len(resumen)) * 100
        print_with_time(f"Porcentaje de éxito: {porcentaje_exito:.1f}%")

    # Lista detallada de remitos exitosos
    if remitos_exitosos_lista:
        print_with_time("")
        print_with_time("REMITOS PROCESADOS EXITOSAMENTE:")
        print_with_time("-" * 40)
        for i, remito in enumerate(remitos_exitosos_lista, 1):
            print_with_time(f"{i:2d}. {remito} - EXITOSO")

    # Lista detallada de remitos no procesados
    if remitos_no_procesados_lista:
        print_with_time("")
        print_with_time("REMITOS NO PROCESADOS:")
        print_with_time("-" * 40)
        for i, remito_info in enumerate(remitos_no_procesados_lista, 1):
            print_with_time(f"{i:2d}. {remito_info['comprobante']} - NO PROCESADO")
            print_with_time(f"    Razón: {remito_info['razon']}")
    # Lista detallada de remitos con errores
    if remitos_fallidos_lista:
        print_with_time("")
        print_with_time("REMITOS CON ERRORES:")
        print_with_time("-" * 40)
        for i, remito_info in enumerate(remitos_fallidos_lista, 1):
            print_with_time(f"{i:2d}. {remito_info['comprobante']} - ERROR")
            # Mostrar solo la primera línea del error en el resumen
            error_lines = remito_info['error'].split('\n')
            if error_lines:
                print_with_time(f"    Error: {error_lines[0]}")

        # Opcionalmente mostrar traces completos si hay pocos errores
        if len(remitos_fallidos_lista) <= 3:
            print_with_time("")
            print_with_time("DETALLES COMPLETOS DE ERRORES:")
            print_with_time("-" * 40)
            for i, remito_info in enumerate(remitos_fallidos_lista, 1):
                print_with_time(f"Error #{i} - Remito {remito_info['comprobante']}:")
                print_with_time(remito_info['error'])
                print_with_time("-" * 40)

    print_with_time('FIN BODY')
    print_with_time(f"Fecha y hora de inicio: {inicio.strftime('%Y-%m-%d %H:%M:%S')}")
    print_with_time(f"Fecha y hora de finalización: {fin.strftime('%Y-%m-%d %H:%M:%S')}")
    print_with_time(f"Tiempo transcurrido: {tiempo_transcurrido}")
    print_with_time("=" * 50)
    
def customer_update(page, cuit):
    navigate_to_section(page, "Clientes")
    time.sleep(2)
    frame = page.wait_for_event("frameattached", timeout=10000)
    frame=page.frames[1] # Ajusta el índice según sea necesario
    percepcion_valor = 0.0
    filters = frame.locator("input.TOOLBARTooltipSearch")
    filters.fill(cuit)
    filters.press('Enter')
    grid_body = frame.locator("div.webix_ss_body")
    cantidad_registros = grid_body.locator("div.webix_cell")
    if cantidad_registros.count() >0:
        percepcion_valor = 0
        link = frame.locator('div.webix_column[column="2"] a')
        link.first.click()
        time.sleep(2)
        agregar_percepcion( frame, percepcion_valor)
    
    boton_guardar = frame.locator("#_onSave")
    print_with_time("Guardando la percepcion del cliente")
    #boton_guardar.nth(1).click()
    boton_cerrar = frame.locator("#close")
    boton_cerrar.nth(1).click()
    time.sleep(1)
    
def main():
    import argparse

    parser = argparse.ArgumentParser(description='Process company invoices')
    parser.add_argument('--company', type=str, required=True, help='Company name to process')
    args = parser.parse_args()

    process_company(args.company)


if __name__ == "__main__":
    main()
