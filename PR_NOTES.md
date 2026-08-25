# AquaGold Smart CRM rollout

## Verified
- Dedicated Neon Postgres project is active and separate from existing apps.
- PostgreSQL 18 schema is applied on Neon main.
- PostGIS and pg_trgm are enabled.
- Customer, multiple phones, service visits, service items, intake sessions, users, and inventory schemas are in place.
- GPS proximity lookup was tested with the Sadeghi sample and returned the customer at ~5m with both phone numbers and 5,600,000 last amount.
- Vercel Git integration is connected to this repository.
- Preview deployment reached READY.
- Preview `/health` returned HTTP 200 with `{database: neon, status: healthy}`.
- CORS configuration was corrected for the Vercel production/branch aliases.

## Production rollout
After this verified preview, merge PR #1 into `main`. Vercel Git integration should then produce a fresh production deployment for `aquagold-db.vercel.app`.
