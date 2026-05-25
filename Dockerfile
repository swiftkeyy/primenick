# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/srv/app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates libpq-dev && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /srv/app
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts
RUN chmod +x /srv/app/scripts/*.sh /srv/app/scripts/*.py && \
    addgroup --system app && adduser --system --ingroup app --home /srv/app app && \
    chown -R app:app /srv/app
USER app
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import os, urllib.request; p=os.environ.get('PORT','8080'); urllib.request.urlopen('http://127.0.0.1:%s/healthz' % p, timeout=3).read()"
CMD ["./scripts/railway_entrypoint.sh"]
