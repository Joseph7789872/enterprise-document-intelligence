# Deploying the Sales Assistant to Fly.io (Phase D)

This is the runbook for a hosted SaaS deploy: two Fly apps (backend API + frontend web),
managed Postgres, and S3-compatible object storage. It assumes the [`fly` CLI](https://fly.io/docs/flyctl/)
is installed and you've run `fly auth login`.

The Fly configs live in [`backend.fly.toml`](backend.fly.toml) and
[`frontend.fly.toml`](frontend.fly.toml). They reuse the existing `backend/Dockerfile` and
`frontend/Dockerfile`. **No secrets live in the toml** — set them with `fly secrets set`.

> Pick your own app names and replace `sales-assistant-api` / `sales-assistant-web`
> throughout (including inside the two toml files).

## 1. Create the apps

```bash
fly apps create sales-assistant-api
fly apps create sales-assistant-web
```

## 2. Provision Postgres and attach it to the backend

```bash
fly postgres create --name sales-assistant-db --region iad
# Attaching sets DATABASE_URL on the backend app automatically:
fly postgres attach sales-assistant-db -a sales-assistant-api
```

Fly's `DATABASE_URL` uses the `postgres://` scheme. The app expects an async driver, so
override it to asyncpg (Alembic derives the sync URL from this automatically):

```bash
# Take the host/db/credentials Fly printed and set the async form:
fly secrets set -a sales-assistant-api \
  DATABASE_URL="postgresql+asyncpg://<user>:<pass>@<host>:5432/<db>"
```

## 3. Object storage (documents)

Fly machine disks are ephemeral, so document bytes must live in S3-compatible storage.
Fly Tigris is the easiest:

```bash
fly storage create   # provisions a Tigris bucket + sets AWS_* / bucket env on the app
```

Then point the app's storage at it:

```bash
fly secrets set -a sales-assistant-api \
  STORAGE_BACKEND=s3 \
  S3_BUCKET=<bucket> S3_ENDPOINT_URL=<tigris-endpoint> \
  S3_ACCESS_KEY=<key> S3_SECRET_KEY=<secret> S3_REGION=auto
```

## 4. Backend secrets

```bash
# Generate strong secrets locally first:
#   python -c "import secrets; print(secrets.token_urlsafe(64))"           # JWT_SECRET_KEY
#   python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"  # MASTER_KEK

fly secrets set -a sales-assistant-api \
  JWT_SECRET_KEY="<64-char-secret>" \
  MASTER_KEK="<base64-32-byte-key>" \
  OPENAI_API_KEY="<openai-key>" \
  LLM_API_KEY="<openai-key>" \
  FRONTEND_BASE_URL="https://sales-assistant-web.fly.dev" \
  CORS_ALLOW_ORIGINS="https://sales-assistant-web.fly.dev"

# SMTP (any relay — SES/Mailgun/Postmark/etc.):
fly secrets set -a sales-assistant-api \
  SMTP_HOST="<host>" SMTP_PORT="587" SMTP_USERNAME="<user>" SMTP_PASSWORD="<pass>" \
  SMTP_FROM="Sales Assistant <noreply@yourdomain.com>"

# Stripe (only if ENABLE_BILLING=true). The webhook secret is filled in at step 7.
fly secrets set -a sales-assistant-api \
  STRIPE_API_KEY="<sk_live_or_test>" \
  STRIPE_PRICE_PRO="<price_id>" STRIPE_PRICE_BUSINESS="<price_id>"
```

The backend **fails fast on boot** if `ENVIRONMENT=production` and any required secret is
weak/missing (see `app/core/config.py`), so a misconfigured deploy never serves traffic.

## 5. Deploy the backend

```bash
cd backend
fly deploy -c ../deploy/fly/backend.fly.toml
```

The `[deploy] release_command = "alembic upgrade head"` runs migrations before the new
machines take traffic. Verify: `curl https://sales-assistant-api.fly.dev/health`.

## 6. Deploy the frontend

```bash
fly secrets set -a sales-assistant-web \
  BACKEND_API_URL="https://sales-assistant-api.fly.dev"

cd frontend
fly deploy -c ../deploy/fly/frontend.fly.toml
```

The frontend reads `BACKEND_API_URL` at **runtime** (via `/api/runtime-config`), so you can
re-point it at a different backend with `fly secrets set` + a restart — no rebuild.

## 7. Stripe webhook (if billing is on)

In the Stripe dashboard, add a webhook endpoint:

```
https://sales-assistant-api.fly.dev/billing/webhook
```

Subscribe to `checkout.session.completed`, `customer.subscription.updated`, and
`customer.subscription.deleted`. Copy the signing secret and set it:

```bash
fly secrets set -a sales-assistant-api STRIPE_WEBHOOK_SECRET="whsec_..."
```

## Notes & caveats

- **Background ingestion** runs in-process (FastAPI `BackgroundTasks`). The backend config
  keeps one machine always on (`auto_stop_machines = false`, `min_machines_running = 1`) so
  uploads aren't dropped mid-ingest. Moving ingestion to Celery + Redis (Fly Redis/Upstash)
  is the scaling follow-up.
- **Backups**: enable scheduled snapshots on the Fly Postgres volume
  (`fly volumes snapshots ...`) or use Fly's managed Postgres backups.
- **Monitoring**: `fly logs -a sales-assistant-api` for live logs; set `LOG_FORMAT=json` for
  a log shipper. `/health` is the liveness check.
- **Turning billing off**: set `ENABLE_BILLING=false` — plan-limit enforcement becomes a
  no-op and the `/billing` routes are unmounted. Signup still works (tenants just start on
  the trial plan, unenforced).
