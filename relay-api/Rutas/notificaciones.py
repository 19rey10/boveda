from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from Datos.db import obtener_db
from Datos.modelos import Usuario, TokenPush
from Utils.seguridad import obtener_usuario_actual

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


class TokenIn(BaseModel):
    token: str


@router.post("/registrar-token")
def registrar_token(
    datos: TokenIn,
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    """Guarda (o actualiza el dueño de) el token de notificaciones push
    de este dispositivo, para poder avisarle cuando haya fotos nuevas."""
    existente = db.query(TokenPush).filter(TokenPush.token == datos.token).first()
    if existente:
        existente.usuario_id = usuario.id
    else:
        db.add(TokenPush(usuario_id=usuario.id, token=datos.token))
    db.commit()
    return {"mensaje": "Token registrado"}


@router.delete("/registrar-token")
def borrar_token(
    datos: TokenIn,
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    """Para cuando el usuario cierra sesión - dejar de mandarle push a
    ese dispositivo."""
    db.query(TokenPush).filter(TokenPush.token == datos.token).delete()
    db.commit()
    return {"mensaje": "Token eliminado"}
