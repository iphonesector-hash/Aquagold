-- AquaGold 005: revocable sessions, integrity guarantees and offline idempotency

create or replace function public._aquagold_normalize_phone_migration_005(value text)
returns text language sql immutable strict as $$
  select case
    when digits ~ '^00989[0-9]{9}$' then '0' || substring(digits from 5)
    when digits ~ '^989[0-9]{9}$' then '0' || substring(digits from 3)
    when digits ~ '^9[0-9]{9}$' then '0' || digits
    else digits
  end
  from (
    select regexp_replace(
      translate(value, '۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'),
      '[^0-9]', '', 'g'
    ) digits
  ) cleaned
$$;

do $$
begin
  if exists (
    select 1 from public.customer_phones
    where public._aquagold_normalize_phone_migration_005(phone) !~ '^09[0-9]{9}$'
  ) then
    raise exception 'Invalid legacy phone numbers exist. Clean them before applying migration 005.';
  end if;
  if exists (
    select 1 from public.customer_phones
    group by public._aquagold_normalize_phone_migration_005(phone)
    having count(distinct customer_id) > 1
  ) then
    raise exception 'Duplicate normalized phone numbers exist across customers. Merge them before applying migration 005.';
  end if;
end $$;

delete from public.customer_phones phone
using (
  select id from (
    select id,row_number() over (
      partition by customer_id,public._aquagold_normalize_phone_migration_005(phone)
      order by is_primary desc,id
    ) duplicate_rank
    from public.customer_phones
  ) ranked where duplicate_rank > 1
) duplicate
where phone.id=duplicate.id;

update public.customer_phones
set phone=public._aquagold_normalize_phone_migration_005(phone)
where phone<>public._aquagold_normalize_phone_migration_005(phone);

drop function public._aquagold_normalize_phone_migration_005(text);

create unique index if not exists customer_phones_phone_unique_idx
  on public.customer_phones(phone);

update public.users set role=lower(trim(role));
update public.users set role='viewer'
where role not in ('viewer','technician','admin','superadmin');
alter table public.users alter column role set default 'viewer';
alter table public.users
  add constraint users_role_check
  check (role in ('viewer','technician','admin','superadmin')) not valid;
alter table public.users validate constraint users_role_check;

update public.service_visits set payment_method=case payment_method
  when 'نقد' then 'cash'
  when 'کارت' then 'card'
  when 'کارت‌خوان' then 'card'
  when 'کارت‌به‌کارت' then 'transfer'
  when 'چک' then 'cheque'
  else payment_method
end
where payment_method in ('نقد','کارت','کارت‌خوان','کارت‌به‌کارت','چک');

update public.products set category='device_filter' where category='filter';

alter table public.service_visits
  add constraint service_visits_payment_method_check
  check (payment_method is null or payment_method in ('cash','card','transfer','cheque','credit','other')) not valid;
alter table public.service_visits
  add constraint service_visits_status_check
  check (status in ('scheduled','registered','completed','revisit','cancelled','unpaid','partial')) not valid;
alter table public.products
  add constraint products_category_check
  check (category in ('device_filter','fridge_filter','accessory','service')) not valid;
alter table public.invoices
  add constraint invoices_status_check
  check (status in ('draft','issued','paid','void')) not valid;
alter table public.expenses
  add constraint expenses_category_check
  check (category in ('goods','fuel','parking','tools','food','other')) not valid;

alter table public.service_visits
  add column if not exists overpayment_amount bigint not null default 0;

update public.service_visits
set overpayment_amount = greatest(received_amount - invoice_amount, 0),
    customer_balance = greatest(invoice_amount - received_amount, 0);

create table if not exists public.auth_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id bigint not null references public.users(id) on delete cascade,
  token_hash text not null unique,
  csrf_hash text not null,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  user_agent text,
  ip_address text,
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now()
);

create index if not exists auth_sessions_active_idx
  on public.auth_sessions(token_hash, expires_at)
  where revoked_at is null;
create index if not exists auth_sessions_user_idx
  on public.auth_sessions(user_id, created_at desc);

create table if not exists public.api_idempotency (
  user_id bigint not null references public.users(id) on delete cascade,
  idempotency_key uuid not null,
  request_path text not null,
  request_hash text not null,
  status_code integer,
  response_body jsonb,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now() + interval '7 days',
  primary key(user_id, idempotency_key)
);

create index if not exists api_idempotency_expiry_idx
  on public.api_idempotency(expires_at);

create table if not exists public.geocode_cache (
  query_hash text primary key,
  normalized_query text not null,
  response jsonb not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now() + interval '30 days'
);

alter table public.customers_v2
  add constraint customers_v2_last_name_length_check
  check (char_length(last_name) between 1 and 160) not valid;
alter table public.customer_phones
  add constraint customer_phones_iran_mobile_check
  check (phone ~ '^09[0-9]{9}$') not valid;

-- Existing installations can validate these after cleaning legacy rows:
-- alter table public.customers_v2 validate constraint customers_v2_last_name_length_check;
-- alter table public.customer_phones validate constraint customer_phones_iran_mobile_check;
