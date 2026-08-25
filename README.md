# AquaGold CRM

AquaGold is a Persian, mobile-first CRM/PWA for water-purifier field service teams. It combines customer and phone management, service visits, financial reports, expenses, settlements, a product catalog and invoices, GPS/PostGIS search, server-side geocoding and route planning, and assisted intake from Persian service messages.

## Production stack

- Flask/Gunicorn API deployed as a Vercel Python function
- Neon PostgreSQL with PostGIS and `pg_trgm`
- Alpine.js, MapLibre GL, Chart.js and Tailwind browser runtime, pinned and self-hosted
- Cookie sessions, CSRF protection, role guards, audit records and request idempotency
- Installable PWA with an IndexedDB cache and ordered offline mutation queue

## Local setup

Requirements: Python 3.12+, PostgreSQL 16+ with PostGIS, and Node.js 20+ for JavaScript checks.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/migrate.py
python app.py
```

The application is served at `http://127.0.0.1:5000`. Environment variables from `.env` must be exported by your shell or process manager; the application deliberately does not load local secret files itself.

Create the first administrator only during initial provisioning by setting `AQUAGOLD_ADMIN_USERNAME` and `AQUAGOLD_ADMIN_PASSWORD`. Remove both variables after the account exists.

For a disposable local PostGIS stack, set `AQUAGOLD_DB_PASSWORD` and `AQUAGOLD_SECRET_KEY` in `.env`, then run `docker compose up --build`. Compose applies migrations before starting Gunicorn and exposes the app through nginx on port 80.

## Database migrations

Migrations are immutable and run in lexical order:

1. `001_core_app.sql`
2. `002_crm_geo.sql`
3. `003_finance_reports.sql`
4. `004_commerce.sql`
5. `005_security_integrity.sql`

Before migration 005 on an existing database, run:

```bash
psql "$AQUAGOLD_DATABASE_URL" -f scripts/check_phone_duplicates.sql
python scripts/migrate.py
```

The migration runner uses a PostgreSQL advisory lock and stores SHA-256 checksums in `schema_migrations`. It refuses to continue if an already-applied migration was edited.

## Tests and quality gates

```bash
python -m py_compile *.py scripts/*.py
ruff check --select=E9,F63,F7,F82 *.py scripts tests
pytest -q
for file in *.js; do node --check "$file"; done
pip-audit -r requirements.txt
```

Integration tests require `TEST_DATABASE_URL` pointing to a disposable PostgreSQL/PostGIS database. The GitHub Actions workflow provisions one automatically, applies all migrations from zero, and runs the full suite.

## Security model

- Browser authentication uses a random, revocable, server-side session in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie.
- Unsafe requests require a matching CSRF token and support an `Idempotency-Key` UUID.
- Roles are ordered as `viewer`, `technician`, `admin`, and `superadmin`.
- Customer, service, finance, product and invoice mutations are validated server-side and audited.
- Database credentials and AI provider keys stay on the server.

See [docs/SECURITY.md](docs/SECURITY.md), [docs/OFFLINE_AND_ROUTING.md](docs/OFFLINE_AND_ROUTING.md), and [VERCEL.md](VERCEL.md) for operational details.
