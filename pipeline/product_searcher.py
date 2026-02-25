"""Product search module using Rakuten Ichiba API + affiliate links."""

from __future__ import annotations

import logging
import os
import re
import time
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

RAKUTEN_API_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"

MOSHIMO_BASE = (
    "https://af.moshimo.com/af/c/click?a_id={a_id}"
    "&p_id=54&pc_id=54&pl_id=616"
    "&url={encoded_url}"
)


def search_product(keyword: str, app_id: str, affiliate_id: str = "") -> dict | None:
    """Search Rakuten Ichiba for a product and return the top result.

    Returns dict with: name, price, url, affiliate_url, image_url, or None.
    """
    params = {
        "applicationId": app_id,
        "keyword": keyword,
        "hits": 3,
        "formatVersion": 2,
        "sort": "standard",
    }
    if affiliate_id:
        params["affiliateId"] = affiliate_id

    try:
        resp = requests.get(RAKUTEN_API_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("Rakuten API request failed for '%s': %s", keyword, e)
        return None

    items = data.get("Items", [])
    if not items:
        logger.info("No Rakuten results for '%s'", keyword)
        return None

    item = items[0]
    return {
        "name": item.get("itemName", ""),
        "price": item.get("itemPrice", 0),
        "url": item.get("itemUrl", ""),
        "affiliate_url": item.get("affiliateUrl", ""),
        "image_url": (item.get("mediumImageUrls") or [""])[0] if item.get("mediumImageUrls") else "",
    }


def build_moshimo_link(product_url: str, a_id: str) -> str:
    """Wrap a Rakuten product URL with Moshimo affiliate tracking."""
    return MOSHIMO_BASE.format(
        a_id=a_id,
        encoded_url=quote(product_url, safe=""),
    )


# Known brand names for extraction from article body
_BRANDS_JA = [
    "パナソニック", "日立", "シャープ", "東芝", "三菱", "ダイキン",
    "アイリスオーヤマ", "象印", "タイガー", "サーモス", "ティファール",
    "ブラウン", "フィリップス", "ダイソン", "iRobot", "ルンバ", "ブラーバ",
    "Roborock", "Anker", "Eufy", "エコバックス", "ECOVACS",
    "バルミューダ", "デロンギ", "ネスプレッソ", "ボニーク", "BONIQ",
    "オムロン", "タニタ", "ファイテン", "ドクターエア",
    "ピップ", "ルルド", "コイズミ", "テスコム",
]

_PRODUCT_PATTERN_JA = re.compile(
    r"(?:「|【|＜|<|\*\*)"
    r"([^」】＞>\*\n]{4,40})"
    r"(?:」|】|＞|>|\*\*)",
)


def extract_product_names(body: str, lang: str = "ja") -> list[str]:
    """Extract specific product names from article body text."""
    if lang != "ja":
        return []

    found = []

    def _clean(name: str) -> str:
        return name.strip().strip("「」【】＜＞<>").strip()

    def _is_duplicate(name: str, existing: list[str]) -> bool:
        for e in existing:
            if name in e or e in name:
                return True
        return False

    # Method 1: Find quoted/bold product names that contain a known brand
    for match in _PRODUCT_PATTERN_JA.finditer(body):
        name = _clean(match.group(1))
        for brand in _BRANDS_JA:
            if brand in name and len(name) > len(brand) + 2:
                if not _is_duplicate(name, found):
                    found.append(name)
                break

    # Method 2: Find "Brand + model" patterns in table cells or plain text
    for brand in _BRANDS_JA:
        pattern = re.compile(
            rf"{re.escape(brand)}\s*[A-Za-z0-9\-]+[\s\-]*[A-Za-z0-9]*"
        )
        for m in pattern.finditer(body):
            name = m.group(0).strip()
            if len(name) > len(brand) + 2 and not _is_duplicate(name, found):
                found.append(name)

    return found[:5]


def search_products_for_article(
    product_keywords: list[str],
    config: dict,
) -> list[dict]:
    """Search Rakuten for each product keyword and return results with affiliate links.

    Uses Rakuten affiliate ID for direct affiliate URLs when available,
    falls back to Moshimo link wrapping.
    """
    app_id = config.get("affiliate", {}).get("rakuten_app_id", "")
    if not app_id:
        app_id = os.environ.get("RAKUTEN_APP_ID", "")
    if not app_id:
        logger.warning("No Rakuten App ID configured, skipping product search")
        return []

    affiliate_id = config.get("affiliate", {}).get("rakuten_affiliate_id", "")
    moshimo_a_id = config.get("affiliate", {}).get("moshimo_rakuten_a_id", "")

    if not affiliate_id and not moshimo_a_id:
        logger.warning("No affiliate ID configured, skipping product search")
        return []

    results = []
    for kw in product_keywords[:5]:
        product = search_product(kw, app_id, affiliate_id)
        if not product or not product["url"]:
            time.sleep(1)
            continue

        # Use Rakuten's direct affiliate URL if available, otherwise Moshimo
        if not product.get("affiliate_url") and moshimo_a_id:
            product["affiliate_url"] = build_moshimo_link(product["url"], moshimo_a_id)

        if product.get("affiliate_url"):
            results.append(product)
            logger.info("Found product: %s (¥%s)", product["name"][:50], product["price"])

        time.sleep(1)

    return results
