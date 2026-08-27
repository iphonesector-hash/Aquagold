-- AquaGold 006: Aqua AI audit foundation and a useful starter catalog.

create table if not exists public.aqua_ai_events (
  id uuid primary key default gen_random_uuid(),
  user_id bigint references public.users(id) on delete set null,
  event_type text not null,
  status text not null default 'completed',
  action_nonce text unique,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists aqua_ai_events_created_idx
  on public.aqua_ai_events(created_at desc);

insert into public.products(id,name,category,description,price,image_url,badge,origin,lifetime_text,is_active,sort_order)
values
 ('a0000000-0000-4000-8000-000000000001','فیلتر مرحله اول PP','device_filter','حذف شن، گل‌ولای و ذرات معلق؛ مناسب سرویس دوره‌ای دستگاه تصفیه آب.',0,'/assets/product-ro-filter.svg','ضروری','AquaGold','۳ تا ۶ ماه',true,10),
 ('a0000000-0000-4000-8000-000000000002','فیلتر کربن گرانول UDF','device_filter','کاهش کلر، بو و طعم نامطبوع آب در مرحله دوم.',0,'/assets/product-ro-filter.svg','پرفروش','AquaGold','۶ ماه',true,20),
 ('a0000000-0000-4000-8000-000000000003','فیلتر کربن بلاک CTO','device_filter','تکمیل حذف کلر و ترکیبات آلی پیش از ممبران.',0,'/assets/product-ro-filter.svg','','AquaGold','۶ ماه',true,30),
 ('a0000000-0000-4000-8000-000000000004','ممبران RO خانگی','device_filter','فیلتر اصلی اسمز معکوس برای کاهش سختی و املاح محلول.',0,'/assets/product-ro-filter.svg','تخصصی','AquaGold','۱۸ تا ۲۴ ماه',true,40),
 ('a0000000-0000-4000-8000-000000000005','فیلتر پست کربن','device_filter','بهبود نهایی طعم و بوی آب خروجی مخزن.',0,'/assets/product-ro-filter.svg','','AquaGold','۱۲ ماه',true,50),
 ('a0000000-0000-4000-8000-000000000006','فیلتر مینرال','device_filter','افزودن کنترل‌شده مواد معدنی و بهبود طعم آب.',0,'/assets/product-ro-filter.svg','','AquaGold','۱۲ ماه',true,60),
 ('a0000000-0000-4000-8000-000000000007','فیلتر یخچال ساید','fridge_filter','فیلتر بیرونی یخچال برای کاهش بو، کلر و رسوبات.',0,'/assets/product-fridge-filter.svg','محبوب','AquaGold','۶ ماه',true,70),
 ('a0000000-0000-4000-8000-000000000008','سرویس کامل دستگاه','service','بازدید، تست فشار و TDS، تعویض فیلتر و کنترل نشتی.',0,'/assets/product-ro-filter.svg','خدمات','AquaGold','دوره‌ای',true,80)
on conflict(id) do nothing;
