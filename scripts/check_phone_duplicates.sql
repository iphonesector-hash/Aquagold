-- Run before migration 005. Both result sets must be empty.
with digits as (
  select id,customer_id,phone,
         regexp_replace(
           translate(phone, '۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'),
           '[^0-9]', '', 'g'
         ) raw_digits
  from public.customer_phones
), normalized as (
  select *,case
    when raw_digits ~ '^00989[0-9]{9}$' then '0' || substring(raw_digits from 5)
    when raw_digits ~ '^989[0-9]{9}$' then '0' || substring(raw_digits from 3)
    when raw_digits ~ '^9[0-9]{9}$' then '0' || raw_digits
    else raw_digits
  end normalized_phone
  from digits
)
select id,customer_id,phone,normalized_phone
from normalized
where normalized_phone !~ '^09[0-9]{9}$'
order by id;

with digits as (
  select customer_id,
         regexp_replace(
           translate(phone, '۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'),
           '[^0-9]', '', 'g'
         ) raw_digits
  from public.customer_phones
), normalized as (
  select customer_id,case
    when raw_digits ~ '^00989[0-9]{9}$' then '0' || substring(raw_digits from 5)
    when raw_digits ~ '^989[0-9]{9}$' then '0' || substring(raw_digits from 3)
    when raw_digits ~ '^9[0-9]{9}$' then '0' || raw_digits
    else raw_digits
  end normalized_phone
  from digits
)
select normalized_phone,
       count(distinct customer_id) customer_count,
       array_agg(distinct customer_id) customer_ids
from normalized
group by normalized_phone
having count(distinct customer_id) > 1
order by customer_count desc,normalized_phone;
