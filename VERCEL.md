# Vercel target

AquaGold production architecture is Vercel + a dedicated Neon Postgres/PostGIS database.

Deployment expectations:
- Production uses the Neon main branch.
- Preview deployments use the connected Neon preview/database branch integration when available.
- The browser never receives the database connection string; all database access stays in the Flask/Vercel backend.
- `app.py` is the production Flask entrypoint and `vercel.json` contains the Vercel function configuration.

Usable CRM interface includes customer creation, service creation, customer history, GPS/map, nearby-customer search, and Smart Intake. This branch update triggers a fresh Vercel preview for end-to-end verification.
