# Health & Workload surface (Issue #113)

Status: groundwork. The surface is **role-gated, audit-logged, and policy-safe**,
but **no athlete health or workload data is surfaced yet** — every upstream
source is a documented contract in `not_connected` state.

This document is the contract for the athlete health/workload product surface:
who may see it, what the UI may say, what it audits, and the placeholder
integration contracts that future feeds must satisfy. It complements
[`governance.md`](governance.md), which owns the platform-wide RBAC/audit
layer.

> **Naming note.** This surface (athlete wellness / training load) is **not**
> the same thing as `GET /api/v1/health/workload` in
> [`governance.md` §4](governance.md), which reports *system GPU-queue capacity*
> for the job-gating layer. They share the `health_workload` policy name by
> history only.

## 1. Role-based access

The surface is restricted to the central RBAC policy
`app.governance.POLICY[(Resource.HEALTH_WORKLOAD, Action.READ)]`:

| Role                | Health & Workload access |
|---------------------|--------------------------|
| `admin`             | ✅ |
| `analyst`           | ✅ (analytics lead)      |
| `sportsperformance` | ✅ (S&C / wellness staff) |
| `coach`             | ❌ |
| `player`            | ❌ |
| `viewer`            | ❌ |

Coaches are intentionally excluded: sports performance is a *parallel* track,
not a coaching view (see `app/deps.py` `require_sportsperformance_or_above`).

### Backend access pattern

`GET /api/v1/health-workload/surface` returns the policy-safe surface status.
It is gated by `require_policy(Resource.HEALTH_WORKLOAD, Action.READ)`:

* approved roles → `200` with the surface status (below);
* any other role → `403` with `error_code: "policy_denied"`.

The payload carries **no athlete PII** — only the viewer's role, the approved-role
list, the placeholder integration contracts, and the disclaimer:

```jsonc
{
  "role": "sportsperformance",
  "data_available": false,
  "disclaimer": "Training-load and wellness context for sports-performance staff only. …",
  "approved_roles": ["admin", "analyst", "sportsperformance"],
  "integrations": [
    { "source": "wellness", "status": "not_connected", "data_categories": ["self_reported_soreness", …], … },
    { "source": "gps_wearables", "status": "not_connected", … },
    { "source": "strength_conditioning", "status": "not_connected", … }
  ]
}
```

Source of truth: `app/health_workload.py` (contracts + `build_surface_status`)
and `app/routers/health_workload.py` (the gated route).

### Frontend gating

The UI is **hidden unless the role is approved**, enforced in two places so a
deep link cannot bypass it:

* **Navigation** — `football-shell.tsx` filters the "Health & Workload" entry
  out for non-approved roles.
* **Page** — the `HealthWorkload` view in `page-renderer.tsx` renders a
  *restricted* notice instead of the surface when the role is not approved. The
  dashboard "Workload & Health" teaser follows the same gate.

Client-side role is resolved by `frontend/src/lib/roles.ts` (`resolveCurrentRole`):

1. the JWT `role` claim when signed in (re-verified by the backend on every
   request — the client gate is *display only*, never a security boundary);
2. a `NEXT_PUBLIC_DEMO_ROLE` override for demos/screenshots;
3. a safe default of `coach`, which is **not** approved — so the surface stays
   hidden until a real session proves an approved role.

To preview the approved-role experience locally, set
`NEXT_PUBLIC_DEMO_ROLE=sportsperformance` (or `analyst` / `admin`).

## 2. Audit logging

Every read of the surface emits a structured audit line via
`app.governance.audit_event`, carrying only the actor UUID, role, and the
`(resource, action)` pair plus a coarse `surface` label — **never** athlete
metrics, names, or other PII (the emitter hard-limits its allow-listed keys).

| Event                                   | When |
|-----------------------------------------|------|
| `audit.health_workload.surface.read`    | A `GET /surface` succeeds for an approved role. |
| `audit.access.denied`                   | A non-approved role is rejected by `require_policy`. |

When real data feeds land, each athlete-data read must emit its own
`audit.health_workload.*` event following the same allow-listed-keys discipline.

## 3. Policy-safe UI copy

The surface is sports-performance *context*, not medicine. UI copy must avoid
diagnosis, injury-risk, or return-to-play claims.

**Do**
* "Training-load and wellness context."
* "Supports staff judgement; it does not replace it."
* Mark illustrative/sample values with the mock badge.
* Show the disclaimer (`HEALTH_WORKLOAD_DISCLAIMER`) on the surface.

**Don't**
* "Injury risk", "readiness score", "return-to-play", "diagnosis", "medical".
* Imply prediction of injury or a clinical assessment.
* Surface raw athlete health values without an approved role and audit trail.

The disclaimer string lives once in `app/health_workload.py` (backend) and
`frontend/src/lib/health-workload.ts` (frontend) and is shown verbatim.

## 4. Placeholder integration contracts

Three upstream sources are planned. All are `not_connected`; connecting one is
a future, separately reviewed change that must keep passing the policy/audit
gates above. Categories are deliberately **coarse and non-diagnostic**.

| Source (`source`)         | Display name              | Data categories (planned)                               | Provider examples |
|---------------------------|---------------------------|---------------------------------------------------------|-------------------|
| `wellness`                | Wellness self-report      | self-reported soreness, sleep, energy                   | Team wellness questionnaire; athlete check-in app |
| `gps_wearables`           | GPS / wearables           | total distance, high-speed distance, accelerations, player load | GPS tracking vest; wrist/chest wearable |
| `strength_conditioning`   | Strength & conditioning   | session volume, tonnage, session RPE                    | S&C session log; weight-room tracking sheet |

Wellness data is **self-reported context**, never a clinical assessment.

## 5. Tests

* Backend — `backend/tests/test_health_workload_surface.py`: RBAC gate
  (approved vs. denied roles), policy-safe payload (no PII), and the three
  contracts all starting `not_connected`.
* Frontend — `frontend/src/app/health-workload/health-workload.test.tsx` and
  `frontend/src/lib/roles.test.ts`: nav + page gating per role and the role-resolution
  helpers.

When real endpoints land, add authorization tests for each per-athlete read
(acceptance criterion: "Tests cover authorization behavior once endpoints
exist").
