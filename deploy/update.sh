#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

cd "$PROJECT_ROOT"

if [ -n "$(git status --porcelain)" ]; then
  echo "На сервере есть несохранённые изменения. Обновление остановлено." >&2
  exit 1
fi

BRANCH=${DEPLOY_BRANCH:-$(git branch --show-current)}
if [ -z "$BRANCH" ]; then
  echo "Не удалось определить deployment-ветку." >&2
  exit 1
fi

PREVIOUS_REVISION=$(git rev-parse HEAD)
"$SCRIPT_DIR/backup.sh" --if-running
git fetch --prune origin "$BRANCH"
git pull --ff-only origin "$BRANCH"
printf '%s\n' "$PREVIOUS_REVISION" > "$PROJECT_ROOT/.deploy-previous-revision"

if ! SKIP_BACKUP=1 "$SCRIPT_DIR/deploy.sh"; then
  echo "Deployment завершился ошибкой." >&2
  echo "Предыдущая версия: $PREVIOUS_REVISION" >&2
  echo "Для отката выполните ./deploy/rollback.sh" >&2
  exit 1
fi
