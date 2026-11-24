"""Small shared helpers."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC time as a naive ``datetime``.

    ``datetime.utcnow()`` is deprecated since Python 3.12. This helper keeps
    exactly the same value (UTC, no ``tzinfo``) so stored timestamps and the
    public API stay unchanged, without emitting a deprecation warning.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
