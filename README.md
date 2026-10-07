# Gestión de Folios - Dirección Provincial de Salud Santiago 1

Sistema de gestión de certificados del Departamento de Bioestadística.

## Requisitos

- Docker y Docker Compose
- Python 3.11+

## Instalación con Docker

```bash
# Iniciar servicios
docker compose up -d

# Acceder a la app
http://localhost:8089

# phpMyAdmin (opcional, tras profile "tools")
docker compose --profile tools up -d phpmyadmin
http://localhost:8081
```

## Usuario por defecto

- **Usuario:** admin
- **Contraseña:** aleatoria — `init_db.py` la imprime una sola vez en consola al crearla. Guárdela; para bases ya inicializadas no cambia.

## Configuración de seguridad (`.env`)

| Variable | Default | Notas |
|----------|---------|-------|
| `SECRET_KEY` | — | Obligatoria. La app arranca solo si no es un valor de ejemplo (`change-me-in-production`, `cambie-…`). Genere una: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DB_USER` / `DB_PASSWORD` | `folios_app` | Usuario con privilegios solo sobre `DB_NAME`. Arrancar como `root` emite un warning en el log. `DB_PASSWORD` (app) y `DB_ROOT_PASSWORD` (root) deben ser distintos. |
| `SESSION_COOKIE_SECURE` | `false` | Póngala en `true` **solo** detrás de TLS. Con HTTP plano `true` hace que el navegador descarte la cookie y el login no persista. |
| `TRUST_PROXY` | `false` | `true` solo detrás de un reverse proxy que fije `X-Forwarded-For`. Permite que los rate limits distingan IP reales. |
| `RATELIMIT_DEFAULT` | `300 per hour` | Tope global de peticiones. `/health` va exento. |
| `TZ` | UTC (contenedor) | Hora local para las fechas de auditoría y detalle de folio (se guardan en UTC). |
| `SCANS_FOLDER` | `<raíz del proyecto>/scans` | Carpeta de los JPG de folios escaneados: `<SCANS_FOLDER>/<año>/<número>.jpg`. En Docker montada como `./scans:/app/scans` — ver el gotcha de ownership en [Escaneos](#escaneos). |

### Rotar credenciales de MariaDB

`MYSQL_ROOT_PASSWORD` y `MYSQL_PASSWORD` de `docker-compose.yml` solo se aplican
en la **primera** inicialización del volumen `mariadb_data`. Editarlas en `.env`
**no** cambia la contraseña ya guardada en la base:

```bash
# 1) Cambiar la contraseña en MariaDB (usando la contraseña vigente)
docker compose exec -T db sh -c "MYSQL_PWD='<actual>' mariadb -uroot -e \
  \"ALTER USER 'root'@'localhost' IDENTIFIED BY '<nueva>';
    ALTER USER 'root'@'%' IDENTIFIED BY '<nueva>'; FLUSH PRIVILEGES;\""

# 2) Actualizar .env y recrear el contenedor de la app
docker compose up -d --force-recreate app
```

Si `.env` y la base quedan desincronizadas, el contenedor sigue saliendo
**healthy** (el healthcheck `/health` no consulta la base) y cualquier petición
real falla con 500.

## Desarrollo local

```bash
# Crear virtual environment
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Iniciar MariaDB (requiere Docker o instalación local)
docker compose up -d db

# Inicializar base de datos
python3 init_db.py

# Ejecutar app (DEBUG solo con FLASK_CONFIG=development)
FLASK_CONFIG=development python3 run.py

# Tests
pip install -r requirements-dev.txt
python3 -m pytest
```

## Restablecer contraseña olvidada

Si un usuario olvidó su contraseña (incluido el admin), desde el servidor con
el stack Docker levantado (`.env` usa `DB_HOST=db`, que solo resuelve dentro de
la red de compose):

```bash
# Genera contraseña aleatoria y la imprime una sola vez
docker compose exec app python reset_password.py juan

# Contraseña propia (acepta username o email)
docker compose exec app python reset_password.py juan@salud.gob.cu --password NuevaClave123

# Opcional: quién registra la acción en auditoría (default: el propio usuario)
docker compose exec app python reset_password.py juan --password NuevaClave123 --by admin
```

Fuera de compose (DB local con `DB_HOST` resolvable desde el host), el mismo
script corre con el venv: `venv/bin/python reset_password.py juan`.

No hay reset por correo. Cada uso deja registro en `audit_logs` con
`ip_address='cli'`. Salida 1 = usuario no encontrado o contraseña menor de 6
caracteres. Los admin también pueden cambiarla desde `/usuarios/edit` sin
salir de la app.

## Migraciones de base de datos

El esquema se gestiona con Flask-Migrate (Alembic) en `migrations/`. `DATABASE_URL` (si existe) tiene prioridad sobre `DB_*` de `.env`.

```bash
# DB nueva: aplicar todo
FLASK_APP=run.py flask db upgrade

# DB existente creada antes de las migraciones: marcar baseline una sola vez y subir
FLASK_APP=run.py flask db stamp 0001_baseline
FLASK_APP=run.py flask db upgrade        # aplica 0002_integrity y posteriores

# Verificar que el esquema coincide con los modelos
FLASK_APP=run.py flask db check
```

Revisions: `0001_baseline` (esquema original) → `0002_integrity` (constraints únicos) → `0003_indexes` (índices compuestos de consulta: `(anioCert, estado, nulo)`, `(tipoCert_id, anioCert)` y `audit_logs.fecha`; elimina los índices de una sola columna que quedan subsumidos) → `0004_sync_config` (tabla `sync_config`: estado y frecuencia de la sincronización a Google Sheets) → `0005_permisos_usuario` (tabla `permiso_usuarios`: permisos granulares por usuario, FK a `usuarios` con CASCADE) → `0006_marca_config` (tabla `marca_config`: nombre/subtítulo de la app + logo y favicon como BLOB).

**Antes de `0002` en una BD con datos**, compruebe que no haya duplicados (el ALTER fallará si los hay):

```sql
SELECT rangoId, folio, COUNT(*) FROM folios GROUP BY rangoId, folio HAVING COUNT(*) > 1;
SELECT anioCert, tipoCert_id, folio, COUNT(*) FROM folios GROUP BY anioCert, tipoCert_id, folio HAVING COUNT(*) > 1;
SELECT folio_id, COUNT(*) FROM entrega_folios GROUP BY folio_id HAVING COUNT(*) > 1;
SELECT folio_id, COUNT(*) FROM devolucion_folios GROUP BY folio_id HAVING COUNT(*) > 1;
```

Si hay filas, resuélvalas manualmente antes del upgrade.

### DB con cadena de migraciones ajena

Si `alembic_version` contiene una revisión que no existe en `migrations/versions/`, tanto `db upgrade` como `db check` fallan con `Can't locate revision`. Reparación (respaldar antes):

```bash
docker compose exec db mariadb-dump -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" > backup.sql
docker compose exec db mariadb -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" -e \
  "UPDATE alembic_version SET version_num='0001_baseline'"
FLASK_APP=run.py flask db upgrade
```

Después de reparar, `flask db check` puede seguir reportando objetos extra heredados de esa cadena ajena (índices `idx_folio_folio`, `idx_audit_user_fecha`, `idx_entrega_fechaEntrega`, `idx_devolucion_fechaDevolucion` y los únicos `uq_entrega_folio`/`uq_devolucion_folio`, duplicados de los de `0002`). No afectan al funcionamiento; son inofensivos.

## Sincronización con Google Sheets

La tabla `folios` se replica a una hoja de Google Sheets con cuenta de servicio
(estrategia upsert por `id`: solo se actualizan las celdas que cambiaron, se
agregan los folios nuevos y se eliminan las filas huérfanas). Se dispara de dos
formas: botón **Sincronizar ahora** (solo administradores) y el servicio
`sync-worker` (APScheduler), cuya frecuencia se configura desde el módulo
**Sincronización** sin reiniciar nada.

**Puesta en marcha:**

```bash
# 1) Cuenta de servicio en Google Cloud (proyecto > IAM > Cuentas de servicio):
#    crear cuenta, generar clave JSON (tipo), descargar.
mkdir -p secrets && mv ~/Downloads/*.json secrets/service_account.json

# 2) Crear una hoja en blanco y compartir la hoja con el client_email del JSON
#    como Lector/Editor. Copiar el ID de la URL entre /d/ y /edit.

# 3) .env (ver .env.example)
GOOGLE_SERVICE_ACCOUNT_JSON=/app/secrets/service_account.json
GOOGLE_SHEET_ID=1AbCdEf...
GOOGLE_SHEET_WORKSHEET=folios
# Opcional: token para disparar POST /sincronizacion/api/sincronizar desde curl/cron externo
SHEET_SYNC_TOKEN=

# 4) Migración (tabla sync_config) y levantar todo
FLASK_APP=run.py flask db upgrade
docker compose up -d --build
```

Luego entrar a **Sincronización** en la UI: activar la sincronización
automática, elegir la frecuencia (5–10080 minutos) y probar con
**Sincronizar ahora**. El estado (último intento, resultado/error, próximo
intento) se guarda en `sync_config` y se muestra en la misma pantalla; los
fallos se reintentan a los 15 minutos en vez de esperar el intervalo completo.
El navbar muestra una cuenta atrás con la próxima sincronización automática
(`GET /sincronizacion/api/proxima`, visible para cualquier usuario autenticado;
`--:--` si está desactivada). Endpoint para disparadores externos:

```bash
curl -fsX POST -H "X-Sync-Token: $SHEET_SYNC_TOKEN" \
  http://localhost:8089/sincronizacion/api/sincronizar
```

## Módulos

| Módulo | Ruta | Descripción |
|--------|------|-------------|
| Dashboard | `/dashboard` | KPIs y gráficas |
| Recepción | `/recepcion` | Registrar rangos de folios |
| Folios | `/folios` | Listar y gestionar folios |
| Entregas | `/entregas` | Asignar folios a centros |
| Devoluciones | `/devoluciones` | Registrar devoluciones |
| Reportes | `/reportes` | Exportar PDF/Excel |
| Usuarios | `/usuarios` | Gestión de usuarios |
| Centros | `/centros` | Centros de salud |
| Certificados | `/certificados` | Tipos de certificado |
| Auditoría | `/auditoria` | Bitácora de acciones |
| Sincronización | `/sincronizacion` | Sync folios → Google Sheets (manual + automático) |
| Permisos | `/permisos` | Permisos granulares por usuario (admin) |
| Marca | `/marca` | Nombre, subtítulo, logo y favicon (admin) |
| Copias | `/backup` | Descarga y restauración de respaldos JSON (admin) |
| Escaneos | `/escaneos/subir` | Subir JPG de folios escaneados y marcarlos (permiso `escaneos.subir`) |

## Escaneos

Admin/operador → **Escaneos** (`/escaneos/subir`), permiso `escaneos.subir`
(rol `edit` o `admin`).

- **Convención de nombre:** cada archivo debe llamarse `<número>.jpg` o
  `<número>.jpeg` (1–10 dígitos, mayúspulas/minúsculas indiferentes). El
  destino en disco se reconstruye desde el número parseado, así que el nombre
  que llega del navegador nunca toca el filesystem.
- **Subcarpeta por año:** el selector de año del form manda; los archivos se
  guardan en `<SCANS_FOLDER>/<año>/`. El año se aplica a todo el lote, sin
  importar la fecha del archivo.
- **Sobrescritura:** subir de nuevo el mismo número sobrescribe el JPG
  existente (gana el último del lote) y el folio sigue marcado.
- **Lote tolerante a errores:** un nombre inválido (`.png`, espacios, ruta,
  más de 10 dígitos…) no aborta el request — se reporta por archivo como
  "Nombre inválido", no se escribe nada para él y el resto del lote se
  procesa normalmente. No hay validación `FileAllowed` en el form: el único
  gate es la regex de `app/services/escaneos.py`.
- **Marcado:** al guardar, los folios con ese `(año, número)` quedan en
  `escaneado=True` (auditable); si no existe el folio el JPG se guarda igual
  y se reporta "Sin coincidencia".

### Volumen Docker: crear `scans/` antes del primer arranque

`docker-compose.yml` monta `./scans:/app/scans`. Si la carpeta **no existe**
en el host, Docker la crea como **root**, pero la app corre como `appuser`
(UID 1000) y toda subida fallaría con "Error al guardar" (permiso denegado).
Crée la carpeta con el ownership correcto **antes** de `docker compose up -d`:

```bash
mkdir -p scans
chown 1000:1000 scans   # UID/GID de appuser (Dockerfile)
```

Si la carpeta ya existe como root (la creó Docker por nosotros):

```bash
sudo chown -R 1000:1000 scans
```

`SCANS_FOLDER` (env var, default `<raíz>/scans`) cambia la ruta solo a nivel
de aplicación; en Docker el punto de montaje sigue siendo `./scans` — ajuste
también `docker-compose.yml` si la renombra.

## Copias de respaldo

Admin → **Copias** (`/backup`). Dos formatos, complementarios:

### 1. JSON desde la aplicación (migración cómoda, testeada)

- **Descargar copia**: JSON con todas las tablas (negocio, usuarios, permisos,
  marca, auditoría) más `meta.esquema` — las columnas de cada tabla al momento
  de copiar. Se guarda en el navegador; el servidor no almacena respaldos.
- **Restaurar** es en dos pasos:
  1. **Analizar archivo**: valida y muestra el diff (filas por tabla, columnas
     nuevas que se rellenan, columnas obsoletas que se ignoran, tablas que
     quedarían vacías) **sin tocar la base**. El archivo queda en un almacén
     temporal con un token de un solo uso (30 min) ligado a la sesión.
  2. **Restaurar**: confirma con el token y aplica el reemplazo total en una
     sola transacción (un error revierte todo).
- **Tolerancia al esquema**: no importa si `alembic_version` cambió. Las
  columnas nuevas se dejan fuera del INSERT (SQLAlchemy/DB aplican su default
  o NULL) y las que ya no existen se descartan. Se **bloquea** si hay una
  columna obligatoria sin default (mejor un error claro que un 500 a mitad de
  la operación).
- Se **vacían todas las tablas**, no solo las del archivo: así una tabla
  ausente no deja filas huérfanas apuntando a claves foráneas inexistentes.
- **Anti-lockout**: se rechaza un respaldo sin usuarios (o con la tabla
  usuarios vacía), porque dejaría la aplicación sin cuenta de acceso.
- Respaldos **anteriores a `meta.esquema`** (formato viejo) solo se restauran
  si `meta.alembic` coincide con la versión actual.
- Límite de subida: `MAX_CONTENT_LENGTH` (default 32 MB).

### 2. Dump SQL de la base (copia de desastre total)

Corre `mariadb-dump` **dentro del contenedor `db`** — la app no necesita el
cliente:

```bash
scripts/dump_db.sh                      # → backups/db_<fecha>.sql.gz
scripts/restore_db.sh backups/db_*.sql.gz   # ⚠ reemplaza todo
```

- El dump incluye esquema + datos + `alembic_version` (si existe) → tras
  restaurar, `FLASK_APP=run.py flask db upgrade` lleva el esquema al HEAD.
- Se usa `root` del contenedor (el usuario de la app no tiene
  `LOCK TABLES`/`SHOW VIEW`) y la contraseña viaja por `MYSQL_PWD`, no en argv.
- `backups/` está en `.gitignore`.

## Tech Stack

- **Backend:** Python 3 + Flask + SQLAlchemy
- **Frontend:** Jinja2 + Bootstrap 5 + jQuery + SweetAlert2
- **DB:** MariaDB 11.4
- **DevOps:** Docker + Docker Compose (Redis para rate limits entre workers)
