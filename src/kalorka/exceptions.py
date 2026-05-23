"""Exception hierarchy for kalorka."""
from __future__ import annotations


class KalorkaError(Exception):
    """Base class for everything this library raises."""


class ConfigError(KalorkaError):
    """Configuration is missing or invalid (e.g. no credentials)."""


class AuthenticationError(KalorkaError):
    """Login was rejected by the server."""


class APIError(KalorkaError):
    """The server returned a non-success response.

    The raw ``status`` and ``body`` are kept so callers can inspect them.
    """

    def __init__(self, status: int, body: str, message: str | None = None) -> None:
        self.status = status
        self.body = body
        super().__init__(message or f"HTTP {status}: {body[:200]}")


class NotFoundError(APIError):
    """A requested resource (entry id, date, …) doesn't exist."""
