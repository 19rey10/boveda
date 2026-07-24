import hashlib
from typing import List

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session

from Datos.db import obtener_db
from Datos.modelos import Usuario, Archivo
from Utils.seguridad import obtener_usuario_actual
from Funciones.cola import encolar

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

        resultados.append({
            "nombre": archivo.filename,
            "estado": "en_cola",
            "archivo_id": registro.id,
            "mensaje": "Subido. Se guardara en la SSD cuando el servidor este en linea.",
        })

    return {"resultados": resultados}
