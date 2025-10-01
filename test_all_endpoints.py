#!/usr/bin/env python3
"""
Prueba todos los endpoints de email para verificar que funcionan
"""

import requests
import sys
import os
import json
from dotenv import load_dotenv

def test_endpoint(endpoint_name, url, data_type, data, expected_status=200):
    """Función helper para probar endpoints"""
    print(f"\n🧪 PROBANDO: {endpoint_name}")
    print(f"🌐 URL: {url}")
    print(f"📝 Tipo: {data_type}")
    print("-" * 50)

    try:
        if data_type == "json":
            response = requests.post(url, json=data, timeout=30)
        elif data_type == "form":
            response = requests.post(url, data=data, timeout=30)
        else:
            print("❌ Tipo de datos no soportado")
            return False

        print(f"📊 Status Code: {response.status_code}")

        if response.status_code == expected_status:
            try:
                result = response.json()
                if result.get('success'):
                    print("✅ ÉXITO!")
                    print(f"   📧 Mensaje: {result.get('message', 'N/A')}")
                    print(f"   🎯 Endpoint: {result.get('endpoint', 'N/A')}")
                    print(f"   🔧 Método: {result.get('method', 'N/A')}")
                    return True
                else:
                    print("❌ FALLÓ EN EL ENVÍO")
                    print(f"   🚨 Error: {result.get('error', 'Desconocido')}")
                    if result.get('suggestion'):
                        print(f"   💡 Sugerencia: {result.get('suggestion')}")
                    return False
            except json.JSONDecodeError:
                print(f"❌ Respuesta no es JSON válido: {response.text[:200]}")
                return False
        else:
            print(f"❌ Status code inesperado: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   🚨 Error: {error_data.get('error', 'Desconocido')}")
            except:
                print(f"   📄 Respuesta: {response.text[:200]}")
            return False

    except requests.exceptions.ConnectionError:
        print("❌ ERROR DE CONEXIÓN - ¿Está el servidor corriendo?")
        return False
    except requests.exceptions.Timeout:
        print("❌ TIMEOUT - El request tardó más de 30 segundos")
        return False
    except Exception as e:
        print(f"❌ ERROR INESPERADO: {e}")
        return False

def main():
    load_dotenv()

    # Configuración
    base_url = os.getenv('API_BASE_URL', 'http://localhost:8000')

    if len(sys.argv) < 2:
        print("❌ Uso: python test_all_endpoints.py <email_destino>")
        print("📝 Ejemplo: python test_all_endpoints.py pepe@gmail.com")
        sys.exit(1)

    email_destino = sys.argv[1]

    print("🚀 PRUEBA DE TODOS LOS ENDPOINTS DE EMAIL")
    print("=" * 60)
    print(f"📧 Email destino: {email_destino}")
    print(f"🌐 Servidor base: {base_url}")

    # Datos de prueba comunes
    asunto = "Prueba de endpoints desde script"
    mensaje = "<h1>Prueba exitosa!</h1><p>Este email fue enviado desde el script de prueba de endpoints.</p>"

    # Lista de endpoints a probar
    endpoints = [
        {
            "name": "/send-email/ (JSON)",
            "url": f"{base_url}/send-email/",
            "type": "json",
            "data": {
                "to": email_destino,
                "subject": f"{asunto} - JSON",
                "body": f"{mensaje}<p><strong>Endpoint:</strong> /send-email/ (JSON)</p>",
                "body_type": "html"
            }
        },
        {
            "name": "/send-email/ (Form-data)",
            "url": f"{base_url}/send-email/",
            "type": "form",
            "data": {
                "to": email_destino,
                "subject": f"{asunto} - Form-data",
                "body": f"{mensaje}<p><strong>Endpoint:</strong> /send-email/ (Form-data)</p>",
                "body_type": "html"
            }
        },
        {
            "name": "/send-email-form/",
            "url": f"{base_url}/send-email-form/",
            "type": "form",
            "data": {
                "to": email_destino,
                "subject": f"{asunto} - Form endpoint",
                "body": f"{mensaje}<p><strong>Endpoint:</strong> /send-email-form/</p>",
                "body_type": "html"
            }
        },
        {
            "name": "/send-email-smtp/",
            "url": f"{base_url}/send-email-smtp/",
            "type": "form",
            "data": {
                "to": email_destino,
                "subject": f"{asunto} - SMTP endpoint",
                "body": f"{mensaje}<p><strong>Endpoint:</strong> /send-email-smtp/</p>",
                "body_type": "html"
            }
        },
        {
            "name": "/send-email-n8n/",
            "url": f"{base_url}/send-email-n8n/",
            "type": "form",
            "data": {
                "to": email_destino,
                "subject": f"{asunto} - N8N endpoint",
                "body": f"{mensaje}<p><strong>Endpoint:</strong> /send-email-n8n/</p>",
                "body_type": "html"
            }
        }
    ]

    # Ejecutar pruebas
    resultados = []
    for endpoint in endpoints:
        resultado = test_endpoint(
            endpoint["name"],
            endpoint["url"],
            endpoint["type"],
            endpoint["data"]
        )
        resultados.append({
            "endpoint": endpoint["name"],
            "success": resultado
        })

    # Resumen
    print("\n" + "=" * 60)
    print("📊 RESUMEN DE RESULTADOS")
    print("=" * 60)

    exitosos = 0
    for resultado in resultados:
        status = "✅ ÉXITO" if resultado["success"] else "❌ FALLÓ"
        print(f"{status:12} {resultado['endpoint']}")
        if resultado["success"]:
            exitosos += 1

    print(f"\n📈 Total: {exitosos}/{len(resultados)} endpoints funcionaron correctamente")

    if exitosos == len(resultados):
        print("🎉 ¡TODOS LOS ENDPOINTS FUNCIONAN!")
    elif exitosos > 0:
        print("⚠️  Algunos endpoints funcionan, verifica la configuración SMTP")
    else:
        print("🚨 NINGÚN ENDPOINT FUNCIONA - Verifica:")
        print("   1. Que el servidor esté corriendo")
        print("   2. Configuración SMTP en .env")
        print("   3. App Password de Gmail")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()