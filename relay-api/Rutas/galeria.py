import mimetypes
from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

from Datos.db import obtener_db
from Datos.modelos import Usuario, Archivo, SolicitudDescarga
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


def _puede_ver(archivo: Archivo, usuario: Usuario) -> bool:
    return archivo.es_publica or archivo.uploader_id == usuario.id or usuario.es_admin


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


@router.get("/{archivo_id}/miniatura")
def miniatura(
    archivo_id: int,
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    archivo = db.query(Archivo).filter(Archivo.id == archivo_id).first()
    if not archivo:
        raise HTTPException(404, "No encontrado")
    if not _puede_ver(archivo, usuario):
        raise HTTPException(403, "No tenes permiso para ver este archivo")
    if not archivo.thumbnail_blob:
        raise HTTPException(404, "Miniatura no disponible todavia")

    return StreamingResponse(BytesIO(archivo.thumbnail_blob), media_type="image/jpeg")


@router.get("/{archivo_id}/descargar")
def descargar(
    archivo_id: int,
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    """
    El relay no tiene el archivo original (solo la laptop, en la SSD).
    Primera vez que se pide: se crea una solicitud y la laptop la ve en
    su proximo ciclo de polling, sube el archivo, y ahi si se entrega.
    El frontend deberia reintentar cada pocos segundos mientras reciba
    estado "preparando".
    """
    archivo = db.query(Archivo).filter(Archivo.id == archivo_id).first()
    if not archivo:
        raise HTTPException(404, "No encontrado")
    if not _puede_ver(archivo, usuario):
        raise HTTPException(403, "No tenes permiso para ver este archivo")

    if not archivo.sincronizado or not archivo.ruta_ssd:
        return JSONResponse(
            status_code=409,
            content={
                "estado": "en_cola",
                "mensaje": "El archivo todavia esta en cola, esperando a que "
                           "el servidor de la laptop se conecte para guardarlo.",
            },
        )

    # ¿ya hay una solicitud lista para entregar?
    lista = (
        db.query(SolicitudDescarga)
        .filter(SolicitudDescarga.archivo_id == archivo_id, SolicitudDescarga.listo.is_(True))
        .order_by(SolicitudDescarga.creado_en.desc())
        .first()
    )
    if lista:
        contenido = lista.contenido_blob
        nombre = lista.nombre_archivo or f"archivo_{archivo_id}"
        db.delete(lista)
        db.commit()

        media_type, _ = mimetypes.guess_type(nombre)
        media_type = media_type or "application/octet-stream"

        return StreamingResponse(
            BytesIO(contenido),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
        )

    # ¿ya hay una solicitud pendiente sin resolver? no duplicar
    pendiente = (
        db.query(SolicitudDescarga)
        .filter(SolicitudDescarga.archivo_id == archivo_id, SolicitudDescarga.listo.is_(False))
        .first()
    )
    if not pendiente:
        nueva = SolicitudDescarga(archivo_id=archivo_id, listo=False)
        db.add(nueva)
        db.commit()

    return JSONResponse(
        status_code=202,
        content={
            "estado": "preparando",
            "mensaje": "Pidiendole el archivo original al servidor de "
                       "almacenamiento. Volve a intentar en unos segundos.",
        },
    )


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
        "tiene_miniatura": a.thumbnail_blob is not None,
    }