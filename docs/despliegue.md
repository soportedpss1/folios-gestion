# Despliegue en otro servidor

Guía para levantar **folios de gestión** en un servidor ajeno usando la imagen
publicada en Docker Hub (`soportedpss1/folios-gestion`), sin necesidad de
código fuente ni de compilar.

Contenido:

1. [Requisitos](#1-requisitos)
2. [Archivos necesarios](#2-archivos-necesarios)
3. [Crear el `.env`](#3-crear-el-env)
4. [Preparar carpetas](#4-preparar-carpetas)
5. [Arrancar el stack](#5-arrancar-el-stack)
6. [Inicializar la base](#6-inicializar-la-base)
7. [Copias de seguridad](#7-copias-de-seguridad)
8. [Reverse proxy con TLS](#8-reverse-proxy-con-tls)
9. [Actualizar a otra versión](#9-actualizar-a-otra-versión)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Requisitos

| Requisito | Mínimo |
|-----------|--------|
| Docker Engine | 24+ (con plugin `docker compose` v2) |
| RAM | 2 GB libres (gunicorn 4 workers + MariaDB + Redis) |
| Disco | 2 GB (imagen ~620 MB + MariaDB) |
| Puertos libres | `8089` (app), `8081` (phpMyAdmin, opcional) |
| Internet | solo para el `docker pull` inicial |

La imagen es **pública**: no hace falta `docker login` para descargarla
(loguearse solo si Docker Hub limita la descarga anónima o el repo pasa a
privado).

## 2. Archivos necesarios

Tres archivos, todos en la raíz del proyecto (se copian con `scp`, se pegan a
mano o se descargan desde donde almacene el release):

| Archivo | Qué es |
|---------|--------|
| `docker-compose.deploy.yml` | stack completo usando la **imagen publicada** (no compila) |
| `.env.example` | plantilla de variables → se copia a `.env` |
| `docs/despliegue.md` | esta guía |

```bash
mkdir -p /opt/folios && cd /opt/folios
scp usuario@origen:/ruta/proyecto/{docker-compose.deploy.yml,.env.example} .
```

> `docker-compose.yml` (el del repo) usa `build: .` y sirve para **desarrollo**
> sobre el código. En el servidor se usa siempre `docker-compose.deploy.yml`.
> Ambos conviven bien: si prefieres un solo nombre, renómbralo a
> `docker-compose.yml` y omite el `-f` de todos los comandos.

## 3. Crear el `.env`

```bash
cd /opt/folios
cp .env.example .env
chmod 600 .env
```

Ejemplo completo y anotado (es el contenido de `.env.example`; las tres
líneas marcadas como `cambie-` son **obligatorias de reemplazar**):

```dotenv
FLASK_APP=run.py
# development = DEBUG local; el contenedor Docker fuerza production (docker-compose.yml)
FLASK_CONFIG=development
# Genere una real: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=cambie-estouniqueporunasecretkeyrealde32bytesominimo
DB_HOST=db
DB_PORT=3306
DB_NAME=folios_bioest
# Usuario de aplicación con privilegios SOLO sobre DB_NAME (no use root).
DB_USER=folios_app
DB_PASSWORD=cambie-esta-clave-de-base-de-datos
DB_ROOT_PASSWORD=cambie-esta-clave-de-root-solo-para-la-primera-vez

# --- Opcionales ---
# Detrás de reverse proxy con TLS: SESSION_COOKIE_SECURE=true y TRUST_PROXY=true
#SESSION_COOKIE_SECURE=true
#TRUST_PROXY=true
# Rate limit global por defecto (el endpoint /health va exento)
#RATELIMIT_DEFAULT=300 per hour
# Rate limits compartidos entre workers (compose lo inyecta solo en Docker)
#RATELIMIT_STORAGE_URI=redis://redis:6379

# --- Sincronización con Google Sheets ---
# Ruta al JSON de la cuenta de servicio (comparta la hoja con el client_email como editor)
#GOOGLE_SERVICE_ACCOUNT_JSON=/app/secrets/service_account.json
# ID de la hoja (trecho entre /d/ y /edit de la URL)
#GOOGLE_SHEET_ID=
# Pestaña de destino (se crea si no existe)
#GOOGLE_SHEET_WORKSHEET=folios
# Token para POST /sincronizacion/api/sincronizar (trigger externo); sin él la ruta queda 403
#SHEET_SYNC_TOKEN=

# --- Imagen a desplegar (opcional, para probar otra versión sin editar el compose) ---
#FOLIOS_IMAGE=soportedpss1/folios-gestion:1.1.0

# --- Zona horaria de las fechas mostradas en la UI ---
#TZ=America/Havana
```

Generar las claves en el servidor:

```bash
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
echo "DB_PASSWORD=$(python3 -c 'import secrets; token_urlsafe=secrets.token_urlsafe; print(token_urlsafe(24))')"
echo "DB_ROOT_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
```

Variables críticas:

| Variable | Notas |
|----------|-------|
| `SECRET_KEY` | sin ella (o con el valor de ejemplo) la app **no arranca** |
| `DB_HOST` | debe ser `db` (el nombre del servicio en compose) |
| `DB_ROOT_PASSWORD` | solo se usa en el **primer** arranque del volumen MariaDB |
| `TZ` | `America/Havana` por defecto vía compose; los timestamps se guardan en UTC y se muestran con `|localtime` |
| `SESSION_COOKIE_SECURE` / `TRUST_PROXY` | `true` solo detrás de TLS (ver §8) |

## 4. Preparar carpetas

```bash
cd /opt/folios
mkdir -p scans secrets backups
# Ownership 1000:1000: el contenedor corre como appuser (UID 1000).
# Si Docker crea scans/ como root, TODA subida de escaneos falla con "Error al guardar".
sudo chown -R 1000:1000 scans secrets
```

`secrets/` solo es necesario si usa la sincronización con Google Sheets
(allí va `service_account.json`).

## 5. Arrancar el stack

```bash
cd /opt/folios
docker compose -f docker-compose.deploy.yml pull
docker compose -f docker-compose.deploy.yml up -d
docker compose -f docker-compose.deploy.yml ps
```

Esperar a que `app` y `db` estén `healthy` y verificar:

```bash
curl -fs http://localhost:8089/health     # {"status": "ok"}
```

> El healthcheck **no toca la base**: `ok` significa que el proceso corre, no
> que la DB responda. La DB responde si `db` está `healthy` y los logs de
> `app` no muestran 500 en las primeras consultas.

Útiles:

```bash
docker compose -f docker-compose.deploy.yml logs -f app     # gunicorn
docker compose -f docker-compose.deploy.yml logs -f db      # MariaDB
docker compose -f docker-compose.deploy.yml --profile tools up -d phpmyadmin   # :8081
```

## 6. Inicializar la base

**Servidor nuevo (sin datos):**

```bash
cd /opt/folios
# 1) tablas + usuario admin con contraseña aleatoria (se imprime UNA vez)
docker compose -f docker-compose.deploy.yml exec app python init_db.py

# 2) esquema al HEAD de las migraciones
docker compose -f docker-compose.deploy.yml exec -e FLASK_APP=run.py app flask db upgrade
```

Guardar la contraseña de `admin` impresa por `init_db.py`. Si se pierde:

```bash
docker compose -f docker-compose.deploy.yml exec app python reset_password.py admin
```

**Base heredada de una instalación anterior (ya tiene datos):**

- Con `alembic_version` a una revisión conocida → solo `flask db upgrade`.
- Base **pre-migraciones** (sin tabla `alembic_version`) → una sola vez:
  `flask db stamp 0001_baseline` y después `flask db upgrade`
  (ver README → Migraciones; `0002_integrity` exige resolver duplicados con
  el SQL documentado antes de subir).

Comprobar el esquema:

```bash
docker compose -f docker-compose.deploy.yml exec -e FLASK_APP=run.py app flask db check
```

**Migrar datos desde otra instalación:** opción A — copia de la UI
(*Copias → Descargar*) y *Restaurar* en la nueva; opción B — dump SQL (§7).

## 7. Copias de seguridad

**Dump SQL completo** (esquema + datos + `alembic_version`), sin instalar nada
en el host:

```bash
cd /opt/folios
mkdir -p backups
docker compose -f docker-compose.deploy.yml exec -T db sh -c \
  'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
   exec mariadb-dump --single-transaction --quick --add-drop-table \
     --routines --triggers --hex-blob --default-character-set=utf8mb4 \
     -uroot "$MYSQL_DATABASE"' | gzip > "backups/db_$(date +%Y%m%d_%H%M%S).sql.gz"
```

**Restaurar:**

```bash
gunzip -c backups/db_XXXX.sql.gz | \
  docker compose -f docker-compose.deploy.yml exec -T db sh -c \
  'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mariadb -uroot "$MYSQL_DATABASE"'
docker compose -f docker-compose.deploy.yml exec -e FLASK_APP=run.py app flask db upgrade
```

El repo incluye `scripts/dump_db.sh` y `scripts/restore_db.sh` (mismas
operaciones con manejo de errores); si copia `scripts/` al servidor, dígales
qué compose usar:

```bash
COMPOSE_FILE=docker-compose.deploy.yml scripts/dump_db.sh backups
```

También está el respaldo JSON desde la UI (**Copias**), que además permite
restaurar *renombrando* tablas para previsualizar.

## 8. Reverse proxy con TLS

La app escucha en `:8089` HTTP. Detrás de nginx/Caddy con certificado,
activar en `.env`:

```dotenv
SESSION_COOKIE_SECURE=true
TRUST_PROXY=true
```

Sin `TRUST_PROXY=true` los rate limits y la IP real del cliente se leen mal;
con `SESSION_COOKIE_SECURE=true` sobre HTTP plano el navegador **descarta la
cookie** y el login no persiste — solo se activa con TLS real.

Ejemplo nginx mínimo:

```nginx
server {
    listen 443 ssl http2;
    server_name folios.ejemplo.cu;
    ssl_certificate     /etc/letsencrypt/live/folios.ejemplo.cu/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/folios.ejemplo.cu/privkey.pem;

    client_max_body_size 32m;   # subida de escaneos y respaldos

    location / {
        proxy_pass http://127.0.0.1:8089;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 130s;            # gunicorn timeout 120s
    }
}
```

Puerto en compose: cambiar `ports: "8089:8089"` por `"127.0.0.1:8089:8089"`
para que la app no sea visible desde Internet sin el proxy.

## 9. Actualizar a otra versión

```bash
cd /opt/folios
# opcional: fijar versión en .env → FOLIOS_IMAGE=soportedpss1/folios-gestion:1.1.0
docker compose -f docker-compose.deploy.yml pull
docker compose -f docker-compose.deploy.yml up -d
docker compose -f docker-compose.deploy.yml exec -e FLASK_APP=run.py app flask db upgrade
```

Antes de actualizar en producción: dump SQL (§7). Las migraciones son
adhierentes: una base nueva y una actualizada quedan en el mismo esquema.

## 10. Troubleshooting

| Síntoma | Causa y arreglo |
|---------|-----------------|
| `app` healthy pero cualquier consulta da 500 | credenciales de MariaDB rotadas en `.env` sin `ALTER USER`: el volumen conserva las viejas. Ver README → *Rotar credenciales de MariaDB* |
| Aborta al arrancar: `SECRET_KEY` | falta o es el valor de ejemplo en `.env` |
| Subida de escaneos: "Error al guardar" | `scans/` creada como root → `chown 1000:1000 scans` (§4) |
| Login no persiste tras el proxy | `SESSION_COOKIE_SECURE=true` sin TLS, o falta `TRUST_PROXY=true` (§8) |
| `Can't locate revision` en `flask db upgrade` | `alembic_version` trae una cadena ajena → fijar a `0001_baseline` (README → *DB con cadena de migraciones ajena*) |
| 400 en POST (CSRF) | cookie de sesión perdida o `SECRET_KEY` cambiado: relogin |
| `429 Too Many Requests` | rate limit global (`RATELIMIT_DEFAULT`, default `300 per hour`); subirlo en `.env` |
| Puerto 8089 ocupado | cambiar el lado host del `ports` en compose |
| phpMyAdmin no sube | es opcional y de perfil: `docker compose --profile tools up -d phpmyadmin` |

Checklist post-instalación:

- [ ] `curl -fs http://localhost:8089/health` → `{"status": "ok"}`
- [ ] Login con el usuario `admin` y contraseña de `init_db.py`
- [ ] Crear usuarios con rol `operador`/`lectura` (Usuarios o Permisos)
- [ ] `docker compose -f docker-compose.deploy.yml ps` → todos `healthy`
- [ ] Dump SQL de prueba en `backups/` restaurado en otro host
- [ ] Si hay proxy: login con `SESSION_COOKIE_SECURE=true` persiste
