# AquaGold Smart CRM

## Phase 1 included
- Persian smart intake parser for semi-structured service messages
- Multi-phone extraction and customer matching
- GPS capture in the browser
- Nearby-customer lookup
- Customer + service visit registration
- Follow-up amount updates
- Field map at `/smart`
- Supabase/PostGIS production schema prepared for a dedicated AquaGold project

## Example
Input:

```text
سه شنبه از الان الی ۱۵:۳۰
فیلتر
صادقی ۰۹۱۲۵۷۸۲۸۰۳
۰۹۱۲۲۵۰۱۲۷۲
آریا شهر آیت الله کاشانی خ بهنام شهرک
فرهنگیان وارانک ۵ پ ۱۰ واحد ۵
مهمانی۳
```

The parser extracts surname, both phone numbers, address, service type, visitor code and time text. A subsequent message such as `دریافتی ۵/۶۰۰/۰۰۰` can update the active visit amount through the amount endpoint.

## Temporary compatibility mode
`server_smart.py` extends the existing Flask + SQLite deployment so the current app keeps running before the dedicated Supabase project is provisioned.

## Production target
Vercel frontend/API + dedicated Supabase PostgreSQL/PostGIS. The migration intentionally revokes browser roles from CRM tables; sensitive customer data should be served only through authenticated server APIs.

## Environment / rollout notes
1. Create a dedicated AquaGold Supabase project (do not reuse LoveHub or SectorLand databases).
2. Enable/apply PostGIS migration in `supabase/migrations/001_aquagold_smart_crm.sql`.
3. Configure server-side Supabase credentials only in deployment secrets.
4. Migrate legacy SQLite customers/jobs.
5. Replace compatibility nearest-customer Haversine scan with indexed PostGIS `ST_DWithin` query.
6. Add geocoding/routing provider and address-to-pin confirmation flow.
