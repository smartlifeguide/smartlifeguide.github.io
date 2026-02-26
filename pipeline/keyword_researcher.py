"""Keyword research module using pytrends, Google Suggest API, and Gemini fallback."""

from __future__ import annotations

import json
import logging
import os
import random
import re
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


def generate_keywords_with_gemini(
    niches: list[dict],
    lang: str,
    existing_keywords: set[str],
    config: dict,
    count: int = 20,
) -> list[str]:
    """Generate new keyword ideas using Gemini when Google Suggest is exhausted."""
    from google import genai
    from google.genai import types

    gemini_cfg = config.get("gemini", {})
    api_key = gemini_cfg.get("api_key")
    if not api_key:
        logger.warning("No Gemini API key, skipping AI keyword generation")
        return []

    client = genai.Client(api_key=api_key)
    model_name = gemini_cfg.get("model", "gemini-2.5-flash")

    # Build context about existing keywords and niches
    lang_key = f"seed_keywords_{lang}"
    name_key = f"name_{lang}"
    niche_info = []
    for n in niches:
        name = n.get(name_key, n.get("id", ""))
        seeds = n.get(lang_key, [])
        niche_info.append(f"- {name}: {', '.join(seeds)}")

    existing_sample = sorted(existing_keywords)[:50]

    if lang == "ja":
        prompt = f"""あなたはSEOキーワードリサーチの専門家です。
以下のニッチカテゴリに対して、ブログ記事のターゲットキーワードを{count}個提案してください。

## ターゲット読者
40〜50代の主婦・パート勤務の女性。Google検索で「○○ おすすめ」「○○ 比較」と調べる層。

## ニッチカテゴリ
{chr(10).join(niche_info)}

## 既存キーワード（重複禁止）
{chr(10).join(existing_sample)}

## 要件
- 検索ボリュームが見込めるロングテールキーワード（2〜4語）
- 上記の既存キーワードと重複しない新しいキーワード
- 商品比較・おすすめ系のキーワードを多めに（アフィリエイト向き）
- ペルソナの生活に密着した実用的なキーワード
- 5つのニッチカテゴリから万遍なく提案

## 出力形式
キーワードのみをJSON配列で出力してください：
["キーワード1", "キーワード2", ...]"""
    else:
        prompt = f"""You are an SEO keyword research expert.
Suggest {count} blog article target keywords for the following niche categories.

## Target Reader
Families looking for practical advice on household topics.

## Niche Categories
{chr(10).join(niche_info)}

## Existing Keywords (do NOT duplicate)
{chr(10).join(existing_sample)}

## Requirements
- Long-tail keywords (3-6 words) with search volume potential
- Must NOT overlap with existing keywords above
- Focus on product comparisons, reviews, and "best of" lists
- Practical, everyday topics
- Cover all niche categories evenly

## Output Format
Output only a JSON array of keywords:
["keyword 1", "keyword 2", ...]"""

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=8192,
                temperature=0.9,
                thinking_config=types.ThinkingConfig(thinking_budget=1024),
            ),
        )
        text = response.text or ""
        # Extract JSON array from response
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            keywords = json.loads(match.group(0))
            if isinstance(keywords, list):
                result = [k.strip() for k in keywords if isinstance(k, str) and k.strip()]
                logger.info("Gemini generated %d keyword candidates for %s", len(result), lang)
                return result
    except Exception as e:
        logger.warning("Gemini keyword generation failed: %s", e)

    return []


def research_keywords(niches: list[dict], config: dict) -> dict:
    """Run full keyword research pipeline for all languages.

    Uses Google Suggest for expansion, with Gemini AI fallback
    when suggest results are exhausted.

    Returns the updated keywords data structure.
    """
    keywords_path = get_data_path("keywords.json")
    languages = config.get("site", {}).get("languages", ["en", "ja"])

    # Load existing keywords for dedup
    existing_data = _load_keywords(keywords_path)
    existing_kws = {
        (k["keyword"].lower(), k["lang"]) for k in existing_data.get("keywords", [])
    }

    all_keywords: list[dict] = []

    for lang in languages:
        logger.info("Researching keywords for language: %s", lang)

        # Expand seed keywords via Google Suggest
        expanded = expand_keywords_from_niches(niches, lang)

        # Filter out already-known keywords
        new_expanded = [
            kw for kw in expanded
            if (kw.lower().strip(), lang) not in existing_kws
        ]
        logger.info(
            "Found %d expanded keywords for %s (%d new)",
            len(expanded), lang, len(new_expanded),
        )

        # Gemini fallback: if fewer than 5 new keywords from Suggest
        if len(new_expanded) < 5:
            logger.info("Few new keywords from Suggest, using Gemini to generate more for %s", lang)
            existing_for_lang = {k for (k, l) in existing_kws if l == lang}
            ai_keywords = generate_keywords_with_gemini(
                niches, lang, existing_for_lang, config, count=20,
            )
            # Add AI keywords that aren't duplicates
            for kw in ai_keywords:
                if (kw.lower().strip(), lang) not in existing_kws:
                    new_expanded.append(kw)

        if not new_expanded:
            continue

        # Get trends interest scores
        geo = "JP" if lang == "ja" else ""
        interest_scores = fetch_trends_interest(new_expanded[:50], geo=geo)

        # Score and rank
        scored = score_keywords(interest_scores)

        for item in scored:
            item["lang"] = lang
            item["researched_at"] = datetime.now(timezone.utc).isoformat()

        all_keywords.extend(scored)

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
