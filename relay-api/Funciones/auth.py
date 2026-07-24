"""
Autenticacion: hash de contraseñas, JWT, tokens de recuperacion por email.
NUNCA se guarda ni se loguea una contraseña en texto plano - eso incluye
no ponerla en archivos .py, .env commiteados, ni logs.
"""
import os
import secrets
from datetime import datetime, timedelta

import bcrypt
import jwt

SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    raise RuntimeError(
        "Falta JWT_SECRET en el .env. Generalo con: "
        "python -c \"import secrets; print(secrets.token_hex(32))\""
    )

ALGORITMO = "HS256"
EXPIRACION_HORAS = 24 * 7  # el login dura 1 semana


def hashear_password(password_plano: str) -> str:
    return bcrypt.hashpw(password_plano.encode(), bcrypt.gensalt()).decode()


def verificar_password(password_plano: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password_plano.encode(), password_hash.encode())


def crear_token(usuario_id: int, username: str, es_admin: bool) -> str:
    payload = {
        "sub": str(usuario_id),
        "username": username,
        "es_admin": es_admin,
        "exp": datetime.utcnow() + timedelta(hours=EXPIRACION_HORAS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITMO)


def verificar_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITMO])
    except jwt.PyJWTError:
        return None


def generar_token_recuperacion() -> tuple[str, datetime]:
    """Token random para recuperacion de password, valido 1 hora."""
    token = secrets.token_urlsafe(32)
    expira = datetime.utcnow() + timedelta(hours=1)
    return token, expira
