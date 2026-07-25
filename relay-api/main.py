from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from Datos.db import crear_tablas
from Rutas import auth, subir, galeria, sync, admin, notificaciones

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


@app.on_event("startup")
def startup():
    crear_tablas()


@app.get("/health")
def health():
    return {"estado": "ok"}
