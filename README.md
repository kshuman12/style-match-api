# Style Match API

FastAPI backend for the Style Match MVP. Classifies a user's style archetype and ranks matched looks from the seeded catalog. See `SPEC.md` for the full product spec.

## Endpoints

- `GET /health` — liveness probe. No auth.
- `POST /match` — body `{ "user_id": "<uuid>" }`, header `X-API-Key: <shared secret>`. Reads the user's profile from Supabase, computes archetype + top 5 looks, writes a row to `results`, and returns `{ "status": "ok", "result_id": "<uuid>" }`.

## Local development

### 1. Apply the database migration and seed

From the repo root, with the Supabase CLI installed and linked to your project:

```bash
supabase db push
psql "$SUPABASE_DB_URL" -f supabase/seed.sql
```

(Or paste `supabase/migrations/0001_init.sql` and `supabase/seed.sql` into the SQL editor in the Supabase dashboard.)

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in:

- `SUPABASE_URL` — project URL from the Supabase dashboard
- `SUPABASE_SERVICE_ROLE_KEY` — service role key (Project Settings → API)
- `SHARED_SECRET` — any random string; the Next.js frontend must send the same value on `X-API-Key`

### 3. Install and run

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 4. Smoke test

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/match \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SHARED_SECRET" \
  -d '{"user_id":"<an existing profiles.user_id>"}'
```

## Deployment (Render)

`render.yaml` declares a free-tier web service. To deploy:

1. Push this repo to GitHub.
2. In Render, create a new Blueprint from the repo. The blueprint will pick up `render.yaml`.
3. Set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `SHARED_SECRET` in the service's environment.
4. Render runs `pip install -r requirements.txt` and starts `uvicorn main:app --host 0.0.0.0 --port $PORT`. The free tier sleeps after 15 minutes of inactivity; the first request after sleep takes ~30s.

## Algorithm notes

- **Archetype classification:** weighted Jaccard over `style_prefs`, `color_prefs`, `occasion_prefs` against the hardcoded `ARCHETYPE_PROFILES`. Weights: 0.4 / 0.3 / 0.3.
- **Look ranking:** weighted Jaccard on style/color/occasion tags plus a budget-tier score (exact = 1.0, adjacent = 0.5, else 0). Weights: 0.4 / 0.3 / 0.2 / 0.1. Looks are pre-filtered to the chosen archetype and to those whose `size_range` contains the user's `top_size`.
- **Explanation:** template-based, references 2–3 of the user's actual survey answers (style/color/occasion overlap, with budget or body shape as fallback). No LLM call.
- **Photos:** `photo_url` is read but unused. The `# TODO: incorporate photo analysis` marker in `main.py` is the hook for later vision work.
