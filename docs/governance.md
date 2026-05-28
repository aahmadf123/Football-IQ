# Governance: roles, visibility modes, and workload gating

Status: implemented in this PR (closes #113 and #114).

This document describes the runtime governance layer that all sensitive
Football-IQ APIs build on.  It is intentionally short: implementation details
live in `app/governance.py` and `app/workload.py`, while this document
captures the *contract* — what callers can rely on and what reviewers should
check when extending it.

## 1. Roles

| Role               | Intent                                              |
|--------------------|-----------------------------------------------------|
| `admin`            | Full platform access; manages users and policy.     |
| `analyst`          | Analytics lead; approves recruiting visibility.     |
| `coach`            | Position / position-group coach.                    |
| `sportsperformance`| Sports performance / S&C / wellness staff.          |
| `player`           | A roster player viewing their own development.      |
| `viewer`           | Read-only external account (recruiting boards, …).  |

Roles live on `users.role` (`app.models.UserRole`).  Convenience FastAPI
dependencies in `app/deps.py` (`require_coach_or_above`, `require_any_staff`,
`require_sportsperformance_or_above`, …) wrap simple role-set checks; the
central RBAC policy below replaces ad-hoc booleans for cross-resource
permissions.

## 2. RBAC policy

`app.governance.POLICY` is the **single source of truth** for which role can
perform which action on which resource.  The posture is **deny-by-default**:
any (resource, action) pair not listed in the table is forbidden.

| Resource              | Action     | Allowed roles                                 |
|-----------------------|------------|-----------------------------------------------|
| `player_profile`      | `read`     | all authenticated roles                       |
| `player_visibility`   | `write`    | admin, analyst, coach                         |
| `player_visibility`   | `approve`  | admin, analyst (recruiting approval)          |
| `player_metrics`      | `read`     | admin, analyst, coach, sportsperformance, player |
| `health_workload`     | `read`     | admin, analyst, sportsperformance             |
| `heavy_workload`      | `trigger`  | admin, analyst                                |
| `cfbd_analytics`      | `read`     | admin, analyst, coach, sportsperformance      |

Routers enforce policies via `require_policy(resource, action)` where the
resource/action matrix is applied. Every denial
emits a structured `audit.access.denied` log line containing only the actor
UUID, role, and the (resource, action) pair — never request payloads.

## 3. Visibility modes (Issue #114)

Player records have an outward-facing **lifecycle state** that controls which
projections they participate in:

* `staff_only` *(default)* — internal only.
* `player_approved` — player may see their own profile.
* `recruiting_approved` — recruiting view (external) is exposed.
* `archived` — hidden from all non-staff projections; staff can still view
  and un-archive.

`GET /api/v1/players` and `GET /api/v1/players/{id}` accept `?mode=` of
`staff` | `player` | `recruiting`.  Modes are validated against the caller's
role (`resolve_visibility_mode`) and the result is shaped server-side
(`shape_player`).  Defense in depth: even if a column is present on the ORM
row, sensitive fields (`metadata`, `user_id`) are stripped before serializing
non-staff projections.  Recruiting omits additional bookkeeping (`is_active`,
`created_at`) so it returns identity facts only.

Transitions are recorded in `player_visibility_audit` and emit
`audit.visibility.changed` log lines.  `PATCH /api/v1/players/{id}/visibility`
is the only mutation surface; recruiting approvals require the
`PLAYER_VISIBILITY:APPROVE` policy (admin or analyst).

Player records whose state excludes them from the requested mode return
`404` rather than `403` so external callers cannot learn whether a record
exists.

### Approval workflow

1. Player record lands in `staff_only` (default).
2. A coach reviews the staff projection and `PATCH`es to `player_approved`
   when the player may see their own profile.
3. An analyst or admin further reviews and `PATCH`es to
   `recruiting_approved` when the profile may be released externally.
4. `archived` removes the record from all non-staff projections.  Staff
   retain read/write access so the record can be revived or audited.

## 4. Health/workload gating (Issue #113)

`app.workload` samples the queued/running `processing_jobs` counts and
classifies the worker pool as `healthy`, `degraded`, or `saturated`.
Thresholds are environment-driven (see
[`.env.example`](../.env.example)):

* `WORKLOAD_QUEUE_THRESHOLD` (default `50`)
* `WORKLOAD_RUNNING_THRESHOLD` (default `20`)
* `WORKLOAD_GATING_DISABLED` (default `false`) — emergency bypass.

`require_workload_capacity("<endpoint-name>")` is a FastAPI dependency
applied to heavy endpoints.  When the snapshot is `saturated` (and gating is
not disabled) it returns:

```json
HTTP/1.1 503 Service Unavailable
Retry-After: 30
{
  "detail": {
    "error_code": "workload_gated",
    "endpoint": "jobs.create",
    "message": "Heavy workload temporarily unavailable due to system load. Please retry shortly.",
    "workload": { "queued": 60, "running": 5, "queue_threshold": 50, "running_threshold": 20, "status": "saturated", "gating_disabled": false }
  }
}
```

A `503` with `error_code=workload_gated` is intentionally distinguishable
from `401`/`403` authorization failures so callers can implement different
retry strategies.  Every decision (allowed or rejected) is emitted as
`audit.gating.allowed` / `audit.gating.rejected` for offline audit.

### Endpoints currently gated

* `POST /api/v1/jobs`
* `POST /api/v1/jobs/{id}/retry`
* `GET /api/cfbd/mac/benchmark` (Issue #163 — cross-conference aggregation)

These two endpoints currently authorize via `require_any_staff` and apply
workload gating independently. The `heavy_workload:trigger` policy row is
reserved for endpoints that explicitly opt into `require_policy(...)`.

The gating dependency is intentionally cheap and reusable — apply it to
additional heavy endpoints (embedding rebuilds, video re-renders, bulk
exports) as those land.

### Health/workload status surface

`GET /api/v1/health/workload` returns the current snapshot for operators.
It is restricted to the `health_workload:read` policy (admin / analyst /
sports-performance) and contains aggregate counters only — no per-player or
per-job identifiers.

## 5. Audit logging

`audit_event(event, **fields)` in `app.governance` is the single emitter for
governance audit lines.  It hard-limits the fields it will serialize
(`_AUDIT_ALLOWED_KEYS`) and coerces values to scalars to guarantee that
medical data, names, or large payloads never end up in the log stream.

Events to expect:

* `audit.access.denied`
* `audit.visibility.applied`
* `audit.visibility.changed`
* `audit.visibility.mode_denied`
* `audit.visibility.archived_hidden`
* `audit.visibility.player_view_blocked`
* `audit.visibility.recruiting_blocked`
* `audit.gating.allowed`
* `audit.gating.rejected`
* `audit.health_workload.read`

These follow the existing structlog JSON format and can be filtered by
`event=audit.*` in log aggregators.

## 6. Extending the policy

When adding a new sensitive surface:

1. Add a `Resource` member and any new `Action` members to
   `app.governance`.
2. Add the explicit row(s) to `POLICY`.  Default-deny means missing roles are
   already rejected.
3. Use `Depends(require_policy(resource, action))` on the router.
4. For heavy work, additionally apply
   `Depends(require_workload_capacity("module.endpoint"))`.
5. Add tests in `backend/tests/test_governance.py` /
   `test_workload_gating.py` covering the role matrix and the gating
   behaviour.

## 7. Integration placeholders

Health and workload data sources beyond `processing_jobs` (GPS/wearables,
S&C platforms, wellness surveys) are out of scope for this batch.  When
those integrations land, they should publish snapshots through the existing
`assess_workload` interface (or a sibling sampler) and remain subject to the
`health_workload:read` policy.
