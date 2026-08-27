-- AquaGold operational v8 schema additions.
create table if not exists push_subscriptions(
  id bigserial primary key,
  user_id text,
  subscription jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  active boolean not null default true,
  unique(subscription)
);

create table if not exists ops_cron_runs(
  run_key text primary key,
  run_at timestamptz not null default now(),
  result jsonb
);

create table if not exists customer_notes(
  id bigserial primary key,
  customer_id uuid not null references customers_v2(id) on delete cascade,
  note_text text not null,
  note_type text not null default 'text',
  created_by text,
  created_at timestamptz not null default now()
);
create index if not exists idx_customer_notes_customer_created on customer_notes(customer_id,created_at desc);

create table if not exists service_media(
  id bigserial primary key,
  service_visit_id uuid not null references service_visits(id) on delete cascade,
  kind text not null check(kind in ('before','after')),
  data_url text not null,
  created_by text,
  created_at timestamptz not null default now()
);
create index if not exists idx_service_media_service on service_media(service_visit_id,created_at);

create or replace function aquagold_set_next_service_v8() returns trigger as $$
begin
  if new.status='completed' and new.next_service_at is null then
    new.next_service_at := coalesce(new.visited_at,new.created_at,now()) + interval '6 months';
  end if;
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_aquagold_set_next_service_v8 on service_visits;
create trigger trg_aquagold_set_next_service_v8
before insert or update of status,visited_at,next_service_at on service_visits
for each row execute function aquagold_set_next_service_v8();

update service_visits
set next_service_at = coalesce(visited_at,created_at,now()) + interval '6 months'
where status='completed' and next_service_at is null;
