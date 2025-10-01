#!/usr/bin/env python3
"""
Programa para probar envío de emails vía SMTP
Uso: python test_smtp.py destinatario@email.com "Asunto" "Mensaje"
"""

import sys
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import mimetypes
from pathlib import Path
from dotenv import load_dotenv

def main():
    # Cargar variables de entorno
    load_dotenv()

    # Verificar argumentos
    if len(sys.argv) < 4:
        print("❌ Uso: python test_smtp.py <destinatario> <asunto> <mensaje> [archivo_adjunto]")
        print("📝 Ejemplo: python test_smtp.py pepe@gmail.com 'Prueba' 'Hola mundo!'")
        print("📎 Con adjunto: python test_smtp.py pepe@gmail.com 'Con archivo' 'Mensaje' archivo.pdf")
        sys.exit(1)

    destinatario = sys.argv[1]
    asunto = sys.argv[2]
    mensaje = sys.argv[3]
    archivo_adjunto = sys.argv[4] if len(sys.argv) > 4 else None

    # Leer configuración SMTP desde .env
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_username = os.getenv('SMTP_USERNAME')
    smtp_password = os.getenv('SMTP_PASSWORD')
    sender_email = os.getenv('SMTP_SENDER_EMAIL', smtp_username)

    print("🔧 Configuración SMTP:")
    print(f"   Servidor: {smtp_server}:{smtp_port}")
    print(f"   Usuario: {smtp_username}")
    print(f"   Remitente: {sender_email}")
    print(f"   Contraseña: {'✅ Configurada' if smtp_password else '❌ No configurada'}")
    print()

    # Validar configuración
    if not smtp_username or not smtp_password:
        print("❌ Error: Faltan credenciales SMTP en el archivo .env")
        print("   Necesitas configurar:")
        print("   - SMTP_USERNAME=tu-email@gmail.com")
        print("   - SMTP_PASSWORD=tu-app-password")
        sys.exit(1)

    # Validar archivo adjunto si se especifica
    if archivo_adjunto and not os.path.exists(archivo_adjunto):
        print(f"❌ Error: Archivo adjunto no encontrado: {archivo_adjunto}")
        sys.exit(1)

    print("📧 Datos del email:")
    print(f"   Para: {destinatario}")
    print(f"   Asunto: {asunto}")
    print(f"   Mensaje: {mensaje[:50]}{'...' if len(mensaje) > 50 else ''}")
    if archivo_adjunto:
        print(f"   Adjunto: {archivo_adjunto}")
    print()

    try:
        # Crear mensaje
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = destinatario
        msg['Subject'] = asunto

        # Agregar cuerpo del mensaje
        msg.attach(MIMEText(mensaje, 'plain'))

        # Agregar archivo adjunto si existe
        if archivo_adjunto:
            print(f"📎 Procesando adjunto: {archivo_adjunto}")

            # Determinar tipo MIME
            content_type, encoding = mimetypes.guess_type(archivo_adjunto)
            if content_type is None or encoding is not None:
                content_type = 'application/octet-stream'

            main_type, sub_type = content_type.split('/', 1)

            with open(archivo_adjunto, 'rb') as fp:
                attachment = MIMEBase(main_type, sub_type)
                attachment.set_payload(fp.read())

            encoders.encode_base64(attachment)
            attachment.add_header(
                'Content-Disposition',
                f'attachment; filename={Path(archivo_adjunto).name}'
            )
            msg.attach(attachment)
            print(f"   ✅ Adjunto agregado: {Path(archivo_adjunto).name}")

        print("🔄 Conectando al servidor SMTP...")

        # Crear contexto SSL
        context = ssl.create_default_context()

        # Conectar y enviar
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            print("🔐 Iniciando TLS...")
            server.starttls(context=context)

            print("🔑 Autenticando...")
            server.login(smtp_username, smtp_password)

            print("📤 Enviando email...")
            text = msg.as_string()
            server.sendmail(sender_email, destinatario, text)

        print("✅ ¡Email enviado exitosamente!")
        print(f"   Desde: {sender_email}")
        print(f"   Para: {destinatario}")
        print(f"   Servidor: {smtp_server}")

    except smtplib.SMTPAuthenticationError as e:
        print("❌ Error de autenticación SMTP")
        print("   Verifica:")
        print("   1. Que tienes autenticación de 2 factores activada en Gmail")
        print("   2. Que generaste una App Password en https://myaccount.google.com/apppasswords")
        print("   3. Que usas la App Password (no tu contraseña normal) en SMTP_PASSWORD")
        print(f"   Error técnico: {e}")

    except smtplib.SMTPRecipientsRefused as e:
        print(f"❌ Email de destino rechazado: {destinatario}")
        print("   Verifica que el email de destino sea válido")
        print(f"   Error técnico: {e}")

    except smtplib.SMTPException as e:
        print(f"❌ Error SMTP: {e}")

    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        print("   Verifica tu conexión a internet y la configuración")

if __name__ == "__main__":
    main()