# PRIME NICK SaaS — production Telegram username engine

## Brand
Bot name: **PRIME NICK**

## Payment provider
Provider: **Robokassa**.

Required Robokassa cabinet settings:

```text
ResultURL:  https://bot.example.com/payments/robokassa/result
SuccessURL: https://bot.example.com/payments/robokassa/success
FailURL:    https://bot.example.com/payments/robokassa/fail
Method:     POST preferred; GET also accepted
Algorithm:  match ROBOKASSA_HASH_ALGORITHM, default sha256
Encoding:   utf-8
```

## Architecture

```text
Internet
  -> Cloudflare / DDoS-Guard / WAF / Turnstile edge challenge for web flows
  -> NGINX edge: TLS, HSTS, CSP, per-IP and endpoint rate limits, webhook secret gate
  -> aiogram webhook app (aiohttp): security middleware, adaptive Redis limits, abuse engine
  -> PostgreSQL: users, reservations, payments, audit, abuse, quotas
  -> Redis: token buckets, sliding windows, dedupe, queues, circuit-breaker state
  -> Celery workers:
       priority queue: VIP generation / priority availability
       availability queue: Telegram/Pyrogram and compliant HTTP profile checks
       payments queue: reconciliation and callbacks
       analytics queue: quota refill, security telemetry
  -> Prometheus/Grafana: metrics, alert-ready dashboards, JSON logs for Loki/ELK
```

## Security posture
- Webhook-only aiogram; polling disabled.
- Telegram webhook header verification before update parsing.
- Redis Lua token-bucket + sliding-window rate limits: global, per IP, per Telegram ID, per endpoint.
- Adaptive throttling based on user abuse score; VIP gets higher concurrency only while risk score is low.
- Abuse event ledger with auto-cooldown, auto-ban by Telegram ID/IP/fingerprint/subnet.
- Race-safe reservations via PostgreSQL row locks and unique constraints.
- Robokassa ResultURL signature verification with Password #2.
- Robokassa SuccessURL signature verification with Password #1; fulfillment never happens on SuccessURL.
- Replay protection via `payment_webhook_events(provider,event_id)` + payload hash audit.
- No VIP discounts. VIP is quota, premium modes, priority queues, longer reservation TTL.

## Production start
```bash
cp .env.example .env
# Fill real secrets. Use 32-64 byte random values.
openssl rand -base64 48
./scripts/deploy.sh
```

## Required edge controls
- Cloudflare: orange-cloud origin, Bot Fight Mode/Super Bot Fight, WAF managed rules, rate limit `/telegram/webhook` and `/payments/robokassa/*`, origin TLS strict.
- Telegram webhook: set by app with `X-Telegram-Bot-Api-Secret-Token`.
- Robokassa: configure ResultURL/SuccessURL/FailURL exactly as above; only ResultURL fulfills orders.
- fail2ban: install filters from `infra/fail2ban` on the host receiving NGINX logs.

## Ubuntu hardening baseline
```bash
apt update && apt -y upgrade
apt -y install ufw fail2ban unattended-upgrades docker.io docker-compose-plugin
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
sysctl -w net.ipv4.tcp_syncookies=1 net.core.somaxconn=65535 net.ipv4.ip_local_port_range="1024 65000"
```

## Backups
```bash
./scripts/backup_postgres.sh
# Ship backups off-host to S3-compatible object storage with immutable retention.
```

## Compliance note
Availability clients are bounded, queued, circuit-broken and rate-limited. External HTTP checks identify as PrimeNickAvailabilityBot and must be operated according to platform terms and legal constraints.

## Railway deployment

### Recommended Railway topology

Create one Railway project with PostgreSQL and Redis plugins, then create services from the same GitHub repo:

```text
prime-nick-web
  SERVICE_ROLE=web
  exposes HTTP
  healthcheck: /healthz
  runs migrations

prime-nick-worker-default
  SERVICE_ROLE=worker-default
  no public domain
  disable HTTP healthcheck in Railway service settings

prime-nick-worker-priority
  SERVICE_ROLE=worker-priority
  no public domain
  disable HTTP healthcheck in Railway service settings

prime-nick-scheduler
  SERVICE_ROLE=scheduler
  no public domain
  one replica only
  disable HTTP healthcheck in Railway service settings
```

For a quick single-service starter deploy, set:

```text
SERVICE_ROLE=all
```

This runs web + workers + beat in one container. Use it only for bootstrap/small load; production should split roles.

### Railway variables

Use `.env.railway.example` as the source of truth. Railway PostgreSQL/Redis usually inject:

```text
DATABASE_URL
REDIS_URL
```

The app automatically converts Railway `postgresql://` / `postgres://` URLs to SQLAlchemy async `postgresql+asyncpg://` and derives Celery broker/result DBs from Redis.

Minimum variables for every service:

```text
APP_ENV=production
APP_NAME=PRIME NICK
APP_BASE_URL=https://your-public-railway-domain.up.railway.app
BOT_TOKEN=...
BOT_WEBHOOK_SECRET=...
INTERNAL_HMAC_SECRET=...
JWT_SECRET_2026_05=...
ROBOKASSA_MERCHANT_LOGIN=...
ROBOKASSA_PASSWORD1=...
ROBOKASSA_PASSWORD2=...
ROBOKASSA_HASH_ALGORITHM=sha256
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
TRUSTED_PROXIES=127.0.0.1/32,10.0.0.0/8,172.16.0.0/12,100.64.0.0/10,fc00::/7
```

Generate secrets:

```bash
openssl rand -base64 48
```

### Railway deploy sequence

1. Push repository to GitHub.
2. Railway → New Project → Deploy from GitHub repo.
3. Add PostgreSQL plugin.
4. Add Redis plugin.
5. Set variables from `.env.railway.example`.
6. First deploy `prime-nick-web` with `SERVICE_ROLE=web`.
7. Open Railway generated public domain.
8. Set `APP_BASE_URL` to that exact HTTPS domain or attach a custom domain.
9. Redeploy web service so Telegram webhook is registered with the final URL.
10. Add worker services from the same repo and set their `SERVICE_ROLE` values.

### Robokassa URLs for Railway

After Railway domain is known, configure Robokassa:

```text
ResultURL:  https://your-domain/payments/robokassa/result
SuccessURL: https://your-domain/payments/robokassa/success
FailURL:    https://your-domain/payments/robokassa/fail
Method:     POST preferred
Encoding:   utf-8
Algorithm:  sha256
```

### Railway operational notes

- Web service must keep healthcheck `/healthz`.
- Worker and scheduler services must not use HTTP healthcheck unless you add sidecar health endpoints.
- Scheduler must run as exactly one replica to avoid duplicate monthly quota refills and reservation expiry ticks.
- Scale `worker-priority` independently for VIP fast lane.
- Keep Railway public domain only on the web service; workers remain private.
