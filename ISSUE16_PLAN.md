# Issue #16 — Real-Time Same-Session Feedback Pipeline
## Implementation Plan & AI Tool Ownership

**Issue:** [#16](https://github.com/aahmadf123/Football-IQ/issues/16)
**Phase:** 3 | **Priority:** P1 | **Effort:** 4–6 weeks
**Deps:** Issues #3 (processing pipeline), #4 (Practice Inbox), #11
**Branch:** `feature/issue-16-realtime-feedback`

---

## ⛔ DO NOT START Until

- [ ] Phase 1 MVP exit criteria met (Issue #2)
- [ ] Processing pipeline stable with <30 min turnaround on full-session videos (Issue #3)
- [ ] At least one full practice week processed without failures

---

## Target Latency Goals

| Delivery Window | Target |
|---|---|
| Period-break feedback | Clip-ready metrics within 5–10 min of period end |
| Same-session full processing | Full session reviewable within 60 min of practice end |
| Pre-game summary | Last-night practice summary before morning walkthrough |

---

## Resolved Design Decisions

| Decision | Answer | Source |
|---|---|---|
| Cloudflare Queue provisioned? | ✅ Yes — already provisioned and ready | Confirmed by @aahmadf123 |
| Lightweight model for period-break | **RTMPose-t or RTMPose-s** (tiny/small variants) — 430+ FPS on GTX 1660 Ti for RTMPose-m; t/s variants are faster. Full quality (RTMPose-m) runs nightly | Derived from Issue #6 model stack |
| Device targets | **Laptop + iPad** — responsive web app (PWA) covers both without a native app | Confirmed by @aahmadf123 |
| Alert push mechanism | **Server-Sent Events (SSE)** — aligns with Cloudflare Workers edge streaming, no WebSocket infra needed for one-way push | Derived from tech spec CF Workers architecture |
| Biomechanical alert baseline window | **Rolling 4-week window** — season-to-date dilutes early-season baselines; 4-week captures recent training block trends accurately | Derived from tech spec longitudinal profile design |
| Frontend framework | **Next.js** (already in tech spec recommended stack) — Cloudflare Pages deployment, works on laptop and iPad via browser | From `toledo-football-cv-technical-implementation-spec.pplx.md` |
| Backend API | **FastAPI** (already in use per existing codebase) | From existing repo stack |
| Queue architecture | **Cloudflare Queues (edge dispatch) + Redis/Celery (backend processing)** — dual queue per tech spec Phase 2+ recommendation | From `toledo-football-cv-technical-implementation-spec.pplx.md` |

---

## AI Tool Ownership

> **Rule:** Never run two AI tools on the same file simultaneously. Each module has one owner.
> If you need to hand off a module, document it in the Handoff Log at the bottom of this file.

### GitHub Copilot — Infrastructure & Boilerplate

Copilot owns all well-defined, repeatable infrastructure work. Scope it strictly to the modules below.

**Copilot prompt note:**
> "See `ISSUE16_PLAN.md` in the repo root. You own only the modules in the GitHub Copilot section.
> Do NOT touch alert logic, anomaly detection, pose integration, SSE push, or Practice Inbox integration.
> Those are owned by Claude Code. Build on the existing FastAPI + Cloudflare stack already in this repo."

| Module | Path | Description |
|---|---|---|
| Same-session job queue | `gpu-worker/queue/same_session_queue.py` | High-priority queue separate from nightly full-session queue; `priority` field already in `processing_jobs` schema — use it |
| Cloudflare Queue trigger | `gpu-worker/queue/cf_trigger.py` | Video upload from drone/iPad → immediate job dispatch via already-provisioned CF Queue |
| GPU worker auto-scaling | `gpu-worker/worker/autoscale.py` | Burst GPU triggered when same-session queue is non-empty |
| Pipeline timeout & fallback | `gpu-worker/worker/timeout_handler.py` | If period-break job exceeds 8 min → queue for nightly run |
| Lightweight overlay renderer | `gpu-worker/renderer/period_renderer.py` | Reduced resolution, no full HLS encode, period-break delivery only |
| Full-resolution HLS encoder | `gpu-worker/renderer/hls_encoder.py` | Nightly follow-up full-quality encode job |
| Offline upload queue | `gpu-worker/upload/offline_queue.py` | Clips queue automatically when drone connectivity restores |
| Responsive clip view (laptop + iPad) | `frontend/views/clip_review_responsive.*` | Touch-optimized + desktop — Next.js component, Cloudflare Pages deployment |
| Infra unit tests | `gpu-worker/tests/test_queue.py`, `test_autoscale.py`, `test_timeout.py`, `test_renderer.py` | Tests for all Copilot-owned modules |

---

### Claude Code — Smart Logic, Alerts & Integration

Claude Code owns all modules requiring deep codebase awareness, pose data from Issue #6, and connection to Practice Inbox (Issue #4).

**Claude Code prompt note:**
> "See `ISSUE16_PLAN.md` in the repo root. Copilot has already built the queue, worker auto-scaling,
> renderer, HLS encoder, and upload infra. Build on top of those — do NOT rewrite them.
> You own: anomaly/alert logic, SSE push, Practice Inbox integration, and position-group filtering.
> Key decisions already made: SSE for push, rolling 4-week baseline for bio alerts,
> RTMPose-t/s for period-break lightweight model, FastAPI backend, Next.js frontend."

| Module | Path | Description |
|---|---|---|
| Biomechanical deviation alert | `gpu-worker/alerts/bio_deviation_alert.py` | Flags rep where pose metrics deviate >2 SD from player's rolling 4-week baseline (requires Issue #6 pose pipeline) |
| Effort anomaly detection | `gpu-worker/alerts/effort_anomaly.py` | Flags player sprint-to-ball significantly below session average |
| Formation execution anomaly | `gpu-worker/alerts/formation_anomaly.py` | Flags player alignment significantly off from formation baseline |
| Configurable alert thresholds | `backend/app/models/alert_config.py` | Per position group, configurable by sports performance or coaching staff |
| SSE alert push | `backend/app/routers/alerts_sse.py` | Server-Sent Events endpoint for real-time coaching app push — aligns with CF Workers edge streaming |
| Alert router & endpoints | `backend/app/routers/alerts.py` | REST endpoints for alert creation, history, and acknowledgment |
| Practice Inbox integration | `backend/app/routers/inbox_integration.py` | Real-time processing status in Practice Inbox (Issue #4) |
| Position-group filter | `backend/app/deps/position_filter.py` | Each coach sees only their position group's clips and metrics |
| Period-break clip package | `gpu-worker/pipeline/period_package.py` | Per-period summary builder: effort + formation + identity conflict flags |
| Lightweight model router | `gpu-worker/pipeline/model_router.py` | Routes to RTMPose-t/s for same-session jobs, RTMPose-m for nightly full-quality run |
| One-tap correction sync | `backend/app/routers/correction_sync.py` | iPad one-tap corrections sync to main correction queue (feeds `coach_corrections` table) |
| Claude Code tests | `backend/tests/test_alerts.py`, `backend/tests/test_alerts_sse.py`, `gpu-worker/tests/test_period_package.py`, `gpu-worker/tests/test_anomaly.py`, `gpu-worker/tests/test_model_router.py` | Tests for all Claude Code-owned modules |

---

## Implementation Order

### Step 1 — Copilot: Infrastructure (Week 1–2)
1. Create branch `feature/issue-16-realtime-feedback` from `main`
2. Run Copilot scoped **only** to the infrastructure modules above
3. Confirm CF Queue trigger connects to already-provisioned CF Queue
4. Review and merge Copilot's work to the feature branch
5. ✅ Gate: queue, autoscale, timeout/fallback, renderer, HLS encoder, offline queue all working with basic tests

### Step 2 — Claude Code: Smart Logic & Integration (Week 2–4)
1. Branch **from `feature/issue-16-realtime-feedback`** — do NOT branch from `main`
2. Start in **plan mode**: ask Claude to read `ISSUE16_PLAN.md` and the existing infra before any code
3. Implement anomaly/alert logic, SSE push, Practice Inbox integration, position-group filtering
4. Implement lightweight model router (RTMPose-t/s for same-session, RTMPose-m for nightly)
5. Add tests for all new modules
6. Review and merge back to feature branch

### Step 3 — Integration & Final Review (Week 4–5)
1. One Claude Code session to validate end-to-end pipeline connectivity
2. Run full test suite: `pytest backend/tests/ gpu-worker/tests/`
3. Confirm CI lint passes (`ruff check .`, `ruff format --check`, `mypy app`)
4. Open PR from `feature/issue-16-realtime-feedback` → `main`

### Step 4 — Validation Against Exit Criteria (Week 5–6)
- [ ] Period-break clip package delivered within 10 min on 3 consecutive practice days
- [ ] Coaching staff confirms same-session feedback changes at least one in-practice coaching point
- [ ] Live anomaly alert tested and confirmed useful by sports performance staff
- [ ] Fallback to nightly processing working reliably when same-session job exceeds timeout

---

## Alert Governance

All alerts follow the same governance pattern established in Issue #6:

- Alerts are **never auto-shown to players**
- Biomechanical deviation alerts require **Issue #6 pose pipeline active and coach-approved for at least one position group**
- Alert thresholds are **configurable per position group** by sports performance or coaching staff
- Biomechanical baseline = **rolling 4-week window** per player
- Alert delivery: **Practice Inbox (#4) + SSE coaching app push** — not player-facing views
- All anomaly alerts carry a **confidence score and clip link** (evidence-first principle from tech spec)

---

## Lightweight vs. Full-Quality Model Split

| Job Type | Model | When |
|---|---|---|
| Period-break (same-session) | RTMPose-t or RTMPose-s | <8 min window between periods |
| Nightly full-quality | RTMPose-m (430 FPS on GTX 1660 Ti) | Full session after practice ends |

The `model_router.py` module (Claude Code-owned) handles this routing logic based on job priority level.

---

## Module Ownership Quick Lookup

```
gpu-worker/queue/             → Copilot
gpu-worker/worker/            → Copilot
gpu-worker/renderer/          → Copilot
gpu-worker/upload/            → Copilot
frontend/views/clip_review_*  → Copilot
gpu-worker/alerts/            → Claude Code
gpu-worker/pipeline/period_*  → Claude Code
gpu-worker/pipeline/model_router.py  → Claude Code
backend/app/routers/alerts*   → Claude Code
backend/app/routers/inbox_*   → Claude Code
backend/app/routers/correction_sync.py → Claude Code
backend/app/deps/position_filter.py   → Claude Code
backend/app/models/alert_config.py    → Claude Code
```

---

## Handoff Log

> If ownership of a module changes during implementation, record it here.

| Date | Module | From | To | Reason |
|---|---|---|---|---|
| — | — | — | — | — |

---

*Last updated: 2026-05-08 | Author: @aahmadf123*
