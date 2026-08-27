-- AquaGold 007: Bale group work inbox and lifecycle.

create table if not exists public.bale_jobs (
  id uuid primary key default gen_random_uuid(),
  bale_update_id bigint unique,
  chat_id bigint not null,
  chat_title text,
  message_id bigint not null,
  sender_id bigint,
  sender_name text,
  raw_text text not null,
  customer_name text,
  phone text,
  address text,
  job_type text,
  customer_id uuid references public.customers_v2(id) on delete set null,
  service_visit_id uuid references public.service_visits(id) on delete set null,
  status text not null default 'new' check(status in ('new','completed','cancelled','review')),
  received_amount bigint check (received_amount is null or received_amount >= 0),
  cancel_reason text,
  parsed jsonb not null default '{}'::jsonb,
  received_at timestamptz not null default now(),
  completed_at timestamptz,
  cancelled_at timestamptz,
  updated_at timestamptz not null default now(),
  unique(chat_id,message_id)
);

create index if not exists bale_jobs_status_received_idx on public.bale_jobs(status, received_at desc);
create index if not exists bale_jobs_phone_idx on public.bale_jobs(phone) where phone is not null;

insert into public.app_settings(key,value)
values ('bale_bot', '{"allowed_chat_ids":[],"auto_reply":true,"enabled":false}'::jsonb)
on conflict(key) do nothing;
