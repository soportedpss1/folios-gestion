#!/usr/bin/env bash
# Restaura un .sql o .sql.gz producido por scripts/dump_db.sh.
#
# ⚠ DESTRUCTIVO: reemplaza TODO el esquema y los datos de la base.
# Si la base tiene alembic_version, el dump la trae dentro: después de
# restaurar hay que correr las migraciones para llevar el esquema al HEAD:
#   FLASK_APP=run.py flask db upgrade
#
# Uso: scripts/restore_db.sh backups/db_20261006_120000.sql.gz
set -euo pipefail

cd "$(dirname "$0")/.."

archivo="${1:?Uso: scripts/restore_db.sh <archivo.sql[.gz]>}"
[ -f "$archivo" ] || { echo "No existe el archivo: $archivo" >&2; exit 1; }

echo "⚠ Esto REEMPLAZA todos los datos de la base con los de: $archivo"
echo "   Ctrl+C en 5 segundos para cancelar..."
sleep 5

# gzip si viene comprimido, texto plano si no.
if [[ "$archivo" == *.gz ]]; then
    dumper=(gzip -dc "$archivo")
else
    dumper=(cat "$archivo")
fi

docker compose exec -T db sh -c \
  'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
   exec mariadb -uroot --default-character-set=utf8mb4 "$MYSQL_DATABASE"' \
  < <("${dumper[@]}")

echo "Restauración completada."
echo "Si la base usaba alembic_version, ejecute ahora:"
echo "  FLASK_APP=run.py flask db upgrade"
