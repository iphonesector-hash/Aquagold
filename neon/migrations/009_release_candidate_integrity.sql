-- AquaGold v8 final release-candidate integrity additions.
alter table customer_notes
  add column if not exists audio_data_url text,
  add column if not exists audio_mime_type text;

create table if not exists app_notifications(
  id uuid primary key default gen_random_uuid(),
  user_id text,
  title text not null,
  body text,
  page text,
  category text not null default 'info',
  dedupe_key text unique,
  created_at timestamptz not null default now(),
  read_at timestamptz,
  dismissed_at timestamptz
);
create index if not exists idx_app_notifications_user_created
  on app_notifications(user_id, created_at desc);
create index if not exists idx_app_notifications_unread
  on app_notifications(user_id, created_at desc)
  where read_at is null and dismissed_at is null;

create index if not exists idx_service_visits_latest_completed_customer
  on service_visits(customer_id, coalesce(visited_at, created_at) desc, created_at desc)
  where status='completed';
