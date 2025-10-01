import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional
import mimetypes
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno (solo en desarrollo local)
# En Railway/producción las variables se configuran directamente en la plataforma
try:
    load_dotenv()
except:
    pass  # En Railway no hay archivo .env, usar variables del sistema

class SMTPEmailService:
    """Servicio para envío de emails vía SMTP (simple, ideal para n8n)"""

    def __init__(self):
        # Configuración SMTP desde variables de entorno
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.sender_email = os.getenv('SMTP_SENDER_EMAIL', self.smtp_username)

    def create_message(self, to: str, subject: str, body: str, body_type: str = 'html', attachment_path: Optional[str] = None):
        """Crea un mensaje de email con posible adjunto"""
        message = MIMEMultipart()
        message['From'] = self.sender_email
        message['To'] = to
        message['Subject'] = subject

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

        return message

    def send_email(self, to: str, subject: str, body: str, body_type: str = 'html', attachment_path: Optional[str] = None):
        """Envía un email usando SMTP"""
        try:
            # Validar configuración
            if not self.smtp_username or not self.smtp_password:
                return {
                    'success': False,
                    'error': 'Configuración SMTP incompleta. Verifica SMTP_USERNAME y SMTP_PASSWORD en .env'
                }

            # Crear mensaje
            message = self.create_message(to, subject, body, body_type, attachment_path)

            # Configurar conexión SMTP
            context = ssl.create_default_context()

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.smtp_username, self.smtp_password)

                # Enviar mensaje
                text = message.as_string()
                server.sendmail(self.sender_email, to, text)

            return {
                'success': True,
                'message': f'Email enviado exitosamente vía SMTP a {to}',
                'smtp_server': self.smtp_server
            }

        except smtplib.SMTPAuthenticationError:
            return {
                'success': False,
                'error': 'Error de autenticación SMTP. Verifica las credenciales en .env'
            }
        except smtplib.SMTPRecipientsRefused:
            return {
                'success': False,
                'error': f'Email de destino rechazado: {to}'
            }
        except smtplib.SMTPException as error:
            return {
                'success': False,
                'error': f'Error SMTP: {error}'
            }
        except Exception as error:
            return {
                'success': False,
                'error': f'Error enviando email: {error}'
            }

# Instancia global del servicio SMTP
smtp_service = SMTPEmailService()

def send_email_smtp(to: str, subject: str, body: str, body_type: str = 'html', attachment_path: Optional[str] = None):
    """Función helper para enviar emails vía SMTP"""
    return smtp_service.send_email(to, subject, body, body_type, attachment_path)