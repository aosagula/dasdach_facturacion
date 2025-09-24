# Configuración de Email Service para Gmail API (Service Account)

## Variables de Entorno Requeridas

Agrega las siguientes variables a tu archivo `.env`:

```env
# Gmail API Service Account Configuration
GMAIL_SERVICE_ACCOUNT_FILE=path/to/service-account.json
# O alternativamente:
GMAIL_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"..."}
GMAIL_SENDER_EMAIL=tu_email@tudominio.com
```

**Nota:** Usa `GMAIL_SERVICE_ACCOUNT_FILE` para apuntar a un archivo JSON, o `GMAIL_SERVICE_ACCOUNT_JSON` para poner el JSON completo como variable de entorno.

## Configuración en Google Cloud Console

### 1. Crear un Proyecto en Google Cloud Console

1. Ve a [Google Cloud Console](https://console.cloud.google.com)
2. Crea un nuevo proyecto o selecciona uno existente
3. Anota el **Project ID**

### 2. Habilitar Gmail API

1. En el menú lateral, ve a **APIs & Services** > **Library**
2. Busca "Gmail API"
3. Haz clic en **Gmail API** y luego en **Enable**

### 3. Crear Service Account

1. Ve a **APIs & Services** > **Credentials**
2. Haz clic en **Create Credentials** > **Service Account**
3. Completa la información:
   - Service account name: `gmail-service`
   - Service account ID: `gmail-service` (se auto-completa)
   - Description: `Service Account para envío de emails`
4. Haz clic en **Create and Continue**
5. En **Grant this service account access to project** (opcional):
   - Role: `Project > Editor` (o más específico si lo prefieres)
6. Haz clic en **Continue** y luego **Done**

### 4. Generar Clave del Service Account

1. En la lista de Service Accounts, encuentra el que acabas de crear
2. Haz clic en el email del Service Account
3. Ve a la pestaña **Keys**
4. Haz clic en **Add Key** > **Create new key**
5. Selecciona **JSON** y haz clic en **Create**
6. Se descargará un archivo JSON - guárdalo de forma segura

### 5. Configurar Domain-Wide Delegation (G Suite/Google Workspace)

**Solo si usas G Suite/Google Workspace:**

1. En la configuración del Service Account, habilita **Enable Google Workspace Domain-wide Delegation**
2. Anota el **Client ID** del Service Account
3. En tu Google Admin Console:
   - Ve a **Security** > **API Controls** > **Domain-wide delegation**
   - Haz clic en **Add new**
   - Client ID: [Client ID del Service Account]
   - OAuth scopes: `https://www.googleapis.com/auth/gmail.send`
   - Haz clic en **Authorize**

### 6. Configurar Variables de Entorno

**Opción A: Archivo JSON**
```env
GMAIL_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
GMAIL_SENDER_EMAIL=tu-email@tudominio.com
```

**Opción B: JSON como string (más seguro para contenedores)**
```env
GMAIL_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"tu-proyecto",...}
GMAIL_SENDER_EMAIL=tu-email@tudominio.com
```

## Uso del Service Account

### Sin Autenticación Manual

Con Service Account **NO necesitas** autenticación manual:

1. **Configuración automática** - Solo necesitas las variables de entorno
2. **Sin browser** - No se abre ningún navegador web
3. **Sin tokens** - No se generan archivos de token
4. **Inmediato** - Funciona desde el primer uso

### Tipos de Configuración

**Para Gmail personal:** Necesitas Domain-Wide Delegation (más complejo)
**Para G Suite/Google Workspace:** Configuración directa con Domain-Wide Delegation

## Endpoints Disponibles

### 1. Envío JSON (recomendado para APIs)

```bash
POST /send-email/
Content-Type: application/json

{
  "to": "destinatario@email.com",
  "subject": "Asunto del email",
  "body": "<h1>Hola!</h1><p>Este es el cuerpo del email.</p>",
  "body_type": "html"
}
```

### 2. Envío con Form-Data (ideal para n8n)

```bash
POST /send-email-form/
Content-Type: multipart/form-data

to=destinatario@email.com
subject=Asunto del email
body=<h1>Hola!</h1><p>Este es el cuerpo del email.</p>
body_type=html
attachment=[archivo opcional]
```

## Configuración para n8n

### HTTP Request Node para n8n:

```
Method: POST
URL: http://tu-servidor:8000/send-email-form/
Body Content Type: Form-Data

Parameters:
- to: {{ $json.email }}
- subject: {{ $json.subject }}
- body: {{ $json.html_content }}
- body_type: html
- attachment: [desde nodo anterior si es necesario]
```

## Ejemplo de Respuesta Exitosa

```json
{
  "success": true,
  "message": "Email enviado exitosamente a destinatario@email.com",
  "message_id": "1234567890abcdef",
  "details": {
    "to": "destinatario@email.com",
    "subject": "Asunto del email",
    "body_type": "html",
    "attachment": "archivo.pdf"
  }
}
```

## Errores Comunes y Soluciones

### Error: "credenciales inválidas" / "service account file not found"
- Verifica que `GMAIL_SERVICE_ACCOUNT_FILE` apunte al archivo JSON correcto
- O que `GMAIL_SERVICE_ACCOUNT_JSON` contenga JSON válido
- Asegúrate de que el proyecto tenga Gmail API habilitado

### Error: "access_denied" / "insufficient permissions"
- Verifica que Domain-Wide Delegation esté configurado (G Suite/Workspace)
- Confirma que el scope `https://www.googleapis.com/auth/gmail.send` esté autorizado
- Verifica que `GMAIL_SENDER_EMAIL` sea un email válido del dominio

### Error: "invalid_grant" / "subject not found"
- El email en `GMAIL_SENDER_EMAIL` no existe o no tiene permisos
- Para Gmail personal, necesitas configuración adicional más compleja

### Error: "forbidden" / "API not enabled"
- Gmail API no está habilitada en el proyecto
- Ve a Google Cloud Console > APIs & Services > Library > Gmail API > Enable

## Seguridad

- **Nunca** commits las credenciales al repositorio
- Mantén el archivo `gmail_token.json` seguro y privado
- Usa variables de entorno para todas las credenciales
- Considera usar Google Service Accounts para aplicaciones de producción

## Tipos de Cuerpo Soportados

- **html**: Para emails con formato HTML (recomendado)
- **text**: Para emails de texto plano

## Archivos Adjuntos

- Soporta cualquier tipo de archivo
- Detección automática del tipo MIME
- Archivos temporales se eliminan automáticamente después del envío
- Tamaño máximo depende de la configuración de FastAPI (por defecto ~16MB)