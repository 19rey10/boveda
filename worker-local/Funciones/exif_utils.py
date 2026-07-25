"""
Extrae la fecha REAL en que se tomo la foto/video (no la de subida),
para poder organizar todo por dia real. Tambien genera miniaturas.
"""
import subprocess
import json
from datetime import datetime
from io import BytesIO

from PIL import Image
from PIL.ExifTags import TAGS


def generar_miniatura(contenido: bytes) -> bytes | None:
    """Genera una miniatura JPEG chica (max 400x400) para mostrar en la
    galeria sin tener que mandar la imagen completa. Devuelve None si
    no se pudo (ej: es un video, o el archivo esta corrupto)."""
    try:
        img = Image.open(BytesIO(contenido))
        img = img.convert("RGB")
        img.thumbnail((400, 400))
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=80)
        return buffer.getvalue()
    except Exception:
        return None


def generar_miniatura_video(ruta_temporal: str) -> bytes | None:
    """Extrae un frame del segundo 1 del video con ffmpeg y lo convierte
    en miniatura JPEG chica. Requiere ffmpeg instalado."""
    try:
        resultado = subprocess.run(
            [
                "ffmpeg", "-y", "-ss", "1", "-i", ruta_temporal,
                "-vframes", "1", "-vf", "scale=400:-1",
                "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
            ],
            capture_output=True, timeout=20,
        )
        if resultado.returncode == 0 and resultado.stdout:
            return resultado.stdout
    except Exception:
        pass
    return None


def fecha_de_imagen(contenido: bytes) -> datetime | None:
    try:
        img = Image.open(BytesIO(contenido))
        exif = img.getexif()
        for tag_id, valor in exif.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "DateTimeOriginal" or tag == "DateTime":
                return datetime.strptime(valor, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def fecha_de_video(ruta_temporal: str) -> datetime | None:
    """
    Requiere ffprobe instalado (viene con ffmpeg).
    sudo apt install ffmpeg
    """
    try:
        resultado = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", ruta_temporal,
            ],
            capture_output=True, text=True, timeout=15,
        )
        datos = json.loads(resultado.stdout)
        fecha_str = datos.get("format", {}).get("tags", {}).get("creation_time")
        if fecha_str:
            return datetime.strptime(fecha_str[:19], "%Y-%m-%dT%H:%M:%S")
    except Exception:
        pass
    return None
