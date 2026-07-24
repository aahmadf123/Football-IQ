"""Seed the admin and GPU-worker service accounts (idempotent).

Usage (env-driven so compose can run it unattended):

    SEED_ADMIN_EMAIL=admin@example.com SEED_ADMIN_PASSWORD=... \\
    SEED_WORKER_EMAIL=worker@example.com SEED_WORKER_PASSWORD=... \\
    python -m scripts.seed_users

Use a routable domain: the login endpoint validates emails with
``EmailStr``, which REJECTS reserved special-use domains like ``.local`` —
an account seeded at ``worker@footballiq.local`` could never authenticate.

Existing accounts are left untouched (their passwords are NOT rotated) —
re-running is always safe. The worker account gets the ``analyst`` role,
which every writeback route accepts via ``require_any_staff``.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import structlog
from app.auth import hash_password
from app.config import get_settings
from app.models import User, UserRole
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

log = structlog.get_logger(__name__)


async def _ensure_user(
    session: AsyncSession, email: str, password: str, full_name: str, role: UserRole
) -> bool:
    """Create the account if absent; return True when created."""
    # Store the canonical (lowercased) email so it matches the login
    # endpoint's normalization — otherwise a seeded "Admin@X" never matches
    # a sign-in as "admin@x".
    email = email.strip().lower()
    existing = await session.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        log.info("seed_user_exists", email=email)
        return False
    session.add(
        User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=role,
        )
    )
    log.info("seed_user_created", email=email, role=role.value)
    return True


async def main() -> int:
    admin_email = os.environ.get("SEED_ADMIN_EMAIL", "")
    admin_password = os.environ.get("SEED_ADMIN_PASSWORD", "")
    worker_email = os.environ.get("SEED_WORKER_EMAIL", "")
    worker_password = os.environ.get("SEED_WORKER_PASSWORD", "")

    if not any([admin_email, worker_email]):
        print(
            "Nothing to seed: set SEED_ADMIN_EMAIL/SEED_ADMIN_PASSWORD and/or "
            "SEED_WORKER_EMAIL/SEED_WORKER_PASSWORD.",
            file=sys.stderr,
        )
        return 2

    engine = create_async_engine(get_settings().database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    created = 0
    async with session_factory() as session:
        if admin_email:
            if not admin_password:
                print("SEED_ADMIN_PASSWORD is required with SEED_ADMIN_EMAIL", file=sys.stderr)
                return 2
            created += await _ensure_user(
                session, admin_email, admin_password, "Administrator", UserRole.admin
            )
        if worker_email:
            if not worker_password:
                print("SEED_WORKER_PASSWORD is required with SEED_WORKER_EMAIL", file=sys.stderr)
                return 2
            created += await _ensure_user(
                session, worker_email, worker_password, "GPU Worker", UserRole.analyst
            )
        await session.commit()
    await engine.dispose()
    print(f"Seed complete: {created} account(s) created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
