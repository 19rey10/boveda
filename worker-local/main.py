"""
Corre en tu laptop. Cada N segundos revisa si el relay esta online y si
hay archivos pendientes; si los hay, los baja, les saca la fecha real
(EXIF/metadata), los guarda en la SSD organizados, sube una miniatura,
y confirma al relay. Tambien resuelve pedidos de descarga del original.

Uso:
    python main.py

Para que esto siga corriendo aunque cierres la terminal, en Linux usar
systemd o "nohup python main.py &"; en Windows, el Programador de Tareas
o convertirlo en servicio con NSSM.
"""
import base64
import os
import tempfile
import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from Utils.cliente_relay import (
    obtener_pendientes, confirmar, marcar_fallo, relay_esta_online,
    subir_miniatura, obtener_descargas_pendientes, completar_descarga,
)
from Funciones.exif_utils import fecha_de_imagen, fecha_de_video, generar_miniatura
from Funciones.almacenamiento import guardar_archivo, espacio_disponible_gb

INTERVALO_SEGUNDOS = int(os.getenv("INTERVALO_POLLING", "30"))


def procesar_item(item: dict):
    contenido = base64.b64decode(item["contenido_base64"])
    nombre_original = item["nombre_original"]
    es_video = nombre_original.lower().endswith((".mp4", ".mov", ".avi", ".mkv"))

    fecha = None
    if es_video:
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(nombre_original)[1]) as tmp:
            tmp.write(contenido)
            tmp.flush()
            fecha = fecha_de_video(tmp.name)
    else:
        fecha = fecha_de_imagen(contenido)

    fecha = fecha or datetime.utcnow()  # fallback: fecha de subida

    username = item.get("username", "usuario_desconocido")
    es_publica = item.get("es_publica", False)

    ruta_final = guardar_archivo(contenido, username, es_publica, fecha, nombre_original)

    # generar y subir miniatura (por ahora solo para imagenes)
    if not es_video:
        miniatura = generar_miniatura(contenido)
        if miniatura:
            subir_miniatura(item["archivo_id"], miniatura)

    return ruta_final


def procesar_descargas_pendientes():
    """Revisa si algun usuario pidio descargar un archivo original, lo
    busca en la SSD, y se lo manda de vuelta al relay para que se lo
    entregue."""
    try:
        pendientes = obtener_descargas_pendientes()
    except Exception as e:
        print(f"  No se pudo consultar descargas pendientes: {e}")
        return

    for p in pendientes:
        ruta = p.get("ruta_ssd")
        if not ruta or not os.path.exists(ruta):
            continue

        try:
            with open(ruta, "rb") as f:
                contenido = f.read()
            nombre = os.path.basename(ruta)
            completar_descarga(p["solicitud_id"], contenido, nombre)
            print(f"  Descarga resuelta -> {nombre}")
        except Exception as e:
            print(f"  Error resolviendo descarga de {ruta}: {e}")


def ciclo():
    if not relay_esta_online():
        print(f"[{datetime.now()}] Relay no disponible, reintento en {INTERVALO_SEGUNDOS}s")
        return

    espacio = espacio_disponible_gb()
    if espacio < 5:
        print(f"[{datetime.now()}] ADVERTENCIA: solo quedan {espacio}GB libres en la SSD")

    pendientes = obtener_pendientes()
    if pendientes:
        print(f"[{datetime.now()}] Procesando {len(pendientes)} archivos pendientes...")
        for item in pendientes:
            try:
                ruta_final = procesar_item(item)
                confirmar(item["cola_id"], ruta_final)
                print(f"  OK -> {ruta_final}")
            except Exception as e:
                print(f"  ERROR con {item['nombre_original']}: {e}")
                marcar_fallo(item["cola_id"])

    procesar_descargas_pendientes()


if __name__ == "__main__":
    print("Worker de Boveda iniciado. Ctrl+C para detener.")
    while True:
        try:
            ciclo()
        except Exception as e:
            print(f"Error en el ciclo: {e}")
        time.sleep(INTERVALO_SEGUNDOS)
