# folios-gestion

Sistema de seguimiento de folios de certificados para una Dirección Provincial
de Salud: recepción de rangos, entrega/devolución a centros de salud, escaneos
y reportes. Interfaz en español, Flask + MariaDB.

- **App:** Flask 3 + SQLAlchemy + Flask-Login + Flask-WTF + Flask-Limiter
- **UI:** Jinja2 + Bootstrap 5 + jQuery + SweetAlert2
- **Servidor:** Gunicorn (4 workers) en el puerto `8089`
- **Extras:** Redis (rate limits compartidos), MariaDB 11.4, worker de
  sincronización con Google Sheets (APScheduler)
- **Exports:** PDF (WeasyPrint) y Excel (openpyxl) — las librerías de
  pango/cairo ya vienen en la imagen

## Quickstart

```bash
mkdir -p /opt/folios && cd /opt/folios
#   docker-compose.deploy.yml   compose que usa esta imagen (no compila)
#   .env.example                plantilla de variables
#   docs/despliegue.md          guía completa
# Código y docs: https://github.com/soportedpss1/folios-gestion
curl -fsSLO https://raw.githubusercontent.com/soportedpss1/folios-gestion/main/docker-compose.deploy.yml
curl -fsSLO https://raw.githubusercontent.com/soportedpss1/folios-gestion/main/.env.example
curl -fsSL -o despliegue.md https://raw.githubusercontent.com/soportedpss1/folios-gestion/main/docs/despliegue.md

cp .env.example .env && chmod 600 .env
# editar .env: SECRET_KEY, DB_PASSWORD, DB_ROOT_PASSWORD
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

mkdir -p scans secrets && sudo chown -R 1000:1000 scans secrets

docker compose -f docker-compose.deploy.yml up -d

# Orden correcto: migraciones primero, init_db después
# (init_db hace create_all y dejaría el esquema fuera de alembic_version)
docker compose -f docker-compose.deploy.yml exec -e FLASK_APP=run.py app flask db upgrade
docker compose -f docker-compose.deploy.yml exec app python init_db.py

open http://localhost:8089
```

`init_db.py` crea el usuario **admin** con una contraseña aleatoria que se
imprime **una sola vez** en consola.

El compose de despliegue usa la imagen publicada:

```yaml
services:
  app:
    image: soportedpss1/folios-gestion:1.0.0
    ports:
      - "8089:8089"
    env_file: .env
    # ... db (mariadb:11.4) + redis, healthchecks y volúmenes
```

## Configuración (`.env`)

| Variable | Requerida | Notas |
|----------|-----------|-------|
| `SECRET_KEY` | sí | sin ella (o con valor de ejemplo) la app no arranca |
| `DB_HOST` | sí | `db` (nombre del servicio MariaDB en compose) |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | sí | usuario de app con privilegios solo sobre `DB_NAME` |
| `DB_ROOT_PASSWORD` | sí | solo se usa en el primer arranque del volumen |
| `SESSION_COOKIE_SECURE` / `TRUST_PROXY` | no | `true` solo detrás de reverse proxy con TLS |
| `TZ` | no | default `America/Santo_Domingo`; timestamps en UTC, UI en local |
| `RATELIMIT_DEFAULT` | no | default `300 per hour` (`/health` exento) |
| `GOOGLE_SHEET_ID` / `GOOGLE_SERVICE_ACCOUNT_JSON` | no | sincronización con Google Sheets |

## Notas de operación

- **Puerto:** `8089` (HTTP). Detrás de proxy TLS activar
  `SESSION_COOKIE_SECURE=true` + `TRUST_PROXY=true`.
- **Carpeta `scans/`:** debe pertenecer a UID `1000` (`chown 1000:1000 scans`)
  — el contenedor corre como `appuser`; si Docker la crea como root, las
  subidas de escaneos fallan.
- **Permisos:** roles `admin` / `operador` / `lectura` más permisos
  granulares por usuario (Usuarios → Permisos). Recepción y escaneos son de
  admin por defecto; un admin puede concederlos.
- **Copias:** respaldo JSON desde la UI (Copias) o dump SQL desde el
  contenedor `db` con `mariadb-dump` (ver `docs/despliegue.md`).
- **Migraciones:** `FLASK_APP=run.py flask db upgrade` dentro del contenedor
  `app`; bases pre-migraciones requieren `flask db stamp 0001_baseline` una
  vez.
- **Rotar credenciales MariaDB:** cambiar `.env` no cambia la contraseña ya
  inicializada en el volumen — ver README (Rotar credenciales de MariaDB).

## Tags

- `soportedpss1/folios-gestion:1.0.0` — versión fija, recomendada en
  producción
- `soportedpss1/folios-gestion:latest` — última build, para pruebas

Para probar otra versión sin editar el compose: `FOLIOS_IMAGE=...:tag` en el
`.env`.

## Documentación

La guía completa de despliegue (`.env` anotado, reverse proxy TLS, copias y
restauración, actualización y troubleshooting) vive en `docs/despliegue.md`
del proyecto, junto a `docker-compose.deploy.yml` y `.env.example`.
