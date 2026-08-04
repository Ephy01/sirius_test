#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
REVISION_FILE="$PROJECT_ROOT/.deploy-previous-revision"

cd "$PROJECT_ROOT"

if [ -n "$(git status --porcelain)" ]; then
  echo "На сервере есть несохранённые изменения. Откат остановлен." >&2
  exit 1
fi

TARGET_REVISION=${1:-}
if [ -z "$TARGET_REVISION" ] && [ -f "$REVISION_FILE" ]; then
  TARGET_REVISION=$(sed -n '1p' "$REVISION_FILE")
fi
if [ -z "$TARGET_REVISION" ]; then
  echo "Укажите commit или tag: ./deploy/rollback.sh <revision>" >&2
  exit 1
fi

git cat-file -e "$TARGET_REVISION^{commit}"
"$SCRIPT_DIR/backup.sh" --if-running
git switch --detach "$TARGET_REVISION"
SKIP_BACKUP=1 "$SCRIPT_DIR/deploy.sh"

echo "Код временно запущен с revision $TARGET_REVISION в detached HEAD."
echo "Откат кода не отменяет уже применённые миграции базы."
