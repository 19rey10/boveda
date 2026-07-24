"""
Estas rutas las llama SOLO el worker-local (tu laptop), no la app de
usuarios. Se protegen con un secreto propio (WORKER_SECRET), no con el
login de usuarios normales.
"""
import base64
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from Datos.db import obtener_db
from Funciones.cola import obtener_pendientes, confirmar_procesado, marcar_fallo

router = APIRouter(prefix="/sync", tags=["sync"])

WORKER_SECRET = os.getenv("WORKER_SECRET")


def _verificar_worker(x_worker_secret: str = Header(...)):
    if not WORKER_SECRET or x_worker_secret != WORKER_SECRET:
        raise HTTPException(401, "Secreto de worker invalido")


@router.get("/pendientes", dependencies=[Depends(_verificar_worker)])
def pendientes(db: Session = Depends(obtener_db)):
    items = obtener_pendientes(db)
    return [
        {
            "cola_id": i.id,
            "archivo_id": i.archivo_id,
            "nombre_original": i.nombre_original,
            "contenido_base64": base64.b64encode(i.archivo_blob).decode(),
        }
        for i in items
    ]


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
