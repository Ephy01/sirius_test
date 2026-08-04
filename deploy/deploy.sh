#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
ENV_FILE=${ENV_FILE:-"$PROJECT_ROOT/.env.production"}
APP_VERSION=${APP_VERSION:-$(git -C "$PROJECT_ROOT" rev-parse --short=12 HEAD 2>/dev/null || echo local)}
export APP_VERSION

if [ ! -f "$ENV_FILE" ]; then
  echo "Не найден $ENV_FILE. Сначала выполните ./deploy/init-env.sh." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker не установлен." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Не установлен Docker Compose plugin." >&2
  exit 1
fi

compose() {
  docker compose --env-file "$ENV_FILE" -f "$PROJECT_ROOT/compose.yml" "$@"
}

compose config --quiet

env_value() {
  sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1
}

case "$(env_value AI_ENABLED | tr '[:upper:]' '[:lower:]')" in
  true|1|yes)
    for required_name in YANDEX_AI_API_KEY YANDEX_AI_FOLDER_ID YANDEX_AI_MODEL_URI; do
      if [ -z "$(env_value "$required_name")" ]; then
        echo "AI_ENABLED=true, но $required_name не заполнен." >&2
        exit 1
      fi
    done
    ;;
esac

if [ "${SKIP_BACKUP:-0}" != "1" ]; then
  "$SCRIPT_DIR/backup.sh" --if-running
fi

compose build --pull
compose up -d --remove-orphans --wait --wait-timeout 180
compose ps

echo "Sirius Gate запущен. Проверка API: /api/v1/ready"
