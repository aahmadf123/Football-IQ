# Frontend mock mode

The Football-IQ frontend can run in three modes, gated by environment variables.

| Mode    | Env                                                  | Behavior                                                                  |
| ------- | ---------------------------------------------------- | ------------------------------------------------------------------------- |
| Mock    | `NEXT_PUBLIC_USE_MOCKS=1`                            | Boots with `frontend/src/lib/mock-data.ts`. Status badge shows "Mock data". No network calls. |
| Live    | `NEXT_PUBLIC_API_URL=https://api.example.com`        | Boots empty, fetches `/api/v1/videos`, `/api/v1/jobs`, `/api/v1/self-scout/tendencies`. Empty responses stay empty — no silent mock substitution. |
| Offline | neither set (default)                                 | Boots empty. Status badge shows "API offline". Empty states everywhere. |

Mock mode is for local development, demos, and screenshots. It is **never** the default in production: empty data must surface as empty states, and API failures must surface as offline states, so the product never gives the false impression that it is more connected than it is.

## How to run each mode

```bash
# Default (offline) — empty states, "API offline" badge
cd frontend && npm run dev

# Mock — populated demo data, "Mock data" badge
NEXT_PUBLIC_USE_MOCKS=1 npm run dev

# Live — points at a real backend, no mock fallback
NEXT_PUBLIC_API_URL=https://api.example.com npm run dev
```

## What changed in the shell

- `frontend/src/components/football-shell.tsx` System Status panel now reports the real API connectivity instead of hardcoded "Connected / Enabled / v2.4.1" values.
- The Confidence Score donut was hardcoded at 92%; it now renders an empty state until per-clip confidence is wired (`#102`).
- Several decorative panels (Biomechanics, Analytics Model Quality, Health Trend, Settings sensitivity) are flagged with a small "Mock data" badge to communicate that those numbers are not yet sourced from a real pipeline.

## How fallback used to work, and why it changed

Previously `frontend/src/lib/app-state.tsx` initialized state with `footballData` and silently fell back to mock on any API failure or empty response. That made a fully empty backend look like a fully populated product. The current implementation:

- Initial state: `useMocks() ? footballData : emptyFootballData`.
- Empty arrays from the API are accepted as valid live data.
- API failures degrade to `offline` and the UI shows the badge — no mock substitution.

See `docs/adr/0001-session-kind-possession-side-of-ball-and-single-camera.md` for the data-model decisions that this work makes room for.
