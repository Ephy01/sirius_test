#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
ENV_FILE=${ENV_FILE:-"$PROJECT_ROOT/.env.production"}
BACKUP_DIR=${BACKUP_DIR:-"$PROJECT_ROOT/backups"}
MODE=${1:-required}

if [ ! -f "$ENV_FILE" ]; then
  echo "Не найден $ENV_FILE." >&2
  exit 1
fi

compose() {
  docker compose --env-file "$ENV_FILE" -f "$PROJECT_ROOT/compose.yml" "$@"
}

if ! compose ps --status running --services | grep -qx db; then
  if [ "$MODE" = "--if-running" ]; then
    echo "PostgreSQL ещё не запущен; резервная копия не требуется."
    exit 0
  fi
  echo "Контейнер PostgreSQL не запущен." >&2
  exit 1
fi

umask 077
mkdir -p "$BACKUP_DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_FILE="$BACKUP_DIR/sirius_gate_$STAMP.dump"
TEMP_FILE="$BACKUP_FILE.tmp"
trap 'rm -f "$TEMP_FILE"' EXIT HUP INT TERM

compose exec -T db sh -ec \
  'pg_dump --format=custom --no-owner --no-acl -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > "$TEMP_FILE"

if [ ! -s "$TEMP_FILE" ]; then
  echo "PostgreSQL вернул пустую резервную копию." >&2
  exit 1
fi

if ! compose exec -T db pg_restore --list < "$TEMP_FILE" >/dev/null; then
  echo "Проверка резервной копии завершилась ошибкой." >&2
  exit 1
fi

mv "$TEMP_FILE" "$BACKUP_FILE"
trap - EXIT HUP INT TERM
find "$BACKUP_DIR" -type f -name 'sirius_gate_*.dump' -mtime +14 -delete
echo "Резервная копия: $BACKUP_FILE"
