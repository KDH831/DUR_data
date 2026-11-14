-- ════════════════════════════════════════════════════════════
-- 내 약 지킴이 – Supabase 스키마
-- Supabase 대시보드 → SQL Editor → New query → 전체 붙여넣기 → Run
-- ════════════════════════════════════════════════════════════

-- ① 사용자별 데이터: 본인 것만 보고 고칠 수 있음 (RLS)
create table if not exists profiles (
  id         bigint generated always as identity primary key,
  user_id    uuid not null default auth.uid() references auth.users on delete cascade,
  name       text not null,
  birthdate  date,
  pregnant   boolean not null default false,
  crush      boolean not null default false,
  avoid      jsonb   not null default '[]',
  memo       text    not null default ''
);

create table if not exists meds (
  id          bigint generated always as identity primary key,
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  profile_id  bigint not null references profiles on delete cascade,
  product_key text not null,      -- DUR 제품코드 / api-품목기준코드 / note:이름(영양제 등)
  label       text,               -- note: 항목의 표시 이름
  times       jsonb not null default '[]',
  added_at    date  not null default current_date,
  unique (profile_id, product_key)
);

create table if not exists intake (
  user_id    uuid not null default auth.uid() references auth.users on delete cascade,
  profile_id bigint not null references profiles on delete cascade,
  day        date not null,
  slot       text not null,
  med_id     bigint not null references meds on delete cascade,
  primary key (profile_id, day, slot, med_id)
);

alter table profiles enable row level security;
alter table meds     enable row level security;
alter table intake   enable row level security;

drop policy if exists own_profiles on profiles;
create policy own_profiles on profiles for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

drop policy if exists own_meds on meds;
create policy own_meds on meds for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid())
              and exists (select 1 from profiles p where p.id = profile_id and p.user_id = (select auth.uid())));

drop policy if exists own_intake on intake;
create policy own_intake on intake for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid())
              and exists (select 1 from meds m where m.id = med_id and m.user_id = (select auth.uid())));

-- ② 공동 약 캐시: 식약처 API에서 받은 공식 데이터만 저장
--    로그인 사용자는 읽기만 가능, 쓰기는 앱 서버(service_role 키)만 가능 → 사용자가 임의 데이터를 못 넣음
create table if not exists drug_cache (
  key         text primary key,   -- DUR 제품코드(전체 성분 보강) 또는 api-품목기준코드(DUR 목록 밖 약)
  name        text not null,
  ingredients jsonb not null,      -- 정규화된 성분 목록
  raw         text,                -- API 원문 (검증·재처리용)
  source      text not null default 'mfds_api',
  fetched_at  timestamptz not null default now(),
  constraint ingredients_not_empty check (jsonb_array_length(ingredients) > 0)
);
alter table drug_cache enable row level security;
drop policy if exists read_cache on drug_cache;
create policy read_cache on drug_cache for select to authenticated using (true);
create index if not exists drug_cache_name_idx on drug_cache (name);
