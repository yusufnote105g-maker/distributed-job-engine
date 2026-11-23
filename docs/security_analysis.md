# Security analysis

## Threat model

The service accepts job payloads over HTTP and executes them in-process. The
main risks are therefore unauthorised submissions, payload-driven abuse, and
resource exhaustion. It is assumed to run behind a trusted network boundary or
an API gateway.

## Controls present

| Area | Control |
| --- | --- |
| Transport | None built in — terminate TLS at a reverse proxy |
| Authentication | Optional shared key in `X-API-Key`; compared in constant time (`hmac.compare_digest`) against `SECRET_KEY`; empty key disables auth |
| Input validation | Pydantic models: payload length, enum priority, timeout 1–86400, retries 0–100, idempotency key ≤64 |
| SQL injection | All access goes through SQLAlchemy Core constructs with bound parameters; no string-formatted SQL in `src/` |
| Error leakage | 5xx responses return a generic message; stack traces go to the server log only |
| Container | Docker image runs as a non-root user (uid 10001) |
| CORS | `allow_origins=["*"]` with `allow_credentials=False` — no cookie-based auth is possible, but it is permissive by design |

## Risks and mitigations

**Unauthenticated access.** With `SECRET_KEY` unset, anyone who can reach the
port can enqueue jobs. Mitigation: set `SECRET_KEY` and keep the service
private.

**Static key comparison.** Keys are compared with `hmac.compare_digest`, so the
comparison is constant-time. The remaining weakness is that the key is shared,
long-lived and not rotated automatically.

**No rate limiting.** A client can submit jobs until the database or memory
fills. Mitigation: rate-limit at the proxy, cap `total` pending jobs, or add a
token bucket.

**Resource exhaustion per job.** Payloads can request a long `sleep`; the
per-job `timeout` and `max_retries` bound the damage, and `worker_count` bounds
concurrency.

**Payload trust.** The default runner only understands `noop`, `sleep`, `fail`
and `flaky`. It never evaluates code. If you replace `_execute_payload` with
something that shells out or unpickles data, that becomes the primary attack
surface — validate strictly and never deserialize untrusted pickles.

**Secrets in the database.** Payloads are stored verbatim. Do not put
credentials in payloads; store a reference instead.

**Logging.** Job ids, priorities and error strings are logged. Payload contents
are not logged, which keeps accidental secret leakage low.

## Recommendations before production

1. Set `SECRET_KEY` and terminate TLS in front of the service.
2. Add per-client rate limiting and a cap on pending jobs.
3. Rotate the shared key periodically and keep it out of source control.
4. Restrict CORS to known origins.
5. Move to Postgres if more than one writer node is needed.
6. Ship logs and metrics to a central system; add alerting on `dead_letter`
   growth and on `/health` returning `degraded`.
