import os
import base64
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, Union
import mimetypes
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Alcance necesario para enviar emails
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

class GmailService:
    def __init__(self):
        self.service = None
        self.credentials = None

    def authenticate(self):
        """Autentica con Gmail API usando Service Account"""
        try:
            # Método 1: Desde archivo JSON
            service_account_file = os.getenv('GMAIL_SERVICE_ACCOUNT_FILE')
            if service_account_file and os.path.exists(service_account_file):
                creds = Credentials.from_service_account_file(
                    service_account_file,
                    scopes=SCOPES
                )
            else:
                # Método 2: Desde variable de entorno JSON
                service_account_json = os.getenv('GMAIL_SERVICE_ACCOUNT_JSON')
                if service_account_json:
                    try:
                        # Intentar parsear como JSON
                        service_account_info = json.loads(service_account_json)
                    except json.JSONDecodeError:
                        raise ValueError("GMAIL_SERVICE_ACCOUNT_JSON contiene JSON inválido")

                    creds = Credentials.from_service_account_info(
                        service_account_info,
                        scopes=SCOPES
                    )
                else:
                    raise ValueError(
                        "Se requiere GMAIL_SERVICE_ACCOUNT_FILE o GMAIL_SERVICE_ACCOUNT_JSON en el .env"
                    )

            # Configurar delegación para enviar como el usuario especificado
            sender_email = os.getenv('GMAIL_SENDER_EMAIL')
            if sender_email:
                creds = creds.with_subject(sender_email)

            self.credentials = creds
            self.service = build('gmail', 'v1', credentials=creds)
            return True

        except Exception as e:
            raise ValueError(f"Error autenticando con Service Account: {e}")

    def create_message(self, to: str, subject: str, body: str, body_type: str = 'html', attachment_path: Optional[str] = None):
        """Crea un mensaje de email con posible adjunto"""
        message = MIMEMultipart()
        message['to'] = to
        message['subject'] = subject

        # Obtener el email del remitente desde .env o usar el email autenticado
        sender_email = os.getenv('GMAIL_SENDER_EMAIL', 'me')
        message['from'] = sender_email

        # Adjuntar el cuerpo del mensaje
        if body_type.lower() == 'html':
            message.attach(MIMEText(body, 'html'))
        else:
            message.attach(MIMEText(body, 'plain'))

        # Adjuntar archivo si se proporciona
        if attachment_path and os.path.exists(attachment_path):
            attachment_path = Path(attachment_path)

            # Determinar el tipo MIME del archivo
            content_type, encoding = mimetypes.guess_type(str(attachment_path))
            if content_type is None or encoding is not None:
                content_type = 'application/octet-stream'

            main_type, sub_type = content_type.split('/', 1)

            with open(attachment_path, 'rb') as fp:
                attachment = MIMEBase(main_type, sub_type)
                attachment.set_payload(fp.read())

            encoders.encode_base64(attachment)
            attachment.add_header(
                'Content-Disposition',
                f'attachment; filename={attachment_path.name}'
            )
            message.attach(attachment)

        # Codificar el mensaje en base64
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        return {'raw': raw_message}

    def send_email(self, to: str, subject: str, body: str, body_type: str = 'html', attachment_path: Optional[str] = None):
        """Envía un email usando Gmail API"""
        try:
            if not self.service:
                self.authenticate()

            message = self.create_message(to, subject, body, body_type, attachment_path)

            # Enviar el mensaje
            result = self.service.users().messages().send(userId='me', body=message).execute()

            return {
                'success': True,
                'message_id': result.get('id'),
                'message': f'Email enviado exitosamente a {to}'
            }

        except HttpError as error:
            return {
                'success': False,
                'error': f'Error de Gmail API: {error}',
                'details': str(error)
            }
        except Exception as error:
            return {
                'success': False,
                'error': f'Error enviando email: {error}',
                'details': str(error)
            }

# Instancia global del servicio
gmail_service = GmailService()

def send_gmail(to: str, subject: str, body: str, body_type: str = 'html', attachment_path: Optional[str] = None):
    """Función helper para enviar emails"""
    return gmail_service.send_email(to, subject, body, body_type, attachment_path)