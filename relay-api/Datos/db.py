"""
Conexion a la base de datos del relay.
Por defecto usa SQLite (simple, cero configuracion). Si el proyecto crece
(30+ usuarios activos), cambiar DATABASE_URL en el .env a Postgres.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .modelos import Base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./boveda_relay.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def crear_tablas():
    Base.metadata.create_all(bind=engine)


def obtener_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
