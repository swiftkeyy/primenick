#!/usr/bin/env sh
set -eu

ROLE="${SERVICE_ROLE:-web}"
export PYTHONUNBUFFERED=1
export PYTHONPATH="${PYTHONPATH:-/srv/app}"

echo "[prime-nick] starting role=${ROLE} port=${PORT:-8080}"

run_migrations() {
  if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "[prime-nick] running alembic migrations"
    alembic upgrade head
  fi
}

case "$ROLE" in
  web)
    run_migrations
    exec python -m app.bot.main
    ;;
  worker|worker-default)
    exec celery -A app.core.celery_app.celery_app worker \
      -Q default,availability,payments,analytics \
      --loglevel="${CELERY_LOG_LEVEL:-INFO}" \
      --concurrency="${CELERY_CONCURRENCY:-4}" \
      --prefetch-multiplier=1 \
      --max-tasks-per-child=1000
    ;;
  worker-priority|priority)
    exec celery -A app.core.celery_app.celery_app worker \
      -Q priority,ai_generation \
      --loglevel="${CELERY_LOG_LEVEL:-INFO}" \
      --concurrency="${CELERY_CONCURRENCY:-8}" \
      --prefetch-multiplier=1 \
      --max-tasks-per-child=750
    ;;
  scheduler|beat)
    exec celery -A app.core.celery_app.celery_app beat --loglevel="${CELERY_LOG_LEVEL:-INFO}"
    ;;
  all)
    run_migrations
    celery -A app.core.celery_app.celery_app worker -Q default,availability,payments,analytics --loglevel="${CELERY_LOG_LEVEL:-INFO}" --concurrency="${CELERY_CONCURRENCY_DEFAULT:-2}" --prefetch-multiplier=1 --max-tasks-per-child=1000 &
    celery -A app.core.celery_app.celery_app worker -Q priority,ai_generation --loglevel="${CELERY_LOG_LEVEL:-INFO}" --concurrency="${CELERY_CONCURRENCY_PRIORITY:-2}" --prefetch-multiplier=1 --max-tasks-per-child=750 &
    celery -A app.core.celery_app.celery_app beat --loglevel="${CELERY_LOG_LEVEL:-INFO}" &
    exec python -m app.bot.main
    ;;
  *)
    echo "Unknown SERVICE_ROLE=${ROLE}. Valid: web, worker-default, worker-priority, scheduler, all" >&2
    exit 64
    ;;
esac
