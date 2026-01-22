
import os
import requests
import time

from util import print_with_time, timestamp, get_video_path, save_screenshot, install_hud
from dotenv import load_dotenv
from playwright.sync_api import Playwright
import traceback

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
        time.sleep(2)
        #page.wait_for_load_state('networkidle', timeout=10000)
        print_with_time(f"Navigated to {section_name} section")
        screenshot_bytes = page.screenshot()
        save_screenshot(screenshot_bytes, "finnegans_facturacion_loaded.png")
        
    
        return True
    except Exception as e:
        print_with_time(f"Error navigating to {section_name}: {e}")
        return False
    
def wait_in_all_frames(page, selector, timeout=15000):
    """
    Espera hasta que selector exista en algún frame.
    Devuelve el frame en el que apareció.
    """
    import time
    start = time.time()

    while True:
        for frame in page.frames:
            try:
                if frame.locator(selector).count() > 0:
                    # si el objeto existe pero no es visible, esperar visibilidad
                    try:
                        frame.locator(selector).wait_for(state="visible", timeout=2000)
                    except:
                        pass
                    return frame
            except:
                pass

        if (time.time() - start) * 1000 > timeout:
            raise TimeoutError(f"No apareció el selector '{selector}' en ningún frame.")
        
        time.sleep(0.1)
    
def find_frame_with_plantillas(page):
    for frame in page.frames:
        if frame.locator("a.TOOLBARBtnStandard.secondary.dropDown", has_text="Plantillas").count() > 0:
            return frame
    return None

#TODO: Modificar para buscar el frame con el div overDivPrint 
def find_frame_with_printer(page):
    for frame in page.frames:
        try:
            if frame.query_selector("div.overDivPrint") is not None:
                return frame
        except Exception:
            pass
    return None
def find_in_all_frames(page, selector):
    """
    Busca un selector dentro de todos los frames de la page.
    Retorna el frame donde el selector existe y es visible.
    """
    for frame in page.frames:
        loc = frame.locator(selector)
        try:
            if loc.count() > 0 and loc.first.is_visible():
                return frame
        except Exception as e:
            traceback.print_exc()
            print_with_time(f"Error checking frame for selector {selector}: {e}")
            pass
    return None  # si no se encuentra

def run_finnegans_login(playwright: Playwright) -> tuple:
    load_dotenv()
    
    username = os.getenv('USER_FINNEGANS')
    password = os.getenv('PASSWORD_FINNEGANS')
    workspace = os.getenv('WORKSPACE_FINNEGANS', '')
    webpage = os.getenv('WEBPAGE_FINNEGANS', 'https://services.finneg.com/login')
    base_origin = 'https://core-web.finneg.com'
    
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
                'Referer': base_origin + '/',
                'Origin': base_origin,
            }

        }
    else:
        print_with_time("Video recording disabled")
        context_options = {

            "no_viewport": True,
            "user_agent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36',
            "extra_http_headers": {
                'Referer': base_origin + '/',
                'Origin': base_origin,
            }

        }
    
    # Configurar modo headless desde variable de entorno
    headless_mode = os.getenv('HEADLESS', 'true').lower() == 'true'
    browser_name = os.getenv('PLAYWRIGHT_BROWSER', 'chromium').lower()
    browser_type = {
        'chromium': playwright.chromium,
        'firefox': playwright.firefox,
        'webkit': playwright.webkit,
    }.get(browser_name, playwright.chromium)
    
    launch_options = {"headless": headless_mode}
    if browser_type is playwright.chromium:
        launch_options["args"] = ['--start-maximized']
    browser = browser_type.launch(**launch_options)
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
        if not page.query_selector(username_element):
            username_element = 'input[name="email"]'
        if not page.query_selector(company_element):
            company_element = 'input[name="workspace"]'
        
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
