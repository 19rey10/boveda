"""
Envio de correos (recuperacion de contraseña). Usa SMTP generico -
funciona con Gmail (con contraseña de aplicacion), Resend, SendGrid, etc.
Configurar en .env: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
"""
import os
import smtplib
from email.mime.text import MIMEText

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
APP_URL = os.getenv("APP_URL", "https://tuapp.ejemplo.com")


def enviar_email_recuperacion(email_destino: str, token: str) -> bool:
    if not SMTP_HOST:
        print(f"[correo] SMTP no configurado. Token para {email_destino}: {token}")
        return False

    link = f"{APP_URL}/reset-password?token={token}"
    cuerpo = (
        f"Pediste restablecer tu contraseña de Boveda.\n\n"
        f"Entra a este link (valido 1 hora):\n{link}\n\n"
        f"Si no fuiste vos, ignora este correo."
    )
    msg = MIMEText(cuerpo)
    msg["Subject"] = "Recuperar contraseña - Boveda"
    msg["From"] = SMTP_FROM
    msg["To"] = email_destino

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[correo] Error enviando email: {e}")
        return False
