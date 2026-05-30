"""Analytics helpers that are pure (no FastAPI / DB dependencies).

These modules hold the deterministic football math behind self-scout
tendency-break alerts (Issue #137) so routers stay thin and the logic is
unit-testable without a database or HTTP client.
"""
