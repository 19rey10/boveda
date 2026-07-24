"""
Extrae la fecha REAL en que se tomo la foto/video (no la de subida),
para poder organizar todo por dia real.
"""
import subprocess
import json
from datetime import datetime
from io import BytesIO

from PIL import Image
from PIL.ExifTags import TAGS


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
