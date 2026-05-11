-- Style Match MVP — initial schema
-- Creates profiles, looks, results tables, RLS policies, and the photos storage bucket.

-- ============================================================
-- profiles
-- ============================================================
create table if not exists public.profiles (
    user_id           uuid primary key references auth.users(id) on delete cascade,
    gender_pathway    text,
    height_cm         integer,
    weight_kg         integer,
    top_size          text,
    bottom_size       text,
    shoe_size_us      numeric,
    body_shape        text,
    style_prefs       text[],
    color_prefs       text[],
    occasion_prefs    text[],
    budget_tier       text,
    photo_url         text,
    profile_version   integer     not null default 1,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "profiles_select_own"
    on public.profiles for select
    to authenticated
    using (auth.uid() = user_id);

create policy "profiles_insert_own"
    on public.profiles for insert
    to authenticated
    with check (auth.uid() = user_id);

create policy "profiles_update_own"
    on public.profiles for update
    to authenticated
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

create policy "profiles_delete_own"
    on public.profiles for delete
    to authenticated
    using (auth.uid() = user_id);

-- ============================================================
-- looks (the fake match pool — service role only)
-- ============================================================
create table if not exists public.looks (
    id              uuid primary key default gen_random_uuid(),
    gender_pathway  text not null,
    archetype       text not null,
    name            text not null,
    description     text,
    image_url       text,
    size_range      text[],
    style_tags      text[],
    color_tags      text[],
    occasion_tags   text[],
    budget_tier     text,
    created_at      timestamptz not null default now()
);

create index if not exists looks_gender_archetype_idx
    on public.looks (gender_pathway, archetype);

-- RLS on with no policies = no access for anon/authenticated.
-- The service role bypasses RLS, so the FastAPI backend can still read.
alter table public.looks enable row level security;

-- ============================================================
-- results
-- ============================================================
create table if not exists public.results (
    id                     uuid primary key default gen_random_uuid(),
    user_id                uuid not null references auth.users(id) on delete cascade,
    profile_version        integer not null,
    archetype              text not null,
    archetype_score        numeric,
    archetype_explanation  text,
    matched_look_ids       uuid[],
    created_at             timestamptz not null default now()
);

create index if not exists results_user_created_idx
    on public.results (user_id, created_at desc);

alter table public.results enable row level security;

create policy "results_select_own"
    on public.results for select
    to authenticated
    using (auth.uid() = user_id);

-- ============================================================
-- photos storage bucket
-- ============================================================
insert into storage.buckets (id, name, public)
values ('photos', 'photos', false)
on conflict (id) do nothing;

create policy "photos_insert_own"
    on storage.objects for insert
    to authenticated
    with check (
        bucket_id = 'photos'
        and (storage.foldername(name))[1] = auth.uid()::text
    );

create policy "photos_select_own"
    on storage.objects for select
    to authenticated
    using (
        bucket_id = 'photos'
        and (storage.foldername(name))[1] = auth.uid()::text
    );

create policy "photos_update_own"
    on storage.objects for update
    to authenticated
    using (
        bucket_id = 'photos'
        and (storage.foldername(name))[1] = auth.uid()::text
    )
    with check (
        bucket_id = 'photos'
        and (storage.foldername(name))[1] = auth.uid()::text
    );

create policy "photos_delete_own"
    on storage.objects for delete
    to authenticated
    using (
        bucket_id = 'photos'
        and (storage.foldername(name))[1] = auth.uid()::text
    );
