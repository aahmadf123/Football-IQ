---
name: football-iq-repo-guardrails
description: Repo guardrails for Football-IQ — service architecture, model-router contract, secret-handling rules, soccer denylist, required test commands, and PR expectations. Load this before writing code, opening PRs, or proposing external resources for the Football-IQ repo.
version: 1.0.0
---

# Football-IQ repo guardrails

> Why this skill lives at `.agents/skills/football-iq-repo-guardrails/SKILL.md`:
> the repo already reserves `.agents/skills/` for agent-loadable skills
> (`.agents/skills/testing-football-iq-frontend/` was the first slot). We keep
> that convention rather than introducing a parallel top-level `skills/`
> directory.

## 1. When to use this skill

Load this skill whenever you (a Claude Code agent or human contributor working
from one of the 22-package Claude Code prompts) are about to:

- Open, edit, or close any issue or PR in `aahmadf123/Football-IQ`.
- Touch the FastAPI backend (`backend/`), the Next.js frontend (`frontend/`),
  the Cloudflare Worker (`workers/`), or the CUDA GPU worker (`gpu-worker/`).
- Change pipeline routing (`gpu-worker/pipeline/model_router.py`,
  `gpu-worker/pipeline/model_routing.json`, `docs/model-routing.md`).
- Add or modify an environment variable, secret, model weight, dataset, API
  client, or third-party dependency.
- Propose an external resource (dataset, model, API, library) — especially
  anything matching "football", which often returns soccer / association-
  football results.
- Run, extend, or rely on the test suites for any of the four services or the
  Alembic migration chain.

Skip this skill only for purely cosmetic doc edits that do not touch
architecture, routing, secrets, external resources, or test contracts.

## 2. Four-service architecture (the only services that exist)

Anything outside this map is **not** part of the production Football-IQ stack —
do not invent extra services, queues, or data stores.

| Service | Role | Host | Tech |
|---|---|---|---|
| **Backend API** | REST API: video metadata, clips, labels, jobs, embeddings, CFBD cache, auth, settings, reports | **Fly.io** | FastAPI, Python 3.12, SQLAlchemy, Alembic |
| **Frontend** | Coach-facing web UI: video library, clip review, scouting, analytics, settings | **Cloudflare Pages** | Next.js 16, React 19, TypeScript |
| **Edge gateway** | Presigned R2 URL issuance, job enqueue, JWT validation at the edge | **Cloudflare Workers** | TypeScript |
| **GPU worker** | Video processing pipeline: segment → calibrate → detect → ball → track → reid → pose → embed → render | **CUDA GPU host** (GTX 1660 Ti class) | PyTorch 2.5.1 + CUDA 12.4, Ultralytics YOLOv8, RTMPose |

Shared infra:

- **Postgres 16 + pgvector** — single primary store for relational data **and**
  similarity vectors. No separate vector database (see §6).
- **Cloudflare R2** — four buckets: `raw-video`, `clips`, `overlays`,
  `artifacts`. All R2 access from the client goes through presigned URLs
  issued by the Worker or backend.
- **Cloudflare Queues** — `video-processing-jobs` (Worker → GPU worker) and
  `nightly-training-exports` (backend → GPU worker for nightly runs).

Boundaries to respect:

- Only the **backend** talks to third-party data APIs that require a key
  (CFBD, Kaggle, etc.). The Worker and frontend must never see those secrets.
- Only the **GPU worker** loads model weights and runs inference. The backend
  never imports torch / ultralytics / RTMPose.
- The frontend never holds long-lived credentials; it receives short-lived
  JWTs from the backend and presigned URLs from the Worker / backend.

## 3. Model-router contract

Pipeline routing is centralised in
`gpu-worker/pipeline/model_router.py`. Every pipeline stage **must** route
through it — do not hard-code variant strings inside stage modules.

Public API (do not break these signatures):

- `select_model(stage: str, priority: int) -> str` — returns the variant id
  for a stage at a given job priority. Unknown stages return
  `UNKNOWN_STAGE_FALLBACK` and log a warning rather than raising.
- `build_routing_artifact(stage: str, priority: int) -> dict[str, str]` —
  returns `{stage: variant}` so the dispatcher can merge it into
  `processing_jobs.output_artifacts["model_routing"]` for the audit trail.
- `is_same_session(priority)`, `is_nightly(priority)`,
  `is_nightly_only_variant(variant)`, `reload_routing()` — stable helpers.

Stages currently routed: `segment`, `calibrate`, `detect`, `ball`, `track`,
`reid`, `pose`, `render`, `embeddings`. New stages must be added to
`DEFAULT_ROUTING` with both `same_session` and `nightly` entries.

Priority buckets (defined in `queue/same_session_queue.py`):

- **Same-session — priority `10` (`SAME_SESSION_PRIORITY`)**. Period-break
  clips. Must fit the 5–10 minute feedback window on the production GTX
  1660 Ti class GPU. Routes to the fast variant.
- **Nightly — priority `0` (`NIGHTLY_PRIORITY`)**. Heavier variants allowed.

`NIGHTLY_ONLY_VARIANTS` is a **hard guardrail**: variants in that frozenset
(currently `sam3.1`, `sam3-mask-tracker`, `play-embed-clip-vitb32-baseline`,
`botsort`, `strongsort`, `parseq-ocr`) are blocked from the same-session bucket
even if a `MODEL_ROUTING_CONFIG` override tries to place them there — the
router replaces them with the default same-session variant and logs
`model_router_blocked_nightly_only_in_same_session`. When adding a new heavy /
experimental / token-gated variant, add it to `NIGHTLY_ONLY_VARIANTS`.

Audit trail: every completed pipeline stage must persist the routing decision
into `processing_jobs.output_artifacts["model_routing"]` via
`build_routing_artifact`. This is how we prove, after the fact, which variant
served a given job. Tests that mutate `MODEL_ROUTING_CONFIG` must call
`reload_routing()` (or reload the module) — the table is resolved at import.

See `docs/model-routing.md` for the full table and rollout notes.

## 4. Secrets and environment variables

Required secret names already wired into the backend (`backend/app/config.py`
`Settings`) and `.env.example`:

- `CFBD_API_KEY` — College Football Data API key. Backend-only. The
  `/api/cfbd/*` route serves cached Postgres rows and never ships the key
  to clients. Defaults to `""`; CFBD calls degrade to cached data when unset.
- `CFBD_BASE_URL` — defaults to `https://api.collegefootballdata.com`.

Required secret names for in-flight work (Issue #164, Kaggle / NFL Big Data
Bowl adapter). When you wire these up you **must** add them to both
`.env.example` and the backend `Settings` class in the same PR:

- `KAGGLE_USERNAME`
- `KAGGLE_API_TOKEN`

Rules for every env var or secret:

1. **Backend-only by default.** If a key is read by the backend, add it to
   `backend/app/config.py` `Settings` as a typed field with a safe default
   (usually `""`) and document it in `.env.example` with the issue number and
   a one-line description.
2. **Never expose secrets to the Worker, frontend, or client bundle.** No
   `NEXT_PUBLIC_*` for API keys. No copying of backend secrets into Worker
   bindings.
3. **Never commit a populated secret value.** `.env` is gitignored; only
   `.env.example` lives in the repo, and it must show the variable name with
   an empty or placeholder value.
4. **Do not log secrets.** Redact at the structured-logging layer when in
   doubt. Do not echo env vars into CI logs or test fixtures.
5. **Rotate-friendly.** Treat any secret as rotatable; do not bake the value
   into code paths, tests, or migrations.

## 5. Soccer / association-football denylist (Issue #166)

Football-IQ is an **American football** platform (Toledo Rockets, MAC, NFL-
style analysis). Soccer / fútbol resources are **rejected**, even when the
upstream package or dataset uses the word "football". Do not add these as
dependencies, ingestion sources, training data, benchmarks, or even
documentation examples without an explicit override decision recorded in an
ADR:

- `worldfootballR` — soccer R package (FBref / Transfermarkt / Understat).
- **SoccerNet** — soccer broadcast video benchmark.
- **FBref / Transfermarkt / WhoScored** scrapers — soccer data.
- Generic **StatsBomb open data** — soccer event data. (StatsBomb *American
  Football* is a separate product; treat it as a brand-new resource and run
  the full rubric.)
- **football-data.org** — soccer API despite the name.
- **SportMonks** football / soccer APIs — soccer unless a separately verified
  American-football product is proposed.
- Generic **FIFA / UEFA / European league** datasets — soccer.

Before adding any external resource that mentions "football", verify sport
coverage against this denylist and the full rubric in
`docs/external-resource-rubric.md`. Fill in the PR template's
**External resource** section and add a row to `LICENSES.md` for any new
model or library dependency.

## 6. Hard repo rules ("don't do this")

These rules apply to every PR. If a task seems to require breaking one, stop
and open an issue first instead of working around it.

- **No secrets in code, tests, fixtures, logs, or commit history.** See §4.
- **No model weights in git.** Weights live in R2 `artifacts/` or are fetched
  at runtime; do not commit `.pt`, `.onnx`, `.bin`, or large `.safetensors`
  files. Update `LICENSES.md` when adding a new upstream model.
- **No new vector database.** Similarity search uses Postgres + pgvector
  (see `docs/embeddings-architecture.md`). Do not introduce Pinecone,
  Weaviate, Qdrant, Milvus, FAISS-as-a-service, or any parallel vector store.
- **No multi-camera assumptions.** The capture protocol is single-camera
  (`docs/capture-protocol-v1.md`). Do not add code paths that assume synced
  multi-camera rigs or that fail when only one camera is present.
- **No duplicate SAM integration.** SAM 3.1 lives **only** behind the
  `ENABLE_SAM3_NIGHTLY` env flag in `model_router.py`, routed for `detect`
  and `track` nightly buckets. Do not add a second SAM call site, a
  same-session SAM variant, or a parallel masking pipeline.
- **No mock data presented as real.** Tests, fixtures, and demo flows that
  produce synthetic detections, fake tracking IDs, fabricated CFBD rows, or
  placeholder embeddings must be clearly labelled at the data layer and in
  any UI surface that renders them. Never wire a `mock_*` fixture into a
  production code path or a coach-visible endpoint.
- **Do not bypass the model router.** Stages must call `select_model` rather
  than reading variant strings from env vars or hard-coding them.

## 7. Required test commands

Before opening a PR, run the suites for every service you touched. Backend,
frontend, Worker, and Alembic commands match `.github/workflows/ci.yml`;
GPU-worker commands are local expectations until that service is added to CI.

Backend (FastAPI, Python 3.12):

```bash
cd backend
pip install -r requirements-dev.txt
export SECRET_KEY=any-32-char-string
export DATABASE_URL=postgresql+asyncpg://footiq:footiq_dev@localhost:5432/footiq
ruff check .
ruff format --check .
mypy app
pytest -v --cov=app --cov-report=xml
```

Alembic migration round-trip (CI gates on this; never merge if it fails):

```bash
cd backend
alembic upgrade head
alembic downgrade base
```

Frontend (Next.js 16):

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm run build
npm test                    # Vitest unit tests
npm run e2e:install && npm run e2e   # Playwright E2E (offline / mocked)
```

Cloudflare Worker (edge gateway):

```bash
cd workers
npm ci
npm run lint
npm run typecheck
npm run build
```

GPU worker (CUDA pipeline):

```bash
cd gpu-worker
pip install -r requirements.txt pytest
pytest -v
```

If a service is genuinely untouched by a PR, state that explicitly in the PR
description rather than silently skipping its suite.

## 8. PR expectations

- **Branch from `main`, PR to `main`.** No direct pushes to `main`. Use a
  descriptive branch name (e.g. `claude/<short-slug>` or `feat/<short-slug>`).
- **Fill out the PR template** (`.github/pull_request_template.md`):
  - **Summary** — what changed and why.
  - **External resource** section — fill this in whenever the PR adds a
    dataset, model, API, or library; otherwise delete the section per the
    template instruction. Confirm the soccer-denylist check, the license
    gate, and the `LICENSES.md` row.
  - **Checklist** — tests pass locally, docs updated where relevant.
- **Update `LICENSES.md`** for every new external model or library
  dependency, even if it is added behind a feature flag.
- **Cite issue links** in the PR body (`Closes #NNN` for issues this PR
  resolves; `Refs #NNN` for related work). Issues to consult for context on
  the 22-package Claude Code plan include #125 (Phase CV epic), #160 (AmF
  external-data epic), #161 / #162 / #163 (CFBD v1), #164 (Kaggle / NFL Big
  Data Bowl), #166 (governance / denylist), #167 (Roboflow / StatsBomb AMF
  spike), #168 (SportQA / SportR), #169 (sportypy / cfbplotR).
- **Include tests run** in the PR body — paste the commands actually
  executed and call out any service you intentionally skipped (with the
  reason).
- **Agents must not approve PRs.** Open the PR and request review from a
  human maintainer. Do not click "Approve". Comments are fine; approval is
  not.
- **Do not merge your own PR via the agent.** Merging is a human action.

When in doubt, defer to the documents in `docs/` (especially
`docs/governance.md`, `docs/external-resource-rubric.md`, and
`docs/model-routing.md`) and to the open issues linked above.
