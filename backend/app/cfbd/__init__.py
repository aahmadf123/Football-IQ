"""Backend-only College Football Data (CFBD) integration.

Football-IQ calls CFBD from the FastAPI backend only (Issues #160/#161/#162).
The vendor API key (``CFBD_API_KEY``) must never reach frontend code, browser
bundles, logs, or coach-visible errors, and is never persisted to the database.

Submodules:
    errors   — explicit CFBD error classes.
    schemas  — typed Pydantic v2 response models.
    client   — async ``CFBDClient`` (bearer auth, retries/backoff, rate limits).
    models   — Postgres cache table ORM models.
    sync     — idempotent Toledo/MAC ingestion into the cache tables.

Imports here are kept light on purpose: ``app.models`` imports
``app.cfbd.models`` to register the cache tables with ``Base.metadata``, so this
package must not pull in heavy HTTP dependencies at import time.
"""
