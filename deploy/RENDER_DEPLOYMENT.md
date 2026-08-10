# Deploying to Render

This file is a deployment reference, not a secrets store — the generated secrets below are for
you to copy into Render's dashboard as environment variables. **Do not commit real secret values
to git; this file should stay out of version control** (see the note at the bottom).

## Generated production secrets (copy these into Render, do not reuse dev defaults)

```
JWT_SECRET=kZTJJVkKU3Fj_0-_TjdiDHT2ts9uYxz9xIqVBm0eWN4
SECRET_ENCRYPTION_KEY=SeuGxf7YQHvuGTInjRKliP6HW5_VqF2Qwcx6lU3D3RI
ADMIN_API_KEY=admin_RIwk42b24Or5Z8T-sUn7QNdVWaTt42Jh
VIEWER_API_KEY=viewer_D0hbbcJSvHbROXa7aDjW5z07yOyQBOtP
```

These were generated with cryptographically random values (32 bytes, base64url). Rotate them if
they are ever exposed (e.g. pasted somewhere public).

## Services to create on Render

| Render service | Type | Source | Command |
|---|---|---|---|
| `eparking-api` | Web Service | `services/api/Dockerfile` | (Dockerfile CMD) |
| `eparking-worker` | Background Worker | `services/ingestion/Dockerfile` | `celery -A app.celery_app worker --loglevel=INFO` |
| `eparking-beat` | Background Worker | `services/ingestion/Dockerfile` | `celery -A app.celery_app beat --loglevel=INFO` |
| `eparking-frontend` | Web Service | `frontend/` (Node/Next.js) | `npm run build` / `npm run start` |
| `eparking-redis` | Key Value (Redis) | Render-managed | — |
| — Postgres — | **Not on Render** | Existing AWS RDS instance | — |

## Environment variables — every service needs `APP_ENV=production`

Setting `APP_ENV=production` activates the app's production validator, which will refuse to
start if any of these are still dev defaults. This is intentional — treat a failed startup as
"a real default was missed," not a bug to work around.

### `eparking-api`, `eparking-worker`, `eparking-beat` (shared config)

```
APP_ENV=production

POSTGRES_HOST=reporting-postgres-db.cdy6aa84iwdx.af-south-1.rds.amazonaws.com
POSTGRES_PORT=5432
POSTGRES_DB=eparking
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<real value from local .env>

REDIS_HOST=<from Render's Redis service — Render provides an internal connection string>
REDIS_PORT=<from Render Redis>
REDIS_DB=0
REDIS_PASSWORD=<from Render Redis, if set>

PAYSTACK_SECRET_KEY=<real live key from local .env>

JWT_SECRET=kZTJJVkKU3Fj_0-_TjdiDHT2ts9uYxz9xIqVBm0eWN4
SECRET_ENCRYPTION_KEY=SeuGxf7YQHvuGTInjRKliP6HW5_VqF2Qwcx6lU3D3RI
JWT_ALGORITHM=HS256
JWT_EXPIRY_MINUTES=60

ADMIN_API_KEY=admin_RIwk42b24Or5Z8T-sUn7QNdVWaTt42Jh
VIEWER_API_KEY=viewer_D0hbbcJSvHbROXa7aDjW5z07yOyQBOtP

SESSION_COOKIE_SECURE=true
CORS_ORIGINS=https://<your-real-frontend-domain>.onrender.com
```

### `eparking-api` additionally needs

```
API_HOST=0.0.0.0
API_PORT=10000        # Render's default web service port — check the actual assigned port
```

### `eparking-frontend`

```
API_BASE_URL=https://<your-real-api-domain>.onrender.com
NEXT_PUBLIC_API_BASE_URL=https://<your-real-api-domain>.onrender.com
APP_ORIGIN=https://<your-real-frontend-domain>.onrender.com
ADMIN_API_KEY=admin_RIwk42b24Or5Z8T-sUn7QNdVWaTt42Jh
VIEWER_API_KEY=viewer_D0hbbcJSvHbROXa7aDjW5z07yOyQBOtP
```

`ADMIN_API_KEY`/`VIEWER_API_KEY` must be **identical** on the frontend and the API — they're the
same shared secret, just needed in two places (frontend attaches it, backend validates it).

## Before deploying: AWS RDS network access

Render's outbound traffic comes from a set of static IPs (visible in Render's dashboard once a
service is created, under that service's "Connect" tab). Your RDS security group must allow
inbound Postgres (port 5432) from those IPs — the same kind of security-group edit you already
did once this session to let this local environment reach RDS. Do this **before** the first
deploy attempt, or the `migrate` step will fail with a connection-refused error identical to what
we saw earlier.

## Migrations on Render

There's no separate `migrate` service concept on Render the way docker-compose has one. Options:
1. **Render "Pre-Deploy Command"** on `eparking-api` — run `python -m app.migrate` before each
   deploy goes live. Cleanest, matches the existing idempotent-migration design.
2. A manual one-off Render Job, run once before first deploy and again after any migration
   changes.

Recommend option 1 — the migration runner is already idempotent (safe to run every deploy).

## First deploy checklist

1. [ ] RDS security group allows Render's outbound IPs.
2. [ ] Render Redis service created; note its internal connection details.
3. [ ] All four services created, env vars set per above, `APP_ENV=production` on all backend
       services.
4. [ ] Pre-deploy migration command configured on `eparking-api`.
5. [ ] Deploy `eparking-api` first — confirm `/healthz` and `/readyz` respond correctly on the
       new public URL before deploying anything else.
6. [ ] Deploy `eparking-worker` and `eparking-beat`.
7. [ ] Deploy `eparking-frontend`, pointed at the real deployed API URL.
8. [ ] Log in as the real admin account (`spencerdsheel749@gmail.com`) against the production URL
       to confirm the full auth flow works end-to-end on real infrastructure.
9. [ ] Confirm `celery-beat`'s scheduled Paystack sync actually fires in production (check
       `run_logs` after ~15 minutes).

## After first successful deploy

- Add `deploy/RENDER_DEPLOYMENT.md` to `.gitignore` if it isn't already excluded, since it
  contains real secret values — or strip the secret values out and keep only the structural
  reference once secrets are safely stored in Render's dashboard.
