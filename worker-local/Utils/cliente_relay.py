"""
Cliente para que la laptop hable con el relay via su IP de Tailscale
(o el hostname .ts.net que te da Tailscale automaticamente).
"""
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


def relay_esta_online() -> bool:
    try:
        r = requests.get(f"{RELAY_URL}/health", timeout=60)
        return r.status_code == 200
    except requests.RequestException:
        return False
