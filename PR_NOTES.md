# AquaGold production hardening

This change consolidates the active v4 application and adds:

- revocable cookie sessions, CSRF, rate limits, roles and audit controls;
- ordered, checksummed migrations plus phone uniqueness and overpayment integrity;
- strict API validation and PostgreSQL/PostGIS integration tests;
- paginated customer/service queries and Neon pooled connections;
- self-hosted pinned frontend dependencies and security headers;
- a user-bound IndexedDB offline cache, ordered idempotent mutation replay and PWA shell;
- server-side geocoding and road-aware route planning with a documented fallback;
- a disposable PostGIS CI database, dependency auditing and deployment runbook.

Production migration and promotion are intentionally separate approval-gated operations. Test the exact commit on a Neon branch and Vercel Preview before touching the production database.
