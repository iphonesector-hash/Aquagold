-- AquaGold 008: persistent Web Push subscriptions for iPhone/PWA alerts.

create table if not exists public.push_subscriptions (
  endpoint_hash text primary key,
  endpoint text not null,
  subscription jsonb not null,
  user_id text,
  user_agent text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists push_subscriptions_updated_idx
  on public.push_subscriptions(updated_at desc);

insert into public.app_settings(key,value)
values ('web_push', '{}'::jsonb)
on conflict(key) do nothing;
