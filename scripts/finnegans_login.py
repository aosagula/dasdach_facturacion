import os
from dotenv import load_dotenv
from playwright.sync_api import Playwright, sync_playwright
import time
import re
import sys
sys.path.append('/app')
from file_manager import save_photo

def run_finnegans_login(playwright: Playwright) -> tuple:
    load_dotenv()
    
    username = os.getenv('USER_FINNEGANS')
    password = os.getenv('PASSWORD_FINNEGANS')
    workspace = os.getenv('WORKSPACE_FINNEGANS', '')
    webpage = os.getenv('WEBPAGE_FINNEGANS', 'https://services.finneg.com/login')
    
    if not username or not password:
        print("Error: USER_FINNEGANS and PASSWORD_FINNEGANS must be set in .env file")
        return None, None, None
    
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    
    try:
        print("Navigating to Finnegans login page...")
        page.goto(webpage)
        
        print("Waiting for page to load...")
        page.wait_for_load_state('networkidle')
        
       
        
        print("Looking for login form elements...")
        page.wait_for_timeout(2000)
        
        username_element = 'input[name="userName"]'
        password_element = 'input[name="password"]'
        company_element = 'input[name="empresa"]'
        
        print("Filling credentials...")
        page.fill(username_element, username)
        page.fill(password_element, password)
        
        if workspace:
            print(f"Filling company field with: {workspace}")
            page.fill(company_element, workspace)
        
        print("Submitting login form...")
        submit_button = page.locator('input[name="standardSubmit"]')
        print("Taking screenshot for debugging...")
        screenshot_bytes = page.screenshot()
        save_photo(screenshot_bytes, "finnegans_login_page.png", "finnegans_login")
        
        submit_button.click()
        
        print("Waiting for login to complete...")
        
        # Esperar a que la URL cambie después del login
        try:
            page.wait_for_url(lambda url: 'login' not in url.lower(), timeout=15000)
            current_url = page.url
            print(f"Login successful! Redirected to: {current_url}")
            
            # Tomar screenshot de la página después del login
            screenshot_bytes = page.screenshot()
            save_photo(screenshot_bytes, "finnegans_post_login_page.png", "finnegans_login")
            
            # Esperar a que la página se cargue completamente
            page.wait_for_load_state('networkidle', timeout=10000)
            
        except Exception as redirect_error:
            current_url = page.url
            print(f"Login redirect timeout. Current URL: {current_url}")
            if 'login' in current_url.lower():
                print("Login may have failed - still on login page")
                screenshot_bytes = page.screenshot()
                save_photo(screenshot_bytes, "finnegans_login_failed_page.png", "finnegans_login")
                return None, None, None
            
        time.sleep(2)
        return browser, context, page
        
    except Exception as e:
        print(f"Error during login: {e}")
        if context:
            context.close()
        if browser:
            browser.close()
        return None, None, None

def run_finnegans_facturacion(browser, context, page) -> None:
    if not page:
        print("Error: No active page session")
        return
        
    print("=== FACTURACION MODULE ===")
    current_url = page.url
    print(f"Current URL: {current_url}")
    
    # Tomar screenshot del estado actual
    screenshot_bytes = page.screenshot()
    save_photo(screenshot_bytes, "finnegans_facturacion_start.png", "finnegans_login")
    
    # Buscar elementos de navegación o menús
    try:
        page.locator("#menu_button i").click()
        page.get_by_role("button", name=" Gestión Empresarial").click()
        page.get_by_text("Ventas", exact=True).click()
        #page.get_by_text("Facturas").click()
        
        
        # page.wait_for_url(lambda url: 'login' not in url.lower(), timeout=15000)
        # current_url = page.url
        # print(f"Login successful! Redirected to: {current_url}")
        
        # Tomar screenshot de la página después del login
       
        
        
        
        
        #with context.expect_page() as new_page_info:
        page.get_by_text("Facturas").click()
        #new_page = new_page_info.value
        time.sleep(2)
        #page.wait_for_load_state('networkidle', timeout=10000)
        print("Navigated to Facturas section")
        screenshot_bytes = page.screenshot()
        save_photo(screenshot_bytes, "finnegans_facturacion_loaded.png", "finnegans_login")
        
        time.sleep(2)
        print("Nueva Factura button is visible")
        screenshot_bytes = page.screenshot()
        save_photo(screenshot_bytes, "finnegans_facturacion_nueva_factura_1.png", "finnegans_login")
        
        frame = page.frames[1] # Ajusta el índice según sea necesario
        
        btn_nueva_factura = frame.locator("#ActionNewDF")
        btn_nueva_factura.click()
        
        elemento = frame.locator("ul >> text=Factura de Venta Electrónica 0005")
        elemento.click()
        time.sleep(2)
        print("Nueva Factura button is visible")
        screenshot_bytes = page.screenshot()
        save_photo(screenshot_bytes, "finnegans_facturacion_nueva_factura_2.png", "finnegans_login")
        
        asistente = frame.locator("input[type=radio][name='WizardWorkflowSelect'][value='160']")
        asistente.click()
        time.sleep(2)
        print("Nueva Factura button is visible")
        screenshot_bytes = page.screenshot()
        save_photo(screenshot_bytes, "finnegans_facturacion_nueva_factura_3.png", "finnegans_login")
        
        frame.locator('#OPERACIONSIGUIENTEPASO1_0').click()
        time.sleep(2)
        
        
        #busqueda = frame.locator('#NAME_VORGANIZACION_0')
        #busqueda.type('TRANSVIP S.A.')
        #time.sleep(1)

        #busqueda.press('Enter')
        #time.sleep(1)
        
        frame.locator("button[onclick^='VRefrescarOperaciones']").click()
        time.sleep(2)
        
        
        grid_body = frame.locator("div.webix_ss_body")
        time.sleep(1)
        
        cells = grid_body.locator("div.webix_cell")
        
        print(f"Found {cells.count()} cells in the grid")
        
        if cells.count() > 0:
            filters = frame.locator("input.TOOLBARTooltipSearch")
            filters.nth(6).fill("P-0000-00006716")
            filters.nth(6).press('Enter')
            time.sleep(2)
            frame.locator("input.mainCheckbox").nth(1).check()
            pass
        
           
    except Exception as e:
        print(f"Error exploring navigation: {e}")
    
    print("Ready for additional facturacion operations...")

def run_finnegans_reports(browser, context, page) -> None:
    if not page:
        print("Error: No active page session")
        return
        
    print("=== REPORTS MODULE ===")
    current_url = page.url
    print(f"Current URL: {current_url}")
    
    screenshot_bytes = page.screenshot()
    save_photo(screenshot_bytes, "finnegans_reports_start.png", "finnegans_login")
    print("Ready for reports operations...")

def navigate_to_section(page, section_name: str) -> bool:
    """
    Navega a una sección específica del sistema
    """
    print(f"Trying to navigate to: {section_name}")
    
    try:
        # Buscar enlaces que contengan el nombre de la sección
        section_link = page.locator(f'a:has-text("{section_name}")').first
        if section_link.is_visible():
            section_link.click()
            page.wait_for_load_state('networkidle', timeout=10000)
            print(f"Successfully navigated to {section_name}")
            return True
        else:
            print(f"Could not find navigation link for {section_name}")
            return False
    except Exception as e:
        print(f"Error navigating to {section_name}: {e}")
        return False
    
def close_finnegans_session(browser, context):
    if context:
        context.close()
    if browser:
        browser.close()
    print("Session closed")
    
def main():
    print("Starting Finnegans login automation...")
    with sync_playwright() as playwright:
        browser, context, page = run_finnegans_login(playwright)
        
        if browser and context and page:
            print(f"\n=== POST-LOGIN URL: {page.url} ===")
            
            # Ejecutar diferentes módulos
            run_finnegans_facturacion(browser, context, page)
            
            # Opcional: ejecutar otros módulos
            # run_finnegans_reports(browser, context, page)
            
            #input("\nPress Enter to close browser...")
            close_finnegans_session(browser, context)
        else:
            print("Login failed, skipping additional operations")

if __name__ == "__main__":
    main()