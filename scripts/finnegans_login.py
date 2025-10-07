import os
from dotenv import load_dotenv
from playwright.sync_api import Playwright, sync_playwright
import time
import re
import sys
import os
import requests
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import threading
import traceback
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    Agrupa por COMPROBANTE (y usa TRANSACCIONID como ref secundaria si hiciera falta)
    y devuelve: comprobante, docnroint, fecha_comprobante, total_bruto, total_conceptos,
    total, cliente, condicion_pago, provincia_destino, identificacion_tributaria, nro_de_identificacion.
    """
    resumen_por_clave: Dict[tuple, Dict[str, Any]] = {}

    for row in items:
        comp = row.get("COMPROBANTE")
        trx_id = row.get("TRANSACCIONID")  # por si hubiera duplicados de comprobante en otra op.
        if not comp:
            # si faltara, saltamos este registro
            continue

        clave = (comp, trx_id)

        if clave in resumen_por_clave:
            # ya registrado, no necesitamos sobreescribir (son iguales a nivel cabecera)
            continue

        identificacion_tributaria = _coalesce(
            row,
            # variantes que suelen venir con typos
            "INDENTIFICACIONTRIBUTARIA",
            "IDENTIFICACIONTRIBUTARIA"
        )

        provincia_destino = _coalesce(
            row,
            "PROVINCIADESTINO",       # a nivel cabecera
            "PROVINCIADESTINOITEM"    # a nivel ítem
        )

        resumen_por_clave[clave] = {
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
            "importe": row.get("IMPORTE"),
            "importe_gravado": row.get("GRAVADO"),
            "importe_no_gravado": row.get("NO GRAVADO"),
        }

    # devolvemos como lista (orden por comprobante asc y luego por trx_id para estabilidad)
    return [resumen_por_clave[k] for k in sorted(resumen_por_clave.keys(), key=lambda x: (str(x[0]), x[1] or 0))]


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
            "record_video_size": {"width": 1280, "height": 720}
        }
    else:
        print_with_time("Video recording disabled")
    
    # Configurar modo headless desde variable de entorno
    headless_mode = os.getenv('HEADLESS', 'true').lower() == 'true'
    browser = playwright.chromium.launch(headless=headless_mode)
    context = browser.new_context(**context_options)
    page = context.new_page()
    install_hud(context)
    try:
        print_with_time("Navigating to Finnegans login page...")
        page.goto(webpage)
        
        print_with_time("Waiting for page to load...")
        page.wait_for_load_state('networkidle')
        
       
        
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
        
        page.get_by_role("button", name="Gestión Empresarial").click()
        page.get_by_text("Ventas", exact=True).click()
        
        page.get_by_text("Facturas").click()
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

def search_and_make_invoice_avianca(page, frame, remito) -> None:
    
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
            time.sleep(3)
            
            print_with_time("Ingresando al detalle de la factura")
            
            # Hay dos botones con el mismo id, se toma el segundo que es el boton con la palabra "Guardar "
            boton_guardar = frame.locator("#_onSave")
            print_with_time("Guardando la factura")
            boton_guardar.nth(1).click()
            time.sleep(5)
            
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
def search_and_make_invoice_dasdach(page, frame, remito) -> None:
    
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
            time.sleep(3)
            
            print_with_time("Ingresando al detalle de la factura")
            
            #TODO: agregar llamada al endpoint de alicuotas
            # endpoint : curl -X 'GET' \
            #                   'http://localhost:8000/alicuotas/?cuits=20223012931' \
            #                   -H 'accept: application/json'
            # resultado OK :
            # {
            #    "resultados": [
            #        {
            #        "cuit": "20223012931",
            #        "alicuota": null,
            #        "vigencia_desde": null,
            #        "vigencia_hasta": null,
            #        "fecha_emision": null,
            #        "encontrado": false
            #        }
            #    ],
            #    "total_consultados": 1,
            #    "encontrados": 0,
            #    "no_encontrados": 1
            #}
            
            cuit = re.sub(r'\D', '', remito['nro_de_identificacion'])
            alicuotas_info = get_alicuotas([cuit])
            
            
            
            # Hay dos botones con el mismo id, se toma el segundo que es el boton con la palabra "Guardar "
            # boton_guardar = frame.locator("#_onSave")
            # print_with_time("Guardando la factura")
            # boton_guardar.nth(1).click()
            # time.sleep(5)
            
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
     
def ejecutar_factura(page, remito, company) -> None:
    try:
        # Navegar a la sección de facturación
        time.sleep(2)
        if not navigate_to_section(page, "Facturación"):
            raise Exception("Failed to navigate to Facturación section")
        time.sleep(2)
        frame = create_new_invoice(page, remito)
        if not frame:
            raise Exception("Failed to create new invoice frame")
        if company == "AVIANCA":
            search_and_make_invoice_avianca(page, frame, remito)
        else:
            search_and_make_invoice_dasdach(page, frame, remito)
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

    # Listas para tracking detallado
    remitos_exitosos_lista = []
    remitos_fallidos_lista = []

    # Buscar elementos de navegación o menús
    for i, remito in enumerate(resumen, 1):
        try:
            print_with_time(f"Processing remito {i}/{len(resumen)}: {remito['comprobante']} for client {remito['cliente']} CUIT: {remito['nro_de_identificacion']}")
            show_comprobante(page, f"Procesando remito: {remito['comprobante']} ({i}/{len(resumen)})")
            if remito['importe'] in (0, None, ''):
                print_with_time(f"Remito {remito['comprobante']} tiene monto 0, no se procesa")
                #continue
            else:
                ejecutar_factura(page, remito, company)
            remitos_exitosos += 1
            remitos_exitosos_lista.append(remito['comprobante'])
            print_with_time(f"✓ Remito {remito['comprobante']} procesado exitosamente")
        except Exception as e:
            remitos_fallidos += 1
            error_trace = traceback.format_exc()
            error_msg = f"{str(e)}\n{error_trace}"
            remitos_fallidos_lista.append({'comprobante': remito['comprobante'], 'error': error_msg})
            print_with_time(f"✗ Error procesando remito {remito['comprobante']}: {str(e)}")
            print_with_time(f"Stack trace:\n{error_trace}")
            # Continuar con el siguiente remito sin interrumpir el proceso
        finally:
            hide_comprobante(page)

    return remitos_exitosos, remitos_fallidos, remitos_exitosos_lista, remitos_fallidos_lista
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
    remitos_exitosos_lista = []
    remitos_fallidos_lista = []
    
    #TODO: listar remitos a procesar
    print_with_time("Remitos to be processed:")
    for remito in resumen:
        print_with_time(f" - {remito['comprobante']} for client {remito['cliente']} CUIT: {remito['nro_de_identificacion']}")
    
     # Solo proceder si hay remitos para procesar
    
    if len(resumen) > 0 and resumen is not None:
        with sync_playwright() as playwright:
            browser, context, page = run_finnegans_login(playwright)

            if browser and context and page:
                print_with_time(f"=== POST-LOGIN URL: {page.url} ===")

                # Ejecutar diferentes módulos
                remitos_exitosos, remitos_fallidos, remitos_exitosos_lista, remitos_fallidos_lista = run_finnegans_facturacion(browser, context, page, company, resumen)

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
    print_summary(remitos_exitosos, remitos_fallidos, remitos_exitosos_lista, remitos_fallidos_lista, resumen, inicio, fin, fin - inicio)
def print_summary(remitos_exitosos, remitos_fallidos, remitos_exitosos_lista, remitos_fallidos_lista, resumen, inicio, fin, tiempo_transcurrido):
    print_with_time("=" * 50)
    print_with_time("REPORTE FINAL DE PROCESAMIENTO")
    print_with_time("=" * 50)
    print_with_time(f"Total de remitos encontrados: {len(resumen)}")
    print_with_time(f"Remitos procesados exitosamente: {remitos_exitosos}")
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

    print_with_time("")
    print_with_time(f"Fecha y hora de inicio: {inicio.strftime('%Y-%m-%d %H:%M:%S')}")
    print_with_time(f"Fecha y hora de finalización: {fin.strftime('%Y-%m-%d %H:%M:%S')}")
    print_with_time(f"Tiempo transcurrido: {tiempo_transcurrido}")
    print_with_time("=" * 50)
    
def main():
    
    #process_company("AVIANCA")
    process_company("Das Dach")
    # Reporte final


if __name__ == "__main__":
    main()