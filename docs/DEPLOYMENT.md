# Deployment & CI/CD

| Layer    | Platform                 | QA (`qa` branch)                         | Production (`main` branch)           |
| -------- | ------------------------ | ---------------------------------------- | ------------------------------------ |
| Frontend | Cloudflare Pages         | `qa.<project>.pages.dev` (branch alias)  | `<project>.pages.dev` / custom domain |
| Backend  | Render (Python web svc)  | `env-management-api-qa`                  | `env-management-api-prod`            |
| Database | Supabase (Postgres)      | Supabase project `env-management-qa`     | Supabase project `env-management-prod` |

## Branching

```
feature/* ──PR──▶ qa ──PR──▶ main
```

- **Pull requests** into `qa` / `main` run `CI` (`.github/workflows/ci.yml`): backend pytest,
  migrate-and-seed against a throwaway Postgres 16, the frontend type-check/build and Playwright e2e tests.
- **Push to `qa`** deploys to QA; **push to `main`** deploys to production
  (`.github/workflows/deploy.yml`). Steps run in order and stop on the first failure:
  1. CI (same checks as above)
  2. `alembic upgrade head` against Supabase
  3. Trigger the Render deploy hook, then poll `/api/health` until it reports the pushed commit
  4. Build the frontend with `VITE_API_BASE_URL=<BACKEND_URL>/api` and deploy to Cloudflare Pages
- Protect `main` (and optionally `qa`) in **Settings → Branches**: require PRs and the `CI` checks.
- Add **required reviewers** on the `production` GitHub environment to get a manual approval gate
  before anything touches production.

## One-time setup

### 1. Supabase (one project per environment)

1. Create two projects, e.g. `env-management-qa` and `env-management-prod`.
2. Project → **Connect** → copy the connection strings:
   - **Session pooler** (port `5432`) → used by GitHub Actions for migrations.
     GitHub runners have no IPv6, so don't use the direct `db.<ref>.supabase.co` host.
   - **Transaction pooler** (port `6543`) → used by the Render service at runtime.
3. Format: `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:<port>/postgres?sslmode=require`

Tables are created by Alembic (`backend/migrations/versions`) in the pipeline, not on app startup
(`RUN_MIGRATIONS=false` in deployed environments). To load the sample dataset into a Supabase
database once: `cd backend && DATABASE_URL=<session pooler URL> python -m app.flows.seed` (add `--with-environments` for the demo environment inventory; leave it off for real data — an empty inventory shows first-run guidance instead).

### 2. Render

1. **New → Blueprint** → select this repo; Render reads `render.yaml` and creates
   `env-management-api-qa` (branch `qa`) and `env-management-api-prod` (branch `main`).
2. For each service set the `sync: false` env vars:
   - `DATABASE_URL` – the Supabase **transaction pooler** URL for that environment
   - `CORS_ORIGINS` – the Cloudflare Pages URL(s), comma-separated or a JSON list,
     e.g. `https://qa.env-management.pages.dev`
   - `CORS_ORIGIN_REGEX` – optional, e.g. `^https://[a-z0-9-]+\.env-management\.pages\.dev$`
   - `AUTH_MODE` – `dev` means **no login**: anyone with the URL is a maintainer. That's fine for an
     empty QA, but don't put real data behind it. `header` mode needs an SSO proxy in front of
     Render (see "Security and roles" in the README); Render alone does not provide one.
3. Service → **Settings → Deploy Hook** → copy the URL (one per service).
   Auto-deploy is off; GitHub Actions triggers deploys only after migrations succeed.

### 3. Cloudflare Pages

1. Create a Pages project using **Direct Upload** (e.g. named `env-management`), with
   **production branch = `main`**. Deployments from the `qa` branch become previews at
   `qa.<project>.pages.dev`.
2. Create an API token with **Account → Cloudflare Pages → Edit** permission and note the
   Account ID.

### 4. GitHub

**Settings → Environments** → create `qa` and `production`, and add to each:

| Kind     | Name                      | Example / notes                                   |
| -------- | ------------------------- | ------------------------------------------------- |
| Secret   | `SUPABASE_DB_URL`         | Supabase **session pooler** URL for that env      |
| Secret   | `RENDER_DEPLOY_HOOK_URL`  | Deploy hook of that env's Render service          |
| Secret   | `CLOUDFLARE_API_TOKEN`    | Pages:Edit token (same value in both envs is fine) |
| Secret   | `CLOUDFLARE_ACCOUNT_ID`   | Cloudflare account ID                             |
| Variable | `BACKEND_URL`             | `https://env-management-api-qa.onrender.com` (no trailing slash) |
| Variable | `FRONTEND_URL`            | `https://qa.env-management.pages.dev`             |
| Variable | `CLOUDFLARE_PROJECT_NAME` | `env-management`                                  |

Optionally restrict each environment's **deployment branches** (`qa` → `qa`, `production` → `main`).

## Notes

- Render's free plan sleeps after inactivity; the first deploy-verification request may take
  ~1 minute to wake it. The workflow waits up to 20 minutes.
- New schema changes: edit `backend/app/models.py`, then
  `cd backend && alembic revision --autogenerate -m "describe change"` and commit the file
  in `backend/migrations/versions`.
- Rollback: re-run an earlier successful `Deploy` run, or use **Rollback** in Render / Cloudflare
  dashboards. Migrations are forward-only in the pipeline; downgrade manually if needed.
