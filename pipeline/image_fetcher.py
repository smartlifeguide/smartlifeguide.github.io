"""Fetch eye-catch images from Unsplash API."""

from __future__ import annotations

import hashlib
import logging
import os
import urllib.request
import urllib.parse
import json
from pathlib import Path

logger = logging.getLogger(__name__)

UNSPLASH_API_URL = "https://api.unsplash.com/search/photos"

# Keyword translation hints for better Unsplash search (Japanese → English)
_JA_SEARCH_HINTS = {
    "掃除機": "robot vacuum cleaner",
    "食洗機": "dishwasher kitchen",
    "空気清浄機": "air purifier",
    "洗濯機": "washing machine laundry",
    "節約": "saving money piggy bank",
    "家計": "household budget",
    "格安SIM": "smartphone mobile",
    "家計簿": "budget planner notebook",
    "肩こり": "shoulder massage relief",
    "目の疲れ": "eye care rest",
    "腰痛": "back pain relief",
    "睡眠": "sleep bedroom",
    "マットレス": "mattress bedroom",
    "教育費": "education family children",
    "学資保険": "education savings family",
    "タブレット学習": "child tablet learning",
    "塾": "tutoring study",
    "見守り": "elderly care family",
    "シニア": "senior elderly",
    "介護": "elderly care",
    "スマホ": "smartphone senior",
    "家電": "home appliances",
    "電気代": "electricity bill energy saving",
    "食費": "grocery shopping food",
}


def _keyword_to_search_query(keyword: str, lang: str) -> str:
    """Convert article keyword to an Unsplash search query."""
    if lang == "ja":
        # Try to find a matching hint
        for ja_key, en_query in _JA_SEARCH_HINTS.items():
            if ja_key in keyword:
                return en_query
        # Fallback: use a generic query based on niche
        return "home lifestyle family"
    return keyword


def _make_slug(keyword: str) -> str:
    """Create a filesystem-safe slug from keyword."""
    return hashlib.md5(keyword.encode()).hexdigest()[:12]


def fetch_image(
    keyword: str,
    lang: str,
    config: dict,
    site_dir: str | Path,
) -> str | None:
    """Fetch an image from Unsplash and save to site/static/images/.

    Returns the image path relative to site root (e.g. /images/abc123.jpg),
    or None if unavailable.
    """
    access_key = os.environ.get("UNSPLASH_ACCESS_KEY", "")
    if not access_key:
        logger.warning("UNSPLASH_ACCESS_KEY not set, skipping image fetch")
        return None

    site_dir = Path(site_dir)
    images_dir = site_dir / "static" / "images" / "articles"
    images_dir.mkdir(parents=True, exist_ok=True)

    slug = _make_slug(keyword)
    output_path = images_dir / f"{slug}.jpg"

    # Skip if already downloaded
    if output_path.exists():
        logger.info("Image already exists: %s", output_path)
        return f"/images/articles/{slug}.jpg"

    query = _keyword_to_search_query(keyword, lang)
    params = urllib.parse.urlencode({
        "query": query,
        "per_page": 1,
        "orientation": "landscape",
    })
    url = f"{UNSPLASH_API_URL}?{params}"

    req = urllib.request.Request(url, headers={
        "Authorization": f"Client-ID {access_key}",
        "Accept-Version": "v1",
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        results = data.get("results", [])
        if not results:
            logger.warning("No Unsplash results for query: %s", query)
            return None

        photo = results[0]
        image_url = photo["urls"]["regular"]  # 1080px width
        photographer = photo["user"]["name"]
        photo_link = photo["links"]["html"]

        logger.info(
            "Downloading image by %s: %s", photographer, image_url
        )

        # Download the image
        img_req = urllib.request.Request(image_url)
        with urllib.request.urlopen(img_req, timeout=30) as img_resp:
            with open(output_path, "wb") as f:
                f.write(img_resp.read())

        # Save attribution info
        attr_path = images_dir / f"{slug}.json"
        with open(attr_path, "w", encoding="utf-8") as f:
            json.dump({
                "photographer": photographer,
                "photo_url": photo_link,
                "unsplash_id": photo["id"],
                "query": query,
                "keyword": keyword,
            }, f, ensure_ascii=False, indent=2)

        logger.info("Image saved: %s (by %s)", output_path, photographer)
        return f"/images/articles/{slug}.jpg"

    except Exception:
        logger.exception("Failed to fetch image for '%s'", keyword)
        return None
