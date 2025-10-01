#!/usr/bin/env python3
"""
Script para verificar variables de entorno SMTP en Railway/local
"""

import os
from dotenv import load_dotenv

def main():
    print("🔍 VERIFICADOR DE VARIABLES DE ENTORNO SMTP")
    print("=" * 60)

    # Intentar cargar .env (solo funciona en desarrollo local)
    try:
        load_dotenv()
        print("✅ Archivo .env cargado (desarrollo local)")
    except:
        print("ℹ️  No hay archivo .env (normal en Railway/producción)")

    print("\n📋 VARIABLES SMTP REQUERIDAS:")
    print("-" * 40)

    # Variables SMTP requeridas
    smtp_vars = {
        'SMTP_SERVER': os.getenv('SMTP_SERVER'),
        'SMTP_PORT': os.getenv('SMTP_PORT'),
        'SMTP_USERNAME': os.getenv('SMTP_USERNAME'),
        'SMTP_PASSWORD': os.getenv('SMTP_PASSWORD'),
        'SMTP_SENDER_EMAIL': os.getenv('SMTP_SENDER_EMAIL')
    }

    all_configured = True
    for var_name, var_value in smtp_vars.items():
        if var_value:
            if var_name == 'SMTP_PASSWORD':
                display_value = f"{'*' * len(var_value)} (oculta)"
            else:
                display_value = var_value
            print(f"✅ {var_name:18} = {display_value}")
        else:
            print(f"❌ {var_name:18} = NO CONFIGURADA")
            all_configured = False

    print("\n" + "=" * 60)

    if all_configured:
        print("🎉 ¡TODAS LAS VARIABLES ESTÁN CONFIGURADAS!")
        print("\n💡 Para probar envío:")
        print("   python test_smtp_simple.py")
        print("   python test_endpoint_n8n.py email@destino.com 'Asunto' 'Mensaje'")
    else:
        print("⚠️  FALTAN VARIABLES DE ENTORNO")
        print("\n🔧 CONFIGURACIÓN EN RAILWAY:")
        print("   1. Ve a tu proyecto en Railway")
        print("   2. Pestaña 'Variables'")
        print("   3. Agrega las variables faltantes:")
        print()
        for var_name, var_value in smtp_vars.items():
            if not var_value:
                if var_name == 'SMTP_SERVER':
                    example = "smtp.gmail.com"
                elif var_name == 'SMTP_PORT':
                    example = "587"
                elif var_name == 'SMTP_USERNAME':
                    example = "tu-email@gmail.com"
                elif var_name == 'SMTP_PASSWORD':
                    example = "tu-app-password-de-gmail"
                elif var_name == 'SMTP_SENDER_EMAIL':
                    example = "tu-email@gmail.com"
                else:
                    example = "valor"
                print(f"      {var_name} = {example}")

        print("\n📱 PARA GMAIL APP PASSWORD:")
        print("   1. Activa autenticación de 2 factores")
        print("   2. Ve a https://myaccount.google.com/apppasswords")
        print("   3. Genera contraseña de aplicación")
        print("   4. Usa esa contraseña en SMTP_PASSWORD")

    print("\n" + "=" * 60)

    # Info adicional sobre el entorno
    print("🌍 INFORMACIÓN DEL ENTORNO:")
    print(f"   Python: {os.sys.version.split()[0]}")
    print(f"   Platform: {os.name}")

    # Detectar si estamos en Railway
    if os.getenv('RAILWAY_ENVIRONMENT'):
        print("   🚂 Ejecutándose en Railway")
        print(f"   Environment: {os.getenv('RAILWAY_ENVIRONMENT')}")
    else:
        print("   💻 Ejecutándose localmente")

if __name__ == "__main__":
    main()