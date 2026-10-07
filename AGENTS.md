# AGENTS.md

## Project

Folios de gestión — certificate folio tracking system for Dirección Provincial de Salud Santiago 1. Spanish-language UI.

## Stack

- **Backend:** Flask 3 + SQLAlchemy + Flask-Login + Flask-WTF (CSRF) + Flask-Limiter
- **DB:** MariaDB 11.4 via PyMySQL
- **Frontend:** Jinja2 + Bootstrap 5 + jQuery + SweetAlert2
- **PDF:** WeasyPrint (requires pango/cairo libs, see Dockerfile)
- **Excel:** openpyxl
- **Deploy:** Docker + Gunicorn (4 workers, 120s timeout) on port 8089 + Redis (rate limits compartidos, sin puerto expuesto)

## Commands

```bash
# Local dev (no Docker for app itself)
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
docker compose up -d db          # start MariaDB only
python3 init_db.py               # seed admin + certificate types
python3 run.py                   # Flask dev server on :8089
venv/bin/python reset_password.py <user|email> [--password X] [--by admin]  # reset contraseña; solo si DB_HOST resuelve desde el host
venv/bin/python vaciar_tablas.py [--by USER]                        # vacía todas las tablas menos usuarios (doble confirmación: s + BORRAR)

# Full Docker stack
docker compose up -d             # app on :8089 (phpMyAdmin: docker compose --profile tools up -d phpmyadmin)
docker compose exec app python reset_password.py <user|email> [--password X] [--by admin]  # reset contraseña (imprime la nueva si se omite)

# Tests (pytest, SQLite in-memory)
pip install -r requirements-dev.txt
python3 -m pytest

# Migraciones (Flask-Migrate; DATABASE_URL opcional, si no usa DB_* de .env)
FLASK_APP=run.py venv/bin/flask db upgrade              # DB nueva
FLASK_APP=run.py venv/bin/flask db check                # esquema == modelos
# DB existente pre-migraciones: FLASK_APP=run.py flask db stamp 0001_baseline (una vez) y luego upgrade
```

Test suite exists (`tests/`, pytest + `requirements-dev.txt`). No linter, formatter, or typecheck commands exist in this repo.

## Environment

Requires `.env` (copy from `.env.example`). Critical vars:
- `SECRET_KEY` — app refuses to start without it. Generate with: `python -c "import secrets; print(secrets.token_hex(32))"`
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`

## Architecture

```
app/
  __init__.py      # create_app(), registers all blueprints, error handlers, /health endpoint
  config.py        # Config loads .env via dotenv; DevelopmentConfig adds DEBUG=True
  extensions.py    # db, login_manager, migrate, csrf, limiter singletons
  models/          # SQLAlchemy models (Usuario, Centro, TipoCertificado, Folio, etc.)
  services/        # lógica transversal: audit.py (log_audit), queries.py (get_or_404), excel.py
  decorators.py    # edit_required (permisos de edición por ruta)
  utils.py         # utcnow() para defaults de columnas DateTime
  auth/            # /auth/login, /auth/logout
  dashboard/       # /dashboard (KPIs + chart APIs)
  recepcion/       # /recepcion — register folio ranges + PDF/Excel export
  folios/          # /folios — list/manage individual folios
  entregas/        # /entregas — assign folios to health centers
  devoluciones/    # /devoluciones — record returns
  reportes/        # /reportes — PDF/Excel export
  escaneos/        # /escaneos — subida de folios escaneados JPG
  usuarios/        # /usuarios — user CRUD
  centros/         # /centros — health center CRUD + list PDF/Excel export + xlsx import
   certificados/    # /certificados — certificate type CRUD
   auditoria/       # /auditoria — audit log
   permisos/        # /permisos — permisos granulares por usuario (admin)
   marca/           # /marca — marca de la app: nombre, subtítulo, logo, favicon (admin)
   backup/          # /backup — copias de respaldo y restauración (admin)
   main/            # `/` redirects to dashboard
  templates/       # Jinja2 templates (shared across blueprints)
  static/          # CSS/JS/images
```

## Conventions

- Each module is a Flask blueprint in its own directory under `app/`. Blueprint registration happens in `app/__init__.py`.
- Models live in `app/models/`, imported via `app/models/__init__.py`.
- Forms use Flask-WTF (WTForms). CSRF is enabled globally.
- Routes requiring auth use `@login_required`. Login rate-limited to 10/min.
- All user-facing text is in **Spanish**.
- DB column names use camelCase in the database (e.g. `folioInicial`, `tipoCert`), but SQLAlchemy models map to `snake_case` attributes with `_id` suffixes for foreign keys (e.g. `tipoCert_id`, `centro_id`).
- Error pages are rendered inline in `app/__init__.py` via `render_template_string`.

## Gotchas

- `SECRET_KEY` must be set in `.env` or the app raises `RuntimeError` on startup (`app/config.py:10`).
- App config selected via `FLASK_CONFIG` (`development`/`production`), default **production**. Docker forces `FLASK_CONFIG: production` in `docker-compose.yml`; local debug needs `FLASK_CONFIG=development`.
- `init_db.py` creates admin with a **random password** printed once to console — no fixed default anymore.
- Migrations: DBs existentes pre-migraciones requieren `flask db stamp 0001_baseline` una vez antes de `flask db upgrade` (ver README para SQL de duplicados previo a `0002_integrity`). `0003_indexes` cambia índices de `folios`/`audit_logs` — crea los compuestos antes de dropear los simples porque el FK `folios.tipoCert_id` exige un índice.
- Si `alembic_version` trae una revisión desconocida (cadena de migraciones ajena), `upgrade`/`check` fallan con `Can't locate revision`: fijarla a `0001_baseline` con `UPDATE alembic_version` y subir (ver README → "DB con cadena de migraciones ajena"). `db check` quedará con extras heredados inofensivos.
- `/auth/logout` is POST-only (navbar renders a form with CSRF token); GET returns 405.
- Rate limits: `RATELIMIT_STORAGE_URI` (default `memory://` para dev; compose inyecta `redis://redis:6379` para que los 4 workers compartan el contador). El cliente `redis` va en `requirements.txt`: Flask-Limiter construye el storage *eager* en `init_app` → sin el paquete la app no arranca (gunicorn exit 3). `RATELIMIT_SWALLOW_ERRORS=true` (fail-open si Redis cae). El límite solo cuenta peticiones que llegan al view: las rechazadas por CSRF global (400) no consumen cuota.
- Sesiones: login marca la sesión como permanente con timeout de 8 h (`PERMANENT_SESSION_LIFETIME`).
- Rate limit global: `RATELIMIT_DEFAULT=300 per hour` cubre toda ruta sin límite propio (exports, listados, API). Las rutas con límite propio (login 10/min) no lo heredan. Ajustable por env.
- Exports: `neutralizar_formulas()` en `app/services/excel.py` evita que nombres que empiezan con `=` se escriban como fórmula en los .xlsx.
- WeasyPrint needs system pango/cairo libraries — only available in the Docker image, not a bare venv.
- `init_db.py` is idempotent (checks for existing admin/types before inserting).
- Credenciales de MariaDB: `MYSQL_ROOT_PASSWORD`/`MYSQL_PASSWORD` solo valen en la **primera** inicialización del volumen. Si `.env` cambia sin `ALTER USER`, la app queda "healthy" (el healthcheck no toca DB) pero cualquier query da 500. Ver README → "Rotar credenciales de MariaDB". El usuario de la app es `folios_app` (privilegios solo sobre `DB_NAME`); `DB_USER=root` emite warning en cada arranque.
- The `/` route redirects to `/dashboard`; there is no landing page.
- Health check endpoint: `GET /health` returns `{"status": "ok"}` y está **exento** de rate limits (el healthcheck de compose lo pingea cada 30 s).
- `SECRET_KEY` de ejemplo (`change-me-in-production`, `cambie-…`) también aborta el arranque, no solo la ausencia.
- `SESSION_COOKIE_SECURE` **default `false`**: con `true` sobre HTTP plano el navegador descarta la cookie y el login no persiste. Activar solo detrás de TLS (`SESSION_COOKIE_SECURE=true` + `TRUST_PROXY=true`).
- `load_user` (`app/__init__.py`) devuelve `None` si `Usuario.activo` es falso: desactivar un usuario corta su sesión viva.
- Permisos: `admin_required` y `edit_required` viven en `app/decorators.py` y ya incluyen `login_required`. No redefinirlos por blueprint.
- Permisos granulares: catálogo en `app/services/permisos.py` (`PERMISOS`, jinja global `puede()`, decorator `permiso_requerido` en `app/decorators.py`). Los grants por usuario (`permiso_usuarios`) **solo suman** al rol base (`edit`/`admin`) — nunca lo restan; para quitar capacidad use el rol o desactivar. `grants_de` cachea en `g` solo dentro de request context (los tests sin request ven estado real).
- Marca: tabla singleton `marca_config` (logo/favicon = BLOB en DB, no volumen Docker). Inyectada como `marca` en todos los templates (`marca_template_dict` en `app/models/marca.py`, cache por request, fallback a defaults si la DB falla — las páginas de error deben renderizar sin DB). `/marca/logo` y `/marca/favicon` son **públicas** (login sin sesión) y `@limiter.exempt` (el favicon se pide en cada carga). PDFs: `app/services/pdf.py::encabezado_pdf/logo_pdf` (data-URI, WeasyPrint).
- Copias: `app/services/backup.py` (`TABLAS_ORDEN` fijo: borrado en orden inverso, inserción en orden de FK, todo en UNA transacción). La restauración **reemplaza total** las tablas; `alembic_version` no viaja en el respaldo. Auditoría `BACKUP`/`RESTORE` se escribe después del commit (sobrevive aunque la copia reemplace `audit_logs`). `MAX_CONTENT_LENGTH` default 32 MB por el upload del respaldo.
- Tolerancia al esquema (`app/services/backup.py`): el respaldo guarda `meta.esquema`; al restaurar se compara con el schema actual — columnas nuevas quedan fuera del INSERT (SQLAlchemy/DB aplican default o NULL), obsoletas se ignoran, y una NOT NULL sin default **bloquea** con `ErrorRespaldo`. Se vacían TODAS las tablas de `TABLAS_ORDEN` (no solo las del archivo) para evitar FK huérfanas, y se rechaza un respaldo sin usuarios (lockout). Respaldos viejos sin `meta.esquema` exigen `meta.alembic` == actual. Flujo en 2 pasos: `POST /backup/previsualizar` (analiza, guarda el JSON en `app/backup/staging.py` con token de sesión, 30 min) → `POST /backup/restaurar` (token de un solo uso).
- Dumps SQL (copia de desastre): `scripts/dump_db.sh` / `scripts/restore_db.sh` corren `mariadb-dump` **dentro del contenedor `db`** (la app no lleva el cliente; el usuario `folios_app` no tiene `LOCK TABLES`/`SHOW VIEW`, se usa root con `MYSQL_PWD`). Salida a `backups/` (ignorado por git). Si la base tiene `alembic_version`, viaja en el dump → tras restaurar, `flask db upgrade`.
- KPIs: `app/services/kpis.py::conteos_folios` es la única fuente de dashboard y reportes; `entregado`/`devuelto` excluyen nulos.
- Timestamps: columnas `created_at`/`createAt`/`fecha` se guardan en UTC naive; se renderizan con el filtro `|localtime` (honra `TZ`, compose pone `America/Havana`). Los campos `fechaEntrega`/`fechaDevolucion` son `Date` de negocio y van en hora local.
- `RecepcionForm` limita el rango a `MAX_FOLIOS_POR_RECEPCION` (10000) folios; el chequeo de solape se repite dentro del `try` de `recepcion/create`, bajo el `FOR UPDATE` de `_next_rango_id`, porque la validación del form corre antes del lock.
- Escaneos: JPG en `SCANS_FOLDER` (env, default `<raíz>/scans`), montado en Docker como `./scans:/app/scans`. **Ownership**: si `scans/` no existe en el host, Docker la crea como root y `appuser` (UID 1000) no puede escribir → toda subida falla con "Error al guardar"; crear antes del primer arranque (`mkdir -p scans && chown 1000:1000 scans`). El único gate de nombre es `NOMBRE_RE` en `app/services/escaneos.py` (`^(\d{1,10})\.(jpg|jpeg)$`): `EscaneoForm.archivos` **no** lleva `FileAllowed` a propósito — un no-JPG no debe abortar el lote; los inválidos se reportan por archivo y no se escriben.
- Tests PDF (`test_pdf_escape`, `test_exports_contenido::…pdf`) requieren pango/cairo: corren en Docker, no en un venv bare.
- Tests: **un solo usuario autenticado por test**. El fixture `app` mantiene un app context activo y Flask lo reusa en cada request ⇒ `g._login_user` (caché de Flask-Login) se comparte entre test clients del mismo test: un segundo client ve al usuario del primero. En producción no aplica (context por request).
