# Sirius Gate API

Серверная часть платформы: FastAPI, SQLAlchemy, Alembic. Общее описание проекта
находится в [корневом README](../README.md), подробности — в
[docs/DOCUMENTATION.md](../docs/DOCUMENTATION.md).

## Запуск

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test,dev]'
cp .env.example .env
.venv/bin/uvicorn app.main:app --reload --port 8001
```

По умолчанию используется `sqlite:///./sirius_gate.db`, схема создаётся при
старте. Для PostgreSQL задайте
`DATABASE_URL=postgresql+psycopg://user:password@host/database` и примените
миграции командой `.venv/bin/python -m alembic -c alembic.ini upgrade head`.

## Проверки

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m pytest
.venv/bin/python -m alembic -c alembic.ini check
```

## Модули

| Модуль | Ответственность |
|---|---|
| `app/main.py` | фабрика приложения |
| `app/api/` | маршруты: `health`, `access`, `contests`, `enrollments`, `participant`, `tasks`, `assistant`, `catalog`, `sandbox` |
| `app/access_codes.py` | персональные коды |
| `app/attempts.py` | попытки, их истечение и seed |
| `app/contest_config.py` | чтение и проверка `task_config` |
| `app/routing.py` | выбор следующего семейства и сложности, seed задачи |
| `app/task_flow.py` | создание, оценка и закрытие задачи |
| `app/events.py` | журнал событий |
| `app/telemetry.py` | текстовый экспорт журнала |
| `app/tasks/` | семейства задач, реестр, director, загрузка модулей задач |
| `sirius_gate/` | интерфейс платформы для авторов модулей и проверка модулей |
| `app/ai/` | ассистент |
| `app/models.py`, `app/schemas.py` | таблицы и схемы API |
| `app/security.py`, `app/dependencies.py` | коды, токены и авторизация |

## Новое семейство задач

1. Создать модуль в `app/tasks/` с генератором, evaluator-ом и записью
   `FAMILY = TaskFamily(...)`.
2. Добавить модуль в `FAMILY_MODULES` в `app/tasks/registry.py`.
3. Написать тесты: детерминизм, проверка эталона, отсутствие скрытых данных в
   `public_state`.

Контракт описан в `app/tasks/family.py`, порядок действий на клиенте — в
разделе 23 документации.

Семейство можно подключить и без правки платформы, как модуль в папке
`TASK_MODULES_DIR`. Модуль проверяется командой
`.venv/bin/python -m sirius_gate.check <папка модулей>`. Подробности в
разделе 23.7 документации.
