import hashlib
from typing import List

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from Datos.db import obtener_db
from Datos.modelos import Usuario, Archivo, ColaSync, SolicitudDescarga, SolicitudEliminacion
from Utils.seguridad import obtener_usuario_actual
from Funciones.cola import encolar
from Funciones.notificaciones import programar_notificaciones_subida

router = APIRouter(prefix="/archivos", tags=["archivos"])


@router.post("/subir")
async def subir_archivos(
    archivos: List[UploadFile] = File(...),
    descripcion: str = Form(""),
    es_publica: bool = Form(False),
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    """
    Sube uno o varios archivos de una. Se guardan en la cola del relay
    inmediatamente (respuesta rapida al usuario) y quedan pendientes de
    que la laptop los baje y los guarde en la SSD organizada.
    """
    resultados = []
    subidas_publicas = 0

    for archivo in archivos:
        contenido = await archivo.read()
        hash_archivo = hashlib.sha256(contenido).hexdigest()

        ya_existe = db.query(Archivo).filter(Archivo.hash_sha256 == hash_archivo).first()
        if ya_existe:
            resultados.append({
                "nombre": archivo.filename,
                "estado": "duplicado",
                "mensaje": "Este archivo ya fue subido antes",
            })
            continue

        tipo = "video" if archivo.content_type and archivo.content_type.startswith("video") else "imagen"

        registro = Archivo(
            uploader_id=usuario.id,
            hash_sha256=hash_archivo,
            tipo=tipo,
            es_publica=es_publica,
            descripcion=descripcion,
            tamano_bytes=len(contenido),
        )
        db.add(registro)
        db.commit()
        db.refresh(registro)

        encolar(db, registro, contenido, archivo.filename)
        if es_publica:
            subidas_publicas += 1

        resultados.append({
            "nombre": archivo.filename,
            "estado": "en_cola",
            "archivo_id": registro.id,
            "mensaje": "Subido. Se guardara en la SSD cuando el servidor este en linea.",
        })

    if subidas_publicas > 0:
        programar_notificaciones_subida(db, usuario.id, usuario.nombre_display, descripcion, subidas_publicas)

    return {"resultados": resultados}


@router.delete("/{archivo_id}")
def eliminar_archivo(
    archivo_id: int,
    db: Session = Depends(obtener_db),
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    """Borra un archivo. Solo quien lo subio o un admin pueden hacerlo.
    El registro se borra al toque de la base; el archivo fisico en la
    SSD se elimina la proxima vez que la laptop se conecte."""
    archivo = db.query(Archivo).filter(Archivo.id == archivo_id).first()
    if not archivo:
        raise HTTPException(404, "No encontrado")

    puede_borrar = archivo.uploader_id == usuario.id or usuario.es_admin
    if not puede_borrar:
        raise HTTPException(403, "No tenes permiso para borrar este archivo")

    # limpiar cualquier cola pendiente relacionada, para no dejar basura
    db.query(ColaSync).filter(ColaSync.archivo_id == archivo_id).delete()
    db.query(SolicitudDescarga).filter(SolicitudDescarga.archivo_id == archivo_id).delete()

    # si ya se habia guardado en la SSD, avisarle a la laptop que lo borre fisicamente
    if archivo.ruta_ssd:
        db.add(SolicitudEliminacion(ruta_ssd=archivo.ruta_ssd, listo=False))

    db.delete(archivo)
    db.commit()

    return {"mensaje": "Archivo eliminado"}
