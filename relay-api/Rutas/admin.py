from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
import secrets

from Datos.db import obtener_db
from Datos.modelos import Usuario, Archivo, ColaSync, CodigoInvitacion, EstadoWorker
from Utils.seguridad import requiere_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/resumen")
def resumen(db: Session = Depends(obtener_db), _: Usuario = Depends(requiere_admin)):
    total_usuarios = db.query(func.count(Usuario.id)).scalar()
    total_archivos = db.query(func.count(Archivo.id)).scalar()
    pendientes_sync = db.query(func.count(ColaSync.id)).scalar()
    total_bytes = db.query(func.sum(Archivo.tamano_bytes)).scalar() or 0

    estado_worker = db.query(EstadoWorker).first()
    minutos_desde_ultimo_contacto = None
    if estado_worker and estado_worker.ultimo_contacto:
        delta = datetime.utcnow() - estado_worker.ultimo_contacto
        minutos_desde_ultimo_contacto = round(delta.total_seconds() / 60, 1)

    return {
        "total_usuarios": total_usuarios,
        "total_archivos": total_archivos,
        "pendientes_sync": pendientes_sync,
        "total_gb_estimado": round(total_bytes / (1024 ** 3), 2),
        "worker_minutos_desde_ultimo_contacto": minutos_desde_ultimo_contacto,
        "worker_ssd_espacio_libre_gb": estado_worker.espacio_libre_gb if estado_worker else None,
    }


@router.get("/usuarios")
def listar_usuarios(db: Session = Depends(obtener_db), _: Usuario = Depends(requiere_admin)):
    usuarios = db.query(Usuario).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "nombre_display": u.nombre_display,
            "es_admin": u.es_admin,
            "activo": u.activo,
            "creado_en": u.creado_en.isoformat(),
        }
        for u in usuarios
    ]


@router.post("/usuarios/{usuario_id}/desactivar")
def desactivar_usuario(
    usuario_id: int, db: Session = Depends(obtener_db), admin: Usuario = Depends(requiere_admin)
):
    if usuario_id == admin.id:
        raise HTTPException(400, "No podes desactivarte a vos mismo")

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(404, "No encontrado")

    usuario.activo = False
    db.commit()
    return {"mensaje": f"Usuario {usuario.username} desactivado"}


@router.get("/cola")
def ver_cola(db: Session = Depends(obtener_db), _: Usuario = Depends(requiere_admin)):
    """Ver que hay esperando a que la laptop se conecte."""
    items = db.query(ColaSync).all()
    return [
        {
            "id": i.id,
            "nombre_original": i.nombre_original,
            "intentos": i.intentos,
            "creado_en": i.creado_en.isoformat(),
        }
        for i in items
    ]


@router.post("/codigos-invitacion")
def generar_codigo_invitacion(
    db: Session = Depends(obtener_db), admin: Usuario = Depends(requiere_admin)
):
    """Genera un codigo de invitacion nuevo, de un solo uso, legible
    para compartir a mano (letras mayusculas y numeros, sin caracteres
    confundibles como 0/O o 1/I)."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    codigo_texto = "".join(secrets.choice(alfabeto) for _ in range(8))

    nuevo = CodigoInvitacion(codigo=codigo_texto, creado_por_id=admin.id)
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)

    return {"codigo": nuevo.codigo, "id": nuevo.id}


@router.get("/codigos-invitacion")
def listar_codigos_invitacion(
    db: Session = Depends(obtener_db), _: Usuario = Depends(requiere_admin)
):
    """Ver todos los codigos generados y su estado (usado o no, por quien)."""
    codigos = db.query(CodigoInvitacion).order_by(CodigoInvitacion.creado_en.desc()).all()
    resultado = []
    for c in codigos:
        usado_por = None
        if c.usado_por_id:
            u = db.query(Usuario).filter(Usuario.id == c.usado_por_id).first()
            usado_por = u.username if u else None

        resultado.append({
            "id": c.id,
            "codigo": c.codigo,
            "usado": c.usado,
            "usado_por": usado_por,
            "creado_en": c.creado_en.isoformat(),
            "usado_en": c.usado_en.isoformat() if c.usado_en else None,
        })
    return resultado
