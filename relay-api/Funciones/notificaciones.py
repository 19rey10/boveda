"""
Envio de notificaciones push (Firebase Cloud Messaging) cuando alguien
sube archivos publicos. Requiere que FIREBASE_CREDENTIALS_JSON este
configurado en el .env con el contenido completo del JSON de la cuenta
de servicio de Firebase.

Las notificaciones de "alguien subio algo" NO se mandan al toque: se
programan con un retraso random distinto por persona (30-50 min), y si
ese horario cae en horas del dia (8am-7pm), se empuja a la noche
(20:00-22:30), para no ser invasivo durante el dia.
"""
import json
import os
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import firebase_admin
from firebase_admin import credentials, messaging
from sqlalchemy.orm import Session

from Datos.modelos import TokenPush, Usuario, NotificacionPendiente

ZONA_HORARIA = os.getenv("APP_TIMEZONE", "America/Santo_Domingo")

_firebase_listo = False


def _inicializar_firebase() -> bool:
    global _firebase_listo
    if _firebase_listo:
        return True

    credenciales_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if not credenciales_json:
        print("[notificaciones] FIREBASE_CREDENTIALS_JSON no configurado, push desactivado")
        return False

    try:
        cred_dict = json.loads(credenciales_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        _firebase_listo = True
        return True
    except Exception as e:
        print(f"[notificaciones] Error inicializando Firebase: {e}")
        return False


def _calcular_hora_envio() -> datetime:
    """Retraso random de 30-50 min. Si cae en horario diurno (8am-7pm
    hora local), se empuja a un horario random entre las 20:00 y las
    22:30 de esa misma noche."""
    try:
        tz = ZoneInfo(ZONA_HORARIA)
    except Exception:
        tz = ZoneInfo("UTC")

    ahora_local = datetime.now(tz)
    minutos_retraso = random.randint(30, 50)
    propuesto = ahora_local + timedelta(minutes=minutos_retraso)

    if 8 <= propuesto.hour < 19:
        minutos_desde_medianoche = random.randint(20 * 60, 22 * 60 + 30)
        noche = propuesto.replace(hour=0, minute=0, second=0, microsecond=0)
        noche += timedelta(minutes=minutos_desde_medianoche)
        if noche <= ahora_local:
            noche += timedelta(days=1)
        propuesto = noche

    return propuesto.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def programar_notificaciones_subida(
    db: Session, uploader_id: int, uploader_nombre: str, descripcion: str, cantidad: int
):
    """Crea una notificacion pendiente para cada usuario con al menos un
    dispositivo registrado (menos quien subio), cada una con su propia
    hora random de envio."""
    destinatarios = (
        db.query(TokenPush.usuario_id)
        .filter(TokenPush.usuario_id != uploader_id)
        .distinct()
        .all()
    )

    for (usuario_id,) in destinatarios:
        db.add(NotificacionPendiente(
            usuario_destino_id=usuario_id,
            uploader_nombre=uploader_nombre,
            descripcion=descripcion,
            cantidad=cantidad,
            enviar_en=_calcular_hora_envio(),
        ))
    db.commit()


def procesar_notificaciones_pendientes(db: Session):
    """Revisa (cada minuto, llamado desde el scheduler en main.py) si
    hay notificaciones cuya hora ya llego, y las manda."""
    if not _inicializar_firebase():
        return

    pendientes = (
        db.query(NotificacionPendiente)
        .filter(
            NotificacionPendiente.enviada.is_(False),
            NotificacionPendiente.enviar_en <= datetime.utcnow(),
        )
        .all()
    )

    for n in pendientes:
        tokens = [
            t[0] for t in db.query(TokenPush.token)
            .filter(TokenPush.usuario_id == n.usuario_destino_id).all()
        ]

        if tokens:
            if n.descripcion:
                cuerpo = f'{n.uploader_nombre} subió {n.cantidad} archivo(s): "{n.descripcion}" ¿Los querés ver?'
            else:
                cuerpo = f"{n.uploader_nombre} subió {n.cantidad} archivo(s) nuevo(s). ¿Los querés ver?"

            mensaje = messaging.MulticastMessage(
                notification=messaging.Notification(title="Bóveda", body=cuerpo),
                tokens=tokens,
            )
            try:
                respuesta = messaging.send_each_for_multicast(mensaje)
                for i, resultado in enumerate(respuesta.responses):
                    if not resultado.success:
                        db.query(TokenPush).filter(TokenPush.token == tokens[i]).delete()
            except Exception as e:
                print(f"[notificaciones] Error enviando push a usuario {n.usuario_destino_id}: {e}")

        n.enviada = True

    if pendientes:
        db.commit()
        print(f"[notificaciones] Procesadas {len(pendientes)} notificaciones pendientes")
