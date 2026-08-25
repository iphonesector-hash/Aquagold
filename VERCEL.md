# Vercel target

AquaGold production architecture is Vercel + a dedicated Neon Postgres/PostGIS database.

Deployment expectations:
- Production uses the Neon main branch.
- Preview deployments use the connected Neon preview/database branch integration when available.
- The browser never receives the database connection string; all database access stays in the Flask/Vercel backend.
- `app.py` is the production Flask entrypoint and `vercel.json` contains the Vercel function configuration.

Preview verification completed successfully. This main-branch update intentionally triggers the production deployment.
