# Security operations

## Authentication and authorization

Successful login creates a high-entropy opaque token. Only its SHA-256 digest is stored in `auth_sessions`; the raw token is delivered in the `aquagold_session` cookie with `HttpOnly`, `SameSite=Strict`, and `Secure` in production. Logout revokes the session server-side.

Cookie-authenticated mutations also require `X-CSRF-Token`, matched against the session's stored digest. Every offline-capable mutation carries an `Idempotency-Key` UUID so a network retry cannot create a second business record.

Role hierarchy:

| Role | Read | Field mutations | Finance/product administration | Audit/export |
|---|---:|---:|---:|---:|
| `viewer` | Yes | No | No | No |
| `technician` | Yes | Yes | No | No |
| `admin` | Yes | Yes | Yes | Yes |
| `superadmin` | Yes | Yes | Yes | Yes |

## Production checklist

- Generate a unique `AQUAGOLD_SECRET_KEY` of at least 32 random characters.
- Use an exact `ALLOWED_ORIGINS` allowlist; never use `*` with credentialed requests.
- Keep Neon, Groq and rate-limit store credentials in deployment secrets only.
- Treat Groq as a data processor: when configured, the smart-intake text (which can contain names, phones and addresses) is sent to its API. Obtain the appropriate customer notice/consent and review retention terms.
- Remove bootstrap administrator variables immediately after provisioning.
- Use a shared Redis-compatible `RATELIMIT_STORAGE_URI` when the application scales beyond one process/instance.
- Review audit entries and failed login/rate-limit events in operational logs.
- Periodically delete expired `auth_sessions` and `api_idempotency` rows.
- Test account deactivation and session revocation during every release rehearsal.

The response policy denies framing and object embedding, restricts scripts and connections to self-hosted application assets and required map tiles, enables HSTS in production, and disables API caching. Tailwind's browser runtime and Alpine expressions currently require the CSP `unsafe-inline`/`unsafe-eval` script allowances; moving to a compiled CSS/JavaScript bundle is the next hardening step if the UI build system is introduced.

The optional device PIN is a convenience screen lock, not encryption or a replacement for the operating system passcode. Cached/offline CRM data remains protected by the iPhone/Android device security boundary and is erased by the application on logout.

## Incident actions

For a suspected session leak, deactivate the affected user and set `revoked_at=now()` on that user's active sessions. For credential exposure, rotate the provider credential first, update the deployment secret, redeploy, then review access logs. Never paste production connection strings into issues, commits, or client-side code.
