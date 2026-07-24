from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from datetime import datetime

from Datos.db import obtener_db
from Datos.modelos import Usuario, TokenRecuperacion, CodigoInvitacion
from Funciones.auth import (
    hashear_password, verificar_password, crear_token, generar_token_recuperacion
)
from Funciones.correo import enviar_email_recuperacion

router = APIRouter(prefix="/auth", tags=["auth"])


class RegistroIn(BaseModel):
    username: str
    email: EmailStr
    password: str
    nombre_display: str
    codigo_invitacion: str


class LoginIn(BaseModel):
    username: str
    password: str


class OlvideIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    password_nuevo: str


@router.post("/registro")
def registro(datos: RegistroIn, db: Session = Depends(obtener_db)):
    codigo = (
        db.query(CodigoInvitacion)
        .filter(CodigoInvitacion.codigo == datos.codigo_invitacion, CodigoInvitacion.usado.is_(False))
        .first()
    )
    if not codigo:
        raise HTTPException(403, "Código de invitación inválido o ya usado")

    existe = db.query(Usuario).filter(
        (Usuario.username == datos.username) | (Usuario.email == datos.email)
    ).first()
    if existe:
        raise HTTPException(400, "Ese usuario o email ya esta registrado")

    usuario = Usuario(
        username=datos.username,
        email=datos.email,
        password_hash=hashear_password(datos.password),
        nombre_display=datos.nombre_display,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    codigo.usado = True
    codigo.usado_por_id = usuario.id
    codigo.usado_en = datetime.utcnow()
    db.commit()

    return {"mensaje": "Cuenta creada", "usuario_id": usuario.id}


@router.post("/login")
def login(datos: LoginIn, db: Session = Depends(obtener_db)):
    usuario = db.query(Usuario).filter(Usuario.username == datos.username).first()
    if not usuario or not verificar_password(datos.password, usuario.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos")
    if not usuario.activo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cuenta deshabilitada")

    token = crear_token(usuario.id, usuario.username, usuario.es_admin)
    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": {
            "id": usuario.id,
            "username": usuario.username,
            "nombre_display": usuario.nombre_display,
            "es_admin": usuario.es_admin,
        },
    }


@router.post("/olvide-password")
def olvide_password(datos: OlvideIn, db: Session = Depends(obtener_db)):
    usuario = db.query(Usuario).filter(Usuario.email == datos.email).first()
    # Responder siempre lo mismo exista o no el email, para no filtrar
    # que emails estan registrados.
    if usuario:
        token, expira = generar_token_recuperacion()
        db.add(TokenRecuperacion(usuario_id=usuario.id, token=token, expira_en=expira))
        db.commit()
        enviar_email_recuperacion(usuario.email, token)

    return {"mensaje": "Si el email existe, vas a recibir un link de recuperacion"}


@router.post("/reset-password")
def reset_password(datos: ResetIn, db: Session = Depends(obtener_db)):
    from datetime import datetime

    registro = db.query(TokenRecuperacion).filter(
        TokenRecuperacion.token == datos.token,
        TokenRecuperacion.usado.is_(False),
    ).first()

    if not registro or registro.expira_en < datetime.utcnow():
        raise HTTPException(400, "Token invalido o vencido")

    usuario = db.query(Usuario).filter(Usuario.id == registro.usuario_id).first()
    usuario.password_hash = hashear_password(datos.password_nuevo)
    registro.usado = True
    db.commit()

    return {"mensaje": "Contraseña actualizada"}
