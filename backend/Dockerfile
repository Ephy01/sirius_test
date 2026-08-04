# syntax=docker/dockerfile:1

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system sirius && adduser --system --ingroup sirius sirius

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && chown -R sirius:sirius /app

USER sirius

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/ready', timeout=2)" || exit 1

ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
CMD ["serve"]
