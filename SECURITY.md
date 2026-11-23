# Security policy

## Supported versions

Only the `master` branch (and tagged `v*` releases) receives security fixes.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private vulnerability
reporting: repository **Security → Advisories → Report a vulnerability**. Include
the affected endpoint or component, a reproduction, and the impact you expect.

You can expect an initial acknowledgement within a few days. There is no bug
bounty.

## Security posture

The service is designed to run behind a trusted network boundary or an API
gateway. It is not hardened for direct exposure to the public internet.

* **Authentication is optional.** Set `SECRET_KEY` to require `X-API-Key` on
  write endpoints. An empty key disables authentication entirely.
* **Key comparison is constant-time** (`hmac.compare_digest`), but the key is a
  single shared secret with no rotation or scopes.
* **No TLS, rate limiting or per-client quotas** are built in. Terminate TLS and
  apply rate limits at the proxy.
* **Payloads are not sandboxed.** The bundled runner only understands `noop`,
  `sleep`, `fail` and `flaky` and never evaluates code. Replacing
  `_execute_payload` with shell-outs or deserialisation changes the threat model.
* **Payloads are stored verbatim.** Do not put credentials or personal data in
  job payloads; store a reference instead.
* **SQLite is a single-writer store.** Run one writer node, or move to
  PostgreSQL before scaling out.

See [`docs/security_analysis.md`](docs/security_analysis.md) for the full threat
model and [`docs/known_limitations.md`](docs/known_limitations.md) for
operational limits.

## Deployment checklist

1. Set a strong `SECRET_KEY`; keep it out of source control.
2. Terminate TLS and add rate limiting in front of the API.
3. Restrict CORS to known origins (the default is `*`).
4. Run the container as a non-root user (the provided image already does).
5. Back up the SQLite file or use a managed PostgreSQL instance.
6. Alert on `/health` returning `degraded` and on `dead_letter` growth.
