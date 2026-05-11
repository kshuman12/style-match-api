import os
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from supabase import Client, create_client

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SHARED_SECRET = os.environ["SHARED_SECRET"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

app = FastAPI(title="Style Match API")


ARCHETYPE_PROFILES: dict[str, dict[str, list[str]]] = {
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

BUDGET_ORDER = ["budget", "mid", "premium"]

# Classification weights across the three preference dimensions.
W_STYLE_CLS, W_COLOR_CLS, W_OCC_CLS = 0.4, 0.3, 0.3

# Look-ranking weights from the spec.
W_STYLE_RANK, W_COLOR_RANK, W_OCC_RANK, W_BUDGET_RANK = 0.4, 0.3, 0.2, 0.1


class MatchRequest(BaseModel):
    user_id: str


class MatchResponse(BaseModel):
    status: str
    result_id: str


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if not x_api_key or x_api_key != SHARED_SECRET:
        raise HTTPException(status_code=401, detail="invalid api key")


def jaccard(a: Optional[list[str]], b: Optional[list[str]]) -> float:
    sa, sb = set(a or []), set(b or [])
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def budget_match_score(user_budget: Optional[str], look_budget: Optional[str]) -> float:
    if not user_budget or not look_budget:
        return 0.0
    if user_budget == look_budget:
        return 1.0
    try:
        diff = abs(BUDGET_ORDER.index(user_budget) - BUDGET_ORDER.index(look_budget))
    except ValueError:
        return 0.0
    return 0.5 if diff == 1 else 0.0


def classify_archetype(profile: dict[str, Any]) -> tuple[str, float]:
    best_name = next(iter(ARCHETYPE_PROFILES))
    best_score = -1.0
    for name, ideal in ARCHETYPE_PROFILES.items():
        score = (
            W_STYLE_CLS * jaccard(profile.get("style_prefs"), ideal["style_prefs"])
            + W_COLOR_CLS * jaccard(profile.get("color_prefs"), ideal["color_prefs"])
            + W_OCC_CLS * jaccard(profile.get("occasion_prefs"), ideal["occasion_prefs"])
        )
        if score > best_score:
            best_score = score
            best_name = name
    return best_name, best_score


def score_look(profile: dict[str, Any], look: dict[str, Any]) -> float:
    return (
        W_STYLE_RANK * jaccard(profile.get("style_prefs"), look.get("style_tags"))
        + W_COLOR_RANK * jaccard(profile.get("color_prefs"), look.get("color_tags"))
        + W_OCC_RANK * jaccard(profile.get("occasion_prefs"), look.get("occasion_tags"))
        + W_BUDGET_RANK * budget_match_score(profile.get("budget_tier"), look.get("budget_tier"))
    )


def generate_explanation(profile: dict[str, Any], archetype: str) -> str:
    ideal = ARCHETYPE_PROFILES[archetype]
    phrases: list[str] = []

    style_overlap = list(set(profile.get("style_prefs") or []) & set(ideal["style_prefs"]))
    if style_overlap:
        phrases.append(f"your taste for {' and '.join(style_overlap[:2])} styles")

    color_overlap = list(set(profile.get("color_prefs") or []) & set(ideal["color_prefs"]))
    if color_overlap:
        readable = [c.replace("_", " ") for c in color_overlap[:2]]
        phrases.append(f"a palette built around {' and '.join(readable)}")

    occasion_overlap = list(set(profile.get("occasion_prefs") or []) & set(ideal["occasion_prefs"]))
    if occasion_overlap:
        readable = [o.replace("_", " ") for o in occasion_overlap[:2]]
        phrases.append(f"a focus on {' and '.join(readable)} wear")

    if len(phrases) < 3 and profile.get("budget_tier"):
        phrases.append(f"a {profile['budget_tier']}-tier budget")

    if len(phrases) < 3 and profile.get("body_shape"):
        phrases.append(f"a {profile['body_shape']} build")

    picks = phrases[:3]
    if not picks:
        return f"You read as a {archetype} based on your overall survey answers."

    if len(picks) == 1:
        joined = picks[0]
    elif len(picks) == 2:
        joined = f"{picks[0]} and {picks[1]}"
    else:
        joined = f"{picks[0]}, {picks[1]}, and {picks[2]}"

    return f"You read as a {archetype} thanks to {joined}."


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/match", response_model=MatchResponse, dependencies=[Depends(require_api_key)])
def match(req: MatchRequest) -> MatchResponse:
    profile_resp = (
        supabase.table("profiles")
        .select("*")
        .eq("user_id", req.user_id)
        .single()
        .execute()
    )
    profile: Optional[dict[str, Any]] = profile_resp.data
    if not profile:
        raise HTTPException(status_code=404, detail="profile not found")

    # TODO: incorporate photo analysis from profile["photo_url"]

    looks_resp = (
        supabase.table("looks")
        .select("*")
        .eq("gender_pathway", profile["gender_pathway"])
        .execute()
    )
    looks: list[dict[str, Any]] = looks_resp.data or []

    archetype, archetype_score = classify_archetype(profile)

    user_top_size = profile.get("top_size")
    candidate_looks = [
        look
        for look in looks
        if look.get("archetype") == archetype
        and user_top_size
        and user_top_size in (look.get("size_range") or [])
    ]

    ranked = sorted(
        ((score_look(profile, look), look["id"]) for look in candidate_looks),
        key=lambda pair: pair[0],
        reverse=True,
    )
    top_look_ids = [look_id for _, look_id in ranked[:5]]

    explanation = generate_explanation(profile, archetype)

    insert_resp = (
        supabase.table("results")
        .insert(
            {
                "user_id": req.user_id,
                "profile_version": profile.get("profile_version", 1),
                "archetype": archetype,
                "archetype_score": archetype_score,
                "archetype_explanation": explanation,
                "matched_look_ids": top_look_ids,
            }
        )
        .execute()
    )
    rows = insert_resp.data or []
    if not rows:
        raise HTTPException(status_code=500, detail="failed to write result row")

    return MatchResponse(status="ok", result_id=rows[0]["id"])
