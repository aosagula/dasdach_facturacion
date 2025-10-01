#!/usr/bin/env python3
"""
Prueba simple de SMTP - solo requiere configurar .env
"""

import os
from dotenv import load_dotenv
from email_service import send_email_smtp

def main():
    # Cargar variables de entorno
    load_dotenv()

    print("🧪 PRUEBA SIMPLE DE SMTP")
    print("=" * 40)

    # Verificar configuración
    smtp_username = os.getenv('SMTP_USERNAME')
    smtp_password = os.getenv('SMTP_PASSWORD')

    if not smtp_username or not smtp_password:
        print("❌ Faltan credenciales SMTP en .env")
        print("Configura:")
        print("SMTP_USERNAME=tu-email@gmail.com")
        print("SMTP_PASSWORD=tu-app-password")
        return

    print(f"📧 Usuario SMTP: {smtp_username}")
    print(f"🔑 Password: {'✅ Configurada' if smtp_password else '❌ Faltante'}")

    # Email de prueba
    destinatario = input("\n📩 Email destino: ")
    if not destinatario:
        destinatario = "test@example.com"

    asunto = "Prueba SMTP desde Python"
    mensaje = """
    <h1>¡Prueba exitosa!</h1>
    <p>Este email fue enviado desde el script de prueba SMTP.</p>
    <p><strong>Configuración:</strong> {}</p>
    <p><em>Timestamp:</em> {}</p>
    """.format(smtp_username, os.popen('date').read().strip())

    print(f"\n📤 Enviando a: {destinatario}")
    print(f"📝 Asunto: {asunto}")

    # Enviar email
    resultado = send_email_smtp(
        to=destinatario,
        subject=asunto,
        body=mensaje,
        body_type='html'
    )

    print("\n📊 RESULTADO:")
    print("=" * 40)

    if resultado.get('success'):
        print("✅ ¡EMAIL ENVIADO EXITOSAMENTE!")
        print(f"📧 Mensaje: {resultado.get('message')}")
        print(f"🏷️ Servidor: {resultado.get('smtp_server')}")
    else:
        print("❌ ERROR AL ENVIAR EMAIL")
        print(f"🚨 Error: {resultado.get('error')}")

        # Sugerencias de solución
        error_msg = resultado.get('error', '').lower()
        if 'autenticación' in error_msg or 'authentication' in error_msg:
            print("\n💡 SUGERENCIAS:")
            print("1. Activa autenticación de 2 factores en Gmail")
            print("2. Ve a https://myaccount.google.com/apppasswords")
            print("3. Genera una App Password")
            print("4. Usa esa password en SMTP_PASSWORD (no tu password normal)")

    print("\n" + "=" * 40)

if __name__ == "__main__":
    main()