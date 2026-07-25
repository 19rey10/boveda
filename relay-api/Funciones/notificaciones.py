"""
Envio de notificaciones push (Firebase Cloud Messaging) cuando alguien
sube archivos publicos. Requiere que FIREBASE_CREDENTIALS_JSON este
configurado en el .env con el contenido completo del JSON de la cuenta
de servicio de Firebase (ver README para como conseguirlo).
"""
import json
import os

import firebase_admin
from firebase_admin import credentials, messaging
from sqlalchemy.orm import Session

from Datos.modelos import TokenPush

_firebase_listo = False


def _inicializar_firebase():
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


def notificar_nueva_subida(db: Session, uploader_id: int, uploader_nombre: str, descripcion: str, cantidad: int):
    """Manda un push a todos los usuarios (menos quien subio) avisando
    que hay fotos/videos publicos nuevos."""
    if not _inicializar_firebase():
        return

    tokens = (
        db.query(TokenPush.token)
        .filter(TokenPush.usuario_id != uploader_id)
        .all()
    )
    tokens = [t[0] for t in tokens]
    if not tokens:
        return

    if descripcion:
        cuerpo = f'{uploader_nombre} subió {cantidad} archivo(s): "{descripcion}" ¿Los querés ver?'
    else:
        cuerpo = f"{uploader_nombre} subió {cantidad} archivo(s) nuevo(s). ¿Los querés ver?"

    mensaje = messaging.MulticastMessage(
        notification=messaging.Notification(
            title="Bóveda",
            body=cuerpo,
        ),
        tokens=tokens,
    )

    try:
        respuesta = messaging.send_each_for_multicast(mensaje)
        print(f"[notificaciones] Enviadas {respuesta.success_count}/{len(tokens)}")

        # limpiar tokens que ya no son validos (apps desinstaladas, etc.)
        for i, resultado in enumerate(respuesta.responses):
            if not resultado.success:
                db.query(TokenPush).filter(TokenPush.token == tokens[i]).delete()
        db.commit()
    except Exception as e:
        print(f"[notificaciones] Error enviando push: {e}")
