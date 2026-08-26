# Vercel + Neon deployment

AquaGold runs as a Flask function on Vercel and uses a dedicated Neon PostgreSQL/PostGIS database. `app.py` is the production entry point. The browser never receives a database URL or provider credential.

## Required production variables

- `AQUAGOLD_DATABASE_URL`: Neon direct URL for migrations; the runtime automatically switches a Neon hostname to its pooled endpoint.
- `AQUAGOLD_SECRET_KEY`: unique random value of at least 32 characters.
- `AQUAGOLD_ENV=production`
- `ALLOWED_ORIGINS` is optional: set comma-separated exact HTTPS origins only when cross-origin browser access is intentionally required. Same-origin Vercel aliases do not need CORS.

Optional variables are documented in `.env.example`. Provisioning-only administrator credentials must be removed after first use.

## Safe release sequence

1. Create a Neon branch from production and test the migration there.
2. Run `scripts/check_phone_duplicates.sql`; resolve any cross-customer duplicate before migration 005.
3. Apply `python scripts/migrate.py` to the preview database.
4. Deploy the Git branch as a Vercel Preview and verify `/health`, login, customer creation, service creation, offline replay, map, invoice and role restrictions.
5. Take a fresh Neon restore point/branch from production.
6. Apply the same migrations to production.
7. Promote the already-verified Vercel deployment.
8. Smoke-test `/health` and one read-only authenticated flow, then monitor function errors and database connections.

Do not point preview deployments at the Neon production branch. Do not run production migrations from a developer laptop unless the exact target has been independently verified.
