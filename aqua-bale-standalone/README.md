# AquaGold Bale — Standalone Runtime

This directory is intentionally isolated from the AquaGold production web app.

## Vercel
- Production branch: `standalone/aqua-bale-20260906`
- Root Directory: `aqua-bale-standalone`
- Required database environment value copied from the existing AquaGold project: `AQUAGOLD_DATABASE_URL` (or `DATABASE_URL`).
- On the dedicated `aquagold-bale` Vercel project, the database variable is intended for Preview deployments of the standalone branch only until final promotion is approved.
- `AQUAGOLD_SECRET_KEY` is preferred when the original project defines it. If the original AquaGold deployment has no explicit secret, the standalone entrypoint reuses AquaGold's stable runtime-secret bootstrap so the same database URL produces the same encryption/session secret material.
- With the same DB + secret behavior, this runtime can read the existing encrypted `bale_bot` token, webhook secret and allowed group IDs from `app_settings`. Optional overrides: `BALE_BOT_TOKEN`, `BALE_WEBHOOK_SECRET`, `BALE_ALLOWED_CHAT_IDS`.

## Security contract for the Bale assistant
- Private chats: never answer operational questions.
- Non-allowlisted groups: never answer and never ingest jobs.
- Allowlisted groups: assistant answers only when the message contains `سکتور`.
- If no allowlist exists, the bot is fail-closed and answers nowhere.
- Ordinary work messages in the allowed group keep the existing AquaGold job-ingestion behavior.

## Supported group questions
- `سکتور کارهای انجام شده امروز رو بده`
- `سکتور امروز چقدر فروش داشتیم؟`
- `سکتور کنسلی های امروز رو بگو`
- `سکتور موسوی کارش چی شد؟`

`POST /api/mini/bale/activate` switches the Bale webhook to this standalone deployment and sends a Mini App button to the allowlisted group(s). It requires an authenticated Mini App session.
