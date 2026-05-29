# Local Development Runbook

This runbook lets a new engineer or AI agent bring Football-IQ up end to end on a local machine with minimal guesswork. Work through the sections in order; each section references the actual files and commands in the repo.

---

## Prerequisites

| Tool | Minimum version | Install |
|------|----------------|---------|
| Docker + Docker Compose | 24+ | https://docs.docker.com/get-docker/ |
| Node.js | 20+ | https://nodejs.org/ |
| Python | 3.12 | https://python.org/ |
| npm | 10+ | bundled with Node |
| (optional) wrangler CLI | 3+ | `npm install -g wrangler` |

The GPU worker requires an NVIDIA GPU with CUDA 12.4+ and Docker GPU support. It is not needed for UI or API development — skip it unless you are working on the video pipeline.

---

## Repository architecture

```
Football-IQ/
├── backend/              FastAPI backend (Python 3.12)
│   ├── app/              Application source
│   │   ├── main.py       FastAPI entrypoint
│   │   ├── config.py     Pydantic settings (reads from env)
│   │   ├── models.py     SQLAlchemy ORM models
│   │   ├── database.py   Async engine + session factory
│   │   ├── auth.py       JWT authentication
│   │   └── routers/      24 router modules (videos, clips, labels, …)
│   ├── migrations/       Alembic migration scripts
│   ├── tests/            Pytest unit tests (no real DB needed)
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── alembic.ini
│
├── frontend/             Next.js 16 app (React 19, TypeScript)
│   ├── src/
│   │   ├── app/          App Router pages (video library, clip review, …)
│   │   ├── components/   Shared components
│   │   └── lib/          API client (lib/api.ts), state, types
│   ├── e2e/              Playwright E2E specs
│   └── package.json
│
├── workers/              Cloudflare Worker (TypeScript)
│   ├── src/
│   │   ├── index.ts      Request handler (routing)
│   │   ├── r2.ts         Presigned URL generation + R2 ops
│   │   ├── queue.ts      Queue bindings
│   │   └── auth.ts       JWT validation
│   └── wrangler.toml     Cloudflare bindings (R2, Queues, secrets)
│
├── gpu-worker/           Video processing pipeline (PyTorch + CUDA)
│   ├── __main__.py       Queue polling + job orchestration
│   └── pipeline/         Per-stage modules (detect, track, pose, …)
│
├── docs/                 Architecture docs and ADRs
├── docker-compose.yml    Local dev: db, backend, migrate, frontend
└── .env.example          Environment variable template
```

**Data flow for a new upload:**

1. Coach uploads an MP4 via the frontend.
2. Frontend calls the **Cloudflare Worker** for a presigned R2 upload URL.
3. File goes directly to **R2** (`raw-video` bucket).
4. Worker enqueues a job on **Cloudflare Queues** (`video-processing-jobs`).
5. **GPU worker** polls the queue, downloads the file from R2, runs the pipeline (detect → track → re-ID → pose → embed → render), and writes results to the **backend API**.
6. Backend persists everything in **PostgreSQL**.
7. Frontend fetches clips and analytics from the backend API.

---

## Environment variables

Copy the template and fill in values before starting any service:

```bash
cp .env.example .env
```

### Local development defaults

For the core local loop (database + backend + frontend via Docker Compose), these are the only values you must set or verify:

| Variable | Docker Compose default | What it is |
|----------|-----------------------|------------|
| `ENVIRONMENT` | `development` | App mode |
| `SECRET_KEY` | `dev-secret-key-not-for-production` | JWT signing key (any 32+ char string for local) |
| `DATABASE_URL` | `postgresql+asyncpg://footiq:footiq_dev@db:5432/footiq` | Async DB URL (used by FastAPI) |
| `DATABASE_SYNC_URL` | `postgresql://footiq:footiq_dev@db:5432/footiq` | Sync DB URL (used by Alembic) |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed origins |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend URL (browser-visible) |
| `NEXT_PUBLIC_WORKER_URL` | `http://localhost:8787` | Worker URL (browser-visible) |

Docker Compose injects the database and CORS values automatically for the `backend` and `migrate` services. If you run services outside Docker you must export them yourself.

### R2 / Cloudflare variables (required for upload flow)

These are needed only if you run the Cloudflare Worker locally (`wrangler dev`) or point the frontend at a live Worker:

| Variable | What it is |
|----------|-----------|
| `CLOUDFLARE_ACCOUNT_ID` | Your Cloudflare account ID |
| `CLOUDFLARE_API_TOKEN` | API token with Workers + R2 + Queues permissions |
| `R2_ACCESS_KEY_ID` | R2 API token key ID |
| `R2_SECRET_ACCESS_KEY` | R2 API token secret |
| `R2_ENDPOINT_URL` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `R2_BUCKET_RAW` | `raw-video` |
| `R2_BUCKET_CLIPS` | `clips` |
| `R2_BUCKET_OVERLAYS` | `overlays` |
| `R2_BUCKET_ARTIFACTS` | `artifacts` |
| `R2_PRESIGN_TTL` | Presigned URL lifetime in seconds (default: `3600`) |
| `CF_QUEUE_VIDEO_PROCESSING` | `video-processing-jobs` |
| `CF_QUEUE_NIGHTLY_TRAINING` | `nightly-training-exports` |
| `WORKER_URL` | Worker base URL |

The Worker reads `JWT_SECRET`, `DATABASE_URL`, and `BACKEND_API_URL` as **Wrangler secrets** (not from `.env`). Set them via:

```bash
cd workers
npx wrangler secret put JWT_SECRET
npx wrangler secret put DATABASE_URL
npx wrangler secret put BACKEND_API_URL
```

### JWT variables

| Variable | Default | What it is |
|----------|---------|-----------|
| `JWT_ALGORITHM` | `HS256` | `HS256` or `RS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token lifetime |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token lifetime |

### GPU worker variables (optional)

| Variable | Default | What it is |
|----------|---------|-----------|
| `GPU_WORKER_POLL_INTERVAL` | `10` | Seconds between queue polls |
| `RUNPOD_API_KEY` | — | RunPod burst GPU key (optional) |
| `MODAL_TOKEN_ID` | — | Modal burst GPU token (optional) |
| `MODAL_TOKEN_SECRET` | — | Modal burst GPU secret (optional) |

GPU worker reuses the `R2_*` variables for downloading and uploading video files.

### SSO (optional)

| Variable | What it is |
|----------|-----------|
| `SSO_PROVIDER_URL` | University SAML/OAuth2 provider URL |
| `SSO_CLIENT_ID` | SSO client ID |
| `SSO_CLIENT_SECRET` | SSO client secret |

Leave these blank for local development; the backend falls back to local JWT auth.

### College Football Data (CFBD) — backend-only (optional)

| Variable | What it is |
|----------|-----------|
| `CFBD_API_KEY` | College Football Data API key — **backend only** |
| `CFBD_BASE_URL` | API base URL (default `https://api.collegefootballdata.com`) |

CFBD powers the Toledo/MAC analytics cache (Issues #160/#161/#162) and is
called **only** from the FastAPI backend — never from the frontend, the Worker,
or any browser bundle. The key is never persisted to the database and never
appears in logs or coach-visible errors.

To set it up locally **without committing any value**:

1. Request a free key at <https://collegefootballdata.com/key>.
2. Add it to your local, git-ignored `.env` (copied from `.env.example`):

   ```bash
   # .env  — never commit this file
   CFBD_API_KEY=<paste-your-key-here>
   ```

3. Leave `CFBD_BASE_URL` at its default unless you are pointing at a mock.

If `CFBD_API_KEY` is unset, the app still boots normally; any CFBD call fails
fast with a clear backend-only `CFBDConfigError` rather than an opaque 401, and
previously cached data in the `cfbd_*` tables remains fully queryable.

To populate the cache for a season once the key is set:

```bash
cd backend
python -m app.cfbd --season 2024                 # Toledo + MAC, regular season
python -m app.cfbd --season 2024 --season-type postseason
```

The command upserts idempotently (safe to re-run) and records every attempt in
`cfbd_sync_runs` (endpoint, params, row counts, status, error summary). If one
endpoint is rate-limited or down, the others still sync and the failure is
recorded without aborting the run.

### Deployment variables (not needed locally)

`FLY_API_TOKEN` and `FLY_APP_NAME` are only used by the CD pipeline (`cd.yml`). Do not set them locally.

---

## Local startup

### Recommended: Docker Compose

Docker Compose manages the database, backend, migrations, and frontend together.

```bash
# Start the database (wait for healthy)
docker-compose up -d db

# Apply all Alembic migrations
docker-compose --profile migrate up migrate

# Start backend (port 8000) and frontend (port 3000)
docker-compose up backend frontend
```

Check the backend is up:

```bash
curl http://localhost:8000/health
```

Open the frontend at `http://localhost:3000`.

Hot reload is enabled for the backend (`--reload` flag) via a volume mount of `./backend:/app`.

### Alternative: without Docker

If you prefer to run services directly:

**Database:**

```bash
# Start a local Postgres 16 instance with the expected credentials
docker run -d \
  --name footiq-db \
  -e POSTGRES_USER=footiq \
  -e POSTGRES_PASSWORD=footiq_dev \
  -e POSTGRES_DB=footiq \
  -p 5432:5432 \
  postgres:16-alpine
```

**Backend:**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

export DATABASE_URL=postgresql+asyncpg://footiq:footiq_dev@localhost:5432/footiq
export DATABASE_SYNC_URL=postgresql://footiq:footiq_dev@localhost:5432/footiq
export SECRET_KEY=dev-secret-key-not-for-production
export CORS_ORIGINS=http://localhost:3000

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend:**

```bash
cd frontend
npm ci

export NEXT_PUBLIC_API_URL=http://localhost:8000
export NEXT_PUBLIC_WORKER_URL=http://localhost:8787

npm run dev
```

Frontend is at `http://localhost:3000`.

### Cloudflare Worker (optional — needed for real uploads)

The upload flow requires the Cloudflare Worker. For local development you can run it with wrangler:

```bash
cd workers
npm ci
npx wrangler dev
```

The local Worker listens on `http://localhost:8787`. Set `NEXT_PUBLIC_WORKER_URL=http://localhost:8787` in the frontend environment.

> **Note:** Local `wrangler dev` uses local Miniflare stubs for R2 and Queues. Uploads reach a local R2 simulation, not a real bucket. The GPU worker will not pick them up unless pointed at the same Cloudflare account. For full end-to-end testing, deploy to a real Cloudflare account.

### GPU worker (optional — hardware-dependent)

The GPU worker requires an NVIDIA GPU with CUDA 12.4+ and the NVIDIA Container Toolkit. It is not needed for UI, API, or analytics development.

```bash
cd gpu-worker
docker build -t football-iq-gpu-worker .

docker run --gpus all \
  -e DATABASE_URL=postgresql+asyncpg://footiq:footiq_dev@host.docker.internal:5432/footiq \
  -e R2_ACCESS_KEY_ID=<your-key> \
  -e R2_SECRET_ACCESS_KEY=<your-secret> \
  -e R2_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com \
  -e GPU_WORKER_POLL_INTERVAL=10 \
  football-iq-gpu-worker
```

Without GPU hardware, the worker will fail at the CUDA initialization step. Cloud GPU providers (RunPod, Modal) can substitute via the `RUNPOD_API_KEY` / `MODAL_TOKEN_*` variables in `.env`.

---

## Database

### Applying migrations

Docker Compose (recommended):

```bash
docker-compose --profile migrate up migrate
```

Directly with Alembic:

```bash
cd backend
alembic upgrade head
```

### Creating a new migration

```bash
cd backend
alembic revision --autogenerate -m "describe_your_change"
# Review the generated file in migrations/versions/ before committing
alembic upgrade head
```

### Rolling back one step

```bash
cd backend
alembic downgrade -1
```

### Checking current state

```bash
cd backend
alembic current
alembic history --verbose
```

### pgvector

The `play_embeddings` table requires the `pgvector` extension. The Docker Compose `db` service uses `postgres:16-alpine` which does not include pgvector by default. Migration `0008_play_embeddings.py` runs `CREATE EXTENSION IF NOT EXISTS vector` — this works on managed Postgres instances (Supabase, Neon) that bundle pgvector. For a plain local Postgres, install pgvector first:

```bash
# Example for pgvector on the Docker-managed Postgres
docker exec footiq-db sh -c "
  apk add --no-cache git build-base postgresql-dev && \
  git clone https://github.com/pgvector/pgvector.git /tmp/pgvector && \
  cd /tmp/pgvector && make && make install
"
```

Alternatively, use a `pgvector/pgvector:pg16` image as the `db` service if you customise `docker-compose.yml`.

### Seed data

There are no seed scripts in the current repo. To bootstrap local data:

1. Start all services.
2. Use the `/docs` (Swagger UI) at `http://localhost:8000/docs` to create a user and POST a video record.
3. Or write a quick Python script using `httpx` against the local API.

---

## Backend tests

Tests live in `backend/tests/`. They use `pytest` with `AsyncMock`-based dependency overrides and do **not** require a running database.

```bash
cd backend
# Activate your virtualenv first if running outside Docker
source .venv/bin/activate

# Install dev deps
pip install -r requirements-dev.txt

# Run all tests
pytest -v

# Run a single file
pytest tests/test_videos.py -v

# Run with coverage (matches CI)
pytest -v --cov=app --cov-report=term-missing
```

The tests require `SECRET_KEY` and `DATABASE_URL` env vars to be set (any valid-shaped values work because no real DB connection is made):

```bash
export SECRET_KEY=any-32-char-string
export DATABASE_URL=postgresql+asyncpg://footiq:footiq_dev@localhost:5432/footiq
```

See `backend/tests/README.md` for mocking conventions and how to add new tests.

### Linting and type checking

```bash
cd backend
ruff check .
ruff format --check .
mypy app
```

---

## Frontend tests

### Unit tests (Vitest)

```bash
cd frontend
npm ci
npm test
```

Runs all `*.test.ts` / `*.spec.ts` files under `src/`. No browser or backend needed.

### E2E tests (Playwright)

The Playwright suite is fully offline: it runs `next dev` and intercepts all backend/Worker HTTP calls. No real Cloudflare or Fly.io credentials are needed.

```bash
cd frontend
npm ci

# One-time: install Chromium (≈ 150 MB)
npm run e2e:install

# Run headless
npm run e2e

# Run with interactive UI (requires a display)
npm run e2e:ui
```

The web server starts on port `3100` by default. Override with `E2E_PORT=<port>`.

See `frontend/docs/E2E.md` for the full spec list and what each one covers.

### Lint and type check

```bash
cd frontend
npm run lint
npm run typecheck
```

---

## Troubleshooting

### API issues

**Symptom:** `curl http://localhost:8000/health` returns connection refused.

- Check `docker-compose ps` — is the `backend` service healthy?
- Check logs: `docker-compose logs backend`.
- Verify `DATABASE_URL` and `SECRET_KEY` are set. The app will fail to start if `app.config.Settings` cannot parse them.
- If running outside Docker, confirm `uvicorn` is running on port 8000: `lsof -i :8000`.

**Symptom:** API returns 500 errors.

- `docker-compose logs backend` usually shows the structured log with the error.
- Most 500s in dev are missing env vars or a failed DB connection.

### CORS issues

**Symptom:** Browser console shows `CORS policy` error when the frontend calls the backend.

- Check `CORS_ORIGINS` in the backend environment. For Docker Compose the default is `http://localhost:3000`.
- If you changed the frontend port, update `CORS_ORIGINS` to match.
- The backend's `app/main.py` reads `CORS_ORIGINS` as a comma-separated list. Example: `CORS_ORIGINS=http://localhost:3000,http://localhost:3001`.

**Symptom:** CORS error when the frontend calls the Worker.

- The Worker (`workers/src/index.ts`) sets CORS headers independently. For local `wrangler dev`, the default allowed origin is `*`. For production you must configure the Worker's CORS policy to match your frontend domain.

### R2 / storage issues

**Symptom:** Upload fails with a 403 or presign URL error.

- Confirm `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_ENDPOINT_URL` are set.
- The endpoint URL must match your Cloudflare account: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.
- R2 access keys are created in the Cloudflare dashboard under **R2 → Manage R2 API tokens**.
- For `wrangler dev` (local simulation), R2 calls hit Miniflare's in-memory store; no real credentials are required.

**Symptom:** Worker cannot read/write a bucket.

- Check `wrangler.toml` binding names (`RAW_VIDEO`, `CLIPS`, `OVERLAYS`, `ARTIFACTS`) match the actual bucket names in the Cloudflare dashboard.
- Run `npx wrangler r2 bucket list` to verify buckets exist.

### Database / migration issues

**Symptom:** `alembic upgrade head` fails with `relation already exists`.

- A partial migration may have run. Check `alembic current` and the state of the `alembic_version` table in Postgres.
- If the database is empty and you want a clean start: `docker-compose down -v` (drops the `postgres_data` volume) then restart.

**Symptom:** Backend fails with `FATAL: role "footiq" does not exist`.

- The DB container may not have finished initializing before the backend tried to connect. Docker Compose uses a healthcheck (`pg_isready -U footiq`) on the `db` service — the `backend` service `depends_on` this. If you start services manually, wait until `pg_isready` succeeds before starting the backend.

**Symptom:** `CREATE EXTENSION vector` fails.

- The Postgres image does not have pgvector installed. See [pgvector section](#pgvector) above.

### Worker / queue issues

**Symptom:** GPU worker does not pick up jobs.

- Confirm the Worker is actually enqueuing to the right Cloudflare Queue. Check the Cloudflare dashboard → Queues for message counts.
- The GPU worker polls `video-processing-jobs`. Verify `CF_QUEUE_VIDEO_PROCESSING=video-processing-jobs` is set.
- For local testing, `wrangler dev` does not deliver queue messages to an external consumer. You must deploy to a real Cloudflare account to test the full queue → GPU worker path.

**Symptom:** `wrangler dev` fails with missing binding errors.

- `wrangler dev` requires the secrets (`JWT_SECRET`, `DATABASE_URL`, `BACKEND_API_URL`) to be available. For local dev, pass them as env vars or create a `.dev.vars` file in `workers/`:

  ```
  JWT_SECRET=local-dev-secret
  DATABASE_URL=postgresql://footiq:footiq_dev@localhost:5432/footiq
  BACKEND_API_URL=http://localhost:8000
  ```

### GPU worker issues

**Symptom:** GPU worker exits with `CUDA out of memory` or `device not found`.

- Verify the host has an NVIDIA GPU: `nvidia-smi`.
- Verify the NVIDIA Container Toolkit is installed: `docker run --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi`.
- Reduce model size by adjusting `GPU_WORKER_POLL_INTERVAL` or using the lightweight model config (`pipeline/lightweight_config.py`).

**Symptom:** GPU worker downloads video but pipeline fails.

- Check R2 credentials — the worker downloads raw video from the `raw-video` bucket using `R2_*` env vars.
- Logs from `gpu-worker/__main__.py` show per-stage errors. Model weights are downloaded on first run (Ultralytics caches in `~/.ultralytics/`); ensure outbound internet access or pre-cache the weights.

---

## Service start order

For a clean local session:

```
1. db (postgres)          → docker-compose up -d db
2. migrate (alembic)      → docker-compose --profile migrate up migrate
3. backend (fastapi)      → docker-compose up -d backend
4. frontend (next.js)     → docker-compose up -d frontend
5. workers (optional)     → cd workers && npx wrangler dev
6. gpu-worker (optional)  → docker run --gpus all ... (see GPU worker section)
```

Steps 1–4 cover the full UI and API experience. Steps 5–6 are only needed for the video upload + processing pipeline.
