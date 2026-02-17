"""Affiliate link insertion module."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Product keyword patterns mapped to Amazon search categories
PRODUCT_PATTERNS_EN = {
    r"\b(app|software|tool|program)\b": "software",
    r"\b(device|gadget|speaker|tracker|watch)\b": "electronics",
    r"\b(desk|chair|monitor|keyboard|mouse|headset)\b": "office-products",
    r"\b(book|guide|manual)\b": "books",
    r"\b(camera|webcam|microphone|mic)\b": "electronics",
    r"\b(router|wifi|modem|hub)\b": "electronics",
    r"\b(phone|tablet|laptop|computer)\b": "electronics",
}

PRODUCT_PATTERNS_JA = {
    r"(アプリ|ソフト|ツール)": "software",
    r"(デバイス|ガジェット|スピーカー|トラッカー|ウォッチ)": "electronics",
    r"(デスク|チェア|モニター|キーボード|マウス|ヘッドセット)": "office-products",
    r"(本|書籍|ガイド)": "books",
    r"(カメラ|ウェブカメラ|マイク)": "electronics",
    r"(ルーター|WiFi|モデム|ハブ)": "electronics",
    r"(スマホ|タブレット|ノートパソコン|PC)": "electronics",
}

AMAZON_SEARCH_URL_EN = "https://www.amazon.com/s?k={query}&tag={tag}"
AMAZON_SEARCH_URL_JA = "https://www.amazon.co.jp/s?k={query}&tag={tag}"


def insert_affiliate_links(article: dict, config: dict) -> dict:
    """Insert affiliate links into an article's body.

    Adds a 'recommended products' section at the end and inline links
    where product mentions are detected.
    """
    if not config.get("affiliate", {}).get("enabled", True):
        return article

    lang = article.get("lang", "en")
    body = article["body"]
    keyword = article.get("keyword", "")

    if lang == "ja":
        tag = config["affiliate"]["amazon_associate_tag_ja"]
        patterns = PRODUCT_PATTERNS_JA
        search_url_template = AMAZON_SEARCH_URL_JA
    else:
        tag = config["affiliate"]["amazon_associate_tag_en"]
        patterns = PRODUCT_PATTERNS_EN
        search_url_template = AMAZON_SEARCH_URL_EN

    # Detect product categories mentioned in the article
    detected_categories: set[str] = set()
    for pattern, category in patterns.items():
        if re.search(pattern, body, re.IGNORECASE):
            detected_categories.add(category)

    if not detected_categories:
        return article

    # Build affiliate search URL for the keyword
    search_query = keyword.replace(" ", "+")
    main_link = search_url_template.format(query=search_query, tag=tag)

    # Add recommended products section
    if lang == "ja":
        section = _build_recommendation_section_ja(main_link, keyword)
    else:
        section = _build_recommendation_section_en(main_link, keyword)

    article["body"] = body + "\n\n" + section
    article["has_affiliate_links"] = True

    logger.info("Inserted affiliate links for '%s' (%s)", keyword, lang)
    return article


def _build_recommendation_section_en(link: str, keyword: str) -> str:
    """Build English product recommendation section."""
    return f"""---

## Recommended Products

Looking for the best {keyword}? Check out the top-rated options available:

**[Browse Top-Rated {keyword.title()} on Amazon]({link})**

*We may earn a small commission from qualifying purchases at no extra cost to you. This helps us continue creating helpful content.*"""


def _build_recommendation_section_ja(link: str, keyword: str) -> str:
    """Build Japanese product recommendation section."""
    return f"""---

## おすすめ商品

{keyword}をお探しですか？高評価の商品をチェックしてみてください：

**[{keyword}の人気商品をAmazonで見る]({link})**

*当サイトはアフィリエイトプログラムに参加しています。購入者様に追加費用は発生しません。*"""
