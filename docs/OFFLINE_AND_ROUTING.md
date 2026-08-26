# Offline data and routing

## Offline behavior

Authenticated GET responses used by the interface, including a session lease capped by the server-side expiry time, are cached in IndexedDB. This lets an already authenticated user reopen the installed app during a temporary outage without persisting the session token in JavaScript storage. Customer, service, expense, settlement, product and invoice creates are queued in creation order when the browser is offline or receives a transient 502/503/504 response. Each queued create receives one UUID used both as its future database ID and its idempotency key, so dependent records can safely reference it before synchronization.

An offline logout immediately removes cached records and drafts from the device. Because the HttpOnly server session cannot be revoked without a network connection, the client records a pending logout and revokes that session automatically before restoring any authenticated state after connectivity returns.

When connectivity returns, the queue replays serially. Successful items are removed. A validation or authorization error stops the queue and remains visible for review; a server/network failure also stops replay and retries on the next synchronization attempt. Cached data is bound to the last authenticated user; switching accounts clears it. Logging out clears cached API data, drafts and queued mutations from that device.

PWA static assets are versioned in `sw.js`. Each asset is cached independently so one optional failure does not invalidate the rest of the offline shell. Map tiles are not bulk-downloaded and therefore the base map still needs connectivity outside previously cached browser resources.

## Geocoding

`GET /api/geocode?q=...` calls the configured provider from the server, limits results to Iran by default, rate-limits requests, and stores results in `geocode_cache`. The provider receives the searched address, so its privacy and retention terms apply. Public Nominatim is suitable only for light interactive use; production volume should use a contracted/self-hosted provider and an identifying `AQUAGOLD_MAP_USER_AGENT`.

## Route planning

`POST /api/route/optimize` accepts a current position and at most 12 customer IDs. It uses an OSRM duration matrix and a nearest-neighbor ordering, then requests road geometry and totals. If the routing provider is temporarily unavailable, it falls back to Haversine ordering and returns a straight-line route marked as a fallback. This is a practical dispatch heuristic, not a guaranteed globally optimal travelling-salesperson solution.

Only customer IDs are sent by the server to load coordinates; names, phones, addresses and financial data are not sent to the routing provider. The provider still receives coordinates, so its privacy terms must be reviewed before production use.
