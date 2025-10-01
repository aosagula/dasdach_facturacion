#!/usr/bin/env python3
"""
Script para probar diferentes métodos HTTP con los endpoints de n8n
"""

import requests
import sys
import os
from dotenv import load_dotenv

def test_endpoint(name, method, url, data=None, params=None):
    """Función para probar un endpoint específico"""
    print(f"\n🧪 PROBANDO: {name}")
    print(f"🔧 Método: {method}")
    print(f"🌐 URL: {url}")
    if params:
        print(f"📝 Query params: {params}")
    if data:
        print(f"📝 Form data: {list(data.keys())}")
    print("-" * 50)

    try:
        if method == "GET":
            response = requests.get(url, params=params, timeout=15)
        elif method == "POST":
            response = requests.post(url, data=data, timeout=15)
        else:
            print(f"❌ Método {method} no soportado")
            return False

        print(f"📊 Status: {response.status_code}")

        try:
            result = response.json()
            if result.get('success'):
                print("✅ ÉXITO!")
                print(f"   📧 Mensaje: {result.get('message', 'N/A')}")
                return True
            else:
                print("❌ FALLÓ")
                print(f"   🚨 Error: {result.get('error', 'Desconocido')}")
                print(f"   🎯 Endpoint: {result.get('endpoint', 'N/A')}")
                print(f"   🔧 Método detectado: {result.get('method', 'N/A')}")
                return False
        except:
            print(f"📄 Respuesta (no JSON): {response.text[:300]}")
            return False

    except requests.exceptions.ConnectionError:
        print("❌ ERROR DE CONEXIÓN")
        return False
    except requests.exceptions.Timeout:
        print("❌ TIMEOUT")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    load_dotenv()

    if len(sys.argv) < 2:
        print("❌ Uso: python test_n8n_methods.py <email_destino>")
        print("📝 Ejemplo: python test_n8n_methods.py test@gmail.com")
        sys.exit(1)

    email = sys.argv[1]
    base_url = os.getenv('API_BASE_URL', 'http://localhost:8000')

    print("🚀 PRUEBA DE MÉTODOS HTTP PARA N8N")
    print("=" * 60)
    print(f"📧 Email destino: {email}")
    print(f"🌐 Servidor: {base_url}")

    # Datos de prueba
    form_data = {
        'to': email,
        'subject': 'Prueba método HTTP',
        'body': '<h1>Prueba de método HTTP</h1><p>Email enviado desde script de prueba.</p>',
        'body_type': 'html'
    }

    query_params = {
        'to': email,
        'subject': 'Prueba GET',
        'body': 'Email enviado via GET desde script de prueba',
        'body_type': 'html'
    }

    # Lista de pruebas
    tests = [
        {
            "name": "GET /send-email-n8n/ (debería fallar con info)",
            "method": "GET",
            "url": f"{base_url}/send-email-n8n/",
            "params": None,
            "data": None
        },
        {
            "name": "POST /send-email-n8n/ (debería funcionar)",
            "method": "POST",
            "url": f"{base_url}/send-email-n8n/",
            "params": None,
            "data": form_data
        },
        {
            "name": "GET /send-email-n8n-hybrid/ (debería funcionar)",
            "method": "GET",
            "url": f"{base_url}/send-email-n8n-hybrid/",
            "params": query_params,
            "data": None
        },
        {
            "name": "POST /send-email-n8n-hybrid/ (debería funcionar)",
            "method": "POST",
            "url": f"{base_url}/send-email-n8n-hybrid/",
            "params": None,
            "data": form_data
        }
    ]

    # Ejecutar pruebas
    resultados = []
    for test in tests:
        resultado = test_endpoint(
            test["name"],
            test["method"],
            test["url"],
            test.get("data"),
            test.get("params")
        )
        resultados.append({
            "test": test["name"],
            "success": resultado
        })

    # Resumen
    print("\n" + "=" * 60)
    print("📊 RESUMEN")
    print("=" * 60)

    exitosos = 0
    for resultado in resultados:
        status = "✅ ÉXITO" if resultado["success"] else "❌ FALLÓ"
        print(f"{status:12} {resultado['test']}")
        if resultado["success"]:
            exitosos += 1

    print(f"\n📈 Resultado: {exitosos}/{len(resultados)} pruebas exitosas")

    print("\n💡 RECOMENDACIONES PARA N8N:")
    print("1. Usa /send-email-n8n-hybrid/ si tienes problemas con redirects")
    print("2. Configura método POST en n8n HTTP Request")
    print("3. Body Content Type: Form-Data")
    print("4. Si ves redirects GET, el endpoint híbrido los maneja")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()