-- AquaGold 008: Web Push subscriptions for new Bale work notifications.
-- users.id is bigint in 001_core_app.sql, so push_subscriptions.user_id must match it.
create table if not exists public.push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id bigint not null references public.users(id) on delete cascade,
  endpoint text not null unique,
  p256dh text not null,
  auth text not null,
  user_agent text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_success_at timestamptz,
  last_error text
);
create index if not exists push_subscriptions_active_idx on public.push_subscriptions(active, updated_at desc) where active=true;
create index if not exists push_subscriptions_user_idx on public.push_subscriptions(user_id, active);
