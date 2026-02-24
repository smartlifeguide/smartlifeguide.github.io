"""Affiliate link insertion module (Amazon Associates + Rakuten via Moshimo + A8.net)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.parse import quote

from pipeline.config import get_data_path

logger = logging.getLogger(__name__)

# Product keyword patterns mapped to Amazon search categories
# Updated for lifestyle niches targeting 40-50yo audience
PRODUCT_PATTERNS_JA = {
    r"(掃除機|ロボット掃除機|ルンバ)": "kitchen",
    r"(食洗機|食器洗い)": "kitchen",
    r"(空気清浄機|加湿器|除湿機)": "kitchen",
    r"(洗濯機|ドラム式|乾燥機)": "kitchen",
    r"(家電|電化製品)": "kitchen",
    r"(マットレス|枕|寝具|布団)": "home",
    r"(肩こり|マッサージ|ストレッチ)": "hpc",
    r"(目の疲れ|アイマスク|ホットアイマスク)": "hpc",
    r"(体重計|血圧計|体温計)": "hpc",
    r"(格安SIM|スマホ|携帯)": "electronics",
    r"(タブレット|iPad)": "electronics",
    r"(見守り|カメラ|センサー)": "electronics",
    r"(家計簿|ノート|手帳)": "office-products",
    r"(保険|学資)": None,  # No Amazon link for insurance
    r"(参考書|問題集|教材|本)": "books",
}

PRODUCT_PATTERNS_EN = {
    r"\b(vacuum|robot vacuum|cleaner)\b": "kitchen",
    r"\b(dishwasher|washing machine|dryer)\b": "kitchen",
    r"\b(air purifier|humidifier|dehumidifier)\b": "kitchen",
    r"\b(appliance|home appliance)\b": "kitchen",
    r"\b(mattress|pillow|bedding)\b": "home",
    r"\b(massage|stretching|pain relief)\b": "hpc",
    r"\b(eye mask|sleep mask)\b": "hpc",
    r"\b(phone|smartphone|tablet|SIM)\b": "electronics",
    r"\b(camera|monitor|sensor)\b": "electronics",
    r"\b(planner|notebook|journal)\b": "office-products",
    r"\b(book|guide|textbook|workbook)\b": "books",
}

AMAZON_SEARCH_URL_JA = "https://www.amazon.co.jp/s?k={query}&tag={tag}"
AMAZON_SEARCH_URL_EN = "https://www.amazon.com/s?k={query}&tag={tag}"

# Moshimo affiliate (楽天市場)
MOSHIMO_BASE = "https://af.moshimo.com/af/c/click?a_id={a_id}&p_id=54&pc_id=54&pl_id=616&url={encoded_url}"


def _load_a8_programs() -> list[dict]:
    """Load A8.net affiliate programs from data/a8_programs.json."""
    a8_path = get_data_path("a8_programs.json")
    try:
        with open(a8_path, encoding="utf-8") as f:
            data = json.load(f)
        return [p for p in data.get("programs", []) if p.get("enabled")]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _find_a8_links(article: dict) -> list[dict]:
    """Find matching A8 programs for an article based on niche and keywords."""
    programs = _load_a8_programs()
    if not programs:
        return []

    body = article.get("body", "")
    categories = article.get("front_matter", {}).get("categories", [])
    keyword = article.get("keyword", "")

    matched = []
    for prog in programs:
        if not prog.get("link"):
            continue

        # Match by niche_id against categories
        niche_id = prog.get("niche_id", "")
        niche_match = any(
            niche_id.replace("_", " ") in cat.lower()
            or niche_id.replace("_", "") in cat.lower().replace(" ", "")
            for cat in categories
        )

        # Match by keywords in article body or keyword
        kw_match = any(
            kw in body or kw in keyword
            for kw in prog.get("keywords", [])
        )

        if niche_match or kw_match:
            matched.append(prog)

    return matched


def insert_affiliate_links(article: dict, config: dict) -> dict:
    """Insert affiliate links into an article's body.

    Adds Amazon product recommendations and A8.net program links
    based on article content and niche.
    """
    if not config.get("affiliate", {}).get("enabled", True):
        return article

    lang = article.get("lang", "en")
    body = article["body"]
    keyword = article.get("keyword", "")

    sections = []

    # --- Amazon Associates ---
    if lang == "ja":
        tag = config["affiliate"]["amazon_associate_tag_ja"]
        patterns = PRODUCT_PATTERNS_JA
        search_url_template = AMAZON_SEARCH_URL_JA
    else:
        tag = config["affiliate"]["amazon_associate_tag_en"]
        patterns = PRODUCT_PATTERNS_EN
        search_url_template = AMAZON_SEARCH_URL_EN

    # Detect product categories mentioned in the article
    has_amazon_category = False
    for pattern, category in patterns.items():
        if category and re.search(pattern, body, re.IGNORECASE):
            has_amazon_category = True
            break

    if has_amazon_category and tag and not tag.startswith("your-tag"):
        search_query = keyword.replace(" ", "+")
        main_link = search_url_template.format(query=search_query, tag=tag)

        if lang == "ja":
            sections.append(_build_amazon_section_ja(main_link, keyword))
        else:
            sections.append(_build_amazon_section_en(main_link, keyword))

    # --- Rakuten via Moshimo (Japanese only) ---
    rakuten_a_id = config.get("affiliate", {}).get("moshimo_rakuten_a_id", "")
    if lang == "ja" and has_amazon_category and rakuten_a_id:
        rakuten_search_url = "https://search.rakuten.co.jp/search/mall/{}/".format(
            quote(keyword, safe=""),
        )
        rakuten_link = MOSHIMO_BASE.format(
            a_id=rakuten_a_id,
            encoded_url=quote(rakuten_search_url, safe=""),
        )
        sections.append(_build_rakuten_section_ja(rakuten_link, keyword))

    # --- A8.net (Japanese only) ---
    if lang == "ja":
        a8_matches = _find_a8_links(article)
        if a8_matches:
            sections.append(_build_a8_section(a8_matches))

    if sections:
        article["body"] = body + "\n\n" + "\n\n".join(sections)
        article["has_affiliate_links"] = True
        logger.info(
            "Inserted affiliate links for '%s' (%s): Amazon=%s, Rakuten=%s, A8=%d",
            keyword, lang, has_amazon_category,
            bool(rakuten_a_id) if lang == "ja" else False,
            len(_find_a8_links(article)) if lang == "ja" else 0,
        )

    return article


def _build_amazon_section_en(link: str, keyword: str) -> str:
    """Build English Amazon recommendation section."""
    return f"""---

## Recommended Products

Looking for the best {keyword}? Check out the top-rated options available:

**[Browse Top-Rated {keyword.title()} on Amazon]({link})**

*We may earn a small commission from qualifying purchases at no extra cost to you. This helps us continue creating helpful content.*"""


def _build_amazon_section_ja(link: str, keyword: str) -> str:
    """Build Japanese Amazon recommendation section."""
    return f"""---

## おすすめ商品

{keyword}をお探しですか？高評価の商品をチェックしてみてください：

**[{keyword}の人気商品をAmazonで見る]({link})**"""


def _build_rakuten_section_ja(link: str, keyword: str) -> str:
    """Build Japanese Rakuten recommendation section via Moshimo."""
    return f"""**[{keyword}を楽天市場で探す]({link})**"""


def _build_a8_section(programs: list[dict]) -> str:
    """Build A8.net affiliate links section."""
    lines = ["## おすすめサービス", ""]
    for prog in programs[:3]:  # Max 3 A8 links per article
        name = prog["name"]
        link = prog["link"]
        desc = prog.get("description", "")
        lines.append(f"**[{name}]({link})**")
        if desc:
            lines.append(f"{desc}")
        lines.append("")

    lines.append(
        "*当サイトはアフィリエイトプログラムに参加しています。"
        "購入者様に追加費用は発生しません。*"
    )
    return "\n".join(lines)
