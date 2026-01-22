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
from util import print_with_time, timestamp, parse_fecha, save_screenshot
from finnegans_common import close_finnegans_session, install_hud, navigate_to_section, run_finnegans_login, select_company_action, find_in_all_frames, find_frame_with_printer,find_frame_with_plantillas, wait_in_all_frames
from db import get_facturas_envio_pendiente, update_factura_estado
 
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_token() -> str:
    """Obtiene el token de autenticación desde la variable de entorno."""
    load_dotenv()

    client_id = os.getenv('FINNEGANS_CLIENT_ID', '')
    client_secret = os.getenv('FINNEGANS_SECRET', '')
    url = f"https://api.teamplace.finneg.com/api/oauth/token?grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}"

    if not client_id or not client_secret:
        print_with_time("Error: FINNEGANS_CLIENT_ID and FINNEGANS_SECRET must be set in .env file")
        exit(1)

    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    print_with_time(f"Error al obtener el token: {response.status_code} - {response.text}")
    exit(1)


def get_vencimientos(fecha: Optional[str] = None, circuito: str = "CIRCGRAL", domain: str = "DASDACH") -> List[Dict[str, Any]]:
    if not fecha:
        fecha = datetime.now().strftime('%Y%m%d')
    token = get_token()
    url = (
        "https://api.finneg.com/api/reports/COMPOSICIONSALDOSCLIENTES"
        f"?domain={domain}"
        f"&PARAMWEBREPORT_fecha={fecha}"
        f"&PARAMWEBREPORT_circuitocontable={circuito}"
        f"&ACCESS_TOKEN={token}"
    )
    response = requests.get(url)
    if response.status_code != 200:
        print_with_time(f"Error al obtener vencimientos: {response.status_code} - {response.text}")
        return []
    try:
        data = response.json()
        
    except Exception:
        print_with_time("Error al parsear vencimientos: respuesta no es JSON válido")
        return []
    rows = [
        {"COMPROBANTE": row.get("COMPROBANTE"), "FECHACASHFLOW": row.get("FECHACASHFLOW")}
        for row in data
        if row.get("COMPROBANTE") and row.get("FECHACASHFLOW")
    ]
    rows.sort(key=lambda r: (r["COMPROBANTE"], r["FECHACASHFLOW"]))
    return rows


vencimientos = [] #get_vencimientos()
_vencimientos_index = None
_vencimientos_index_source = None

def get_fechacashflow_por_comprobante(comprobante: str, vencimientos_list: Optional[List[Dict[str, Any]]] = None) -> List[Any]:
    """Obtiene las FECHACASHFLOW de un comprobante buscando en el array vencimientos."""
    global _vencimientos_index, _vencimientos_index_source
    if vencimientos_list is None:
        vencimientos_list = vencimientos

    if _vencimientos_index is None or _vencimientos_index_source is not vencimientos_list:
        index: Dict[str, List[Any]] = {}
        for row in vencimientos_list:
            comp = row.get("COMPROBANTE")
            if not comp:
                continue
            index.setdefault(comp, []).append(row.get("FECHACASHFLOW"))
        _vencimientos_index = index
        _vencimientos_index_source = vencimientos_list

    return _vencimientos_index.get(comprobante, [])

def get_remito_detalle(DOCNROINT) -> list:
    """Obtiene el detalle de un remito del numero interno de finnegans"""
    load_dotenv()
    token = get_token()
    print_with_time(f"Obteniendo remitos pendientes para la empresa: {DOCNROINT}")

    url = f"https://api.teamplace.finneg.com/api/pedidoVenta/{DOCNROINT}?ACCESS_TOKEN={token}"

    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data

    print_with_time(f"Error al obtener los remitos: {response.status_code} - {response.text}")
    return []


def run_finnegans_print_factura(browser, context, page, company: str, facturas: list[dict]) -> tuple[int, int, list[dict], list[dict]]:
    fac_exitosos = 0
    fac_fallidos = 0
    fac_no_procesados = 0
    fac_exitosos_lista = []
    fac_fallidos_lista = []
    fac_no_procesados_lista = []  
    
    
    
    
    
    select_company_action(page, company)
    
    # TODO: Ver de acceder al modulo de facturas en finnegans, ver login_finnegans.py
    
    time.sleep(2)
    if not navigate_to_section(page, "Facturas de Venta - Das Dach"):
        raise Exception("Failed to navigate to Facturación section")
    time.sleep(6)
    frame = page.frames[1]
    frame_search = wait_in_all_frames(page, "input.TOOLBARTooltipSearch")
    filters = frame_search.locator("input.TOOLBARTooltipSearch")
    for factura in facturas:
        
        comprobante = factura['comprobante']
        numero_factura = factura['numero_factura']
        detalle_remito = get_remito_detalle(factura.get('docnroint'))
        
        OC_text = detalle_remito.get('USROCNUM') if detalle_remito else ''
        vencimientos_factura = get_fechacashflow_por_comprobante(numero_factura)
        
        # se usa solo para Debug
        #if numero_factura != 'A-0005-00006897':
        #    continue
        
        cuit = factura['cuit']
        nro_cae = factura['nro_cae']
        
        if filters.count() > 1:
            filters = filters.nth(0)

        filters.clear()
        filters.fill(numero_factura)
        filters.press('Enter')
        grid_body = frame_search.locator("div.webix_ss_body")
        
        cells = grid_body.locator("div.webix_cell")
        
            
        print_with_time(f"Found {cells.count()} cells in the grid")
        if cells.count() > 0:
                
            time.sleep(1)
            
           
            try:
                print_with_time(f"Processing factura {comprobante} for numero_factura {numero_factura} CUIT: {cuit} CAE: {nro_cae} OC: {OC_text} VTO: {vencimientos_factura}")
                # Aquí iría la lógica para imprimir o descargar la factura desde Finnegans
                # Por ejemplo, navegar a la página correcta, buscar la factura, descargarla, etc.
                # Simulamos éxito
                
                # Hace clic cobre la factura para abrirla
                grid_body.locator('div.webix_column[column="3"] a').first.click()
                
                time.sleep(3)
                
                frame_factura = find_in_all_frames(page, '#_onPrint')
                time.sleep(4)
                mail = frame_factura.locator('#_onPrint')
                count_mail = frame_factura.locator('#count_onMail')
                count_mail_text = count_mail.inner_text()
                count_mail_text = count_mail_text.strip() if count_mail_text else ""
                count_mail_value = int(count_mail_text) if count_mail_text else 0
                
                if count_mail_value == 0:
                    mail.click()
                
                    time.sleep(2)
                


                    frame_printer = find_in_all_frames(page, '#overDivPrint')
                    # NO SE REQUIERAN PLANTILLAS
                    # template = frame_mail.locator("a.TOOLBARBtnStandard.secondary.dropDown", has_text="Plantillas")
                    # template.last.click()
                    # frame_mail.locator('#listaPlantillas li.enabled').nth(2).click()
                    time.sleep(1)
                    #boton_close = frame_mail.locator("a.closePU")
                    #time.sleep(2)
                    
                    #boton_close.click()
                    
                    check = frame_printer.locator("tbody.body tr.gridRow td img[src*='item_chk0.gif']")
                    
                    if check.is_visible() > 0:
                        check.first.click()
                        
                    boton_enviar_x_mail = frame_printer.locator(
                                            "a.WIDGETWidgetButton",
                                            has_text="Enviar por Mail"
                                        ).click()
                    time.sleep(3)
                    frame_mail = find_in_all_frames(page, '#subjectInput')
                    
                    subject_object = frame_mail.locator("#subjectInput")
                    subject_object.clear()
                    if OC_text is None or OC_text.strip() == '':
                        OC_text = ""
                    else:
                        OC_text = f" OC: {OC_text}"  
                    subject_object.fill(f"Envío de Factura Das Dach {numero_factura} {OC_text}")
                    
                    subject_object.press('Tab')
                    body_frame = find_in_all_frames(page, "#tinymce")
                    body = body_frame.locator('#tinymce')
                    parrafo1 = body.locator("p").first
                    
                    parrafo1.fill(f"{OC_text}")
                    parrafo2 = body.locator("p").nth(1)
                    
                    parrafo2.fill(f"Vencimientos: {vencimientos_factura[0] if len(vencimientos_factura) > 0 else 'N/A'}")

                    frame_mail_botom = find_in_all_frames(page, "div.sendButton")
                    boton_enviar = frame_mail_botom.locator("div.sendButton")
                    boton_enviar.click()
                    fac_exitosos += 1
                    fac_exitosos_lista.append(f"{comprobante} - Factura {numero_factura}")
                    print_with_time(f"Factura {comprobante} Mail sent successfully")
                    
                    time.sleep(4)
                    boton_enviar_cerrar = frame_printer.locator(
                                            "a.WIDGETWidgetButton",
                                            has_text="Cerrar"
                                        ).click()
                    
                    
                    #boton_close = frame_mail.locator("a.closePU")
                    #time.sleep(2)
                    
                    #boton_close.click()
                    update_factura_estado(factura.get('id'), comprobante, 'Enviado')
                else:
                    print_with_time(f"Factura {comprobante} not processed, mail count: {count_mail_value}")
                    fac_no_procesados += 1
                    fac_no_procesados_lista.append({'comprobante': comprobante, 'razon': f"Mail count is {count_mail_value}, Mail ya enviado"})
                    update_factura_estado(factura.get('id'), comprobante, 'Enviado')
                
                
                frame_factura = find_in_all_frames(page, '#close')
                    
                    
                boton_factura_cerrar = frame_factura.locator(
                                        "a.TOOLBARBtnStandard",
                                        has_text="Cerrar"
                                    ).first.click()
                
            except Exception as e:
                fac_fallidos += 1
                fac_fallidos_lista.append({'comprobante': comprobante, 'error': str(e)})
                print_with_time(f"Error processing factura {comprobante}: {e}")
                descripcion = traceback.print_exc()
                print_with_time(descripcion)
        else:
            print_with_time(f"No cells found in the grid for factura {numero_factura}")
        time.sleep(3)
    return fac_exitosos, fac_fallidos, fac_exitosos_lista, fac_fallidos_lista, fac_no_procesados, fac_no_procesados_lista

def process_company(company: str) -> None:
    inicio = datetime.now()
    print_with_time("Starting Finnegans login automation...")
    print_with_time(f"Fecha y hora de inicio: {inicio.strftime('%Y-%m-%d %H:%M:%S')}")


    facturas_envio_pendiente = get_facturas_envio_pendiente()
    print_with_time(f"Found {len(facturas_envio_pendiente)} unique remitos to process")

    fac_exitosos = 0
    fac_fallidos = 0
    fac_no_procesados = 0
    fac_exitosos_lista = []
    fac_fallidos_lista = []
    fac_no_procesados_lista = []            
    print_with_time("Remitos to be processed:")
    for factura in facturas_envio_pendiente:
        
        print_with_time(f" - {factura['comprobante']} for factura {factura['numero_factura']} CUIT: {factura['cuit']} CAE: {factura['nro_cae']}")
    
     # Solo proceder si hay remitos para procesar
    
    if len(facturas_envio_pendiente) > 0 and facturas_envio_pendiente is not None:
        global vencimientos, _vencimientos_index, _vencimientos_index_source
        vencimientos = get_vencimientos()
        _vencimientos_index = None
        _vencimientos_index_source = None
        with sync_playwright() as playwright:
            browser, context, page = run_finnegans_login(playwright)

            if browser and context and page:
                print_with_time(f"=== POST-LOGIN URL: {page.url} ===")

                # Ejecutar diferentes módulos
                fac_exitosos, fac_fallidos, fac_exitosos_lista, fac_fallidos_lista, fac_no_procesados, fac_no_procesados_lista = run_finnegans_print_factura(browser, context, page, company, facturas_envio_pendiente)

                # Opcional: ejecutar otros módulos
                # run_finnegans_reports(browser, context, page)

                #input("\nPress Enter to close browser...")
                close_finnegans_session(browser, context)
            else:
                print_with_time("Login failed, skipping additional operations")
                #remitos_fallidos = len(resumen)
                #remitos_fallidos_lista = [{'comprobante': r['comprobante'], 'error': 'Login failed'} for r in resumen]
            
    else:
        print_with_time("No remitos found to process")

    fin = datetime.now()
    tiempo_transcurrido = fin - inicio
    print_summary(fac_exitosos, fac_fallidos, fac_exitosos_lista, fac_fallidos_lista, fac_no_procesados, fac_no_procesados_lista, facturas_envio_pendiente, inicio, fin, fin - inicio)

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
    

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Process company invoices')
    parser.add_argument('--company', type=str, required=True, help='Company name to process')
    args = parser.parse_args()

    process_company(args.company)


if __name__ == "__main__":
    main()
