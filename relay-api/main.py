from dotenv import load_dotenv
load_dotenv()

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from Datos.db import crear_tablas, SessionLocal
from Rutas import auth, subir, galeria, sync, admin, notificaciones
from Funciones.notificaciones import procesar_notificaciones_pendientes

app = FastAPI(title="Boveda - Relay", version="0.1")

# En produccion, reemplazar "*" por el dominio real de tu app de Google AI Studio
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(subir.router)
app.include_router(galeria.router)
app.include_router(sync.router)
app.include_router(admin.router)
app.include_router(notificaciones.router)


async def _loop_notificaciones():
    """Revisa cada 60 segundos si hay notificaciones programadas que ya
    llegaron a su hora de envio."""
    while True:
        try:
            db = SessionLocal()
            procesar_notificaciones_pendientes(db)
            db.close()
        except Exception as e:
            print(f"[scheduler] Error procesando notificaciones: {e}")
        await asyncio.sleep(60)


@app.on_event("startup")
def startup():
    crear_tablas()
    asyncio.create_task(_loop_notificaciones())


@app.get("/health")
def health():
    return {"estado": "ok"}
