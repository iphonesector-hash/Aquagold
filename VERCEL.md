# Vercel target

AquaGold production architecture is Vercel + a dedicated Neon Postgres/PostGIS database.

Deployment expectations:
- Production uses the Neon main branch database.
- Preview deployments use isolated preview/database branches when available.
- The browser never receives the database connection string; all database access stays in the Flask/Vercel backend.
- `app.py` is the production Flask entrypoint and `vercel.json` contains the Vercel function configuration.

Preview verification completed successfully. This post-merge branch update is only to trigger the currently configured Vercel production branch so the public alias can move to the verified build.
