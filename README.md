# Football-IQ

Football-IQ is the Toledo Rockets' video intelligence platform. Coaches upload practice and game film; the system tracks players, detects formations and coverages, generates analytics, and surfaces clips for review — all without manual tagging.

## Service map

| Service | Role | Tech |
|---------|------|------|
| **Frontend** | Coach-facing web UI: video library, clip review, self/opponent scouting, analytics | Next.js 16, React 19, TypeScript |
| **Backend API** | REST API: video metadata, clips, labels, jobs, embeddings, auth | FastAPI, Python 3.12, SQLAlchemy |
| **Database** | Primary data store + pgvector similarity index | PostgreSQL 16 + pgvector |
| **Cloudflare Workers** | Edge upload gateway: generates presigned R2 URLs, enqueues jobs, validates JWT | Cloudflare Workers, TypeScript |
| **Cloudflare R2** | Object storage for raw video, clips, overlays, and model artifacts | 4 buckets: `raw-video`, `clips`, `overlays`, `artifacts` |
| **Cloudflare Queues** | Job dispatch between Worker and GPU worker | `video-processing-jobs`, `nightly-training-exports` |
| **GPU Worker** | Video processing pipeline: detect, track, re-ID, pose, embed, render | PyTorch 2.5.1 + CUDA 12.4, Ultralytics YOLOv8 |

## Quick start (local)

The full local setup guide lives in **[docs/runbook-local.md](docs/runbook-local.md)**.

The short path using Docker Compose:

```bash
# 1. Copy and fill env file
cp .env.example .env
# edit .env — see docs/runbook-local.md for required values

# 2. Start DB
docker-compose up -d db

# 3. Apply migrations
docker-compose --profile migrate up migrate

# 4. Start backend and frontend
docker-compose up backend frontend
```

Backend runs at `http://localhost:8000`, frontend at `http://localhost:3000`.

## Repository layout

```
Football-IQ/
├── backend/          # FastAPI app, Alembic migrations, tests
├── frontend/         # Next.js app, Vitest unit tests, Playwright E2E
├── gpu-worker/       # Video processing pipeline (CUDA required)
├── workers/          # Cloudflare Worker (edge upload gateway)
├── docs/             # Architecture docs, ADRs, local runbook
├── docker-compose.yml
└── .env.example
```

## Environment variables

Copy `.env.example` to `.env` and populate it before starting any service. See [docs/runbook-local.md §Environment variables](docs/runbook-local.md#environment-variables) for a per-service breakdown.

## Running tests

```bash
# Backend unit tests (no real DB needed)
cd backend && pytest -v

# Frontend unit tests
cd frontend && npm test

# Frontend E2E (Playwright, fully offline/mocked)
cd frontend && npm run e2e:install && npm run e2e
```

## Contributing

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Open issues and PRs against the `main` branch.
