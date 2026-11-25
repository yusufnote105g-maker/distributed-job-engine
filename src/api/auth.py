"""API-key authentication with scopes and a simple rate limit.

Keys are configured through ``API_KEYS``, a semicolon-separated list of
``name:scopes:secret`` entries (scopes joined by ``+``):

    API_KEYS="ci:read+write:secret-one; dashboard:read:secret-two"

``SECRET_KEY`` keeps working as a single key named ``default`` with every scope,
so existing deployments do not break. When no key is configured at all,
authentication is disabled and requests are anonymous (all scopes).

Rotation without downtime: add the new key, deploy, switch clients, then remove
the old key and deploy again. Both keys are valid in between.

The rate limit is per key (or per client IP when auth is disabled) and is
in-process: N replicas allow N × ``RATE_LIMIT_PER_MINUTE``. A shared limit needs
a shared store; this is documented in ``docs/known_limitations.md``.
"""

import hashlib
import hmac
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, FrozenSet, Iterable, List, Optional

from fastapi import HTTPException, Request, status

READ = "read"
WRITE = "write"
ADMIN = "admin"
ALL_SCOPES: FrozenSet[str] = frozenset({READ, WRITE, ADMIN})
KNOWN_SCOPES = ALL_SCOPES


@dataclass(frozen=True)
class ApiKey:
    name: str
    scopes: FrozenSet[str]
    secret: str


@dataclass(frozen=True)
class AuthContext:
    name: str
    scopes: FrozenSet[str]
    authenticated: bool


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def parse_api_keys(raw: str) -> List[ApiKey]:
    """Parse ``name:scopes:secret`` entries separated by ``;``.

    Invalid entries fail loudly at startup instead of silently disabling auth.
    """
    keys: List[ApiKey] = []
    for entry in (part.strip() for part in raw.split(";")):
        if not entry:
            continue
        name, separator, rest = entry.partition(":")
        if not separator or not name.strip() or not rest.strip():
            raise ValueError(
                f"Invalid API_KEYS entry {entry!r}: expected name:scopes:secret"
            )
        scopes_raw, separator, secret = rest.partition(":")
        if not separator or not secret:
            raise ValueError(
                f"Invalid API_KEYS entry for {name!r}: expected name:scopes:secret"
            )
        scopes = frozenset(
            scope.strip().lower()
            for scope in scopes_raw.split("+")
            if scope.strip()
        )
        unknown = scopes - KNOWN_SCOPES
        if unknown:
            raise ValueError(
                f"Unknown scope(s) {sorted(unknown)} for key {name!r}; "
                f"known: {sorted(KNOWN_SCOPES)}"
            )
        if not scopes:
            raise ValueError(f"API key {name!r} has no scopes")
        keys.append(ApiKey(name=name.strip(), scopes=scopes, secret=secret))
    return keys


def build_keys(config) -> List[ApiKey]:
    """Combine ``API_KEYS`` with the legacy single ``SECRET_KEY``."""
    keys = parse_api_keys(getattr(config, "api_keys", "") or "")
    legacy = getattr(config, "secret_key", "") or ""
    if legacy and not any(key.secret == legacy for key in keys):
        keys.append(ApiKey(name="default", scopes=ALL_SCOPES, secret=legacy))
    return keys


def authenticate(keys: Iterable[ApiKey], provided: Optional[str]) -> Optional[ApiKey]:
    """Return the matching key, comparing digests in constant time."""
    if not provided:
        return None
    provided_digest = _digest(provided)
    for key in keys:
        if hmac.compare_digest(provided_digest, _digest(key.secret)):
            return key
    return None


def has_scope(scopes: FrozenSet[str], required: str) -> bool:
    return ADMIN in scopes or required in scopes


def client_identity(request: Request, config) -> str:
    if getattr(config, "trust_forwarded_for", False):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


class RateLimiter:
    """Sliding-window counter: at most ``limit`` hits per identity per minute."""

    def __init__(self, limit_per_minute: int, window_seconds: float = 60.0):
        self.limit = max(0, int(limit_per_minute))
        self.window = window_seconds
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, identity: str) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            hits = self._hits.setdefault(identity, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


def require_scope(scope: str):
    """FastAPI dependency enforcing authentication, scope and rate limit."""

    def dependency(request: Request) -> AuthContext:
        config = request.app.state.config
        keys: List[ApiKey] = getattr(request.app.state, "api_keys", [])
        limiter: Optional[RateLimiter] = getattr(
            request.app.state, "rate_limiter", None
        )

        if keys:
            provided = request.headers.get(config.api_key_header)
            key = authenticate(keys, provided)
            if key is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid API key",
                    headers={"WWW-Authenticate": config.api_key_header},
                )
            identity = key.name
            context = AuthContext(name=key.name, scopes=key.scopes, authenticated=True)
        else:
            identity = client_identity(request, config)
            context = AuthContext(
                name="anonymous", scopes=ALL_SCOPES, authenticated=False
            )

        if not has_scope(context.scopes, scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key lacks the '{scope}' scope",
            )

        if limiter is not None and not limiter.allow(identity):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": "60"},
            )

        if context.authenticated:
            request.state.api_key_name = context.name
        return context

    return dependency
