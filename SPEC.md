# Style Match MVP — Spec

A web app where users sign up, complete a style survey, and receive a persistent "style archetype" label plus a curated set of matched looks.

## Stack

- **Frontend:** Next.js 14+ (App Router), TypeScript, Tailwind CSS, deployed to Vercel
- **Auth + Database + Storage:** Supabase
- **Algorithm backend:** FastAPI (Python), deployed to Render free tier
- **Communication:** Frontend calls FastAPI over HTTPS with a shared-secret header. FastAPI reads/writes Supabase using the service role key.

## Core user flow

1. User lands on marketing page, clicks Sign Up
2. Email/password signup via Supabase auth
3. First-time login → redirected to `/onboarding`
4. Onboarding step 1: select gender pathway (men's / women's)
5. Onboarding steps 2–5: survey (measurements, sizes, style prefs, colors, occasions, budget, photo upload)
6. On submit: profile is written to Supabase, frontend calls FastAPI `/match`, FastAPI computes archetype + ranked looks and writes to `results` table, frontend polls and redirects to `/results`
7. Returning users skip onboarding and go to `/dashboard`, which links to their persistent `/results` page and a "retake survey" option

## Survey fields (collected during onboarding)

| Field | Type | Notes |
|---|---|---|
| gender_pathway | enum | 'mens' or 'womens' — selected on step 1, gates everything downstream |
| height_cm | integer | single unit, keep simple |
| weight_kg | integer | |
| top_size | enum | XS, S, M, L, XL, XXL |
| bottom_size | string | free text for now ("32x30", "M", "10", etc.) |
| shoe_size_us | numeric | accept decimals (10.5) |
| body_shape | enum | mens: rectangle, athletic, broad, slim; womens: rectangle, hourglass, pear, apple, athletic |
| style_prefs | string array | multi-select: minimalist, classic, streetwear, preppy, edgy, bohemian, athleisure |
| color_prefs | string array | multi-select: neutrals, earth_tones, brights, monochrome, pastels, jewel_tones |
| occasion_prefs | string array | multi-select: work, casual, going_out, athletic, formal |
| budget_tier | enum | budget, mid, premium |
| photo_url | string | Supabase Storage URL; algorithm ignores this for now |

## Archetypes (same names across genders, different look catalogs)

1. Modern Minimalist
2. Classic Preppy
3. Streetwear Casual
4. Bohemian Relaxed
5. Polished Edgy

Each archetype has an "ideal profile" — a weighted vector across style_prefs, color_prefs, and occasion_prefs that defines its center. Classification picks the archetype whose ideal profile most overlaps the user's preferences.

## Database schema (Supabase)

### `profiles`
- `user_id` uuid (PK, references auth.users)
- `gender_pathway` text
- `height_cm` integer
- `weight_kg` integer
- `top_size` text
- `bottom_size` text
- `shoe_size_us` numeric
- `body_shape` text
- `style_prefs` text[]
- `color_prefs` text[]
- `occasion_prefs` text[]
- `budget_tier` text
- `photo_url` text
- `profile_version` integer default 1
- `created_at` timestamptz default now()
- `updated_at` timestamptz default now()

RLS: users can read/write only their own row.

### `looks` (the fake match pool)
- `id` uuid (PK)
- `gender_pathway` text — 'mens' or 'womens'
- `archetype` text — one of the 5 archetypes
- `name` text — e.g. "The Weekend Editor"
- `description` text — 1–2 sentence blurb
- `image_url` text — stock photo URL
- `size_range` text[] — top sizes this look works for (e.g. ['S','M','L'])
- `style_tags` text[]
- `color_tags` text[]
- `occasion_tags` text[]
- `budget_tier` text
- `created_at` timestamptz default now()

RLS: readable by service role only (frontend never queries this directly).

Seed with ~30 looks per gender (~150 total), distributed across the 5 archetypes.

### `results`
- `id` uuid (PK)
- `user_id` uuid (references auth.users)
- `profile_version` integer — which profile snapshot this result is for
- `archetype` text — the classified archetype
- `archetype_score` numeric — confidence/fit score
- `archetype_explanation` text — 1–2 sentence "why this fits you" note that references their survey answers
- `matched_look_ids` uuid[] — ordered list, top 5
- `created_at` timestamptz default now()

RLS: users can read only their own rows.

### `photos` storage bucket
- Authenticated users can upload to `photos/{user_id}/...`
- Read access scoped to the owning user

## Algorithm (FastAPI `/match` endpoint)

**Input:** `{ user_id: string }` plus shared-secret header for auth.

**Steps:**
1. Read the user's row from `profiles`
2. Read all `looks` rows where `gender_pathway` matches the user's
3. **Classify archetype:** for each of the 5 archetypes, compute a fit score against the user's style_prefs + color_prefs + occasion_prefs using weighted Jaccard similarity against the archetype's ideal profile. Pick the highest-scoring archetype.
4. **Rank looks within archetype:** filter looks to that archetype AND where the user's `top_size` is in the look's `size_range`. Score each remaining look by:
   - Style tag overlap with user's style_prefs (weight 0.4)
   - Color tag overlap with user's color_prefs (weight 0.3)
   - Occasion tag overlap with user's occasion_prefs (weight 0.2)
   - Budget tier match (weight 0.1, exact match = 1, adjacent = 0.5, else 0)
5. Take top 5 look IDs by score.
6. Generate a short `archetype_explanation` string referencing 2–3 of the user's actual survey answers (template-based is fine — no LLM call needed for MVP).
7. Write a row to `results` with all of the above.
8. Return `{ status: 'ok', result_id: <uuid> }`.

The `photo_url` is read from the profile but unused — leave a `# TODO: incorporate photo analysis` comment in the code.

## Archetype ideal profiles (hardcoded in the Python backend)

```python
ARCHETYPE_PROFILES = {
    "Modern Minimalist": {
        "style_prefs": ["minimalist", "classic"],
        "color_prefs": ["neutrals", "monochrome"],
        "occasion_prefs": ["work", "casual"],
    },
    "Classic Preppy": {
        "style_prefs": ["preppy", "classic"],
        "color_prefs": ["neutrals", "jewel_tones"],
        "occasion_prefs": ["work", "casual", "formal"],
    },
    "Streetwear Casual": {
        "style_prefs": ["streetwear", "athleisure"],
        "color_prefs": ["brights", "monochrome"],
        "occasion_prefs": ["casual", "going_out"],
    },
    "Bohemian Relaxed": {
        "style_prefs": ["bohemian", "minimalist"],
        "color_prefs": ["earth_tones", "pastels"],
        "occasion_prefs": ["casual", "going_out"],
    },
    "Polished Edgy": {
        "style_prefs": ["edgy", "classic"],
        "color_prefs": ["monochrome", "jewel_tones"],
        "occasion_prefs": ["going_out", "work", "formal"],
    },
}
```

## Pages and routing (Next.js frontend)

| Route | Purpose | Auth required |
|---|---|---|
| `/` | Marketing landing page with CTA | No |
| `/signup` | Email/password signup | No |
| `/login` | Email/password login | No |
| `/onboarding` | Multi-step survey, gender select first | Yes |
| `/results` | Persistent archetype + matched looks | Yes |
| `/dashboard` | Welcome back screen, links to results + retake | Yes |

Middleware: any authenticated user without a `profiles` row is redirected to `/onboarding`. After onboarding completes, they go to `/results`. Subsequent logins go to `/dashboard`.

## Retake-survey behavior

When a user retakes the survey:
- `profile_version` increments
- A new `results` row is created (old one preserved)
- `/results` always shows the latest result
- No UI to view old results in MVP (data is there for later)

## Environment variables

### Frontend (Vercel)
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `BACKEND_URL` — Render service URL
- `BACKEND_SHARED_SECRET`

### Backend (Render)
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SHARED_SECRET` — must match frontend

## Out of scope for MVP

- Email verification, password reset, social login
- Actual image analysis (photo is uploaded but ignored)
- Editing individual profile fields without retaking full survey
- Look details page / look favoriting / look sharing
- Mobile-specific UI polish
- Rate limiting, abuse prevention
- Analytics, error monitoring
- Multi-language

## Definition of done

A user can sign up with a fresh email, select men's or women's pathway, complete the survey, upload a photo, see an archetype + 5 matched looks on a results page, log out, log back in tomorrow, and see the same results.
