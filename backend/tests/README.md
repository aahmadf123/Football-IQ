# Backend tests

Pytest suite for the FastAPI backend. Run from the `backend/` directory:

```sh
# All tests
pytest -v

# A single file
pytest tests/test_videos.py -v
```

CI runs `pytest -v --cov=app --cov-report=xml` against every PR
(see `.github/workflows/ci.yml`). The `SECRET_KEY` and `DATABASE_URL`
env vars are required for `app.config.Settings` to load — CI sets both,
and locally any valid-shaped value is fine because the round-trip tests
never open a real DB connection.

## Fixture & mocking conventions

The router tests do not start a Postgres instance. Instead they override
two FastAPI dependencies and pass an `AsyncMock` session into the route:

| Dependency           | Replaced with                                        |
| -------------------- | ---------------------------------------------------- |
| `app.deps.get_current_user` | a `MagicMock(spec=User)` with the role being tested  |
| `app.database.get_db`       | an async generator yielding an `AsyncMock` session  |

The async session typically wires:

- `session.execute = AsyncMock(side_effect=…)` — returns a `MagicMock`
  whose `.scalar_one_or_none()`, `.scalars().all()`, `.scalar()`, or
  `.mappings()` is preconfigured per-call.
- `session.add = MagicMock(side_effect=captured.append)` — when a test
  needs to assert what was inserted.
- `session.flush = AsyncMock(side_effect=_flush)` — stand-in for
  `server_default=func.now()` and other Postgres-side defaults so that
  responses can serialize.

For filter tests, `side_effect` captures the rendered SQL via
`stmt.compile(compile_kwargs={"literal_binds": False})` and asserts on
substrings such as `videos.recorded_at >=`. This catches "filter was
declared but never wired into the `WHERE` clause" regressions without
needing a real database.

See `test_videos.py` for the canonical pattern, and the `*_round_trip.py`
files (videos, clips, jobs, inbox, events, corrections) for full
metadata-persistence coverage of the coach workflow.

## Adding a new test

1. Copy the helper shape from `test_jobs_round_trip.py` (simplest example).
2. Build ORM-shaped fixtures with `MagicMock(spec=YourModel)` and set the
   attributes your serializer reads. Do **not** instantiate real ORM
   classes — they would try to load relationships from the mocked DB.
3. Always wrap `TestClient(app)` and override clearing in `try/finally`
   so that a failing assertion does not leak dependency overrides into
   the next test.
