"""Product search module using Rakuten Ichiba API + affiliate links."""

from __future__ import annotations

import logging
import os
import re
import time
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

RAKUTEN_API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"

MOSHIMO_BASE = (
    "https://af.moshimo.com/af/c/click?a_id={a_id}"
    "&p_id=54&pc_id=54&pl_id=616"
    "&url={encoded_url}"
)


def search_product(
    keyword: str,
    application_id: str,
    access_key: str,
    affiliate_id: str = "",
) -> dict | None:
    """Search Rakuten Ichiba for a product and return the top result.

    Returns dict with: name, price, url, affiliate_url, image_url, or None.
    """
    params = {
        "applicationId": application_id,
        "accessKey": access_key,
        "keyword": keyword,
        "hits": 10,
        "formatVersion": 2,
        "sort": "standard",
    }
    if affiliate_id:
        params["affiliateId"] = affiliate_id

    headers = {
        "User-Agent": "SmartLifeGuide",
        "Origin": "https://smartlifeguide.github.io",
    }

    try:
        resp = requests.get(RAKUTEN_API_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("Rakuten API request failed for '%s': %s", keyword, e)
        return None

    items = data.get("Items", [])
    if not items:
        logger.info("No Rakuten results for '%s'", keyword)
        return None

    # Filter out accessories, parts, and used items - prefer the actual product
    item = _pick_best_item(items)
    if not item:
        logger.info("No suitable Rakuten results for '%s' (all filtered)", keyword)
        return None

    return {
        "name": item.get("itemName", ""),
        "price": item.get("itemPrice", 0),
        "url": item.get("itemUrl", ""),
        "affiliate_url": item.get("affiliateUrl", ""),
        "image_url": (item.get("mediumImageUrls") or [""])[0] if item.get("mediumImageUrls") else "",
    }


# Words that indicate an accessory/part rather than the main product
_SKIP_WORDS = [
    "交換用", "互換品", "純正品", "フィルター", "ブラシ", "紙パック",
    "ダストバッグ", "リユース", "中古", "ジャンク", "訳あり",
    "パーツ", "部品", "バッテリー", "リモコン", "カバー", "ケース",
    "洗剤", "クリーナー", "メンテナンス", "消耗品", "充電台", "充電器",
    "アダプター", "延長保証",
]


def _pick_best_item(items: list[dict]) -> dict | None:
    """Pick the best item from search results, filtering out accessories."""
    for item in items:
        name = item.get("itemName", "")
        if any(w in name for w in _SKIP_WORDS):
            continue
        return item
    # If all filtered, return None rather than a bad match
    return None


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

    def _looks_like_product(name: str) -> bool:
        """Check if the name looks like an actual product (has model number or specific name)."""
        # Must contain at least one alphanumeric model-like part
        has_model = bool(re.search(r'[A-Z]{1,3}[\-]?[A-Z0-9]{2,}', name))
        # Or a known specific product name (katakana product series)
        has_series = bool(re.search(r'[ァ-ヶー]{3,}', name))
        # Reject if it's just a description/sentence
        too_long = len(name) > 35
        has_verb = any(w in name for w in ['する', 'した', 'なら', 'って', 'ための', 'について', 'ですか', 'どう'])
        if has_verb or too_long:
            return False
        return has_model or has_series

    # Method 1: Find quoted/bold product names that contain a known brand
    for match in _PRODUCT_PATTERN_JA.finditer(body):
        name = _clean(match.group(1))
        for brand in _BRANDS_JA:
            if brand in name and len(name) > len(brand) + 2:
                if _looks_like_product(name) and not _is_duplicate(name, found):
                    found.append(name)
                break

    # Method 2: Find "Brand + model" patterns (e.g. "パナソニック NA-LX129C")
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
    aff_cfg = config.get("affiliate", {})

    # New Rakuten API requires both applicationId (UUID) and accessKey
    application_id = aff_cfg.get("rakuten_application_id", "")
    access_key = aff_cfg.get("rakuten_access_key", "")
    if not access_key:
        access_key = os.environ.get("RAKUTEN_ACCESS_KEY", "")
    if not application_id or not access_key:
        logger.warning("Rakuten applicationId or accessKey not configured, skipping product search")
        return []

    affiliate_id = aff_cfg.get("rakuten_affiliate_id", "")
    moshimo_a_id = aff_cfg.get("moshimo_rakuten_a_id", "")

    if not affiliate_id and not moshimo_a_id:
        logger.warning("No affiliate ID configured, skipping product search")
        return []

    results = []
    for kw in product_keywords[:5]:
        product = search_product(kw, application_id, access_key, affiliate_id)
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
