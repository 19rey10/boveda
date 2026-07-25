import hashlib
import os
import shutil
from typing import List

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from Datos.db import obtener_db, SessionLocal
from Datos.modelos import Usuario, Archivo, ColaSync, SolicitudDescarga, SolicitudEliminacion
from Utils.seguridad import obtener_usuario_actual
from Funciones.cola import encolar
from Funciones.notificaciones import programar_notificaciones_subida

router = APIRouter(prefix="/archivos", tags=["archivos"])

TAMANO_MAXIMO_MB = int(os.getenv("TAMANO_MAXIMO_MB", "150"))
CARPETA_CHUNKS = "/tmp/boveda_subidas_chunk"


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

        tamano_mb = len(contenido) / (1024 * 1024)
        if tamano_mb > TAMANO_MAXIMO_MB:
            resultados.append({
                "nombre": archivo.filename,
                "estado": "muy_grande",
                "mensaje": f"Supera el máximo de {TAMANO_MAXIMO_MB}MB por archivo "
                           f"(este pesa {tamano_mb:.0f}MB). Probá comprimirlo o "
                           f"acortar el video.",
            })
            continue

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


def _finalizar_subida_en_fondo(
    ruta_ensamblada: str, carpeta_sesion: str, uploader_id: int,
    uploader_nombre: str, nombre_original: str, descripcion: str, es_publica: bool,
):
    """
    Corre DESPUES de responderle al celular (para no hacerlo esperar el
    guardado en la base de datos, que puede tardar con archivos
    grandes). Abre su propia sesion de DB porque la del request original
    ya se cerro para cuando esto corre.
    """
    db = SessionLocal()
    try:
        hasher = hashlib.sha256()
        with open(ruta_ensamblada, "rb") as f:
            while True:
                bloque = f.read(1024 * 1024)
                if not bloque:
                    break
                hasher.update(bloque)
        hash_archivo = hasher.hexdigest()

        ya_existe = db.query(Archivo).filter(Archivo.hash_sha256 == hash_archivo).first()
        if ya_existe:
            return

        with open(ruta_ensamblada, "rb") as f:
            contenido = f.read()

        tipo = "video" if nombre_original.lower().endswith((".mp4", ".mov", ".avi", ".mkv")) else "imagen"

        registro = Archivo(
            uploader_id=uploader_id,
            hash_sha256=hash_archivo,
            tipo=tipo,
            es_publica=es_publica,
            descripcion=descripcion,
            tamano_bytes=len(contenido),
        )
        db.add(registro)
        db.commit()
        db.refresh(registro)

        encolar(db, registro, contenido, nombre_original)

        if es_publica:
            programar_notificaciones_subida(db, uploader_id, uploader_nombre, descripcion, 1)
    finally:
        db.close()
        shutil.rmtree(carpeta_sesion, ignore_errors=True)


@router.post("/subir-chunk")
async def subir_chunk(
    background_tasks: BackgroundTasks,
    chunk: UploadFile = File(...),
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    nombre_original: str = Form(...),
    descripcion: str = Form(""),
    es_publica: bool = Form(False),
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    """
    Recibe un video/foto pesado de a pedacitos, para que ningun pedido
    individual tarde tanto como para que Render lo corte por timeout.
    El cliente manda cada chunk en orden; cuando llega el ultimo, se
    ensambla el archivo completo y se guarda en cola en segundo plano.
    """
    carpeta_sesion = os.path.join(CARPETA_CHUNKS, f"{usuario.id}_{upload_id}")
    os.makedirs(carpeta_sesion, exist_ok=True)

    ruta_parte = os.path.join(carpeta_sesion, f"{chunk_index:06d}.part")
    contenido_parte = await chunk.read()

    tamano_hasta_ahora_mb = sum(
        os.path.getsize(os.path.join(carpeta_sesion, f))
        for f in os.listdir(carpeta_sesion)
    ) / (1024 * 1024)
    if tamano_hasta_ahora_mb + len(contenido_parte) / (1024 * 1024) > TAMANO_MAXIMO_MB:
        shutil.rmtree(carpeta_sesion, ignore_errors=True)
        raise HTTPException(
            413,
            f"Supera el máximo de {TAMANO_MAXIMO_MB}MB por archivo. "
            f"Probá comprimirlo o acortar el video.",
        )

    with open(ruta_parte, "wb") as f:
        f.write(contenido_parte)

    partes_recibidas = len(os.listdir(carpeta_sesion))
    if partes_recibidas < total_chunks:
        return {"estado": "recibiendo", "partes_recibidas": partes_recibidas, "total_chunks": total_chunks}

    # llegaron todas las partes: ensamblar el archivo completo
    ruta_ensamblada = os.path.join(carpeta_sesion, "_completo")
    with open(ruta_ensamblada, "wb") as destino:
        for i in range(total_chunks):
            ruta_parte_i = os.path.join(carpeta_sesion, f"{i:06d}.part")
            with open(ruta_parte_i, "rb") as origen:
                shutil.copyfileobj(origen, destino)

    background_tasks.add_task(
        _finalizar_subida_en_fondo,
        ruta_ensamblada, carpeta_sesion, usuario.id, usuario.nombre_display,
        nombre_original, descripcion, es_publica,
    )

    return {"estado": "completo", "mensaje": "Archivo recibido, procesando..."}
