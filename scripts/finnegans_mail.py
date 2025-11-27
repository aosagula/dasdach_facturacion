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
from scripts.util import print_with_time, timestamp, parse_fecha, save_screenshot
from scripts.finnegans_common import close_finnegans_session, install_hud, get_token, run_finnegans_login
from scripts.db import guardar_factura_generada
 
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Excepción específica para abortar la facturación completa
class FacturacionAbortada(Exception):
    pass

# def parse_fecha(value: Any) -> Optional[datetime]:
#     """
#     Parsea fechas comunes y retorna un datetime o None.
#     Soporta: ISO 8601 (incluyendo sufijo 'Z'), 'YYYY-MM-DD', 'DD/MM/YYYY',
#     y 'YYYY-MM-DDTHH:MM:SS'. Optimizado para decisiones rápidas.
#     """
#     if value is None:
#         return None
#     if isinstance(value, datetime):
#         return value
#     if isinstance(value, str):
#         s = value.strip()
#         if not s:
#             return None

#         # ISO 8601 rápido (maneja 'Z' como UTC)
#         if 'T' in s:
#             if s.endswith('Z'):
#                 try:
#                     return datetime.fromisoformat(s.replace('Z', '+00:00'))
#                 except Exception:
#                     pass
#             # 'YYYY-MM-DDTHH:MM:SS' (y posibles offsets)
#             if len(s) >= 19 and s[4:5] == '-' and s[7:8] == '-' and s[10:11] == 'T':
#                 try:
#                     return datetime.fromisoformat(s)
#                 except Exception:
#                     try:
#                         return datetime.strptime(s[:19], '%Y-%m-%dT%H:%M:%S')
#                     except Exception:
#                         pass

#         # 'YYYY-MM-DD'
#         if len(s) == 10 and s[4:5] == '-' and s[7:8] == '-':
#             try:
#                 return datetime.strptime(s, '%Y-%m-%d')
#             except Exception:
#                 pass

#         # 'DD/MM/YYYY'
#         if len(s) == 10 and s[2:3] == '/' and s[5:6] == '/':
#             try:
#                 return datetime.strptime(s, '%d/%m/%Y')
#             except Exception:
#                 pass

#     return None

# def timestamp() -> str:
#     """Retorna el timestamp actual formateado"""
#     return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

# def print_with_time(message: str) -> None:
#     """Print con timestamp automático"""
#     print(f"[{timestamp()}] {message}")

# def get_token() -> str:
#     """Obtiene el token de autenticación desde la variable de entorno"""
#     load_dotenv()
    
#     client_id = os.getenv('FINNEGANS_CLIENT_ID', '')
#     client_secret = os.getenv('FINNEGANS_SECRET', '')
#     url=f"https://api.teamplace.finneg.com/api/oauth/token?grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}"
    
#     if not client_id or not client_secret:
#         util.print_with_time("Error: FINNEGANS_CLIENT_ID and FINNEGANS_SECRET must be set in .env file")
#         exit(1)
    
#     response = requests.get(url)
#     if response.status_code == 200:
#         data = response.text
#         return data
#     else:
#         util.print_with_time(f"Error al obtener el token: {response.status_code} - {response.text}")
#         exit(1)
        
        


#TODO: get_facturas_envio_pendiente
# Debe acceder a la tabla facturas_generadas y retornar los atributos bajo la condicion que el atributo empresa sea igual 'Das Dash' y que el estado sea 'Generado' y el nro_cae no sea nulo

    
def process_company(company: str) -> None:
    inicio = datetime.now()
    print_with_time("Starting Finnegans login automation...")
    print_with_time(f"Fecha y hora de inicio: {inicio.strftime('%Y-%m-%d %H:%M:%S')}")


    facturas_envio_pendiente = get_facturas_envio_pendiente()
    print_with_time(f"Found {len(facturas_envio_pendiente)} unique remitos to process")

    remitos_exitosos = 0
    remitos_fallidos = 0
    remitos_no_procesados = 0
    remitos_exitosos_lista = []
    remitos_fallidos_lista = []
    remitos_no_procesados_lista = []            
    print_with_time("Remitos to be processed:")
    for factura in facturas_envio_pendiente:
        
        print_with_time(f" - {factura['comprobante']} for client {factura['numero_factura']} CUIT: {factura['cuit']} CAE: {factura['nro_cae']}")
    
     # Solo proceder si hay remitos para procesar
    
    if len(facturas_envio_pendiente) > 0 and facturas_envio_pendiente is not None:
        with sync_playwright() as playwright:
            browser, context, page = run_finnegans_login(playwright)

            if browser and context and page:
                print_with_time(f"=== POST-LOGIN URL: {page.url} ===")

                # Ejecutar diferentes módulos
                remitos_exitosos, remitos_fallidos, remitos_exitosos_lista, remitos_fallidos_lista, remitos_no_procesados, remitos_no_procesados_lista = run_finnegans_print_factura(browser, context, page, company, factura)

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
    #print_summary(remitos_exitosos, remitos_fallidos, remitos_exitosos_lista, remitos_fallidos_lista, remitos_no_procesados, remitos_no_procesados_lista, resumen, inicio, fin, fin - inicio)

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
