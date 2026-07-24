"""
Crea (o promueve) tu usuario admin de forma segura.
La contraseña se pide de forma interactiva (no queda en el historial de la
terminal ni en ningun archivo) usando getpass, que la oculta al escribirla.

Uso:
    python seed_admin.py
"""
import getpass
import sys

from Datos.db import SessionLocal, crear_tablas
from Datos.modelos import Usuario
from Funciones.auth import hashear_password


def main():
    crear_tablas()
    db = SessionLocal()

    username = input("Username: ").strip()
    email = input("Email: ").strip()
    nombre_display = input("Nombre a mostrar: ").strip()
    password = getpass.getpass("Contraseña (no se muestra en pantalla): ")
    password_confirmar = getpass.getpass("Confirma la contraseña: ")

    if password != password_confirmar:
        print("Las contraseñas no coinciden. Abortado.")
        sys.exit(1)

    if len(password) < 8:
        print("La contraseña deberia tener al menos 8 caracteres. Abortado.")
        sys.exit(1)

    usuario = db.query(Usuario).filter(Usuario.username == username).first()

    if usuario:
        usuario.password_hash = hashear_password(password)
        usuario.es_admin = True
        usuario.email = email
        usuario.nombre_display = nombre_display
        print(f"Usuario '{username}' actualizado y promovido a admin.")
    else:
        usuario = Usuario(
            username=username,
            email=email,
            nombre_display=nombre_display,
            password_hash=hashear_password(password),
            es_admin=True,
        )
        db.add(usuario)
        print(f"Usuario admin '{username}' creado.")

    db.commit()
    db.close()


if __name__ == "__main__":
    main()
