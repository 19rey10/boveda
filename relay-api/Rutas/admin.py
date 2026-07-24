from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from Datos.db import obtener_db
from Datos.modelos import Usuario, Archivo, ColaSync
from Utils.seguridad import requiere_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/resumen")
def resumen(db: Session = Depends(obtener_db), _: Usuario = Depends(requiere_admin)):
    total_usuarios = db.query(func.count(Usuario.id)).scalar()
    total_archivos = db.query(func.count(Archivo.id)).scalar()
    pendientes_sync = db.query(func.count(ColaSync.id)).scalar()
    total_bytes = db.query(func.sum(Archivo.tamano_bytes)).scalar() or 0

    return {
        "total_usuarios": total_usuarios,
        "total_archivos": total_archivos,
        "pendientes_sync": pendientes_sync,
        "total_gb_estimado": round(total_bytes / (1024 ** 3), 2),
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
