from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from io import BytesIO

from Datos.db import obtener_db
from Datos.modelos import Usuario, Archivo
from Utils.seguridad import obtener_usuario_actual

router = APIRouter(prefix="/galeria", tags=["galeria"])


def _visible_para(usuario: Usuario):
    """
    Regla de privacidad: una publica la ve cualquiera. Una privada SOLO
    la ve quien la subio, o un admin. Esto se aplica en todas las
    consultas de galeria/busqueda/descarga - nunca se filtra solo en
    el frontend.
    """
    if usuario.es_admin:
        return None  # el admin ve todo, no hace falta filtro
    return or_(
        Archivo.es_publica.is_(True),
        Archivo.uploader_id == usuario.id,
    )


@router.get("/por-dia")
def listar_por_dia(
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    filtro = _visible_para(usuario)
    query = db.query(Archivo).order_by(Archivo.fecha_tomada.desc())
    if filtro is not None:
        query = query.filter(filtro)

    archivos = query.all()

    dias = {}
    for a in archivos:
        fecha = a.fecha_tomada or a.fecha_subida
        clave = fecha.strftime("%Y-%m-%d")
        dias.setdefault(clave, []).append(_serializar(a, usuario))

    return dias


@router.get("/buscar")
def buscar(
    q: str,
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    filtro = _visible_para(usuario)
    query = db.query(Archivo).filter(Archivo.descripcion.ilike(f"%{q}%"))
    if filtro is not None:
        query = query.filter(filtro)

    return [_serializar(a, usuario) for a in query.all()]


@router.get("/{archivo_id}/descargar")
def descargar(
    archivo_id: int,
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    archivo = db.query(Archivo).filter(Archivo.id == archivo_id).first()
    if not archivo:
        raise HTTPException(404, "No encontrado")

    puede_ver = archivo.es_publica or archivo.uploader_id == usuario.id or usuario.es_admin
    if not puede_ver:
        raise HTTPException(403, "No tenes permiso para ver este archivo")

    if not archivo.sincronizado or not archivo.ruta_ssd:
        raise HTTPException(
            409,
            "El archivo todavia esta en cola, esperando a que el servidor "
            "de la laptop se conecte para guardarlo definitivamente.",
        )

    # En produccion esto redirige/streamea desde la laptop via el tunel
    # de Tailscale. Placeholder aca:
    raise HTTPException(501, "Descarga desde SSD: implementar proxy hacia worker-local")


def _serializar(a: Archivo, usuario: Usuario) -> dict:
    return {
        "id": a.id,
        "tipo": a.tipo,
        "descripcion": a.descripcion,
        "es_publica": a.es_publica,
        "es_mio": a.uploader_id == usuario.id,
        "fecha_tomada": a.fecha_tomada.isoformat() if a.fecha_tomada else None,
        "fecha_subida": a.fecha_subida.isoformat(),
        "sincronizado": a.sincronizado,
        "tamano_bytes": a.tamano_bytes,
    }
