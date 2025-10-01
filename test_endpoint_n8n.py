#!/usr/bin/env python3
"""
Prueba del endpoint /send-email-n8n/ usando requests
"""

import requests
import sys
import os
from dotenv import load_dotenv

def main():
    load_dotenv()

    # Configuración del endpoint
    base_url = os.getenv('API_BASE_URL', 'http://localhost:8000')
    endpoint = f"{base_url}/send-email-n8n/"

    print("🧪 PRUEBA ENDPOINT /send-email-n8n/")
    print("=" * 50)
    print(f"🌐 URL: {endpoint}")

    # Verificar argumentos
    if len(sys.argv) < 4:
        print("❌ Uso: python test_endpoint_n8n.py <email> <asunto> <mensaje>")
        print("📝 Ejemplo: python test_endpoint_n8n.py pepe@gmail.com 'Prueba API' 'Hola desde la API!'")
        sys.exit(1)

    email = sys.argv[1]
    asunto = sys.argv[2]
    mensaje = sys.argv[3]

    # Datos para el endpoint
    data = {
        'to': email,
        'subject': asunto,
        'body': f"<h1>Prueba desde API</h1><p>{mensaje}</p><p><em>Endpoint: /send-email-n8n/</em></p>",
        'body_type': 'html'
    }

    print(f"📧 Para: {email}")
    print(f"📝 Asunto: {asunto}")
    print(f"💬 Mensaje: {mensaje}")
    print()

    try:
        print("📤 Enviando request...")

        # Enviar request al endpoint
        response = requests.post(endpoint, data=data, timeout=30)

        print(f"📊 Status Code: {response.status_code}")
        print()

        # Procesar respuesta
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("✅ ¡EMAIL ENVIADO EXITOSAMENTE!")
                print(f"📧 Mensaje: {result.get('message')}")
                print(f"🏷️ Servidor: {result.get('smtp_server')}")
                print(f"👤 Remitente: {result.get('sender')}")
                print(f"🔧 Método: {result.get('method')}")
                print(f"🎯 Endpoint: {result.get('endpoint')}")
            else:
                print("❌ ERROR EN EL ENVÍO")
                print(f"🚨 Error: {result.get('error')}")
                if result.get('suggestion'):
                    print(f"💡 Sugerencia: {result.get('suggestion')}")
        else:
            print("❌ ERROR HTTP")
            try:
                error_data = response.json()
                print(f"🚨 Error: {error_data.get('error', 'Error desconocido')}")
                print(f"🎯 Endpoint: {error_data.get('endpoint', 'N/A')}")
                if error_data.get('smtp_error_type'):
                    print(f"🔧 Tipo de error SMTP: {error_data.get('smtp_error_type')}")
                if error_data.get('suggestion'):
                    print(f"💡 Sugerencia: {error_data.get('suggestion')}")
            except:
                print(f"📄 Respuesta: {response.text}")

    except requests.exceptions.ConnectionError:
        print("❌ ERROR DE CONEXIÓN")
        print("   Verifica que el servidor esté ejecutándose")
        print(f"   URL: {endpoint}")

    except requests.exceptions.Timeout:
        print("❌ TIMEOUT")
        print("   El request tardó más de 30 segundos")

    except Exception as e:
        print(f"❌ ERROR INESPERADO: {e}")

    print("\n" + "=" * 50)

if __name__ == "__main__":
    main()