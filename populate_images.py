"""
One-time script to populate looks.image_url with real Pexels photos.

Usage:
    1. Add PEXELS_API_KEY to your .env file
    2. Run: venv\\Scripts\\python.exe populate_images.py
"""

import os
import time
import httpx
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

PEXELS_API_KEY = os.environ["PEXELS_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Search terms tuned per archetype + gender. Adjust freely.
SEARCH_TERMS = {
    ("Modern Minimalist", "mens"): "men minimalist fashion neutral",
    ("Modern Minimalist", "womens"): "women minimalist fashion neutral",
    ("Classic Preppy", "mens"): "men preppy fashion blazer",
    ("Classic Preppy", "womens"): "women preppy fashion classic",
    ("Streetwear Casual", "mens"): "men streetwear urban fashion",
    ("Streetwear Casual", "womens"): "women streetwear urban fashion",
    ("Bohemian Relaxed", "mens"): "men bohemian fashion relaxed",
    ("Bohemian Relaxed", "womens"): "women bohemian fashion flowy",
    ("Polished Edgy", "mens"): "men edgy fashion black leather",
    ("Polished Edgy", "womens"): "women edgy fashion black leather",
}


def search_pexels(query: str, per_page: int = 15) -> list[str]:
    """Return a list of medium-size photo URLs from Pexels for the query."""
    r = httpx.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": PEXELS_API_KEY},
        params={"query": query, "per_page": per_page, "orientation": "portrait"},
        timeout=30,
    )
    r.raise_for_status()
    photos = r.json().get("photos", [])
    return [p["src"]["large"] for p in photos]


def main() -> None:
    # For each (archetype, gender) combo, fetch a pool of images then assign them
    for (archetype, gender), query in SEARCH_TERMS.items():
        print(f"\n=== {archetype} / {gender} ===")
        print(f"  Searching: {query}")

        try:
            image_urls = search_pexels(query, per_page=15)
        except Exception as e:
            print(f"  ! Pexels error: {e}")
            continue

        if not image_urls:
            print("  ! No photos returned")
            continue

        print(f"  Got {len(image_urls)} photos")

        # Pull every look in this bucket
        result = (
            sb.table("looks")
            .select("id")
            .eq("archetype", archetype)
            .eq("gender_pathway", gender)
            .execute()
        )
        looks = result.data
        print(f"  {len(looks)} looks to update")

        # Cycle through the image pool so each look gets a different photo
        for idx, look in enumerate(looks):
            image_url = image_urls[idx % len(image_urls)]
            sb.table("looks").update({"image_url": image_url}).eq(
                "id", look["id"]
            ).execute()

        # Light rate-limit cushion
        time.sleep(0.3)

    print("\nDone.")


if __name__ == "__main__":
    main()
