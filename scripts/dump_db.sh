#!/usr/bin/env bash
# Copia de la base completa (esquema + datos + alembic_version) en gzip.
#
# Corre mariadb-dump DENTRO del contenedor db: ni la app ni el host necesitan
# el cliente de MariaDB. Uso:
#   scripts/dump_db.sh [directorio_destino]   # default: backups/
set -euo pipefail

cd "$(dirname "$0")/.."

DESTINO="${1:-backups}"
mkdir -p "$DESTINO"
archivo="$DESTINO/db_$(date +%Y%m%d_%H%M%S).sql.gz"

# root porque el usuario de la app (folios_app) no tiene LOCK TABLES / SHOW VIEW.
# La contraseña viaja por MYSQL_PWD (env del contenedor), nunca en argv.
# --hex-blob: marca_config.logo/favicon son BLOB; sin esto se vuelven ilegibles.
# Sin --databases: el dump no incluye CREATE DATABASE, así que se puede
# restaurar en otro esquema (útil para probar).
docker compose exec -T db sh -c \
  'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
   exec mariadb-dump --single-transaction --quick --add-drop-table \
     --routines --triggers --hex-blob --default-character-set=utf8mb4 \
     -uroot "$MYSQL_DATABASE"' | gzip > "$archivo"

echo "Respaldo: $archivo ($(du -h "$archivo" | cut -f1))"
echo "Si la base tiene alembic_version, viaja dentro del dump: tras restaurar,"
echo "ejecute 'FLASK_APP=run.py flask db upgrade' para llevar el esquema al HEAD."
