"""
Cliente para que la laptop hable con el relay via su IP de Tailscale
(o el hostname .ts.net que te da Tailscale automaticamente).
"""
import base64
import os
import requests

RELAY_URL = os.getenv("RELAY_URL", "http://relay.tu-tailnet.ts.net:8000")
WORKER_SECRET = os.getenv("WORKER_SECRET")

HEADERS = {"X-Worker-Secret": WORKER_SECRET}


def obtener_pendientes(limite: int = 10) -> list[dict]:
    r = requests.get(f"{RELAY_URL}/sync/pendientes", headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


def confirmar(cola_id: int, ruta_ssd: str):
    r = requests.post(
        f"{RELAY_URL}/sync/ack/{cola_id}",
        headers=HEADERS,
        params={"ruta_ssd": ruta_ssd},
        timeout=10,
    )
    r.raise_for_status()


def marcar_fallo(cola_id: int):
    requests.post(f"{RELAY_URL}/sync/fallo/{cola_id}", headers=HEADERS, timeout=10)


def subir_miniatura(archivo_id: int, contenido_miniatura: bytes):
    b64 = base64.b64encode(contenido_miniatura).decode()
    requests.post(
        f"{RELAY_URL}/sync/miniatura/{archivo_id}",
        headers=HEADERS,
        json={"contenido_base64": b64},
        timeout=15,
    )


def obtener_descargas_pendientes() -> list[dict]:
    r = requests.get(f"{RELAY_URL}/sync/descargas-pendientes", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def completar_descarga(solicitud_id: int, contenido: bytes, nombre_archivo: str):
    b64 = base64.b64encode(contenido).decode()
    requests.post(
        f"{RELAY_URL}/sync/descargas-pendientes/{solicitud_id}/completar",
        headers=HEADERS,
        json={"contenido_base64": b64, "nombre_archivo": nombre_archivo},
        timeout=30,
    )


def relay_esta_online() -> bool:
    try:
        r = requests.get(f"{RELAY_URL}/health", timeout=60)
        return r.status_code == 200
    except requests.RequestException:
        return False
