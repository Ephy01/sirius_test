# Развёртывание Sirius Gate на AdminVPS

Production-стек состоит из трёх контейнеров:

- `web` — Caddy, HTTPS, React SPA и reverse proxy для `/api/*`;
- `api` — FastAPI, автоматическое применение Alembic-миграций;
- `db` — PostgreSQL 17 с постоянным Docker volume.

Наружу публикуются только порты `80` и `443`. API и PostgreSQL доступны
только внутри Docker-сетей. Данные базы, сертификаты Caddy и конфигурация
TLS не удаляются при пересборке контейнеров.

## 1. Подготовить VPS

Подойдёт Ubuntu или Debian с установленными Docker Engine и Docker Compose
plugin. В панели провайдера и системном firewall должны быть открыты:

- `22/tcp` — SSH;
- `80/tcp` — HTTP и выпуск сертификата;
- `443/tcp`, `443/udp` — HTTPS и HTTP/3.

Для домена создайте DNS `A`-запись, указывающую на IPv4-адрес VPS. Если есть
IPv6, добавьте соответствующую `AAAA`-запись.

## 2. Клонировать deployment-ветку

```bash
sudo mkdir -p /opt/sirius-gate
sudo chown "$USER":"$USER" /opt/sirius-gate
git clone --branch feature/content-v3 \
  https://github.com/Ephy01/sirius_test.git /opt/sirius-gate
cd /opt/sirius-gate
```

Для приватного репозитория используйте отдельный read-only deploy key, а не
личный пароль или API-токен в командной строке. После добавления публичной
части deploy key в GitHub используйте SSH URL:

```bash
git clone --branch feature/content-v3 \
  git@github.com:Ephy01/sirius_test.git /opt/sirius-gate
```

## 3. Создать production-конфигурацию

```bash
./deploy/init-env.sh
nano .env.production
```

Сценарий автоматически создаёт уникальные секреты и выводит код организатора.
Сохраните этот код отдельно. Файл получает права `600` и игнорируется Git.

Минимально проверьте:

```dotenv
SITE_ADDRESS=gate.example.ru
AI_ENABLED=true
YANDEX_AI_API_KEY=...
YANDEX_AI_FOLDER_ID=...
YANDEX_AI_MODEL_URI=gpt://<folder_id>/aliceai-llm
```

Если домена пока нет, оставьте `SITE_ADDRESS=:80` и откройте приложение по IP
через HTTP. После появления DNS замените значение на домен и снова запустите
deployment-сценарий — Caddy автоматически получит сертификат.

Режим `:80` допустим только для технической проверки. Не выдавайте реальные
коды школьникам и не включайте Alice AI до перехода на домен с HTTPS.

## 4. Первый запуск

```bash
./deploy/deploy.sh
```

Сценарий:

1. проверяет production-конфигурацию;
2. собирает свежие образы;
3. запускает PostgreSQL;
4. применяет миграции;
5. запускает API и дожидается readiness-проверки базы;
6. запускает frontend и выводит состояние сервисов.

Проверка:

```bash
curl -f https://gate.example.ru/api/v1/ready
docker compose --env-file .env.production ps
```

Ожидаемый ответ API:

```json
{"status":"ok","service":"Sirius Gate API"}
```

## Обновление

После того как изменения отправлены в ту же Git-ветку:

```bash
cd /opt/sirius-gate
./deploy/update.sh
```

Перед `git pull` сценарий сохраняет PostgreSQL dump, затем получает только
fast-forward изменения, пересобирает образы и пересоздаёт изменившиеся
контейнеры. `docker compose down` не выполняется.

Если на VPS случайно изменены файлы репозитория, обновление остановится. Не
исправляйте production-код прямо на сервере: внесите изменение локально,
проверьте и отправьте в Git.

## Резервные копии

Создать копию вручную:

```bash
./deploy/backup.sh
```

Файлы сохраняются в `backups/` в custom-формате `pg_dump`. Автоматически
удаляются локальные копии старше 14 дней. Для защиты от потери VPS копируйте
каталог во внешнее хранилище или подключите backup-сервис провайдера.

Отдельно сохраните зашифрованную копию `.env.production` в менеджере секретов
или защищённом backup-хранилище. Без `CODE_HMAC_SECRET` восстановленная база не
сможет проверять ранее выданные коды участников; замена `SECURITY_SECRET`
завершит все существующие сессии.

Dump сначала записывается во временный файл, проверяется через `pg_restore`,
и только после успешной проверки атомарно получает окончательное имя.

Восстановление перезаписывает production-данные, поэтому его следует выполнять
только после остановки API и проверки выбранного dump-файла.

## Откат кода

`update.sh` запоминает commit, который работал до обновления. Если новый
deployment не прошёл health checks:

```bash
./deploy/rollback.sh
```

Можно явно указать проверенный commit или tag:

```bash
./deploy/rollback.sh pilot-v1
```

Rollback переключает рабочую копию в detached HEAD и повторно разворачивает
контейнеры. Он не отменяет миграции базы. Перед миграциями, удаляющими или
преобразующими данные, нужен отдельный совместимый план отката и проверенный
backup.

После устранения причины сбоя вернитесь на deployment-ветку:

```bash
git switch feature/content-v3
./deploy/update.sh
```

## Диагностика

```bash
docker compose --env-file .env.production ps
docker compose --env-file .env.production logs --tail=200 api
docker compose --env-file .env.production logs --tail=200 web
docker compose --env-file .env.production logs --tail=200 db
```

Следить за API в реальном времени:

```bash
docker compose --env-file .env.production logs -f api
```

## Важные запреты

- Не добавляйте `.env.production` в Git.
- Не передавайте ключ Alice AI во frontend-переменной `VITE_*`.
- Не публикуйте порт PostgreSQL `5432` наружу.
- Не выполняйте `docker compose down -v`: флаг `-v` удалит production volumes.
- Не удаляйте `backups/`, пока внешний backup не подтверждён.
