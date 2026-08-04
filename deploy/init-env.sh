#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
ENV_FILE=${ENV_FILE:-"$PROJECT_ROOT/.env.production"}
EXAMPLE_FILE="$PROJECT_ROOT/.env.production.example"

if [ -e "$ENV_FILE" ]; then
  echo "Файл $ENV_FILE уже существует; оставляю его без изменений." >&2
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "Для генерации секретов необходим openssl." >&2
  exit 1
fi

umask 077
cp "$EXAMPLE_FILE" "$ENV_FILE"

DB_PASSWORD=$(openssl rand -hex 24)
SECURITY_SECRET=$(openssl rand -hex 32)
CODE_HMAC_SECRET=$(openssl rand -hex 32)
ORGANIZER_CODE="ADMIN-$(openssl rand -hex 8 | tr '[:lower:]' '[:upper:]')"

sed -i.bak \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$DB_PASSWORD|" \
  -e "s|^ORGANIZER_CODE=.*|ORGANIZER_CODE=$ORGANIZER_CODE|" \
  -e "s|^SECURITY_SECRET=.*|SECURITY_SECRET=$SECURITY_SECRET|" \
  -e "s|^CODE_HMAC_SECRET=.*|CODE_HMAC_SECRET=$CODE_HMAC_SECRET|" \
  "$ENV_FILE"
rm -f "$ENV_FILE.bak"
chmod 600 "$ENV_FILE"

echo "Создан $ENV_FILE с правами 600."
echo "Код организатора: $ORGANIZER_CODE"
echo "Сохраните код и укажите SITE_ADDRESS и параметры Alice AI перед запуском."
