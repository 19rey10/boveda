"""
Manejo de la cola de sincronizacion entre el relay y la laptop.
"""
from sqlalchemy.orm import Session
from Datos.modelos import ColaSync, Archivo


def encolar(db: Session, archivo: Archivo, blob: bytes, nombre_original: str) -> ColaSync:
    item = ColaSync(archivo_id=archivo.id, archivo_blob=blob, nombre_original=nombre_original)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def obtener_pendientes(db: Session, limite: int = 20) -> list[ColaSync]:
    return (
        db.query(ColaSync)
        .order_by(ColaSync.creado_en.asc())
        .limit(limite)
        .all()
    )


def confirmar_procesado(db: Session, cola_id: int, ruta_ssd: str) -> bool:
    item = db.query(ColaSync).filter(ColaSync.id == cola_id).first()
    if not item:
        return False

    archivo = db.query(Archivo).filter(Archivo.id == item.archivo_id).first()
    if archivo:
        archivo.ruta_ssd = ruta_ssd
        archivo.sincronizado = True

    db.delete(item)  # ya no hace falta guardar el binario en el relay
    db.commit()
    return True


def marcar_fallo(db: Session, cola_id: int):
    item = db.query(ColaSync).filter(ColaSync.id == cola_id).first()
    if item:
        item.intentos += 1
        db.commit()
