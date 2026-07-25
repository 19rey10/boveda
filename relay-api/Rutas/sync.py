"""
Estas rutas las llama SOLO el worker-local (tu laptop), no la app de
usuarios. Se protegen con un secreto propio (WORKER_SECRET), no con el
login de usuarios normales.
"""
import base64
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from Datos.db import obtener_db
from Datos.modelos import Archivo, Usuario, SolicitudDescarga, SolicitudEliminacion, EstadoWorker
from Funciones.cola import obtener_pendientes, confirmar_procesado, marcar_fallo

router = APIRouter(prefix="/sync", tags=["sync"])

WORKER_SECRET = os.getenv("WORKER_SECRET")


def _verificar_worker(x_worker_secret: str = Header(...)):
    if not WORKER_SECRET or x_worker_secret != WORKER_SECRET:
        raise HTTPException(401, "Secreto de worker invalido")


class MiniaturaIn(BaseModel):
    contenido_base64: str


class DescargaCompletarIn(BaseModel):
    contenido_base64: str
    nombre_archivo: str


class LatidoIn(BaseModel):
    espacio_libre_gb: float


@router.post("/latido", dependencies=[Depends(_verificar_worker)])
def latido(datos: LatidoIn, db: Session = Depends(obtener_db)):
    """La laptop avisa que sigue viva y cuanto espacio libre le queda,
    para que el panel admin lo pueda mostrar."""
    estado = db.query(EstadoWorker).first()
    if not estado:
        estado = EstadoWorker()
        db.add(estado)

    estado.ultimo_contacto = datetime.utcnow()
    estado.espacio_libre_gb = int(datos.espacio_libre_gb)
    db.commit()
    return {"mensaje": "ok"}


@router.get("/pendientes", dependencies=[Depends(_verificar_worker)])
def pendientes(db: Session = Depends(obtener_db)):
    items = obtener_pendientes(db)
    resultado = []
    for i in items:
        archivo = db.query(Archivo).filter(Archivo.id == i.archivo_id).first()
        usuario = (
            db.query(Usuario).filter(Usuario.id == archivo.uploader_id).first()
            if archivo else None
        )
        resultado.append({
            "cola_id": i.id,
            "archivo_id": i.archivo_id,
            "nombre_original": i.nombre_original,
            "contenido_base64": base64.b64encode(i.archivo_blob).decode(),
            "username": usuario.username if usuario else "usuario_desconocido",
            "es_publica": archivo.es_publica if archivo else False,
        })
    return resultado


@router.post("/ack/{cola_id}", dependencies=[Depends(_verificar_worker)])
def ack(cola_id: int, ruta_ssd: str, db: Session = Depends(obtener_db)):
    ok = confirmar_procesado(db, cola_id, ruta_ssd)
    if not ok:
        raise HTTPException(404, "Item de cola no encontrado")
    return {"mensaje": "Confirmado"}


@router.post("/fallo/{cola_id}", dependencies=[Depends(_verificar_worker)])
def fallo(cola_id: int, db: Session = Depends(obtener_db)):
    marcar_fallo(db, cola_id)
    return {"mensaje": "Reintento registrado"}


@router.post("/miniatura/{archivo_id}", dependencies=[Depends(_verificar_worker)])
def subir_miniatura(archivo_id: int, datos: MiniaturaIn, db: Session = Depends(obtener_db)):
    archivo = db.query(Archivo).filter(Archivo.id == archivo_id).first()
    if not archivo:
        raise HTTPException(404, "Archivo no encontrado")

    archivo.thumbnail_blob = base64.b64decode(datos.contenido_base64)
    db.commit()
    return {"mensaje": "Miniatura guardada"}


@router.get("/descargas-pendientes", dependencies=[Depends(_verificar_worker)])
def descargas_pendientes(db: Session = Depends(obtener_db)):
    """La laptop pregunta que archivos originales tiene que ir a buscar
    a la SSD y mandar de vuelta para que un usuario los pueda descargar."""
    pendientes = db.query(SolicitudDescarga).filter(SolicitudDescarga.listo.is_(False)).all()
    resultado = []
    for p in pendientes:
        archivo = db.query(Archivo).filter(Archivo.id == p.archivo_id).first()
        if not archivo or not archivo.ruta_ssd:
            continue
        resultado.append({
            "solicitud_id": p.id,
            "archivo_id": p.archivo_id,
            "ruta_ssd": archivo.ruta_ssd,
        })
    return resultado


@router.post("/descargas-pendientes/{solicitud_id}/completar", dependencies=[Depends(_verificar_worker)])
def completar_descarga(solicitud_id: int, datos: DescargaCompletarIn, db: Session = Depends(obtener_db)):
    solicitud = db.query(SolicitudDescarga).filter(SolicitudDescarga.id == solicitud_id).first()
    if not solicitud:
        raise HTTPException(404, "Solicitud no encontrada")

    solicitud.contenido_blob = base64.b64decode(datos.contenido_base64)
    solicitud.nombre_archivo = datos.nombre_archivo
    solicitud.listo = True
    db.commit()
    return {"mensaje": "Descarga lista"}


@router.get("/eliminaciones-pendientes", dependencies=[Depends(_verificar_worker)])
def eliminaciones_pendientes(db: Session = Depends(obtener_db)):
    """La laptop pregunta que archivos fisicos tiene que borrar de la SSD."""
    pendientes = db.query(SolicitudEliminacion).filter(SolicitudEliminacion.listo.is_(False)).all()
    return [{"id": p.id, "ruta_ssd": p.ruta_ssd} for p in pendientes]


@router.post("/eliminaciones-pendientes/{solicitud_id}/completar", dependencies=[Depends(_verificar_worker)])
def completar_eliminacion(solicitud_id: int, db: Session = Depends(obtener_db)):
    solicitud = db.query(SolicitudEliminacion).filter(SolicitudEliminacion.id == solicitud_id).first()
    if not solicitud:
        raise HTTPException(404, "Solicitud no encontrada")
    db.delete(solicitud)
    db.commit()
    return {"mensaje": "Eliminacion confirmada"}
