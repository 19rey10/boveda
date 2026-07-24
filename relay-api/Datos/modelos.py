"""
Modelos de base de datos del relay.
El relay guarda: usuarios, cola de sincronizacion (pendiente de bajar a la SSD)
y una cache liviana de metadata/miniaturas para poder navegar la galeria
aunque la laptop este apagada.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, LargeBinary
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    nombre_display = Column(String(80), nullable=False)
    es_admin = Column(Boolean, default=False)
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime, default=datetime.utcnow)

    archivos = relationship("Archivo", back_populates="uploader")


class Archivo(Base):
    """
    Cache de metadata en el relay. El archivo original y la fuente de verdad
    de la metadata viven en la SSD de la laptop; esto es una copia liviana
    para poder mostrar la galeria y las miniaturas sin depender de que la
    laptop este online.
    """
    __tablename__ = "archivos"

    id = Column(Integer, primary_key=True)
    uploader_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    hash_sha256 = Column(String(64), unique=True, index=True, nullable=False)

    tipo = Column(String(10), nullable=False)  # "imagen" | "video"
    es_publica = Column(Boolean, default=False, index=True)
    descripcion = Column(Text, nullable=True)

    fecha_tomada = Column(DateTime, nullable=True, index=True)  # de EXIF, puede faltar
    fecha_subida = Column(DateTime, default=datetime.utcnow, index=True)

    ruta_ssd = Column(String(500), nullable=True)  # se completa cuando la laptop lo procesa
    thumbnail_blob = Column(LargeBinary, nullable=True)  # miniatura chica cacheada en el relay
    tamano_bytes = Column(Integer, nullable=True)

    sincronizado = Column(Boolean, default=False, index=True)  # ya lo proceso la laptop?

    uploader = relationship("Usuario", back_populates="archivos")


class ColaSync(Base):
    """
    Cola de archivos pendientes de bajar a la SSD. La laptop hace polling
    de esta tabla via /sync/pendientes y confirma con /sync/ack cuando
    ya guardo el archivo en la SSD.
    """
    __tablename__ = "cola_sync"

    id = Column(Integer, primary_key=True)
    archivo_id = Column(Integer, ForeignKey("archivos.id"), nullable=False)
    archivo_blob = Column(LargeBinary, nullable=False)  # el binario completo, temporal
    nombre_original = Column(String(255), nullable=False)
    intentos = Column(Integer, default=0)
    creado_en = Column(DateTime, default=datetime.utcnow)


class TokenRecuperacion(Base):
    __tablename__ = "tokens_recuperacion"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    token = Column(String(120), unique=True, nullable=False, index=True)
    expira_en = Column(DateTime, nullable=False)
    usado = Column(Boolean, default=False)


class SolicitudDescarga(Base):
    """
    Cuando un usuario pide descargar el archivo original, el relay no lo
    tiene (solo la laptop, en la SSD). Se crea un pedido aca, la laptop
    lo ve la proxima vez que hace polling, sube el archivo, y el usuario
    lo descarga desde el relay. Es de un solo uso: se borra despues de
    entregarse.
    """
    __tablename__ = "solicitudes_descarga"

    id = Column(Integer, primary_key=True)
    archivo_id = Column(Integer, ForeignKey("archivos.id"), nullable=False)
    contenido_blob = Column(LargeBinary, nullable=True)
    nombre_archivo = Column(String(255), nullable=True)
    listo = Column(Boolean, default=False)
    creado_en = Column(DateTime, default=datetime.utcnow)


class SolicitudEliminacion(Base):
    """
    Cuando se borra un archivo, el registro de la base se borra al toque,
    pero el archivo fisico sigue en la SSD hasta que la laptop se conecte
    y lo elimine. Guardamos la ruta directo aca (no una relacion al
    Archivo) porque el Archivo ya se borro para cuando la laptop procesa
    esto.
    """
    __tablename__ = "solicitudes_eliminacion"

    id = Column(Integer, primary_key=True)
    ruta_ssd = Column(String(500), nullable=False)
    listo = Column(Boolean, default=False)
    creado_en = Column(DateTime, default=datetime.utcnow)


class CodigoInvitacion(Base):
    """
    Codigos de invitacion de un solo uso. Solo un admin los genera. Una
    vez usado para registrarse, queda marcado y no sirve mas para nadie.
    """
    __tablename__ = "codigos_invitacion"

    id = Column(Integer, primary_key=True)
    codigo = Column(String(20), unique=True, nullable=False, index=True)
    creado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    usado = Column(Boolean, default=False)
    usado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    creado_en = Column(DateTime, default=datetime.utcnow)
    usado_en = Column(DateTime, nullable=True)
