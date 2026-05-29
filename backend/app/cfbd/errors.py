"""Explicit error classes for the CFBD client.

These let callers distinguish configuration problems (missing key) from
transport, auth, rate-limit, and upstream-status failures, and they keep error
messages free of the API key so nothing sensitive surfaces in logs or
coach-visible responses.
"""

from __future__ import annotations


class CFBDError(Exception):
    """Base class for all CFBD client errors."""


class CFBDConfigError(CFBDError):
    """Raised when the CFBD client is used without a configured API key.

    This is a backend-only failure: the message intentionally never contains
    the key (there is none) and points operators at the env var rather than
    leaking any value.
    """


class CFBDAuthError(CFBDError):
    """Raised on a 401/403 from CFBD (bad or unauthorized key)."""

    def __init__(self, message: str = "CFBD rejected the credentials (401/403)") -> None:
        super().__init__(message)


class CFBDRateLimitError(CFBDError):
    """Raised when CFBD returns 429 and retries have been exhausted."""

    def __init__(
        self,
        message: str = "CFBD rate limit exceeded after retries",
        *,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class CFBDClientError(CFBDError):
    """Raised on a non-retryable 4xx response (other than 401/403/429)."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class CFBDServerError(CFBDError):
    """Raised on a 5xx response after retries are exhausted."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class CFBDTransportError(CFBDError):
    """Raised when the request fails at the transport layer after retries."""
