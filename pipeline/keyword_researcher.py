"""Keyword research module using pytrends and Google Suggest API."""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime, timezone

import requests
from pytrends.request import TrendReq

from pipeline.config import get_data_path

logger = logging.getLogger(__name__)

# Google Suggest endpoint
SUGGEST_URL = "http://suggestqueries.google.com/complete/search"


def fetch_google_suggestions(keyword: str, lang: str = "en") -> list[str]:
    """Fetch autocomplete suggestions from Google Suggest API."""
    params = {
        "client": "firefox",
        "q": keyword,
        "hl": lang,
    }
    try:
        resp = requests.get(SUGGEST_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data[1] if len(data) > 1 else []
    except Exception:
        logger.warning("Failed to fetch suggestions for: %s", keyword)
        return []


def fetch_trends_interest(keywords: list[str], geo: str = "") -> dict[str, float]:
    """Fetch relative search interest from Google Trends via pytrends."""
    if not keywords:
        return {}

    scores: dict[str, float] = {}
    # pytrends accepts max 5 keywords at a time
    batches = [keywords[i : i + 5] for i in range(0, len(keywords), 5)]

    pytrends = TrendReq(hl="en-US", tz=360)

    for batch in batches:
        try:
            pytrends.build_payload(batch, cat=0, timeframe="today 3-m", geo=geo)
            df = pytrends.interest_over_time()
            if df.empty:
                for kw in batch:
                    scores[kw] = 0.0
            else:
                for kw in batch:
                    if kw in df.columns:
                        scores[kw] = float(df[kw].mean())
                    else:
                        scores[kw] = 0.0
            # Rate limiting
            time.sleep(random.uniform(1.0, 3.0))
        except Exception:
            logger.warning("Trends lookup failed for batch: %s", batch)
            for kw in batch:
                scores[kw] = 0.0

    return scores


def score_keywords(
    keywords_with_interest: dict[str, float],
) -> list[dict]:
    """Score keywords based on search interest and estimated competition.

    Higher interest + longer tail (more words) = better opportunity.
    """
    scored = []
    for kw, interest in keywords_with_interest.items():
        word_count = len(kw.split())
        # Long-tail bonus: more words = less competition typically
        long_tail_bonus = min(word_count / 3.0, 2.0)
        score = interest * (1.0 + long_tail_bonus)
        scored.append(
            {
                "keyword": kw,
                "interest": round(interest, 2),
                "word_count": word_count,
                "score": round(score, 2),
            }
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def expand_keywords_from_niches(niches: list[dict], lang: str) -> list[str]:
    """Generate expanded keyword list from niche seed keywords."""
    lang_key = f"seed_keywords_{lang}"
    all_suggestions: list[str] = []

    for niche in niches:
        seeds = niche.get(lang_key, [])
        for seed in seeds:
            suggestions = fetch_google_suggestions(seed, lang=lang[:2])
            all_suggestions.extend(suggestions)
            time.sleep(random.uniform(0.3, 1.0))

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for kw in all_suggestions:
        lower = kw.lower().strip()
        if lower not in seen:
            seen.add(lower)
            unique.append(kw.strip())

    return unique


def research_keywords(niches: list[dict], config: dict) -> dict:
    """Run full keyword research pipeline for all languages.

    Returns the updated keywords data structure.
    """
    keywords_path = get_data_path("keywords.json")
    languages = config.get("site", {}).get("languages", ["en", "ja"])

    all_keywords: list[dict] = []

    for lang in languages:
        logger.info("Researching keywords for language: %s", lang)

        # Expand seed keywords via Google Suggest
        expanded = expand_keywords_from_niches(niches, lang)
        logger.info("Found %d expanded keywords for %s", len(expanded), lang)

        if not expanded:
            continue

        # Get trends interest scores
        geo = "JP" if lang == "ja" else ""
        interest_scores = fetch_trends_interest(expanded[:50], geo=geo)

        # Score and rank
        scored = score_keywords(interest_scores)

        for item in scored:
            item["lang"] = lang
            item["researched_at"] = datetime.now(timezone.utc).isoformat()

        all_keywords.extend(scored)

    # Load existing and merge (avoid duplicates)
    existing_data = _load_keywords(keywords_path)
    existing_kws = {
        (k["keyword"].lower(), k["lang"]) for k in existing_data.get("keywords", [])
    }

    new_keywords = [
        k
        for k in all_keywords
        if (k["keyword"].lower(), k["lang"]) not in existing_kws
    ]

    merged = existing_data.get("keywords", []) + new_keywords
    # Keep top keywords by score
    merged.sort(key=lambda x: x.get("score", 0), reverse=True)

    result = {
        "keywords": merged[:500],  # Cap at 500
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    with open(keywords_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info("Keyword research complete. Total keywords: %d", len(result["keywords"]))
    return result


def get_unused_keyword(lang: str, published_slugs: set[str]) -> dict | None:
    """Pick the highest-scoring unused keyword for a given language."""
    keywords_path = get_data_path("keywords.json")
    data = _load_keywords(keywords_path)

    for kw in data.get("keywords", []):
        if kw.get("lang") != lang:
            continue
        slug = _keyword_to_slug(kw["keyword"])
        if slug not in published_slugs:
            return kw

    return None


def _keyword_to_slug(keyword: str) -> str:
    """Convert a keyword to a URL-friendly slug."""
    import re
    import unicodedata

    # Normalize unicode
    slug = unicodedata.normalize("NFKC", keyword.lower())
    # Replace spaces and special chars with hyphens
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = slug.strip("-")
    return slug


def _load_keywords(path) -> dict:
    """Load keywords from JSON file."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"keywords": [], "last_updated": None}
