# Bóveda — arquitectura y guía de despliegue

Archivo familiar privado de fotos y videos, organizado por día real de
captura, con almacenamiento en SSD local.

## Cómo funciona

```
[App en Google AI Studio]
        |  HTTPS
        v
[relay-api]  <-- desplegado en Render/Fly/Railway, URL publica siempre online
   - login, registro, recuperar contraseña
   - recibe subidas y las encola
   - cachea metadata + miniaturas para poder navegar la galería
     aunque la laptop esté apagada
   - aplica la regla de privacidad: privadas SOLO visibles para
     quien las subió (o admin)
        |
        |  HTTPS (la laptop inicia la conexión, nunca al revés,
        |         asi que no hace falta abrir puertos en tu router)
        v
[worker-local]  <-- corre en tu laptop
   - cada 30s (configurable) pregunta al relay si hay pendientes
   - si tu laptop está apagada o sin internet, simplemente no pasa nada
     y se retoma solo cuando vuelve a estar online
   - a cada archivo le saca la fecha real (EXIF/metadata de video)
   - lo guarda en tu SSD organizado: usuarios/{user}/{publicas|privadas}/AAAA/MM/DD/
   - confirma al relay, que borra el archivo de su cola temporal
```

**Por qué así:** si el relay estuviera caído no pasa nada grave (Render lo reinicia solo). Si tu laptop se apaga por un corte de luz, los usuarios igual pueden subir — solo queda en cola hasta que la laptop vuelva a prenderse y se conecte sola.

## Paso 1: Subir el código a GitHub

```bash
cd boveda
git init
git add .
git commit -m "primera version"
git remote add origin https://github.com/TU_USUARIO/boveda.git
git branch -M main
git push -u origin main
```

Revisá con `git status` antes del commit que no aparezca ningún `.env` real en la lista — el `.gitignore` ya lo excluye, pero conviene chequear.

## Paso 2: Desplegar el relay-api (Render, Fly.io o Railway)

Con Render (más simple):
1. render.com → New + → Web Service → elegí tu repo `boveda`
2. Root Directory: `relay-api`
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. En Environment Variables cargá `JWT_SECRET`, `WORKER_SECRET`, `DATABASE_URL`, los datos de `SMTP_*` y `APP_URL` — nunca subas el `.env` real, esto lo reemplaza
6. Te da una URL tipo `https://boveda-relay.onrender.com` — esa es la que usa tu app de Google AI Studio

Nota: en el plan gratis de Render el servicio "duerme" tras un rato sin uso y tarda unos segundos en despertar con la primera visita. Si eso molesta con 30+ usuarios activos, el plan pago (~$7/mes) lo mantiene siempre despierto.

## Paso 3: Crearte como admin (sin escribir tu contraseña en ningún archivo)

Desde tu compu, apuntando al servicio ya desplegado (Render tiene una consola / shell en el dashboard del servicio):

```bash
python seed_admin.py
# te va a pedir username, email, nombre y contraseña de forma interactiva
```

## Paso 4: Levantar el worker en tu laptop

```bash
cd worker-local
python -m venv venv
source venv/bin/activate  # o venv\Scripts\activate en Windows
pip install -r requirements.txt
cp .env.example .env
# completar RELAY_URL con la URL de Render, WORKER_SECRET (igual al de Render), y RUTA_SSD
python main.py
```

Para que esto corra siempre, incluso al reiniciar la laptop:
- **Linux**: crear un servicio systemd que ejecute `python main.py`
- **Windows**: usar el Programador de Tareas para que arranque al iniciar sesión

## Paso 5: Conectar la app de Google AI Studio

La app le habla al relay-api desplegado (nunca directo a tu laptop). Le pasás la URL de Render como base para estos endpoints:

- `POST /auth/registro`, `POST /auth/login`
- `POST /auth/olvide-password`, `POST /auth/reset-password`
- `POST /archivos/subir` (multipart, varios archivos + descripción + público/privado)
- `GET /galeria/por-dia` (agrupado por día, ya filtrado por privacidad)
- `GET /galeria/buscar?q=...`
- `GET /admin/resumen`, `GET /admin/usuarios`, `GET /admin/cola` (solo admin)

## Nota sobre la SSD (Toshiba THNSNK128GCS8)

128GB es poco para 30+ usuarios subiendo fotos/videos con el tiempo. No es
un tema de calentamiento (esta SSD es SATA de bajo consumo, no se
calienta significativamente), es un tema de **capacidad**. Con fotos de
celular actuales (3-8MB) y videos, se llena rápido. Conviene planear
ampliar el almacenamiento (otra SSD más grande, o un RAID en el Pi que
ya tenés) antes de que sea un problema — el worker ya te avisa en los
logs cuando quedan menos de 5GB libres.
