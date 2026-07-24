"""
Guarda los archivos en la SSD con la estructura:
/ruta_ssd/usuarios/{username}/{publicas|privadas}/{YYYY}/{MM}/{DD}/archivo.ext
"""
import os
import shutil
from datetime import datetime
from pathlib import Path

RUTA_SSD = os.getenv("RUTA_SSD", "/mnt/ssd_boveda")
Path(RUTA_SSD).mkdir(parents=True, exist_ok=True)


def guardar_archivo(
    contenido: bytes,
    username: str,
    es_publica: bool,
    fecha: datetime,
    nombre_original: str,
) -> str:
    visibilidad = "publicas" if es_publica else "privadas"
    carpeta = Path(RUTA_SSD) / "usuarios" / username / visibilidad / \
        fecha.strftime("%Y") / fecha.strftime("%m") / fecha.strftime("%d")
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_final = carpeta / nombre_original
    # evitar sobreescribir si ya existe un archivo con el mismo nombre
    contador = 1
    while ruta_final.exists():
        nombre, ext = os.path.splitext(nombre_original)
        ruta_final = carpeta / f"{nombre}_{contador}{ext}"
        contador += 1
    ruta_final.write_bytes(contenido)
    return str(ruta_final)


def espacio_disponible_gb() -> float:
    total, usado, libre = shutil.disk_usage(RUTA_SSD)
    return round(libre / (1024 ** 3), 2)